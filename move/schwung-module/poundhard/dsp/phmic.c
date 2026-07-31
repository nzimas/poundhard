/*
 * phmic — PoundHard's microphone tap, as a Schwung overtake DSP plugin.
 *
 * THE PROBLEM THIS SOLVES. PoundHard is an `overtake` module: it displaces Schwung's audio
 * chain entirely and runs its own jackd + supernova, with only its OUTPUT mixed back through
 * the shadow driver. Nothing routes the Move's microphone into that. A long search for it
 * came up empty everywhere a JACK client can look — no ALSA on the device, no /dev/snd, the
 * shadow driver's capture ports carrying a dead ~-86 dB floor, and every one of the engine's
 * 36 inputs silent except that floor.
 *
 * The input is not in any of those places. It is in the SPI MAILBOX, and the host hands a
 * pointer to it — but only to a loaded DSP plugin:
 *
 *     host->mapped_memory + host->audio_in_offset      (MOVE_AUDIO_IN_OFFSET = 2048 + 256)
 *     512 bytes = 128 frames, stereo interleaved int16  (MOVE_AUDIO_BYTES_PER_BLOCK)
 *
 * So the way in is to BE a plugin. The shim loads an overtake module's `dsp` and looks for a
 * V2 generator or FX entry point ("Overtake DSP: no V2 generator or FX entry point in %s"),
 * which is exactly the door charlesvestal/schwung-fourtrack walks through.
 *
 * WHAT THIS DOES, AND DELIBERATELY DOES NOT DO. It registers as an audio FX and passes audio
 * through BIT FOR BIT — PoundHard's sound comes out over JACK and must not be touched by, or
 * routed through, this plugin. The only thing it does is copy the microphone block out of the
 * mailbox into a POSIX shared-memory ring that the engine reads. It is a tap, not an effect.
 *
 * REALTIME DISCIPLINE. process_block runs on the audio thread. No allocation, no syscalls, no
 * locks: the shm is mapped once at instance creation and the publish is a release store.
 */
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <stdio.h>

#include "plugin_api_v1.h"
#include "audio_fx_api_v2.h"
#include "phmic.h"

static const host_api_v1_t *g_host = NULL;

typedef struct {
    phmic_shm_t *shm;
    int fd;
} phmic_inst_t;

static void ph_log(const char *msg) {
    if (g_host && g_host->log) g_host->log(msg);
}

/* ---------------------------------------------------------------- lifecycle */
static void *phmic_create(const char *module_dir, const char *config_json) {
    phmic_inst_t *st;
    (void)module_dir; (void)config_json;

    st = (phmic_inst_t *)calloc(1, sizeof(*st));
    if (!st) return NULL;

    /* Created 0666 on purpose: the plugin runs inside MoveOriginal while the engine runs as
     * a different user, and a tap only one of them can open is no tap at all. */
    st->fd = shm_open(PHMIC_SHM, O_CREAT | O_RDWR, 0666);
    if (st->fd < 0) {
        ph_log("phmic: shm_open failed");
        free(st);
        return NULL;
    }
    if (ftruncate(st->fd, (off_t)sizeof(phmic_shm_t)) != 0) {
        /* Already sized by a previous load — not fatal. */
    }
    st->shm = (phmic_shm_t *)mmap(NULL, sizeof(phmic_shm_t), PROT_READ | PROT_WRITE,
                                  MAP_SHARED, st->fd, 0);
    if (st->shm == MAP_FAILED) {
        ph_log("phmic: mmap failed");
        close(st->fd);
        free(st);
        return NULL;
    }
    fchmod(st->fd, 0666);

    /* Header first, counters last: a reader that sees the magic sees a valid header. */
    st->shm->frames = PHMIC_FRAMES;
    st->shm->sample_rate = (g_host && g_host->sample_rate) ? (uint32_t)g_host->sample_rate
                                                           : MOVE_SAMPLE_RATE;
    st->shm->version = 1;
    st->shm->write = 0;
    st->shm->blocks = 0;
    st->shm->peak = 0;
    st->shm->flags = (g_host && g_host->mapped_memory) ? 1u : 0u;
    __sync_synchronize();
    st->shm->magic = PHMIC_MAGIC;

    ph_log((g_host && g_host->mapped_memory)
           ? "phmic: tap up, mailbox available"
           : "phmic: tap up, NO mailbox pointer from host");
    return st;
}

static void phmic_destroy(void *instance) {
    phmic_inst_t *st = (phmic_inst_t *)instance;
    if (!st) return;
    if (st->shm && st->shm != MAP_FAILED) {
        st->shm->magic = 0;             /* readers stop trusting it immediately */
        munmap(st->shm, sizeof(phmic_shm_t));
    }
    if (st->fd >= 0) close(st->fd);
    free(st);
}

/* ---------------------------------------------------------------- the tap */
static void phmic_process(void *instance, int16_t *audio_inout, int frames) {
    phmic_inst_t *st = (phmic_inst_t *)instance;
    const int16_t *in;
    phmic_shm_t *shm;
    uint32_t w, mask;
    int i, pk = 0;

    /* audio_inout is PoundHard's own output on its way out of the box. It is passed through
     * untouched — this plugin is a tap, and colouring the mix would be a bug, not a feature. */
    (void)audio_inout;

    if (!st || !st->shm) return;
    shm = st->shm;
    shm->blocks++;                       /* heartbeat: proves the host calls us at all */

    if (!g_host || !g_host->mapped_memory) return;

    in = (const int16_t *)(g_host->mapped_memory + g_host->audio_in_offset);
    if (frames > MOVE_FRAMES_PER_BLOCK) frames = MOVE_FRAMES_PER_BLOCK;

    w = shm->write;
    mask = PHMIC_FRAMES - 1u;            /* capacity is a power of two */
    for (i = 0; i < frames; ++i) {
        int l = in[(i * 2)];
        int r = in[(i * 2) + 1];
        int m = (l + r) / 2;             /* one capsule; mono is what a MIC take wants */
        int a = m < 0 ? -m : m;
        if (a > pk) pk = a;
        shm->samples[(w + (uint32_t)i) & mask] = (float)m * (1.0f / 32768.0f);
    }
    shm->peak = (uint32_t)pk;

    /* PUBLISH LAST, with a barrier. The reader takes `write` as its promise that every
     * sample behind it is already in the ring; reordering that store ahead of the copy would
     * hand out frames that have not been written yet. */
    __sync_synchronize();
    shm->write = w + (uint32_t)frames;
}

static void phmic_set_param(void *instance, const char *key, const char *val) {
    (void)instance; (void)key; (void)val;
}

static int phmic_get_param(void *instance, const char *key, char *buf, int buf_len) {
    phmic_inst_t *st = (phmic_inst_t *)instance;
    if (!st || !st->shm || !key || !buf || buf_len < 12) return -1;
    /* Enough to diagnose from the outside without attaching anything. */
    if (strcmp(key, "blocks") == 0) {
        int n = snprintf(buf, (size_t)buf_len, "%u", st->shm->blocks);
        return n < buf_len ? n : -1;
    }
    if (strcmp(key, "peak") == 0) {
        int n = snprintf(buf, (size_t)buf_len, "%u", st->shm->peak);
        return n < buf_len ? n : -1;
    }
    return -1;
}

static audio_fx_api_v2_t g_api;

audio_fx_api_v2_t *move_audio_fx_init_v2(const host_api_v1_t *host) {
    g_host = host;
    memset(&g_api, 0, sizeof(g_api));
    g_api.api_version = AUDIO_FX_API_VERSION_2;
    g_api.create_instance = phmic_create;
    g_api.destroy_instance = phmic_destroy;
    g_api.process_block = phmic_process;
    g_api.set_param = phmic_set_param;
    g_api.get_param = phmic_get_param;
    return &g_api;
}
