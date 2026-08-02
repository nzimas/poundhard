#!/usr/bin/env python3
"""Generate the CSOUND engine's architecture matrix.

WHY THIS IS GENERATED. Ten hand-written architectures gave ten sounds, and the ear found the
repeats immediately however the macros were sampled. Getting to hundreds by hand would mean
hundreds of blocks to write, audition and keep correct — so the architectures are a MATRIX
instead: every GENERATOR core is paired with every PROCESSOR stage, and this script emits one
real Csound instrument per pair. Thirty cores against four stages is a hundred and twenty
architectures, each a distinct signal path rather than a different setting of the same one.

Each generated instrument is ordinary, readable Csound — no runtime dispatch, no branching on
an index. That matters for cost (an instrument instantiates only its own opcodes, not thirty
generators' worth) and for debugging (an architecture that misbehaves is a block you can read).

THE MACRO CONTRACT is unchanged, so the controller does not care that any of this happened:
    p4 track, p5 frequency, p6 amplitude, p7..p14 eight macros 0-1
and here they are split
    p7..p10   the generator core
    p11..p13  the processor stage
    p14       the envelope shape — percussive at 0, sustained at 1
Giving the envelope a macro of its own is deliberate: two voices with identical spectra and
different envelopes read as two instruments, and it is the cheapest variety in the file.

Usage:  python3 csound/build-orc.py            (rewrites the generated section in place)
"""
from __future__ import annotations

import pathlib
import random
import re

# --------------------------------------------------------------------------- #
# GENERATOR CORES. Each is a fragment producing mono `agen` from `ifq` and the four
# generator macros k1..k4. They are grouped by family so the recipe table can reason about
# them, and deliberately span physical models, stochastic synthesis, formant methods,
# distortion synthesis and table reading — not thirty tunings of an oscillator.
#
# (name, family, code)
# --------------------------------------------------------------------------- #
GENERATORS = [
    # ---- stochastic / noise-based -------------------------------------------------
    ("GENDY", "stoch", """
  ; Xenakis' dynamic stochastic synthesis: the waveform is a random walk of breakpoints, so
  ; the timbre is never twice the same and the pitch is only as stable as you let it be.
  agen  gendy 1, int(k1 * 5), int(k2 * 5), ifq * 0.5, ifq * 2, k3 * 0.9 + 0.05, k4 * 0.9 + 0.05, 12, 12
  agen  = agen * 0.7"""),
    ("GRAINN", "stoch", """
  ; Grains scattered over a PITCHED table. This read giNoiseT — the frozen noise table — and
  ; so was granulated hiss by construction: measured four noise draws out of four through two
  ; of its four stages. Granulating the inharmonic bell table keeps the grain character and
  ; gives it a fundamental to be grainy ABOUT.
  agen  grain3 ifq, 0, k1 * 120, k2 * 0.35, 0.008 + k3 * 0.1, 12 + k4 * 160, 40, giBell, giGrEnv, 1, 1"""),
    ("RESBANK", "stoch", """
  ; Noise through a bank of sharp resonators: pitched by the filters, not by an oscillator.
  anz   PhNoise 1, 0.5 + k1 * 2.5
  ar1   reson anz, ifq, ifq / (8 + k2 * 90), 2
  ar2   reson anz, ifq * (1.7 + k3 * 3), ifq / (10 + k2 * 60), 2
  ar3   reson anz, ifq * (3.1 + k3 * 5), ifq / (12 + k2 * 40), 2
  agen  = (ar1 + ar2 * 0.6 + ar3 * 0.4) * (0.3 + k4 * 0.7)"""),
    ("DUSTRES", "stoch", """
  ; Sparse impulses ringing a string resonator — clicks that become pitch as density rises.
  adst  dust2 0.7, 4 + k1 * 300
  agen  streson adst, ifq, 0.5 + k2 * 0.49
  agen  = agen * (0.3 + k3 * 0.6) + adst * k4 * 0.3"""),

    # ---- formant / vocal ----------------------------------------------------------
    ("VOSIM", "formant", """
  ; VOSIM: a train of squared-sine pulses. Vocal and percussive at once, and unmistakably
  ; digital in a way no filter sweep imitates.
  agen  vosim 0.6, ifq, ifq * (2 + k1 * 18), k2 * 0.9, 1 + int(k3 * 12), 0.4 + k4, giSine"""),
    ("FOF2", "formant", """
  ; Granular formant synthesis: a fundamental with a formant riding on it, the classic
  ; route to voice-like and insect-like tones from the same three numbers.
  agen  fof2 0.7, ifq, ifq * (1 + k1 * 8), 0, 40 + k2 * 900, 0.003, 0.02 + k3 * 0.1, 0.007, 20, giSine, giGrEnv, 3600, 0, k4"""),
    ("FMVOICE", "formant", """
  agen  fmvoice 0.6, ifq, int(k1 * 63), k2 * 2, 0.1 + k3 * 0.9, 0.1 + k4 * 0.9, giSine, giSine, giSine, giSine, giSine"""),
    ("HSB", "formant", """
  ; Harmonic-stretch oscillator: partials pulled off the harmonic series by a ratio, which
  ; is how a bell stops sounding like an organ.
  agen  hsboscil 0.6, k1 * 4 - 2, k2 * 3, ifq, giSine, giSine, 3 + int(p9 * 5)"""),

    # ---- FM / phase modulation ----------------------------------------------------
    ("CROSSPM", "fm", """
  ; Two oscillators phase-modulating EACH OTHER. The feedback makes the spectrum move on
  ; its own rather than following an index envelope.
  kf1   = ifq
  kf2   = ifq * (1 + k1 * 4)
  a1, a2 crosspm kf1, kf2, k2 * 3.5, k3 * 3.5, 1 + k4 * 5, giSine, giSine
  agen  = (a1 * 0.6 + a2 * 0.4) * 0.7"""),
    ("FMMETAL", "fm", """
  agen  fmmetal 0.55, ifq, k1 * 3, k2 * 5, 0.1 + k3 * 4, 1 + k4 * 8, giSine, giSine, giSine, giSine, giSine"""),
    ("FMBELL", "fm", """
  agen  fmbell 0.5, ifq, k1 * 3, k2 * 4, 0.5 + k3 * 4, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine, 0"""),
    ("FMPERC", "fm", """
  agen  fmpercfl 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 7, giSine, giSine, giSine, giSine, giSine"""),
    ("FMRHOD", "fm", """
  agen  fmrhode 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine"""),
    ("CHAOSFM", "fm", """
  ; Feedback FM taken past the point of stability: harmonic, then period-doubled, then
  ; genuinely chaotic — noise that still tracks pitch.
  aexc  poscil k4 * 0.3, ifq * (0.25 + k1 * 2), giSine
  agen  PhChaos aexc, ifq, 0.2 + k2 * 3.2
  agen  = agen * (0.4 + k3 * 0.5)"""),

    # ---- physical models ----------------------------------------------------------
    ("WGBOW", "physical", """
  agen  wgbow 0.6, ifq, 0.5 + k1 * 5, 0.05 + k2 * 0.85, 0.5 + k3 * 8, k4 * 0.3, giSine"""),
    ("WGFLUTE", "physical", """
  agen  wgflute 0.6, ifq, 0.05 + k1 * 0.7, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine"""),
    ("WGBRASS", "physical", """
  agen  wgbrass 0.7, ifq, 0.55 + k1 * 0.9, 0.02, 0.5 + k2 * 8, k3 * 0.25, giSine
  agen  = agen * (0.5 + k4 * 0.5)"""),
    ("WGCLAR", "physical", """
  agen  wgclar 0.6, ifq, 0.1 + k1 * 0.8, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine"""),
    ("WGPLUCK", "physical", """
  ; A stiff string: the inharmonicity of real wire, which is what a plucked sample has and
  ; a Karplus-Strong loop does not.
  agen  wgpluck2 0.05 + p7 * 0.9, 0.7, ifq, k2 * 0.9, 0.05 + k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.6)"""),
    ("PLUCKM", "physical", """
  ; Karplus-Strong with a SELECTABLE decay method — `pluck`'s imeth picks between simple
  ; averaging, recursive filtering, stretched decay, snare-like inversion and two weighted
  ; forms, so one opcode covers plucked string through to struck metal.
  ; (This slot held barmodel, then gogobel, then wguide2. The first two need external STK
  ; rawwave tables this Csound cannot find and return silence; the third damps to nothing at
  ; low feedback. `pluck` always speaks.)
  ; pluck's six decay methods do NOT share a parameter contract, and feeding one method's
  ; arguments to another is an INIT ERROR, not a bad sound — the note is deleted and the
  ; draw is silent. Method 5 wants param1 + param2 <= 1 while param2 here is a cutoff in the
  ; hundreds; method 2 wants a stretch factor >= 1 while param1 here is 0.1..0.9. Both were
  ; killing draws.
  ; So only the two whose contract these arguments actually satisfy are used: 1 (simple
  ; averaging, which ignores both) and 3 (simple drum, whose param1 IS a 0..1 roughness).
  ; Variety comes from the pick position and the chain after it, not from methods that have
  ; to be fed something else to work.
  imeth = p8 < 0.5 ? 1 : 3
  agen  pluck 0.7, ifq, ifq * (0.5 + p7 * 1.5), giNoiseT, imeth, 0.1 + p9 * 0.8, 10 + p10 * 500
  agen  = agen * (0.5 + k4 * 0.6)"""),
    ("DRIP", "physical", """
  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.02 + p9 * 0.16, 0.9, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 8"""),
    ("TAMB", "physical", """
  agen  tambourine 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.5 + p10), ifq * 2.7"""),
    ("SLEIGH", "physical", """
  agen  sleighbells 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.3 + p10), ifq * 2.1"""),
    ("MODEBANK", "physical", """
  ; An impulse into a bank of `mode` resonators. Gain is normalised against Q, or a high-Q
  ; bank runs hundreds of times over full scale — measured at 470x before this divide.
  aimp  mpulse 1, 0
  iq    = 20
  am1   mode aimp, ifq, 8 + k1 * 400
  am2   mode aimp, ifq * (1.4 + k2 * 3), 8 + k1 * 300
  am3   mode aimp, ifq * (2.1 + k3 * 6), 8 + k1 * 200
  agen  = (am1 + am2 * 0.7 + am3 * 0.5) / (1 + k1 * 8) * (0.4 + k4 * 0.6)"""),

    # ---- table / terrain / distortion synthesis ------------------------------------
    ("WTERRAIN", "table", """
  ; Wave terrain: an orbit traced over a 2-D surface. Small orbit changes rewrite the
  ; spectrum completely, which is exactly the behaviour a macro knob wants.
  agen  wterrain 0.6, ifq, -1 + k1 * 2, -1 + k2 * 2, 0.1 + k3 * 1.9, 0.1 + k4 * 1.9, giSine, giBell"""),
    ("CHEBY", "table", """
  ; Distortion synthesis: a sine through a Chebyshev polynomial, so AMPLITUDE controls the
  ; harmonic content. The envelope becomes a spectral envelope for free.
  asin  poscil 0.2 + k1 * 0.8, ifq, giSine
  agen  chebyshevpoly asin, 0, 1 - k2, k2 * 0.8, k3 * 0.7, k3 * 0.4, k4 * 0.5, k4 * 0.3"""),
    ("PDIST", "table", """
  ; Phase distortion: read a sine with a warped phasor. Casio's trick, and a cheap route to
  ; hard, resonant, aliasing-prone digital tone.
  aph   phasor ifq
  awrp  = aph ^ (0.25 + k1 * 3.5)
  agen  tablei awrp, giSine, 1, 0, 1
  ares  poscil 1, ifq * (1 + int(k2 * 12)), giSine
  agen  = agen * (1 - k3 * 0.6) + agen * ares * k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.5)"""),
    ("VCO2", "table", """
  ; A band-limited analogue-style pair, detuned. Included as CONTRAST: with everything else
  ; in this file leaning metallic and unstable, one clean harmonic source makes the rest
  ; sound deliberate rather than uniform.
  a1    vco2 0.4, ifq, int(p7 * 3) * 2, 0.5
  a2    vco2 0.4, ifq * (1 + (k2 - 0.5) * 0.03), int(p7 * 3) * 2, 0.5
  agen  = (a1 + a2) * (0.4 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + tanh(agen * (1 + k4 * 8)) * k4 * 0.6"""),
    ("SQUINE", "table", """
  acps  =  a(ifq)
  aclp  =  a(k1 * 0.95)
  askw  =  a(k2 * 0.95)
  agen, async squinewave acps, aclp, askw
  agen  = agen * (0.35 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + agen * agen * agen * k4 * 0.5"""),
    ("BUZZ", "table", """
  ; A band-limited pulse whose partial COUNT is swept — additive brightness with none of
  ; the cost, and it thins to a sine at the bottom.
  agen  gbuzz 0.5, ifq, 1 + int(k1 * 40), int(k2 * 6), 0.2 + k3 * 0.75, giSine
  agen  = agen * (0.4 + k4 * 0.6)"""),
    ("MINCER", "table", """
  ; Read a PADsynth table with an independent pointer: pitch and scan rate come apart, so
  ; the same wavetable can be a drone, a stutter or a smear.
  atim  linseg 0, p3, p3 * (0.1 + p7 * 3)
  agen  mincer atim, 0.6, ifq / 220, giPad, 1, 2048
  agen  = agen * (0.4 + k2 * 0.6)
  agen  = agen * (1 - k3 * 0.5) + agen * poscil(1, ifq * (1 + k4 * 6), giSine) * k3 * 0.7"""),
]

# --------------------------------------------------------------------------- #
# SHAPERS. Mono in, mono out — `agen` to `agen` — so any number of them chain in any order.
#
# They used to be four fixed "stages" that each ALSO did the stereo widening, which is why a
# chain could not compose: a stage was terminal by construction. One core, one stage, and
# seven of the sixteen architectures ended in the same one. Measured, the closest pairs in
# the whole palette were all TONE neighbours (VOSIM<->WGBOW at 0.65 against a 3.02 mean) —
# the stage had become the sound, exactly as the FDN wash had before it.
#
# Two things make a reused shaper sound different each time it appears:
#   {s}  a per-position suffix on every local name, so a shaper can appear twice in one
#        chain without its variables colliding with itself.
#   {c1}..{c4}  constants BAKED at build time from a per-architecture seed. The three live
#        macros (k5..k7) still move the chain, but each instance sits somewhere different in
#        its own parameter space — so RINGMOD in one architecture is a shimmer and in
#        another is a clangourous mess.
# --------------------------------------------------------------------------- #
SHAPERS = [
    ("TONE", """
  ; A resonant filter and a little drive. No feedback path, so it cannot smear a core into
  ; noise or swallow it — which is what the FDN it replaced did to everything it touched.
  aflt{s}  zdf_2pole agen, {c1} + k5 * 9000, 0.7 + k6 * 3, 0
  adrv{s}  = tanh(aflt{s} * (1 + k6 * 3)) * (1 / (1 + k6 * 1.2))
  agen     = aflt{s} * (1 - k6 * 0.6) + adrv{s} * k6 * 0.8"""),

    ("SMEAR", """
  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fs{s}    pvsanal agen, 1024, 256, 1024, 1
  fb{s}    pvsblur fs{s}, 0.01 + k5 * {c2}, 0.5
  asm{s}   pvsynth fb{s}
  agen     = agen * (1 - k6 * 0.85) + asm{s} * k6 * 1.4"""),

    ("SHIFT", """
  ; Frequency shifting, not pitch shifting: every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  are{s}, aim{s} hilbert agen
  ksh{s}   = {c3} + k5 * 700
  aco{s}   poscil 1, ksh{s}, giSine, 0.25
  asi{s}   poscil 1, ksh{s}, giSine, 0
  ash{s}   = are{s} * aco{s} - aim{s} * asi{s}
  agen     = agen * (1 - k6) + ash{s} * k6"""),

    ("CRUSH", """
  ; Deliberate digital damage: fold, quantise, then comb.
  afd{s}   = tanh(agen * (1 + k5 * 12)) * 0.8
  kst{s}   = 1 / (2 ^ ({c4} + (1 - k6) * 9))
  aqn{s}   = (int(afd{s} * 32 / kst{s}) * kst{s}) / 32
  agen     = k6 > 0.5 ? aqn{s} : afd{s}"""),

    ("RINGMOD", """
  ; Ring modulation at an INHARMONIC ratio. Every partial splits into a sum and difference
  ; pair that belongs to no harmonic series, which is the shortest route to bell and gong
  ; territory that exists.
  amd{s}   poscil 1, ifq * ({c1} * 0.001 + 0.5 + k5 * 6), giSine
  agen     = agen * (1 - k6 * 0.9) + agen * amd{s} * k6 * 1.3"""),

    ("COMBRES", """
  ; A tuned comb: a delay short enough that its echoes fuse into a pitch. Hollow, plastic,
  ; and it imposes a resonance of its OWN, so what feeds it is coloured rather than replaced.
  icmb{s}  = 1 / ({c2} * 40 + 60)
  acm{s}   comb agen, 0.15 + k5 * 1.4, icmb{s}
  agen     = agen * (1 - k6 * 0.7) + acm{s} * k6 * 0.5"""),

    ("FOLD", """
  ; A WAVEFOLDER, which is not a clipper: past full scale the transfer function turns back
  ; on itself instead of flattening, so drive multiplies partials rather than squaring off.
  agen     = sin(agen * (1 + k5 * {c3} * 0.02)) * (0.5 + k6 * 0.5)"""),

    ("SUBOCT", """
  ; A subharmonic an octave (or two) below, gated by the signal's own envelope so it only
  ; speaks when the note does. This is where weight in the bottom octave comes from.
  afl{s}   follow agen, 0.02
  asb{s}   poscil 1, ifq * ({c4} > 2 ? 0.25 : 0.5), giSine
  agen     = agen + asb{s} * afl{s} * k5 * 1.6"""),

    ("METALBANK", """
  ; A bank of sharp resonators at INHARMONIC ratios, driven by whatever arrives. Struck
  ; metal: the excitation stops mattering and the body takes over.
  ar1{s}   reson agen, ifq * ({c1} * 0.002 + 1.4), ifq / (10 + k5 * 80), 2
  ar2{s}   reson agen, ifq * ({c2} * 0.004 + 2.7), ifq / (14 + k5 * 60), 2
  ar3{s}   reson agen, ifq * ({c3} * 0.006 + 5.1), ifq / (18 + k5 * 40), 2
  amt{s}   = (ar1{s} + ar2{s} * 0.7 + ar3{s} * 0.5) * 0.4
  agen     = agen * (1 - k6 * 0.85) + amt{s} * k6 * 1.2"""),

    ("STUTTER", """
  ; A delay whose time STEPS rather than glides, held for a fraction of the note. The jumps
  ; are what make it a glitch and not a chorus; the time is derived arithmetically from a
  ; phasor so it repeats identically for a given note instead of drifting.
  aph{s}   phasor {c2} * 0.2 + 2 + k5 * 24
  ast{s}   = (int(aph{s} * 8) / 8) * (0.004 + k6 * 0.09) + 0.001
  adl{s}   vdelay3 agen, ast{s} * 1000, 120
  agen     = agen * (1 - k6 * 0.6) + adl{s} * k6 * 0.9"""),

    ("DECIM", """
  ; Sample-and-hold decimation: drop the effective sample rate and let the aliasing fold
  ; back as inharmonic partials. The classic hard digital sound, and it is NOT bitcrushing —
  ; the damage is in time, not amplitude.
  agen     fold agen, 1 + k5 * ({c1} * 0.06 + 30)"""),

    ("FREEZE", """
  ; Spectral freeze: hold the magnitudes and let the phases run. The tone stops evolving and
  ; becomes a held object, which is the one thing a percussive core cannot do by itself.
  ff{s}    pvsanal agen, 1024, 256, 1024, 1
  fz{s}    pvsfreeze ff{s}, k5, k5
  afz{s}   pvsynth fz{s}
  agen     = agen * (1 - k6 * 0.9) + afz{s} * k6 * 1.3"""),
]

# The stereo stage. Always last, never part of the chain — a chain step that also widened
# was what made stages terminal and unchainable in the first place.
SPATIAL = """
  aL, aR PhWide agen, 0.15 + k7 * 0.75"""

# --------------------------------------------------------------------------- #
# THE SIXTEEN, as CHAINS. Each is a core followed by an ordered SEQUENCE of shapers, and the
# sequence is the architecture's identity as much as the core is.
#
# Chosen against the measurement, not by taste alone. The rules behind this table:
#   * no shaper appears more than three times across all sixteen, so none can become the
#     palette's sound the way the FDN wash did and then TONE did after it;
#   * no ordered chain repeats;
#   * every architecture ends on a different shaper from the one preceding it;
#   * the generator families are spread across chain shapes rather than clustered.
#
# Order is used deliberately: METALBANK then CRUSH is a struck body subsequently damaged,
# CRUSH then METALBANK is damage given a body to ring in. Different architectures, and they
# do not measure as one.
# --------------------------------------------------------------------------- #
PAIRS = [
    ("GENDY",    ["TONE", "METALBANK"]),        # stochastic walk given an inharmonic body
    ("VOSIM",    ["RINGMOD", "COMBRES"]),       # vocal pulse, clangourous, then hollow
    ("FOF2",     ["SMEAR", "FREEZE"]),          # formant grains blurred then held
    ("FMVOICE",  ["SHIFT", "TONE"]),            # vocal FM pulled inharmonic, then filtered
    ("HSB",      ["COMBRES", "FOLD"]),          # stretched partials, tubed and folded
    ("CROSSPM",  ["FOLD", "SUBOCT"]),           # self-evolving pair, folded, weighted low
    ("FMMETAL",  ["CRUSH", "METALBANK"]),       # damage given a body to ring in
    ("FMBELL",   ["METALBANK", "SHIFT"]),       # bell body moved off the harmonic series
    ("CHAOSFM",  ["DECIM", "COMBRES"]),         # chaos aliased down, then tuned
    ("WGBOW",    ["SUBOCT", "TONE"]),           # bowed string with weight underneath
    ("WGFLUTE",  ["FREEZE", "RINGMOD"]),        # breath held still, then made metallic
    ("PLUCKM",   ["STUTTER", "TONE"]),          # plucked and glitch-repeated
    ("MODEBANK", ["SHIFT", "STUTTER"]),         # struck metal, inharmonic, stuttered
    ("WTERRAIN", ["RINGMOD", "DECIM"]),         # orbit made metallic, then aliased
    ("CHEBY",    ["CRUSH", "SUBOCT"]),          # distortion synthesis, damaged, weighted
    ("MINCER",   ["SMEAR", "STUTTER"]),         # wavetable smeared and cut up
]

HEADER = """
; ===========================================================================================
; THE ARCHITECTURES — generated by csound/build-orc.py. DO NOT EDIT BY HAND.
;
; {narch} designed pairings of a generator core with a processor stage, instruments {lo}..{hi}.
; Not a cross product: pairing every core with every stage produced 124 cells in which the
; stage frequently erased the core, so the palette had less usable variety than the ten
; hand-written architectures it was meant to expand.
;
; Macros: p7..p10 core, p11..p13 stage, p14 envelope shape (percussive 0 -> sustained 1).
; ===========================================================================================
"""

BODY = """
instr {num}   ; {gen} -> {proc}
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  k1     = p7
  k2     = p8
  k3     = p9
  k4     = p10
  k5     = p11
  k6     = p12
  k7     = p13
  ; ENVELOPE SHAPE ON ITS OWN MACRO. Two voices with the same spectrum and different
  ; envelopes read as two instruments; this is the cheapest variety in the file.
  ; THE ATTACK CANNOT OUTLAST THE NOTE. p14 pushes the attack to 0.35 s while the duration
  ; band reaches down to 0.1 s, so a sustained-shape macro on a short note produced a hit
  ; that ended before it arrived — silence, and 15% of draws through the stage with the
  ; shortest notes. Capped to a fraction of p3, which is what "percussive to sustained"
  ; should have meant all along.
  iatk   = (0.002 + p14 * 0.35) > (p3 * 0.4) ? p3 * 0.4 : 0.002 + p14 * 0.35
  idec   = 0.05 + (1 - p14) * 0.5
  isus   = p14 * 0.85
  kenv   transegr p6, iatk, 2, p6 * (0.25 + isus), idec, -3, p6 * isus, 0.25 + p14 * 3, -3, 0
{core}
{stage}
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = {trim}
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin
"""

FIRST = 21


def _trims() -> dict[int, float]:
    """Measured peak-matched trims, one per instrument.

    Written by the offline probe: render every architecture with random macro draws, take the
    peak, scale toward 0.6. Guessing these is how one architecture ends up inaudible next to
    another that clips — the same spread the ten hand-written ones already correct for.
    """
    f = pathlib.Path(__file__).with_name("trims.txt")
    out: dict[int, float] = {}
    if f.exists():
        for line in f.read_text().split("\n"):
            parts = line.split()
            if len(parts) >= 2:
                out[int(parts[0])] = float(parts[1])
    return out


def build() -> str:
    trims = _trims()
    gens = {g: c for g, _f, c in GENERATORS}
    shapers = dict(SHAPERS)
    out = [HEADER.format(narch=len(PAIRS), lo=FIRST, hi=FIRST + len(PAIRS) - 1)]
    for i, (gname, chain) in enumerate(PAIRS):
        n = FIRST + i
        # Seeded PER ARCHITECTURE, so the constants are stable across builds: a rebuild that
        # silently re-rolled every timbre would make the trims file — and any judgement made
        # by ear — meaningless.
        rng = random.Random("ph-csound|%s|%s|%d" % (gname, ",".join(chain), n))
        body = []
        for pos, sname in enumerate(chain):
            c = {("c%d" % k): "%.4g" % rng.uniform(*_CONST_RANGE[k - 1]) for k in (1, 2, 3, 4)}
            body.append(shapers[sname].rstrip("\n").format(s=pos, **c))
        out.append(BODY.format(num=n, gen=gname, proc=" -> ".join(chain),
                               core=gens[gname].rstrip("\n"),
                               stage="\n".join(body) + SPATIAL,
                               trim="%.4f" % trims.get(n, 1.0)))
    return "\n".join(out)


# Ranges for the baked constants. Wide enough that two instances of a shaper sit in
# genuinely different territory, bounded so neither extreme is a fault rather than a timbre.
_CONST_RANGE = [(200.0, 2400.0),    # c1: a frequency, or a ratio numerator scaled by 0.001..
                (0.05, 0.85),       # c2: a depth or a normalised time
                (-600.0, 600.0),    # c3: a signed offset (shift direction, fold drive)
                (1.0, 4.0)]         # c4: a small integer-ish selector or exponent base


def names() -> list[tuple[int, str, str, str]]:
    """(instrument number, generator, family, processor) for every architecture."""
    fam = {g: f for g, f, _ in GENERATORS}
    return [(FIRST + i, g, fam[g], " -> ".join(p)) for i, (g, p) in enumerate(PAIRS)]


MARK_BEGIN = "; <<< GENERATED ARCHITECTURE MATRIX BEGIN >>>"
MARK_END = "; <<< GENERATED ARCHITECTURE MATRIX END >>>"


def main() -> None:
    orc = pathlib.Path(__file__).with_name("ph-engine.orc")
    text = orc.read_text()
    block = MARK_BEGIN + "\n" + build() + "\n" + MARK_END + "\n"
    if MARK_BEGIN in text:
        text = re.sub(re.escape(MARK_BEGIN) + r".*?" + re.escape(MARK_END) + r"\n",
                      block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block
    orc.write_text(text)
    rows = names()
    print("wrote %d architectures, instr %d..%d" % (len(rows), rows[0][0], rows[-1][0]))
    _assert_reachable(text, rows)


def _assert_reachable(orc_text: str, rows) -> None:
    """Fail the build if the engine cannot actually PLAY what was just written.

    This exists because of a bug that hid every architecture added after the first ten.
    engine.scd clipped the architecture index to a literal 9 and catalog.py advertised a
    range far wider, and nothing connected the two — so the controller assigned architecture
    21, SuperCollider clipped it to 9 and fired instr 20, and sixteen distinct pairings came
    out of one instrument for months. It was silent in every sense: no error, no warning,
    just a palette that would not diversify no matter what was written here.

    The three numbers have to agree, so they are checked together, at the one moment they
    are all known.
    """
    here = pathlib.Path(__file__).resolve().parent.parent
    legacy = sorted(int(m) for m in re.findall(r"^instr (\d+)", orc_text, flags=re.M)
                    if int(m) < FIRST and int(m) >= 11)
    total = len(legacy) + len(rows)          # architecture INDEX 0 is the lowest instrument
    lo = legacy[0] if legacy else FIRST
    want_max = total - 1
    problems = []

    scd = (here / "supercollider" / "engine.scd").read_text()
    m = re.search(r"~csArchMax\s*=\s*(\d+)", scd)
    if not m:
        problems.append("engine.scd: no ~csArchMax — the architecture ceiling is a literal "
                        "again, which is the bug this guard exists to prevent")
    elif int(m.group(1)) != want_max:
        problems.append("engine.scd: ~csArchMax = %s, but the orchestra offers 0..%d"
                        % (m.group(1), want_max))
    m = re.search(r"^\s*\"\$i\"\s*\+\+\s*\((\d+)\s*\+\s*arch\)", scd, flags=re.M)
    if m and int(m.group(1)) != lo:
        problems.append("engine.scd: fires instr %s+arch, but the lowest architecture is %d"
                        % (m.group(1), lo))

    cat = (here / "controller" / "poundhard" / "catalog.py").read_text()
    m = re.search(r"^CS_ARCH_COUNT\s*=\s*(\d+)", cat, flags=re.M)
    if not m:
        problems.append("catalog.py: no CS_ARCH_COUNT")
    elif int(m.group(1)) != total:
        problems.append("catalog.py: CS_ARCH_COUNT = %s, but the orchestra has %d "
                        "architectures" % (m.group(1), total))

    if problems:
        raise SystemExit("ARCHITECTURES ARE NOT REACHABLE:\n  " + "\n  ".join(problems))
    print("reachable: architectures 0..%d -> instr %d..%d (engine.scd and catalog.py agree)"
          % (want_max, lo, rows[-1][0]))


if __name__ == "__main__":
    main()
