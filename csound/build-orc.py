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
  ; Grains scattered over a frozen noise table — periodic noise, so it locks to the pulse
  ; instead of hissing over it.
  agen  grain3 ifq, 0, k1 * 400, k2 * 0.5, 0.005 + k3 * 0.12, 8 + k4 * 190, 40, giNoiseT, giGrEnv, 1, 1"""),
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
  a1, a2 crosspm kf1, kf2, k2 * 6, k3 * 6, 1 + k4 * 8, giSine, giSine
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
    ("WGUIDE2", "physical", """
  ; Two coupled waveguides struck by an impulse: a metal bar or plate with two resonant
  ; paths beating against each other.
  ; (This slot held `barmodel` and then `gogobel`. Both compile and both return silence —
  ; gogobel says why: "No table for Agogobell strike". The STK-derived models need external
  ; rawwave excitation tables this Csound cannot find, so they are avoided entirely.)
  aexc  mpulse 0.7, 0
  aexc  =  aexc + dust2(0.2 * k4, 20 + k4 * 400)
  agen  wguide2 aexc, ifq, ifq * (1.4 + k1 * 3), 2000 + k2 * 9000, 1500 + k2 * 7000, 0.7 + k3 * 0.29, 0.7 + k3 * 0.28"""),
    ("DRIP", "physical", """
  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.05 + p9 * 0.35, 0.6, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 6"""),
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
# PROCESSOR STAGES. Each takes mono `agen` and produces stereo `aL`/`aR` from macros
# k5..k7. These are not effects hung off the end — each rewires what the core produces.
# --------------------------------------------------------------------------- #
PROCESSORS = [
    ("BODY", """
  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8"""),
    ("SMEAR", """
  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75"""),
    ("SHIFT", """
  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5"""),
    ("CRUSH", """
  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6"""),
]

HEADER = """
; ===========================================================================================
; THE ARCHITECTURE MATRIX — generated by csound/build-orc.py. DO NOT EDIT BY HAND.
;
; {ngen} generator cores x {nproc} processor stages = {narch} architectures, instruments
; {lo}..{hi}. Ten hand-written architectures gave ten sounds and the repeats were audible
; however the macros were sampled; this is the answer to that. Every pair is a distinct
; signal path, not a different setting of the same one.
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
  iatk   = 0.002 + p14 * 0.35
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
    out = [HEADER.format(ngen=len(GENERATORS), nproc=len(PROCESSORS),
                         narch=len(GENERATORS) * len(PROCESSORS),
                         lo=FIRST, hi=FIRST + len(GENERATORS) * len(PROCESSORS) - 1)]
    n = FIRST
    for gname, _fam, gcode in GENERATORS:
        for pname, pcode in PROCESSORS:
            out.append(BODY.format(num=n, gen=gname, proc=pname,
                                   core=gcode.rstrip("\n"), stage=pcode.rstrip("\n"),
                                   trim="%.4f" % trims.get(n, 1.0)))
            n += 1
    return "\n".join(out)


def names() -> list[tuple[int, str, str, str]]:
    """(instrument number, generator, family, processor) for every architecture."""
    rows = []
    n = FIRST
    for gname, fam, _ in GENERATORS:
        for pname, _p in PROCESSORS:
            rows.append((n, gname, fam, pname))
            n += 1
    return rows


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


if __name__ == "__main__":
    main()
