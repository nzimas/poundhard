// PhMicIn — the Move's microphone, read from the tap the Schwung DSP plugin publishes.
//
// The mic is not reachable from a JACK client: the device has no ALSA, and the shadow
// driver's capture ports carry a dead noise floor. It lives in the SPI mailbox, which only a
// loaded Schwung DSP plugin can see. PoundHard's `dsp.so` (move/schwung-module/poundhard/dsp)
// runs inside MoveOriginal, copies each 128-frame input block out of the mailbox, and
// publishes it to a lock-free POSIX shm ring. This UGen is the other end of that ring.
//
// SINGLE WRITER, SINGLE READER, NO LOCKS. The writer publishes its frame counter with a
// release barrier after filling the samples, so a counter this side observes is a promise
// that the audio behind it is already there. Nothing here blocks or allocates on the audio
// thread; if the tap is absent the UGen outputs silence, which is the correct behaviour for
// a microphone nobody has plugged in.
#include "SC_PlugIn.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <cstring>
#include "phmic.h"

static InterfaceTable *ft;

struct PhMicIn : public Unit {
    phmic_shm_t *shm;
    int fd;
    uint32 rd;            // our read cursor, in the writer's frame numbering
    float last;           // held sample, so an underrun is a hold rather than a click
    int retry;            // blocks until the next attach attempt
};

static void PhMicIn_next(PhMicIn *unit, int inNumSamples);
static void PhMicIn_Ctor(PhMicIn *unit);
static void PhMicIn_Dtor(PhMicIn *unit);

// Attaching touches the filesystem, so it happens in the constructor and then at most once
// every few seconds — never per block. The plugin may load after the engine does.
static void ph_attach(PhMicIn *unit) {
    unit->fd = shm_open(PHMIC_SHM, O_RDONLY, 0);
    if (unit->fd < 0) return;
    void *p = mmap(nullptr, sizeof(phmic_shm_t), PROT_READ, MAP_SHARED, unit->fd, 0);
    if (p == MAP_FAILED) { close(unit->fd); unit->fd = -1; return; }
    unit->shm = (phmic_shm_t *)p;
    unit->rd = unit->shm->write;      // start live, not at whatever is stale in the ring
}

void PhMicIn_Ctor(PhMicIn *unit) {
    unit->shm = nullptr;
    unit->fd = -1;
    unit->rd = 0;
    unit->last = 0.f;
    unit->retry = 0;
    ph_attach(unit);
    SETCALC(PhMicIn_next);
    ZOUT0(0) = 0.f;
}

void PhMicIn_Dtor(PhMicIn *unit) {
    if (unit->shm) munmap(unit->shm, sizeof(phmic_shm_t));
    if (unit->fd >= 0) close(unit->fd);
}

void PhMicIn_next(PhMicIn *unit, int inNumSamples) {
    float *out = OUT(0);
    float gain = IN0(0);

    if (!unit->shm || unit->shm->magic != PHMIC_MAGIC) {
        // Not attached, or the plugin went away and invalidated the header. Retry rarely.
        if (unit->shm) { munmap(unit->shm, sizeof(phmic_shm_t)); unit->shm = nullptr; }
        if (unit->fd >= 0) { close(unit->fd); unit->fd = -1; }
        if (--unit->retry <= 0) { unit->retry = 200; ph_attach(unit); }
        for (int i = 0; i < inNumSamples; ++i) out[i] = 0.f;
        return;
    }

    phmic_shm_t *s = unit->shm;
    const uint32 w = s->write;                 // acquire: samples behind this are valid
    __sync_synchronize();
    const uint32 cap = s->frames;
    const uint32 mask = cap - 1u;

    // LATENCY IS BOUNDED IN BOTH DIRECTIONS. Falling too far behind means playing audio from
    // seconds ago; running ahead of the writer means reading frames it has not filled. Both
    // are resynchronised by jumping the cursor rather than by stretching, because a
    // microphone wants to be live and a glitch is preferable to drift.
    const uint32 lag = w - unit->rd;           // unsigned wrap is intentional
    if (lag > cap / 2u) unit->rd = w;                       // ahead of the writer, or stale
    else if (lag > (uint32)(inNumSamples * 8)) unit->rd = w - (uint32)(inNumSamples * 2);

    for (int i = 0; i < inNumSamples; ++i) {
        if ((int32)(w - unit->rd) > 0) {
            unit->last = s->samples[unit->rd & mask];
            unit->rd++;
        }
        // else: underrun — hold the last sample rather than emit a step to zero
        out[i] = unit->last * gain;
    }
}

PluginLoad(PhMicIn) {
    ft = inTable;
    DefineDtorUnit(PhMicIn);
}
