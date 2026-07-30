// PhSoftcut — monome's softcut as a SuperCollider UGen.
//
// ONE UGen INSTANCE IS ONE SOFTCUT VOICE: a read/write head on a shared SC buffer, with
// crossfaded looping, subsample-accurate resampling, overdub and pre/post multimode
// filters. Instantiate several in a SynthDef and they share the buffer exactly as norns'
// six voices share theirs.
//
// Why a UGen and not a JACK client (the route the CSOUND engine had to take): softcut-lib
// has no audio I/O of its own and no JACK dependency — it is five source files that
// process a block and let the CALLER own the buffer. So it drops straight onto a bus
// inside scsynth, with no routing, no port pinning, no realtime-priority placement and no
// inter-process latency.
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
    // last-seen control values, so parameters are only pushed into softcut when they
    // actually change — its setters do slew bookkeeping and are not free per block
    float pRate, pStart, pEnd, pPos, pFade, pRec, pPre, pPlayF, pRecF, pLoopF;
    float pFc, pRq, pLp, pHp, pBp, pDry;
    bool started;
};

static void PhSoftcut_next(PhSoftcut *unit, int inNumSamples);
static void PhSoftcut_Ctor(PhSoftcut *unit);
static void PhSoftcut_Dtor(PhSoftcut *unit);

// in, bufnum, rate, loopStart, loopEnd, cutPos, fade, recLevel, preLevel,
// play, rec, loop, fc, rq, lp, hp, bp, dry
enum { kIn, kBuf, kRate, kStart, kEnd, kCut, kFade, kRec, kPre, kPlay, kRecF, kLoop,
       kFc, kRq, kLp, kHp, kBp, kDry };

void PhSoftcut_Ctor(PhSoftcut *unit) {
    unit->voice = new softcut::Voice();
    unit->m_sr = (float)SAMPLERATE;
    unit->voice->setSampleRate(unit->m_sr);
    unit->started = false;
    unit->m_fbufnum = -1e9f;
    // force every parameter to be pushed on the first block
    unit->pRate = unit->pStart = unit->pEnd = unit->pPos = unit->pFade = -12345.f;
    unit->pRec = unit->pPre = unit->pPlayF = unit->pRecF = unit->pLoopF = -12345.f;
    unit->pFc = unit->pRq = unit->pLp = unit->pHp = unit->pBp = unit->pDry = -12345.f;
    SETCALC(PhSoftcut_next);
    ZOUT0(0) = 0.f;
}

void PhSoftcut_Dtor(PhSoftcut *unit) {
    delete unit->voice;
}

static inline void setIfChanged(float now, float &was, void (softcut::Voice::*fn)(float),
                                softcut::Voice *v) {
    if (now != was) { (v->*fn)(now); was = now; }
}

void PhSoftcut_next(PhSoftcut *unit, int inNumSamples) {
    float *in = IN(kIn);
    float *out = OUT(0);
    softcut::Voice *v = unit->voice;

    // --- the buffer. softcut RECORDS into it, so this is GET_BUF (an exclusive lock),
    // not GET_BUF_SHARED, whose bufData is const — a shared lock is for units that only
    // read, and softcut's whole point is that the write head is live. ---
    GET_BUF
    if (!bufData) { ClearUnitOutputs(unit, inNumSamples); return; }
    if (bufChannels != 1) {                 // softcut voices are mono by construction
        ClearUnitOutputs(unit, inNumSamples);
        return;
    }
    if (!unit->started) {
        v->setBuffer(bufData, (unsigned int)bufFrames);
        unit->started = true;
    }

    // --- parameters, pushed only on change ---
    setIfChanged(IN0(kRate),  unit->pRate,  &softcut::Voice::setRate,      v);
    setIfChanged(IN0(kStart), unit->pStart, &softcut::Voice::setLoopStart, v);
    setIfChanged(IN0(kEnd),   unit->pEnd,   &softcut::Voice::setLoopEnd,   v);
    setIfChanged(IN0(kFade),  unit->pFade,  &softcut::Voice::setFadeTime,  v);
    setIfChanged(IN0(kRec),   unit->pRec,   &softcut::Voice::setRecLevel,  v);
    setIfChanged(IN0(kPre),   unit->pPre,   &softcut::Voice::setPreLevel,  v);
    setIfChanged(IN0(kFc),    unit->pFc,    &softcut::Voice::setPostFilterFc, v);
    setIfChanged(IN0(kRq),    unit->pRq,    &softcut::Voice::setPostFilterRq, v);
    setIfChanged(IN0(kLp),    unit->pLp,    &softcut::Voice::setPostFilterLp, v);
    setIfChanged(IN0(kHp),    unit->pHp,    &softcut::Voice::setPostFilterHp, v);
    setIfChanged(IN0(kBp),    unit->pBp,    &softcut::Voice::setPostFilterBp, v);
    setIfChanged(IN0(kDry),   unit->pDry,   &softcut::Voice::setPostFilterDry, v);

    float play = IN0(kPlay), rec = IN0(kRecF), loop = IN0(kLoop);
    if (play != unit->pPlayF) { v->setPlayFlag(play > 0.5f); unit->pPlayF = play; }
    if (rec  != unit->pRecF)  { v->setRecFlag(rec > 0.5f);   unit->pRecF  = rec;  }
    if (loop != unit->pLoopF) { v->setLoopFlag(loop > 0.5f); unit->pLoopF = loop; }

    // cutToPos is a TRIGGER, not a level: it fires when the value changes, so the language
    // side jumps the head by writing a new position rather than by holding one.
    float cut = IN0(kCut);
    if (cut != unit->pPos) {
        if (cut >= 0.f) v->cutToPos(cut);
        unit->pPos = cut;
    }

    v->processBlockMono(in, out, inNumSamples);
}

PluginLoad(PhSoftcut) {
    ft = inTable;
    DefineDtorUnit(PhSoftcut);
}
