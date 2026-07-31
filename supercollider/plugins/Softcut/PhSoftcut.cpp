// PhSoftcut — monome's softcut as a SuperCollider UGen.
//
// ONE UGen INSTANCE IS ONE SOFTCUT VOICE: a read/write head on an SC buffer, with
// crossfaded looping, subsample-accurate resampling, overdub, slewed rate and pre/post
// multimode filters. Give each instance its own buffer and you have norns' arrangement,
// where every voice owns a buffer and they are independent by default.
//
// Why a UGen and not a JACK client (the route the CSOUND engine had to take): softcut-lib
// has no audio I/O of its own and no JACK dependency — it is five source files that
// process a block and let the CALLER own the buffer. So it drops straight onto a bus
// inside scsynth, with no routing, no port pinning, no realtime-priority placement and no
// inter-process latency.
//
// THE INPUT LIST IS THE norns softcut API, deliberately and completely. This UGen exists to
// run real norns scripts unmodified, and a script calls whatever it calls: leave out
// `rate_slew_time` and every rate change becomes a click instead of a tape glide; leave out
// the PRE filter and `pre_filter_dry` silently lands on the post filter, colouring playback
// instead of the record path. Both of those were missing from the first version of this
// file, and both were audible. Anything the API has, this has.
//
// Measured on the CM4 before writing this: 1.26% of one core per voice, 8.32% for six.
#include "SC_PlugIn.h"
#include "softcut/Voice.h"
#include <cstring>

static InterfaceTable *ft;

struct PhSoftcut : public Unit {
    // GET_BUF caches the buffer on the unit and expects these two by name
    float m_fbufnum;
    SndBuf *m_buf;
    softcut::Voice *voice;
    float m_sr;
    // Last-seen control values, so parameters only reach softcut when they actually
    // change — its setters do slew and filter-coefficient bookkeeping and are not free to
    // call per block. 26 of them, hence the array rather than 26 named fields.
    float prev[32];
    bool started;
};

static void PhSoftcut_next(PhSoftcut *unit, int inNumSamples);
static void PhSoftcut_Ctor(PhSoftcut *unit);
static void PhSoftcut_Dtor(PhSoftcut *unit);

enum { kIn, kBuf,
       kRate, kRateSlew, kStart, kEnd, kCut, kFade,
       kRec, kPre, kRecPreSlew, kPlay, kRecF, kLoop, kPhaseQuant, kRecOffset,
       kPreFc, kPreRq, kPreLp, kPreHp, kPreBp, kPreBr, kPreDry,
       kPostFc, kPostRq, kPostLp, kPostHp, kPostBp, kPostBr, kPostDry,
       kNumInputs };

// input index -> Voice setter, for everything that is a plain float parameter
typedef void (softcut::Voice::*VoiceSetter)(float);
struct Mapping { int idx; VoiceSetter fn; };

static const Mapping kMap[] = {
    { kRate,       &softcut::Voice::setRate },
    { kRateSlew,   &softcut::Voice::setRateSlewTime },
    { kStart,      &softcut::Voice::setLoopStart },
    { kEnd,        &softcut::Voice::setLoopEnd },
    { kFade,       &softcut::Voice::setFadeTime },
    { kRec,        &softcut::Voice::setRecLevel },
    { kPre,        &softcut::Voice::setPreLevel },
    { kRecPreSlew, &softcut::Voice::setRecPreSlewTime },
    { kPhaseQuant, &softcut::Voice::setPhaseQuant },
    { kRecOffset,  &softcut::Voice::setRecOffset },
    { kPreFc,      &softcut::Voice::setPreFilterFc },
    { kPreRq,      &softcut::Voice::setPreFilterRq },
    { kPreLp,      &softcut::Voice::setPreFilterLp },
    { kPreHp,      &softcut::Voice::setPreFilterHp },
    { kPreBp,      &softcut::Voice::setPreFilterBp },
    { kPreBr,      &softcut::Voice::setPreFilterBr },
    { kPreDry,     &softcut::Voice::setPreFilterDry },
    { kPostFc,     &softcut::Voice::setPostFilterFc },
    { kPostRq,     &softcut::Voice::setPostFilterRq },
    { kPostLp,     &softcut::Voice::setPostFilterLp },
    { kPostHp,     &softcut::Voice::setPostFilterHp },
    { kPostBp,     &softcut::Voice::setPostFilterBp },
    { kPostBr,     &softcut::Voice::setPostFilterBr },
    { kPostDry,    &softcut::Voice::setPostFilterDry },
};
static const int kMapCount = (int)(sizeof(kMap) / sizeof(kMap[0]));

void PhSoftcut_Ctor(PhSoftcut *unit) {
    unit->voice = new softcut::Voice();
    unit->m_sr = (float)SAMPLERATE;
    unit->voice->setSampleRate(unit->m_sr);
    unit->started = false;
    unit->m_fbufnum = -1e9f;
    for (int i = 0; i < 32; ++i) unit->prev[i] = -1e20f;  // force a push on block one
    SETCALC(PhSoftcut_next);
    ZOUT0(0) = 0.f;
    if (unit->mNumOutputs > 1) ZOUT0(1) = 0.f;
}

void PhSoftcut_Dtor(PhSoftcut *unit) {
    delete unit->voice;
}

void PhSoftcut_next(PhSoftcut *unit, int inNumSamples) {
    float *in = IN(kIn);
    float *out = OUT(0);
    softcut::Voice *v = unit->voice;

    // --- the buffer. softcut RECORDS into it, so this is GET_BUF (an exclusive lock),
    // not GET_BUF_SHARED, whose bufData is const — a shared lock is for units that only
    // read, and softcut's whole point is that the write head is live. ---
    GET_BUF
    if (!bufData || bufChannels != 1) {     // softcut voices are mono by construction
        ClearUnitOutputs(unit, inNumSamples);
        return;
    }
    if (!unit->started) {
        v->setBuffer(bufData, (unsigned int)bufFrames);
        unit->started = true;
    }

    for (int i = 0; i < kMapCount; ++i) {
        float now = IN0(kMap[i].idx);
        if (now != unit->prev[kMap[i].idx]) {
            (v->*(kMap[i].fn))(now);
            unit->prev[kMap[i].idx] = now;
        }
    }

    float play = IN0(kPlay), rec = IN0(kRecF), loop = IN0(kLoop);
    if (play != unit->prev[kPlay]) { v->setPlayFlag(play > 0.5f); unit->prev[kPlay] = play; }
    if (rec  != unit->prev[kRecF]) { v->setRecFlag(rec  > 0.5f);  unit->prev[kRecF] = rec;  }
    if (loop != unit->prev[kLoop]) { v->setLoopFlag(loop > 0.5f); unit->prev[kLoop] = loop; }

    // cutToPos is a TRIGGER, not a level: it fires when the value changes, so the language
    // side jumps the head by writing a new position rather than by holding one. A script
    // calling `softcut.position(i, 4)` twice in a row means two jumps to 4 seconds, so a
    // negative sentinel is written between them to re-arm it.
    float cut = IN0(kCut);
    if (cut != unit->prev[kCut]) {
        if (cut >= 0.f) v->cutToPos(cut);
        unit->prev[kCut] = cut;
    }

    v->processBlockMono(in, out, inNumSamples);

    // Output 1 is the head position in seconds — norns' phase poll, which scripts use both
    // to draw and, in Compass's case, to re-apply loop points on every poll. Without it the
    // script's `update_positions` never runs and half its state never reaches softcut.
    if (unit->mNumOutputs > 1) {
        float *pos = OUT(1);
        float p = v->getActivePosition();
        for (int i = 0; i < inNumSamples; ++i) pos[i] = p;
    }
}

PluginLoad(PhSoftcut) {
    ft = inTable;
    DefineDtorUnit(PhSoftcut);
}
