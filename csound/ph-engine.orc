; PoundHard — the CSOUND engine (engine 20), realtime.
;
; Csound runs as its own JACK client and writes ONE STEREO PAIR PER TRACK into
; supernova's input ports. An SC voice reads that pair straight onto the track bus, so a
; Csound track goes through PoundHard's per-track filter, its 8-slot FX chain, the
; living-FX sends, the mixer and the master exactly like every other engine. Nothing here
; talks to the hardware.
;
; CONTRACT — every architecture takes the same p-fields, so the controller can treat them
; interchangeably and a track's "sound" is just (architecture, eight macro values):
;   p4  track index 0-15   (output pair = channels 3+2*track, 4+2*track)
;   p5  frequency (Hz)
;   p6  amplitude 0-2
;   p7..p14   eight macro parameters, each normalised 0-1
;
; The macros mean something different in each architecture — that is the point. They are
; the eight knobs the rest of PoundHard already knows how to sweep, randomise and lock per
; step, so the Csound engine gets the voice macro, the chaos macro and living-step
; transforms for free.
;
; DESIGN. Not one synthesis method with variations: ten architectures, each a hybrid of
; generators and processors wired as one instrument rather than a synth with effects bolted
; on. The palette leans metallic, inharmonic, granular and unstable — IDM, rhythmic noise,
; industrial and electroacoustic textures — and avoids anything that reads as a vintage
; analogue emulation. Digital artefacts (aliasing, quantisation, feedback on the edge of
; blowing up) are used deliberately, and bounded so they stay musical.

sr      = 44100
ksmps   = 64
0dbfs   = 1

; ---- tables ---------------------------------------------------------------------------
giSine    ftgen 0, 0, 16384, 10, 1
giTri     ftgen 0, 0, 16384, 10, 1, 0, 0.111, 0, 0.04, 0, 0.02
; an inharmonic, metallic partial set — the engine's house timbre
giBell    ftgen 0, 0, 16384, 10, 1, 0.4, 0.7, 0.2, 0.55, 0.15, 0.3, 0.1, 0.25
; a deliberately bright, aliasing-prone table for phase distortion and waveshaping
giSaw     ftgen 0, 0, 16384, 10, 1, 0.5, 0.333, 0.25, 0.2, 0.167, 0.143, 0.125, 0.111, 0.1
; Chebyshev transfer function for waveshaping (distort/powershape partner)
giCheb    ftgen 0, 0, 16384, 13, 1, 1, 0, 1, 0, 0.6, 0, 0.4, 0, 0.25
; grain envelope: a short, asymmetric window keeps clouds gritty rather than smooth
giGrEnv   ftgen 0, 0, 8192, 20, 6, 1
; a frozen block of uniform noise. Read back by a phasor it becomes PERIODIC noise — the
; metallic, looping grain of a shift register, and unlike a live generator it repeats
; exactly, so it locks to the pulse instead of hissing over it.
giNoiseT  ftgen 0, 0, 4096, 21, 1
; PADsynth: a spectrally-smeared, inharmonic wavetable built once at load
giPad     ftgen 0, 0, 262144, "padsynth", 220, 40, 1.6, 1, 1.2, 1, 0.6, 0.9, 0.3, 0.7, 0.2

; ---- helpers --------------------------------------------------------------------------
; A per-note random modulator: every hit lands somewhere slightly different, which is what
; keeps a repeated step from sounding like a sample.
opcode PhJit, k, kk
  kdepth, krate xin
  kj   jitter kdepth, krate * 0.4, krate * 2.2
  xout kj
endop

; Stereo imaging from ONE mono source: a short Haas offset plus opposed spectral tilt.
; Cheaper and less mushy than a reverb, and it keeps the transient centred.
opcode PhWide, aa, ak
  ain, kw xin
  adl  vdelay3 ain, kw * 11, 24
  aL   =  ain * (1 - kw * 0.35) + adl * (kw * 0.55)
  aR   =  ain * (1 - kw * 0.15) - adl * (kw * 0.35)
  aLh  butterhp aL, 120 + kw * 200
  aRl  butterlp aR, 9000 - kw * 3000
  xout aL * 0.7 + aLh * 0.3, aR * 0.7 + aRl * 0.3
endop

; A small feedback delay network: four irrational-ratio taps, cross-fed. Used INSIDE the
; voices as a resonant body, not as a reverb hung off the end.
opcode PhFDN, aa, akk
  ain, ktime, kfb xin
  aL   init 0
  aR   init 0
  ad1  vdelay3 ain + aL * kfb * 0.7, ktime * 1000, 500
  ad2  vdelay3 ain + aR * kfb * 0.7, ktime * 1414, 500
  ad3  vdelay3 ad1 * 0.6 + ad2 * 0.4, ktime * 1732, 500
  ad4  vdelay3 ad2 * 0.6 - ad1 * 0.4, ktime * 2236, 500
  aL   =  butterlp(ad1 + ad3, 6500)
  aR   =  butterlp(ad2 + ad4, 6500)
  xout aL, aR
endop

; NOISE, tamed. `fractalnoise` at a high beta is a random WALK: it wanders off DC and its
; RMS keeps growing, so a voice built on it drifts louder the longer it runs and its level
; depends on beta. DC-block it, then hold it to a fixed RMS against a white reference — now
; beta changes the COLOUR and nothing else.
opcode PhNoise, a, kk
  kamp, kbeta xin
  araw  fractalnoise 1, kbeta
  adc   dcblock2 araw
  aref  rand 0.5
  anrm  balance adc, aref
  xout  anrm * kamp * 2
endop

; CHAOS. Feedback FM: an oscillator phase-modulated by its OWN previous sample. Below a
; threshold it is a harmonic timbre; above it the loop period-doubles and then breaks into
; genuine chaos — the industrial route to noise that still tracks pitch. setksmps 1 is what
; makes it real: at block rate the feedback is 64 samples stale and the route to chaos is
; lost. tanh bounds the loop so it can never run away. (Csound's own `lorenz` NaNs in this
; build at every step size and argument order tried, so the attractor is built here.)
opcode PhChaos, a, akk
  ain, kfreq, kfb xin
  setksmps 1
  aprev init 0
  aph   phasor kfreq
  aval  tablei aph + tanh(aprev * kfb) * 0.5, giSine, 1, 0, 1
  aprev =  aval + ain * 0.3
  xout  aval
endop

; ---- the output bus ---------------------------------------------------------------
; Voices ACCUMULATE here rather than writing to the sound card. A per-voice limiter cannot
; stop a track clipping: each voice was individually under the ceiling and then four
; overlapping hits summed straight past it. One limiter per track pair, after the sum, is
; the only place the ceiling can actually be enforced.
gaL[]  init 17          ; 16 tracks + the audition pair
gaR[]  init 17

; The one exit point. Every architecture ends here: DC blocking, a generous per-voice
; safety clip (so one runaway voice cannot poison the sum), and the track routing.
opcode PhOut, 0, aaii
  aL, aR, itrack, ichan xin
  it   =  itrack
  aLd  dcblock2 aL
  aRd  dcblock2 aR
  aLc  clip aLd, 0, 4
  aRc  clip aRd, 0, 4
  gaL[it] = gaL[it] + aLc
  gaR[it] = gaR[it] + aRc
endop

; ---- the output stage -----------------------------------------------------------------
; Runs for a century so the performance never ends (every note arrives over UDP, so the
; score has nothing else in it), and — because Csound runs instruments in numerical order
; and this is the highest number — it is also where every track's accumulated sum is
; limited and written out, after all voices for the block have contributed.
;
; The limiter rides gain from the block peak: transparent below the ceiling, and it only
; ever pulls DOWN, never boosts. Attack is one control block (1.5 ms), release is slow
; enough not to pump. A soft clip sits behind it as a backstop for the single block an
; instantaneous transient can sneak through before the gain reacts.
; A gain-riding limiter for one stereo pair. Transparent below the ceiling, and it only
; ever pulls DOWN — never boosts. Attack is one control block (1.5 ms); release is slow
; enough not to pump. The clip behind it catches the single block an instantaneous
; transient can sneak through before the gain reacts.
;
; A UDO, called once per track BY NAME rather than from a loop: max_k and kheld are state,
; and a runtime loop would reuse one instance for all 17 pairs, so a single loud track
; would duck every other one.
opcode PhLimit, aa, aai
  aL, aR, iCeil xin
  kpk   max_k abs(aL) + abs(aR), 1, 1
  kwant =  (kpk > iCeil ? iCeil / kpk : 1)
  kheld init 1
  kheld =  (kwant < kheld ? kwant : kheld + (kwant - kheld) * 0.002)
  aLo   clip aL * kheld, 0, 0.95
  aRo   clip aR * kheld, 0, 0.95
  xout  aLo, aRo
endop

instr 999
  iCeil = 0.85
  aL0, aR0  PhLimit gaL[0], gaR[0], iCeil
  outch 3, aL0, 4, aR0
  gaL[0] = 0
  gaR[0] = 0
  aL1, aR1  PhLimit gaL[1], gaR[1], iCeil
  outch 5, aL1, 6, aR1
  gaL[1] = 0
  gaR[1] = 0
  aL2, aR2  PhLimit gaL[2], gaR[2], iCeil
  outch 7, aL2, 8, aR2
  gaL[2] = 0
  gaR[2] = 0
  aL3, aR3  PhLimit gaL[3], gaR[3], iCeil
  outch 9, aL3, 10, aR3
  gaL[3] = 0
  gaR[3] = 0
  aL4, aR4  PhLimit gaL[4], gaR[4], iCeil
  outch 11, aL4, 12, aR4
  gaL[4] = 0
  gaR[4] = 0
  aL5, aR5  PhLimit gaL[5], gaR[5], iCeil
  outch 13, aL5, 14, aR5
  gaL[5] = 0
  gaR[5] = 0
  aL6, aR6  PhLimit gaL[6], gaR[6], iCeil
  outch 15, aL6, 16, aR6
  gaL[6] = 0
  gaR[6] = 0
  aL7, aR7  PhLimit gaL[7], gaR[7], iCeil
  outch 17, aL7, 18, aR7
  gaL[7] = 0
  gaR[7] = 0
  aL8, aR8  PhLimit gaL[8], gaR[8], iCeil
  outch 19, aL8, 20, aR8
  gaL[8] = 0
  gaR[8] = 0
  aL9, aR9  PhLimit gaL[9], gaR[9], iCeil
  outch 21, aL9, 22, aR9
  gaL[9] = 0
  gaR[9] = 0
  aL10, aR10  PhLimit gaL[10], gaR[10], iCeil
  outch 23, aL10, 24, aR10
  gaL[10] = 0
  gaR[10] = 0
  aL11, aR11  PhLimit gaL[11], gaR[11], iCeil
  outch 25, aL11, 26, aR11
  gaL[11] = 0
  gaR[11] = 0
  aL12, aR12  PhLimit gaL[12], gaR[12], iCeil
  outch 27, aL12, 28, aR12
  gaL[12] = 0
  gaR[12] = 0
  aL13, aR13  PhLimit gaL[13], gaR[13], iCeil
  outch 29, aL13, 30, aR13
  gaL[13] = 0
  gaR[13] = 0
  aL14, aR14  PhLimit gaL[14], gaR[14], iCeil
  outch 31, aL14, 32, aR14
  gaL[14] = 0
  gaR[14] = 0
  aL15, aR15  PhLimit gaL[15], gaR[15], iCeil
  outch 33, aL15, 34, aR15
  gaL[15] = 0
  gaR[15] = 0
  aL16, aR16  PhLimit gaL[16], gaR[16], iCeil
  outch 35, aL16, 36, aR16
  gaL[16] = 0
  gaR[16] = 0
endin

; =======================================================================================
; 11 — FMMETAL. Phase modulation with deliberately inharmonic ratios into a waveshaper and
; a modal resonator: struck-metal timbres that are pitched but never harmonic.
; =======================================================================================
instr 11
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.002, 0, p6, 0.1 + p7 * 2.5, -4 - p8 * 6, 0
  kratio = 1.41 + p9 * 5.6                      ; irrational by default -> inharmonic
  kindex = (0.5 + p10 * 9) * kenv               ; index tracks the envelope: bright attack
  kdet   PhJit 0.02 + p11 * 0.1, 3 + p12 * 9
  amod   poscil kindex * ifq, ifq * kratio * (1 + kdet), giSine
  ; TRUE phase modulation: the modulator is added to the carrier's phase ramp, not to its
  ; frequency. poscil's phase input is i-rate only, so the phasor is written out.
  aphs   phasor ifq
  acar   tablei aphs + amod / sr, giSine, 1, 0, 1
  ash    powershape acar, 1 + p13 * 6
  awv    distort1 ash, p13 * 2.5, 0.2 + p13 * 0.5, 0, 0
  amod2  mode awv, ifq * (1.7 + p9 * 3), 8 + p14 * 300
  amod3  mode awv, ifq * (3.1 + p9 * 5), 6 + p14 * 200
  knorm  = 1 / (1 + p14 * 8)                     ; the resonators' gain rides on their Q
  amix   = (awv * (1 - p14 * 0.5) + (amod2 * 0.5 + amod3 * 0.35) * knorm) * kenv
  aL, aR PhWide amix, 0.2 + p11 * 0.7
  iTrim  = 0.070  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 12 — GRANCLOUDS. Granular over the inharmonic wavetable, spectrally blurred, then thrown
; through the FDN. Grain rate and pitch scatter are the two knobs that matter.
; =======================================================================================
instr 12
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.005 + p7 * 0.2, 1, p6, 0.2 + p7 * 3, -3, 0
  kdens  = 8 + p8 * 900
  kspred = p9 * 0.9
  kpitch PhJit p10 * 0.5, 2 + p11 * 12
  ;      cps  phs  freq-dev       phase-dev  grain dur           density  maxovr  wave    window  frpow prpow
  agr    grain3 ifq, 0, kspred * 400, kpitch, 0.004 + p12 * 0.09, kdens, 40, giBell, giGrEnv, 0, 0
  fsig   pvsanal agr, 1024, 256, 1024, 1
  fblur  pvsblur fsig, 0.02 + p13 * 0.4, 0.5
  fsc    pvscale fblur, 1 + p14 * 0.5
  ares   pvsynth fsc
  amix   = (agr * (1 - p13 * 0.6) + ares * (0.4 + p13 * 0.9)) * kenv * 0.5
  adL, adR PhFDN amix, 0.02 + p12 * 0.1, p11 * 0.6
  aL     = amix * 0.6 + adL * 0.5
  aR     = amix * 0.6 + adR * 0.5
  iTrim  = 0.725  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 13 — MODALSTRIKE. A noise burst driving a bank of six detuned modes. Pure resonator
; synthesis: the excitation is gone in milliseconds and the body is the whole sound.
; =======================================================================================
instr 13
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kexc   transegr 1, 0.0005 + p7 * 0.02, -6, 0
  anoise PhNoise 1, 0.5 + p8 * 1.8
  aexc   = anoise * kexc * p6
  kq     = 20 + p9 * 900
  kspr   = 1 + p10 * 2.4                        ; how far the modes fan out
  a1     mode aexc, ifq, kq
  a2     mode aexc, ifq * (1.5 * kspr), kq * 0.8
  a3     mode aexc, ifq * (2.31 * kspr), kq * 0.65
  a4     mode aexc, ifq * (3.87 * kspr), kq * 0.5
  a5     mode aexc, ifq * (5.19 * kspr), kq * 0.4
  a6     mode aexc, ifq * (7.41 * kspr), kq * 0.3
  ; mode's gain is PROPORTIONAL TO Q, so a bank at Q=900 is ~20x a bank at Q=20 and no
  ; fixed output trim can level the two. Normalise against Q here instead.
  knorm  = 1 / (1 + kq * 0.15)     ; measured: mode's gain is ~Q/7
  amix   = (a1 + a2 * 0.8 + a3 * 0.6 + a4 * 0.45 + a5 * 0.3 + a6 * 0.2) * knorm
  ash    powershape amix * (1 + p11 * 3), 1 + p11 * 4
  kring  = 40 + p12 * 3000
  arm    poscil 1, kring, giSine
  amod   = ash * (1 - p12 * 0.7) + ash * arm * (p12 * 0.9)
  kbody  transegr p6, 0.01, 0, p6, 0.3 + p13 * 4, -3, 0
  aL, aR PhWide amod * kbody * 0.4, 0.15 + p14 * 0.8
  iTrim  = 0.005  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 14 — CHAOSDRONE. A Lorenz attractor as the audio source, tamed by a resonant filter and
; ring-modulated. Unstable by construction; the envelope is what makes it a hit.
; =======================================================================================
instr 14
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.004, 0, p6, 0.15 + p7 * 3.5, -3, 0
  kfb    = 0.5 + p8 * 7.5                        ; below ~1.5 harmonic, above it chaotic
  anz    PhNoise 0.05 * p9, 1.4                  ; a little noise into the loop keeps it moving
  achaos PhChaos anz, ifq, kfb
  asrc   = achaos * 0.7
  kcf    PhJit 0.4, 0.5 + p10 * 8
  kcut   = ifq * (1 + p11 * 7) * (1 + kcf * 0.5)
  aflt   moogladder asrc, kcut, 0.2 + p12 * 0.72
  arm    poscil 1, ifq * (0.5 + p13 * 4), giSine
  amod   = aflt * (1 - p13 * 0.6) + aflt * arm * (p13 * 0.8)
  areal, aimag hilbert amod
  ashm   poscil 1, p14 * 400, giSine
  ashc   poscil 1, p14 * 400, giSine, 0.25
  ashift = areal * ashc - aimag * ashm           ; frequency shifter: inharmonic smear
  amix   = (amod * (1 - p14) + ashift * p14) * kenv
  aL, aR PhWide amix, 0.3 + p9 * 0.6
  iTrim  = 3.500  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 15 — WAVEGUIDE. Plucked/bowed waveguide models pushed past their polite range, into a
; feedback delay network that acts as the instrument's body.
; =======================================================================================
instr 15
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.002, 0, p6, 0.2 + p7 * 3, -3.5, 0
  apl    repluck 0.1 + p8 * 0.85, 1, ifq, 0.1 + p9 * 0.8, 0.5, \
                 PhNoise(0.6, 1 + p10 * 1.5)
  abw    wgbow 0.4, ifq * (1 + p11 * 0.02), 1.5 + p11 * 3, 0.1 + p12 * 0.8, \
               0.05 + p9 * 0.4, 6 + p10 * 8
  amix   = apl * (1 - p13) + abw * p13
  ash    distort1 amix, p14 * 3, 0.3, 0, 0
  adL, adR PhFDN ash * 0.5, 0.004 + p12 * 0.06, 0.3 + p14 * 0.55
  aL     = (ash * 0.5 + adL * 0.7) * kenv
  aR     = (ash * 0.5 + adR * 0.7) * kenv
  iTrim  = 0.790  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 16 — SPECTRAL. Generate wide, then rebuild it in the frequency domain: analysis, warping
; and resynthesis are the instrument. Where the electroacoustic textures come from.
; =======================================================================================
instr 16
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.01 + p7 * 0.3, 1, p6, 0.3 + p7 * 3, -2.5, 0
  abuz   gbuzz 0.4, ifq, 6 + p8 * 30, 1, 0.4 + p9 * 0.55, giSine
  anz    PhNoise 0.25 * p10, 1.2
  asrc   = abuz + anz
  fsig   pvsanal asrc, 1024, 256, 1024, 1
  fsc    pvscale fsig, 0.5 + p11 * 2.5, 1, 1
  fbl    pvsblur fsc, 0.01 + p12 * 0.35, 0.4
  fmo    pvsmooth fbl, 0.02 + p13 * 0.6, 0.02 + p13 * 0.6
  ares   pvsynth fmo
  kcut   = 200 + p14 * 9000
  aflt   zdf_2pole ares, kcut, 0.5 + p12 * 4, 0
  amix   = aflt * kenv * 0.8
  aL, aR PhWide amix, 0.4 + p9 * 0.5
  iTrim  = 2.496  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 17 — PHASEDIST. Phase distortion and hard waveshaping — the digital-artefact architecture.
; Aliasing here is the instrument, not a defect, so it is shaped rather than suppressed.
; =======================================================================================
instr 17
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.001, 0, p6, 0.06 + p7 * 1.6, -5, 0
  aph    phasor ifq
  kbend  = 0.05 + p8 * 0.9                       ; where the phase ramp breaks
  ; The two-segment phase warp, written BRANCHLESS — Csound has no a-rate conditional, and
  ; min/max reproduce the break point exactly: below it the first term is the whole value,
  ; above it the first term saturates at 0.5 and the second takes over.
  abend  = a(kbend)                              ; min/max need matching rates
  azero  = a(0)
  awarp  = min(aph, abend) / (2 * kbend) + max(aph - abend, azero) / (2 * (1 - kbend))
  aosc   tablei awarp, giSaw, 1, 0, 1
  kfold  = 1 + p9 * 12
  afold  = tanh(aosc * kfold) / tanh(kfold)
  acheb  chebyshevpoly afold, 0, 1, p10 * 0.9, p10 * 0.5, p11 * 0.6
  kq     = 1 + p12 * 20
  ares   streson acheb, ifq * (1 + p13 * 3), 0.6 + p12 * 0.35
  kbits  = 16 - p14 * 13
  astep  = floor(ares * (2 ^ kbits)) / (2 ^ kbits)   ; deliberate quantisation artefacts
  amix   = (ares * (1 - p14) + astep * p14) * kenv * 0.5
  aL, aR PhWide amix, 0.2 + p10 * 0.6
  iTrim  = 0.457  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 18 — NOISEMACHINE. The rhythmic-noise architecture: correlated noise sources through
; steep dynamic filters, gated hard. Pitch is a filter centre, not an oscillator.
; =======================================================================================
instr 18
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.0005, 0, p6, 0.03 + p7 * 0.9, -6 - p8 * 4, 0
  afr    PhNoise 0.7, 0.2 + p9 * 2.2             ; beta sweeps white -> brown
  aph    phasor 40 + p10 * 3000                  ; periodic noise: metallic, pitched grit
  alf    tablei aph, giNoiseT, 1, 0, 1
  asrc   = afr * (1 - p11) + alf * p11
  kgl    PhJit 0.5, 1 + p12 * 20
  kcut   = ifq * (1 + p13 * 6) * (1 + kgl * 0.6)
  a1     zdf_2pole asrc, kcut, 2 + p12 * 12, 0
  a2     zdf_2pole asrc, kcut * 2.7, 3 + p12 * 14, 2
  amix   = a1 * 0.7 + a2 * 0.5
  ash    distort1 amix, 1 + p14 * 5, 0.4, 0, 0
  agate  = ash * kenv
  adL, adR PhFDN agate * 0.35, 0.003 + p13 * 0.03, p14 * 0.5
  aL     = agate + adL * 0.5
  aR     = agate + adR * 0.5
  iTrim  = 0.066  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 19 — ADDITIVE. Sixteen partials on an inharmonic series, each with its own decay and a
; slow random walk — the evolving-texture architecture.
; =======================================================================================
instr 19
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.004 + p7 * 0.2, 1, p6, 0.4 + p7 * 4, -2.5, 0
  kstr   = 1 + p8 * 1.6                          ; partial stretch: 1 = harmonic
  kwalk  PhJit p9 * 0.03, 0.2 + p10 * 2
  ; written out rather than looped: each partial keeps its OWN decay rate, which is what
  ; makes the spectrum evolve instead of just fading
  a1  poscil 1.00, ifq * (1 * kstr) * (1 + kwalk), giSine
  a2  poscil 0.70, ifq * (2.03 * kstr) * (1 + kwalk * 1.2), giSine
  a3  poscil 0.52, ifq * (3.11 * kstr), giSine
  a4  poscil 0.40, ifq * (4.22 * kstr) * (1 + kwalk * 0.8), giSine
  a5  poscil 0.32, ifq * (5.37 * kstr), giSine
  a6  poscil 0.26, ifq * (6.55 * kstr) * (1 + kwalk * 1.4), giSine
  a7  poscil 0.21, ifq * (7.76 * kstr), giSine
  a8  poscil 0.17, ifq * (9.01 * kstr) * (1 + kwalk), giSine
  k1  transegr 1, 0.3 + p11 * 3.0, -2, 0
  k2  transegr 1, 0.25 + p11 * 2.2, -3, 0
  k3  transegr 1, 0.2 + p11 * 1.6, -3.5, 0
  k4  transegr 1, 0.15 + p11 * 1.1, -4, 0
  amix = (a1 * k1 + a2 * k2 + a3 * k3 + a4 * k4 + a5 * k1 * 0.6 \
          + a6 * k2 * 0.5 + a7 * k3 * 0.4 + a8 * k4 * 0.3) * 0.25
  ash  powershape amix, 1 + p12 * 3
  kcut = 300 + p13 * 9000
  aflt butterlp ash, kcut
  aL, aR PhWide aflt * kenv, 0.3 + p14 * 0.6
  iTrim  = 3.366  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; =======================================================================================
; 20 — PADWAVE. The PADsynth table (spectrally smeared, inharmonic) read as a wavetable,
; cross-modulated with itself and diffused. Wide, evolving, synthetic.
; =======================================================================================
instr 20
  itrack = p4
  ichan  = itrack * 2 + 3
  ifq    = p5
  kenv   transegr p6, 0.01 + p7 * 0.4, 1, p6, 0.3 + p7 * 4, -2, 0
  kdet   PhJit 0.01 + p8 * 0.06, 0.3 + p9 * 3
  a1     poscil 0.5, ifq * (1 + kdet), giPad
  a2     poscil 0.5, ifq * (1 - kdet) * (1 + p10 * 0.01), giPad
  axm    poscil 1, ifq * (0.5 + p11 * 3.5), giSine
  across = (a1 + a2) * (1 - p12 * 0.7) + (a1 * axm + a2) * (p12 * 0.9)
  kcut   = 400 + p13 * 8000
  aflt   zdf_2pole across, kcut, 0.7 + p13 * 3, 0
  adL, adR PhFDN aflt * 0.4, 0.03 + p14 * 0.12, 0.4 + p14 * 0.45
  aL     = (aflt * 0.6 + adL * 0.8) * kenv
  aR     = (aflt * 0.6 + adR * 0.8) * kenv
  iTrim  = 2.673  ; peak-matched: measured raw, then scaled to ~0.6 (the limiter catches excursions)
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; <<< GENERATED ARCHITECTURE MATRIX BEGIN >>>

; ===========================================================================================
; THE ARCHITECTURE MATRIX — generated by csound/build-orc.py. DO NOT EDIT BY HAND.
;
; 31 generator cores x 4 processor stages = 124 architectures, instruments
; 21..144. Ten hand-written architectures gave ten sounds and the repeats were audible
; however the macros were sampled; this is the answer to that. Every pair is a distinct
; signal path, not a different setting of the same one.
;
; Macros: p7..p10 core, p11..p13 stage, p14 envelope shape (percussive 0 -> sustained 1).
; ===========================================================================================


instr 21   ; GENDY -> BODY
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

  ; Xenakis' dynamic stochastic synthesis: the waveform is a random walk of breakpoints, so
  ; the timbre is never twice the same and the pitch is only as stable as you let it be.
  agen  gendy 1, int(k1 * 5), int(k2 * 5), ifq * 0.5, ifq * 2, k3 * 0.9 + 0.05, k4 * 0.9 + 0.05, 12, 12
  agen  = agen * 0.7

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 22   ; GENDY -> SMEAR
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

  ; Xenakis' dynamic stochastic synthesis: the waveform is a random walk of breakpoints, so
  ; the timbre is never twice the same and the pitch is only as stable as you let it be.
  agen  gendy 1, int(k1 * 5), int(k2 * 5), ifq * 0.5, ifq * 2, k3 * 0.9 + 0.05, k4 * 0.9 + 0.05, 12, 12
  agen  = agen * 0.7

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 23   ; GENDY -> SHIFT
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

  ; Xenakis' dynamic stochastic synthesis: the waveform is a random walk of breakpoints, so
  ; the timbre is never twice the same and the pitch is only as stable as you let it be.
  agen  gendy 1, int(k1 * 5), int(k2 * 5), ifq * 0.5, ifq * 2, k3 * 0.9 + 0.05, k4 * 0.9 + 0.05, 12, 12
  agen  = agen * 0.7

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.2110
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 24   ; GENDY -> CRUSH
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

  ; Xenakis' dynamic stochastic synthesis: the waveform is a random walk of breakpoints, so
  ; the timbre is never twice the same and the pitch is only as stable as you let it be.
  agen  gendy 1, int(k1 * 5), int(k2 * 5), ifq * 0.5, ifq * 2, k3 * 0.9 + 0.05, k4 * 0.9 + 0.05, 12, 12
  agen  = agen * 0.7

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 9.1959
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 25   ; GRAINN -> BODY
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

  ; Grains scattered over a frozen noise table — periodic noise, so it locks to the pulse
  ; instead of hissing over it.
  agen  grain3 ifq, 0, k1 * 400, k2 * 0.5, 0.005 + k3 * 0.12, 8 + k4 * 190, 40, giNoiseT, giGrEnv, 1, 1

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2581
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 26   ; GRAINN -> SMEAR
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

  ; Grains scattered over a frozen noise table — periodic noise, so it locks to the pulse
  ; instead of hissing over it.
  agen  grain3 ifq, 0, k1 * 400, k2 * 0.5, 0.005 + k3 * 0.12, 8 + k4 * 190, 40, giNoiseT, giGrEnv, 1, 1

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1726
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 27   ; GRAINN -> SHIFT
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

  ; Grains scattered over a frozen noise table — periodic noise, so it locks to the pulse
  ; instead of hissing over it.
  agen  grain3 ifq, 0, k1 * 400, k2 * 0.5, 0.005 + k3 * 0.12, 8 + k4 * 190, 40, giNoiseT, giGrEnv, 1, 1

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.8224
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 28   ; GRAINN -> CRUSH
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

  ; Grains scattered over a frozen noise table — periodic noise, so it locks to the pulse
  ; instead of hissing over it.
  agen  grain3 ifq, 0, k1 * 400, k2 * 0.5, 0.005 + k3 * 0.12, 8 + k4 * 190, 40, giNoiseT, giGrEnv, 1, 1

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2801
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 29   ; RESBANK -> BODY
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

  ; Noise through a bank of sharp resonators: pitched by the filters, not by an oscillator.
  anz   PhNoise 1, 0.5 + k1 * 2.5
  ar1   reson anz, ifq, ifq / (8 + k2 * 90), 2
  ar2   reson anz, ifq * (1.7 + k3 * 3), ifq / (10 + k2 * 60), 2
  ar3   reson anz, ifq * (3.1 + k3 * 5), ifq / (12 + k2 * 40), 2
  agen  = (ar1 + ar2 * 0.6 + ar3 * 0.4) * (0.3 + k4 * 0.7)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 0.9464
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 30   ; RESBANK -> SMEAR
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

  ; Noise through a bank of sharp resonators: pitched by the filters, not by an oscillator.
  anz   PhNoise 1, 0.5 + k1 * 2.5
  ar1   reson anz, ifq, ifq / (8 + k2 * 90), 2
  ar2   reson anz, ifq * (1.7 + k3 * 3), ifq / (10 + k2 * 60), 2
  ar3   reson anz, ifq * (3.1 + k3 * 5), ifq / (12 + k2 * 40), 2
  agen  = (ar1 + ar2 * 0.6 + ar3 * 0.4) * (0.3 + k4 * 0.7)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2875
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 31   ; RESBANK -> SHIFT
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

  ; Noise through a bank of sharp resonators: pitched by the filters, not by an oscillator.
  anz   PhNoise 1, 0.5 + k1 * 2.5
  ar1   reson anz, ifq, ifq / (8 + k2 * 90), 2
  ar2   reson anz, ifq * (1.7 + k3 * 3), ifq / (10 + k2 * 60), 2
  ar3   reson anz, ifq * (3.1 + k3 * 5), ifq / (12 + k2 * 40), 2
  agen  = (ar1 + ar2 * 0.6 + ar3 * 0.4) * (0.3 + k4 * 0.7)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2420
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 32   ; RESBANK -> CRUSH
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

  ; Noise through a bank of sharp resonators: pitched by the filters, not by an oscillator.
  anz   PhNoise 1, 0.5 + k1 * 2.5
  ar1   reson anz, ifq, ifq / (8 + k2 * 90), 2
  ar2   reson anz, ifq * (1.7 + k3 * 3), ifq / (10 + k2 * 60), 2
  ar3   reson anz, ifq * (3.1 + k3 * 5), ifq / (12 + k2 * 40), 2
  agen  = (ar1 + ar2 * 0.6 + ar3 * 0.4) * (0.3 + k4 * 0.7)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2080
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 33   ; DUSTRES -> BODY
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

  ; Sparse impulses ringing a string resonator — clicks that become pitch as density rises.
  adst  dust2 0.7, 4 + k1 * 300
  agen  streson adst, ifq, 0.5 + k2 * 0.49
  agen  = agen * (0.3 + k3 * 0.6) + adst * k4 * 0.3

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4648
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 34   ; DUSTRES -> SMEAR
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

  ; Sparse impulses ringing a string resonator — clicks that become pitch as density rises.
  adst  dust2 0.7, 4 + k1 * 300
  agen  streson adst, ifq, 0.5 + k2 * 0.49
  agen  = agen * (0.3 + k3 * 0.6) + adst * k4 * 0.3

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 8.2574
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 35   ; DUSTRES -> SHIFT
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

  ; Sparse impulses ringing a string resonator — clicks that become pitch as density rises.
  adst  dust2 0.7, 4 + k1 * 300
  agen  streson adst, ifq, 0.5 + k2 * 0.49
  agen  = agen * (0.3 + k3 * 0.6) + adst * k4 * 0.3

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 36   ; DUSTRES -> CRUSH
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

  ; Sparse impulses ringing a string resonator — clicks that become pitch as density rises.
  adst  dust2 0.7, 4 + k1 * 300
  agen  streson adst, ifq, 0.5 + k2 * 0.49
  agen  = agen * (0.3 + k3 * 0.6) + adst * k4 * 0.3

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2823
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 37   ; VOSIM -> BODY
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

  ; VOSIM: a train of squared-sine pulses. Vocal and percussive at once, and unmistakably
  ; digital in a way no filter sweep imitates.
  agen  vosim 0.6, ifq, ifq * (2 + k1 * 18), k2 * 0.9, 1 + int(k3 * 12), 0.4 + k4, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4118
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 38   ; VOSIM -> SMEAR
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

  ; VOSIM: a train of squared-sine pulses. Vocal and percussive at once, and unmistakably
  ; digital in a way no filter sweep imitates.
  agen  vosim 0.6, ifq, ifq * (2 + k1 * 18), k2 * 0.9, 1 + int(k3 * 12), 0.4 + k4, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3401
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 39   ; VOSIM -> SHIFT
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

  ; VOSIM: a train of squared-sine pulses. Vocal and percussive at once, and unmistakably
  ; digital in a way no filter sweep imitates.
  agen  vosim 0.6, ifq, ifq * (2 + k1 * 18), k2 * 0.9, 1 + int(k3 * 12), 0.4 + k4, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3070
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 40   ; VOSIM -> CRUSH
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

  ; VOSIM: a train of squared-sine pulses. Vocal and percussive at once, and unmistakably
  ; digital in a way no filter sweep imitates.
  agen  vosim 0.6, ifq, ifq * (2 + k1 * 18), k2 * 0.9, 1 + int(k3 * 12), 0.4 + k4, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2657
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 41   ; FOF2 -> BODY
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

  ; Granular formant synthesis: a fundamental with a formant riding on it, the classic
  ; route to voice-like and insect-like tones from the same three numbers.
  agen  fof2 0.7, ifq, ifq * (1 + k1 * 8), 0, 40 + k2 * 900, 0.003, 0.02 + k3 * 0.1, 0.007, 20, giSine, giGrEnv, 3600, 0, k4

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3256
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 42   ; FOF2 -> SMEAR
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

  ; Granular formant synthesis: a fundamental with a formant riding on it, the classic
  ; route to voice-like and insect-like tones from the same three numbers.
  agen  fof2 0.7, ifq, ifq * (1 + k1 * 8), 0, 40 + k2 * 900, 0.003, 0.02 + k3 * 0.1, 0.007, 20, giSine, giGrEnv, 3600, 0, k4

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3864
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 43   ; FOF2 -> SHIFT
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

  ; Granular formant synthesis: a fundamental with a formant riding on it, the classic
  ; route to voice-like and insect-like tones from the same three numbers.
  agen  fof2 0.7, ifq, ifq * (1 + k1 * 8), 0, 40 + k2 * 900, 0.003, 0.02 + k3 * 0.1, 0.007, 20, giSine, giGrEnv, 3600, 0, k4

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2263
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 44   ; FOF2 -> CRUSH
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

  ; Granular formant synthesis: a fundamental with a formant riding on it, the classic
  ; route to voice-like and insect-like tones from the same three numbers.
  agen  fof2 0.7, ifq, ifq * (1 + k1 * 8), 0, 40 + k2 * 900, 0.003, 0.02 + k3 * 0.1, 0.007, 20, giSine, giGrEnv, 3600, 0, k4

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2351
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 45   ; FMVOICE -> BODY
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

  agen  fmvoice 0.6, ifq, int(k1 * 63), k2 * 2, 0.1 + k3 * 0.9, 0.1 + k4 * 0.9, giSine, giSine, giSine, giSine, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 10.4357
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 46   ; FMVOICE -> SMEAR
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

  agen  fmvoice 0.6, ifq, int(k1 * 63), k2 * 2, 0.1 + k3 * 0.9, 0.1 + k4 * 0.9, giSine, giSine, giSine, giSine, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 6.1633
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 47   ; FMVOICE -> SHIFT
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

  agen  fmvoice 0.6, ifq, int(k1 * 63), k2 * 2, 0.1 + k3 * 0.9, 0.1 + k4 * 0.9, giSine, giSine, giSine, giSine, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 7.7865
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 48   ; FMVOICE -> CRUSH
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

  agen  fmvoice 0.6, ifq, int(k1 * 63), k2 * 2, 0.1 + k3 * 0.9, 0.1 + k4 * 0.9, giSine, giSine, giSine, giSine, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2559
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 49   ; HSB -> BODY
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

  ; Harmonic-stretch oscillator: partials pulled off the harmonic series by a ratio, which
  ; is how a bell stops sounding like an organ.
  agen  hsboscil 0.6, k1 * 4 - 2, k2 * 3, ifq, giSine, giSine, 3 + int(p9 * 5)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4130
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 50   ; HSB -> SMEAR
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

  ; Harmonic-stretch oscillator: partials pulled off the harmonic series by a ratio, which
  ; is how a bell stops sounding like an organ.
  agen  hsboscil 0.6, k1 * 4 - 2, k2 * 3, ifq, giSine, giSine, 3 + int(p9 * 5)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2382
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 51   ; HSB -> SHIFT
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

  ; Harmonic-stretch oscillator: partials pulled off the harmonic series by a ratio, which
  ; is how a bell stops sounding like an organ.
  agen  hsboscil 0.6, k1 * 4 - 2, k2 * 3, ifq, giSine, giSine, 3 + int(p9 * 5)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3472
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 52   ; HSB -> CRUSH
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

  ; Harmonic-stretch oscillator: partials pulled off the harmonic series by a ratio, which
  ; is how a bell stops sounding like an organ.
  agen  hsboscil 0.6, k1 * 4 - 2, k2 * 3, ifq, giSine, giSine, 3 + int(p9 * 5)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2415
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 53   ; CROSSPM -> BODY
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

  ; Two oscillators phase-modulating EACH OTHER. The feedback makes the spectrum move on
  ; its own rather than following an index envelope.
  kf1   = ifq
  kf2   = ifq * (1 + k1 * 4)
  a1, a2 crosspm kf1, kf2, k2 * 6, k3 * 6, 1 + k4 * 8, giSine, giSine
  agen  = (a1 * 0.6 + a2 * 0.4) * 0.7

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1820
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 54   ; CROSSPM -> SMEAR
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

  ; Two oscillators phase-modulating EACH OTHER. The feedback makes the spectrum move on
  ; its own rather than following an index envelope.
  kf1   = ifq
  kf2   = ifq * (1 + k1 * 4)
  a1, a2 crosspm kf1, kf2, k2 * 6, k3 * 6, 1 + k4 * 8, giSine, giSine
  agen  = (a1 * 0.6 + a2 * 0.4) * 0.7

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1200
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 55   ; CROSSPM -> SHIFT
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

  ; Two oscillators phase-modulating EACH OTHER. The feedback makes the spectrum move on
  ; its own rather than following an index envelope.
  kf1   = ifq
  kf2   = ifq * (1 + k1 * 4)
  a1, a2 crosspm kf1, kf2, k2 * 6, k3 * 6, 1 + k4 * 8, giSine, giSine
  agen  = (a1 * 0.6 + a2 * 0.4) * 0.7

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.1821
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 56   ; CROSSPM -> CRUSH
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

  ; Two oscillators phase-modulating EACH OTHER. The feedback makes the spectrum move on
  ; its own rather than following an index envelope.
  kf1   = ifq
  kf2   = ifq * (1 + k1 * 4)
  a1, a2 crosspm kf1, kf2, k2 * 6, k3 * 6, 1 + k4 * 8, giSine, giSine
  agen  = (a1 * 0.6 + a2 * 0.4) * 0.7

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1927
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 57   ; FMMETAL -> BODY
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

  agen  fmmetal 0.55, ifq, k1 * 3, k2 * 5, 0.1 + k3 * 4, 1 + k4 * 8, giSine, giSine, giSine, giSine, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1462
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 58   ; FMMETAL -> SMEAR
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

  agen  fmmetal 0.55, ifq, k1 * 3, k2 * 5, 0.1 + k3 * 4, 1 + k4 * 8, giSine, giSine, giSine, giSine, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.7825
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 59   ; FMMETAL -> SHIFT
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

  agen  fmmetal 0.55, ifq, k1 * 3, k2 * 5, 0.1 + k3 * 4, 1 + k4 * 8, giSine, giSine, giSine, giSine, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.2503
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 60   ; FMMETAL -> CRUSH
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

  agen  fmmetal 0.55, ifq, k1 * 3, k2 * 5, 0.1 + k3 * 4, 1 + k4 * 8, giSine, giSine, giSine, giSine, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1861
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 61   ; FMBELL -> BODY
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

  agen  fmbell 0.5, ifq, k1 * 3, k2 * 4, 0.5 + k3 * 4, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine, 0

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1566
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 62   ; FMBELL -> SMEAR
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

  agen  fmbell 0.5, ifq, k1 * 3, k2 * 4, 0.5 + k3 * 4, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine, 0

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.8359
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 63   ; FMBELL -> SHIFT
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

  agen  fmbell 0.5, ifq, k1 * 3, k2 * 4, 0.5 + k3 * 4, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine, 0

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.8003
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 64   ; FMBELL -> CRUSH
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

  agen  fmbell 0.5, ifq, k1 * 3, k2 * 4, 0.5 + k3 * 4, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine, 0

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4115
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 65   ; FMPERC -> BODY
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

  agen  fmpercfl 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 7, giSine, giSine, giSine, giSine, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.6020
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 66   ; FMPERC -> SMEAR
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

  agen  fmpercfl 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 7, giSine, giSine, giSine, giSine, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.0992
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 67   ; FMPERC -> SHIFT
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

  agen  fmpercfl 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 7, giSine, giSine, giSine, giSine, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.8139
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 68   ; FMPERC -> CRUSH
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

  agen  fmpercfl 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 7, giSine, giSine, giSine, giSine, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2366
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 69   ; FMRHOD -> BODY
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

  agen  fmrhode 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0466
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 70   ; FMRHOD -> SMEAR
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

  agen  fmrhode 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3218
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 71   ; FMRHOD -> SHIFT
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

  agen  fmrhode 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.9829
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 72   ; FMRHOD -> CRUSH
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

  agen  fmrhode 0.55, ifq, k1 * 3, k2 * 4, 0.2 + k3 * 3, 1 + k4 * 6, giSine, giSine, giSine, giSine, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2011
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 73   ; CHAOSFM -> BODY
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

  ; Feedback FM taken past the point of stability: harmonic, then period-doubled, then
  ; genuinely chaotic — noise that still tracks pitch.
  aexc  poscil k4 * 0.3, ifq * (0.25 + k1 * 2), giSine
  agen  PhChaos aexc, ifq, 0.2 + k2 * 3.2
  agen  = agen * (0.4 + k3 * 0.5)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4138
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 74   ; CHAOSFM -> SMEAR
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

  ; Feedback FM taken past the point of stability: harmonic, then period-doubled, then
  ; genuinely chaotic — noise that still tracks pitch.
  aexc  poscil k4 * 0.3, ifq * (0.25 + k1 * 2), giSine
  agen  PhChaos aexc, ifq, 0.2 + k2 * 3.2
  agen  = agen * (0.4 + k3 * 0.5)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1709
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 75   ; CHAOSFM -> SHIFT
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

  ; Feedback FM taken past the point of stability: harmonic, then period-doubled, then
  ; genuinely chaotic — noise that still tracks pitch.
  aexc  poscil k4 * 0.3, ifq * (0.25 + k1 * 2), giSine
  agen  PhChaos aexc, ifq, 0.2 + k2 * 3.2
  agen  = agen * (0.4 + k3 * 0.5)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4747
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 76   ; CHAOSFM -> CRUSH
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

  ; Feedback FM taken past the point of stability: harmonic, then period-doubled, then
  ; genuinely chaotic — noise that still tracks pitch.
  aexc  poscil k4 * 0.3, ifq * (0.25 + k1 * 2), giSine
  agen  PhChaos aexc, ifq, 0.2 + k2 * 3.2
  agen  = agen * (0.4 + k3 * 0.5)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1477
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 77   ; WGBOW -> BODY
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

  agen  wgbow 0.6, ifq, 0.5 + k1 * 5, 0.05 + k2 * 0.85, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.3634
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 78   ; WGBOW -> SMEAR
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

  agen  wgbow 0.6, ifq, 0.5 + k1 * 5, 0.05 + k2 * 0.85, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.2034
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 79   ; WGBOW -> SHIFT
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

  agen  wgbow 0.6, ifq, 0.5 + k1 * 5, 0.05 + k2 * 0.85, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.9165
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 80   ; WGBOW -> CRUSH
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

  agen  wgbow 0.6, ifq, 0.5 + k1 * 5, 0.05 + k2 * 0.85, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2105
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 81   ; WGFLUTE -> BODY
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

  agen  wgflute 0.6, ifq, 0.05 + k1 * 0.7, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.8618
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 82   ; WGFLUTE -> SMEAR
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

  agen  wgflute 0.6, ifq, 0.05 + k1 * 0.7, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.1948
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 83   ; WGFLUTE -> SHIFT
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

  agen  wgflute 0.6, ifq, 0.05 + k1 * 0.7, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.6048
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 84   ; WGFLUTE -> CRUSH
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

  agen  wgflute 0.6, ifq, 0.05 + k1 * 0.7, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2370
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 85   ; WGBRASS -> BODY
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

  agen  wgbrass 0.7, ifq, 0.55 + k1 * 0.9, 0.02, 0.5 + k2 * 8, k3 * 0.25, giSine
  agen  = agen * (0.5 + k4 * 0.5)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 86   ; WGBRASS -> SMEAR
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

  agen  wgbrass 0.7, ifq, 0.55 + k1 * 0.9, 0.02, 0.5 + k2 * 8, k3 * 0.25, giSine
  agen  = agen * (0.5 + k4 * 0.5)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 87   ; WGBRASS -> SHIFT
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

  agen  wgbrass 0.7, ifq, 0.55 + k1 * 0.9, 0.02, 0.5 + k2 * 8, k3 * 0.25, giSine
  agen  = agen * (0.5 + k4 * 0.5)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 88   ; WGBRASS -> CRUSH
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

  agen  wgbrass 0.7, ifq, 0.55 + k1 * 0.9, 0.02, 0.5 + k2 * 8, k3 * 0.25, giSine
  agen  = agen * (0.5 + k4 * 0.5)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1634
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 89   ; WGCLAR -> BODY
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

  agen  wgclar 0.6, ifq, 0.1 + k1 * 0.8, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.4643
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 90   ; WGCLAR -> SMEAR
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

  agen  wgclar 0.6, ifq, 0.1 + k1 * 0.8, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.3886
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 91   ; WGCLAR -> SHIFT
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

  agen  wgclar 0.6, ifq, 0.1 + k1 * 0.8, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 8.3344
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 92   ; WGCLAR -> CRUSH
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

  agen  wgclar 0.6, ifq, 0.1 + k1 * 0.8, 0.02, 0.1, 0.2 + k2 * 0.7, 0.5 + k3 * 8, k4 * 0.3, giSine

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2651
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 93   ; WGPLUCK -> BODY
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

  ; A stiff string: the inharmonicity of real wire, which is what a plucked sample has and
  ; a Karplus-Strong loop does not.
  agen  wgpluck2 0.05 + p7 * 0.9, 0.7, ifq, k2 * 0.9, 0.05 + k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.6)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3364
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 94   ; WGPLUCK -> SMEAR
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

  ; A stiff string: the inharmonicity of real wire, which is what a plucked sample has and
  ; a Karplus-Strong loop does not.
  agen  wgpluck2 0.05 + p7 * 0.9, 0.7, ifq, k2 * 0.9, 0.05 + k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.6)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.9762
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 95   ; WGPLUCK -> SHIFT
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

  ; A stiff string: the inharmonicity of real wire, which is what a plucked sample has and
  ; a Karplus-Strong loop does not.
  agen  wgpluck2 0.05 + p7 * 0.9, 0.7, ifq, k2 * 0.9, 0.05 + k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.6)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.3915
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 96   ; WGPLUCK -> CRUSH
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

  ; A stiff string: the inharmonicity of real wire, which is what a plucked sample has and
  ; a Karplus-Strong loop does not.
  agen  wgpluck2 0.05 + p7 * 0.9, 0.7, ifq, k2 * 0.9, 0.05 + k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.6)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2963
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 97   ; WGUIDE2 -> BODY
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

  ; Two coupled waveguides struck by an impulse: a metal bar or plate with two resonant
  ; paths beating against each other.
  ; (This slot held `barmodel` and then `gogobel`. Both compile and both return silence —
  ; gogobel says why: "No table for Agogobell strike". The STK-derived models need external
  ; rawwave excitation tables this Csound cannot find, so they are avoided entirely.)
  aexc  mpulse 0.7, 0
  aexc  =  aexc + dust2(0.2 * k4, 20 + k4 * 400)
  agen  wguide2 aexc, ifq, ifq * (1.4 + k1 * 3), 2000 + k2 * 9000, 1500 + k2 * 7000, 0.7 + k3 * 0.29, 0.7 + k3 * 0.28

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.7999
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 98   ; WGUIDE2 -> SMEAR
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

  ; Two coupled waveguides struck by an impulse: a metal bar or plate with two resonant
  ; paths beating against each other.
  ; (This slot held `barmodel` and then `gogobel`. Both compile and both return silence —
  ; gogobel says why: "No table for Agogobell strike". The STK-derived models need external
  ; rawwave excitation tables this Csound cannot find, so they are avoided entirely.)
  aexc  mpulse 0.7, 0
  aexc  =  aexc + dust2(0.2 * k4, 20 + k4 * 400)
  agen  wguide2 aexc, ifq, ifq * (1.4 + k1 * 3), 2000 + k2 * 9000, 1500 + k2 * 7000, 0.7 + k3 * 0.29, 0.7 + k3 * 0.28

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 99   ; WGUIDE2 -> SHIFT
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

  ; Two coupled waveguides struck by an impulse: a metal bar or plate with two resonant
  ; paths beating against each other.
  ; (This slot held `barmodel` and then `gogobel`. Both compile and both return silence —
  ; gogobel says why: "No table for Agogobell strike". The STK-derived models need external
  ; rawwave excitation tables this Csound cannot find, so they are avoided entirely.)
  aexc  mpulse 0.7, 0
  aexc  =  aexc + dust2(0.2 * k4, 20 + k4 * 400)
  agen  wguide2 aexc, ifq, ifq * (1.4 + k1 * 3), 2000 + k2 * 9000, 1500 + k2 * 7000, 0.7 + k3 * 0.29, 0.7 + k3 * 0.28

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 100   ; WGUIDE2 -> CRUSH
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

  ; Two coupled waveguides struck by an impulse: a metal bar or plate with two resonant
  ; paths beating against each other.
  ; (This slot held `barmodel` and then `gogobel`. Both compile and both return silence —
  ; gogobel says why: "No table for Agogobell strike". The STK-derived models need external
  ; rawwave excitation tables this Csound cannot find, so they are avoided entirely.)
  aexc  mpulse 0.7, 0
  aexc  =  aexc + dust2(0.2 * k4, 20 + k4 * 400)
  agen  wguide2 aexc, ifq, ifq * (1.4 + k1 * 3), 2000 + k2 * 9000, 1500 + k2 * 7000, 0.7 + k3 * 0.29, 0.7 + k3 * 0.28

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 101   ; DRIP -> BODY
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

  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.05 + p9 * 0.35, 0.6, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 6

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4117
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 102   ; DRIP -> SMEAR
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

  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.05 + p9 * 0.35, 0.6, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 6

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.5590
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 103   ; DRIP -> SHIFT
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

  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.05 + p9 * 0.35, 0.6, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 6

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 104   ; DRIP -> CRUSH
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

  agen  dripwater 0.8, 0.01 + p7 * 0.06, 5 + int(p8 * 40), 0.05 + p9 * 0.35, 0.6, ifq, ifq * (1.4 + p10), ifq * 2.3
  agen  = agen * 6

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3215
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 105   ; TAMB -> BODY
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

  agen  tambourine 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.5 + p10), ifq * 2.7

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4117
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 106   ; TAMB -> SMEAR
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

  agen  tambourine 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.5 + p10), ifq * 2.7

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2886
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 107   ; TAMB -> SHIFT
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

  agen  tambourine 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.5 + p10), ifq * 2.7

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4797
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 108   ; TAMB -> CRUSH
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

  agen  tambourine 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.5 + p10), ifq * 2.7

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3387
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 109   ; SLEIGH -> BODY
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

  agen  sleighbells 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.3 + p10), ifq * 2.1

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2593
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 110   ; SLEIGH -> SMEAR
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

  agen  sleighbells 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.3 + p10), ifq * 2.1

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.5170
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 111   ; SLEIGH -> SHIFT
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

  agen  sleighbells 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.3 + p10), ifq * 2.1

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1979
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 112   ; SLEIGH -> CRUSH
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

  agen  sleighbells 0.6, 0.01 + p7 * 0.1, 5 + int(p8 * 40), 0.1 + p9 * 0.8, 0.6, ifq, ifq * (1.3 + p10), ifq * 2.1

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0435
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 113   ; MODEBANK -> BODY
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

  ; An impulse into a bank of `mode` resonators. Gain is normalised against Q, or a high-Q
  ; bank runs hundreds of times over full scale — measured at 470x before this divide.
  aimp  mpulse 1, 0
  iq    = 20
  am1   mode aimp, ifq, 8 + k1 * 400
  am2   mode aimp, ifq * (1.4 + k2 * 3), 8 + k1 * 300
  am3   mode aimp, ifq * (2.1 + k3 * 6), 8 + k1 * 200
  agen  = (am1 + am2 * 0.7 + am3 * 0.5) / (1 + k1 * 8) * (0.4 + k4 * 0.6)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 6.5558
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 114   ; MODEBANK -> SMEAR
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

  ; An impulse into a bank of `mode` resonators. Gain is normalised against Q, or a high-Q
  ; bank runs hundreds of times over full scale — measured at 470x before this divide.
  aimp  mpulse 1, 0
  iq    = 20
  am1   mode aimp, ifq, 8 + k1 * 400
  am2   mode aimp, ifq * (1.4 + k2 * 3), 8 + k1 * 300
  am3   mode aimp, ifq * (2.1 + k3 * 6), 8 + k1 * 200
  agen  = (am1 + am2 * 0.7 + am3 * 0.5) / (1 + k1 * 8) * (0.4 + k4 * 0.6)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 115   ; MODEBANK -> SHIFT
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

  ; An impulse into a bank of `mode` resonators. Gain is normalised against Q, or a high-Q
  ; bank runs hundreds of times over full scale — measured at 470x before this divide.
  aimp  mpulse 1, 0
  iq    = 20
  am1   mode aimp, ifq, 8 + k1 * 400
  am2   mode aimp, ifq * (1.4 + k2 * 3), 8 + k1 * 300
  am3   mode aimp, ifq * (2.1 + k3 * 6), 8 + k1 * 200
  agen  = (am1 + am2 * 0.7 + am3 * 0.5) / (1 + k1 * 8) * (0.4 + k4 * 0.6)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 12.0000
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 116   ; MODEBANK -> CRUSH
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

  ; An impulse into a bank of `mode` resonators. Gain is normalised against Q, or a high-Q
  ; bank runs hundreds of times over full scale — measured at 470x before this divide.
  aimp  mpulse 1, 0
  iq    = 20
  am1   mode aimp, ifq, 8 + k1 * 400
  am2   mode aimp, ifq * (1.4 + k2 * 3), 8 + k1 * 300
  am3   mode aimp, ifq * (2.1 + k3 * 6), 8 + k1 * 200
  agen  = (am1 + am2 * 0.7 + am3 * 0.5) / (1 + k1 * 8) * (0.4 + k4 * 0.6)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.7330
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 117   ; WTERRAIN -> BODY
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

  ; Wave terrain: an orbit traced over a 2-D surface. Small orbit changes rewrite the
  ; spectrum completely, which is exactly the behaviour a macro knob wants.
  agen  wterrain 0.6, ifq, -1 + k1 * 2, -1 + k2 * 2, 0.1 + k3 * 1.9, 0.1 + k4 * 1.9, giSine, giBell

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2990
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 118   ; WTERRAIN -> SMEAR
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

  ; Wave terrain: an orbit traced over a 2-D surface. Small orbit changes rewrite the
  ; spectrum completely, which is exactly the behaviour a macro knob wants.
  agen  wterrain 0.6, ifq, -1 + k1 * 2, -1 + k2 * 2, 0.1 + k3 * 1.9, 0.1 + k4 * 1.9, giSine, giBell

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4321
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 119   ; WTERRAIN -> SHIFT
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

  ; Wave terrain: an orbit traced over a 2-D surface. Small orbit changes rewrite the
  ; spectrum completely, which is exactly the behaviour a macro knob wants.
  agen  wterrain 0.6, ifq, -1 + k1 * 2, -1 + k2 * 2, 0.1 + k3 * 1.9, 0.1 + k4 * 1.9, giSine, giBell

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.8824
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 120   ; WTERRAIN -> CRUSH
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

  ; Wave terrain: an orbit traced over a 2-D surface. Small orbit changes rewrite the
  ; spectrum completely, which is exactly the behaviour a macro knob wants.
  agen  wterrain 0.6, ifq, -1 + k1 * 2, -1 + k2 * 2, 0.1 + k3 * 1.9, 0.1 + k4 * 1.9, giSine, giBell

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2913
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 121   ; CHEBY -> BODY
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

  ; Distortion synthesis: a sine through a Chebyshev polynomial, so AMPLITUDE controls the
  ; harmonic content. The envelope becomes a spectral envelope for free.
  asin  poscil 0.2 + k1 * 0.8, ifq, giSine
  agen  chebyshevpoly asin, 0, 1 - k2, k2 * 0.8, k3 * 0.7, k3 * 0.4, k4 * 0.5, k4 * 0.3

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3397
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 122   ; CHEBY -> SMEAR
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

  ; Distortion synthesis: a sine through a Chebyshev polynomial, so AMPLITUDE controls the
  ; harmonic content. The envelope becomes a spectral envelope for free.
  asin  poscil 0.2 + k1 * 0.8, ifq, giSine
  agen  chebyshevpoly asin, 0, 1 - k2, k2 * 0.8, k3 * 0.7, k3 * 0.4, k4 * 0.5, k4 * 0.3

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.0832
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 123   ; CHEBY -> SHIFT
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

  ; Distortion synthesis: a sine through a Chebyshev polynomial, so AMPLITUDE controls the
  ; harmonic content. The envelope becomes a spectral envelope for free.
  asin  poscil 0.2 + k1 * 0.8, ifq, giSine
  agen  chebyshevpoly asin, 0, 1 - k2, k2 * 0.8, k3 * 0.7, k3 * 0.4, k4 * 0.5, k4 * 0.3

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.1337
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 124   ; CHEBY -> CRUSH
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

  ; Distortion synthesis: a sine through a Chebyshev polynomial, so AMPLITUDE controls the
  ; harmonic content. The envelope becomes a spectral envelope for free.
  asin  poscil 0.2 + k1 * 0.8, ifq, giSine
  agen  chebyshevpoly asin, 0, 1 - k2, k2 * 0.8, k3 * 0.7, k3 * 0.4, k4 * 0.5, k4 * 0.3

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4024
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 125   ; PDIST -> BODY
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

  ; Phase distortion: read a sine with a warped phasor. Casio's trick, and a cheap route to
  ; hard, resonant, aliasing-prone digital tone.
  aph   phasor ifq
  awrp  = aph ^ (0.25 + k1 * 3.5)
  agen  tablei awrp, giSine, 1, 0, 1
  ares  poscil 1, ifq * (1 + int(k2 * 12)), giSine
  agen  = agen * (1 - k3 * 0.6) + agen * ares * k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.5)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4079
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 126   ; PDIST -> SMEAR
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

  ; Phase distortion: read a sine with a warped phasor. Casio's trick, and a cheap route to
  ; hard, resonant, aliasing-prone digital tone.
  aph   phasor ifq
  awrp  = aph ^ (0.25 + k1 * 3.5)
  agen  tablei awrp, giSine, 1, 0, 1
  ares  poscil 1, ifq * (1 + int(k2 * 12)), giSine
  agen  = agen * (1 - k3 * 0.6) + agen * ares * k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.5)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2957
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 127   ; PDIST -> SHIFT
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

  ; Phase distortion: read a sine with a warped phasor. Casio's trick, and a cheap route to
  ; hard, resonant, aliasing-prone digital tone.
  aph   phasor ifq
  awrp  = aph ^ (0.25 + k1 * 3.5)
  agen  tablei awrp, giSine, 1, 0, 1
  ares  poscil 1, ifq * (1 + int(k2 * 12)), giSine
  agen  = agen * (1 - k3 * 0.6) + agen * ares * k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.5)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4702
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 128   ; PDIST -> CRUSH
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

  ; Phase distortion: read a sine with a warped phasor. Casio's trick, and a cheap route to
  ; hard, resonant, aliasing-prone digital tone.
  aph   phasor ifq
  awrp  = aph ^ (0.25 + k1 * 3.5)
  agen  tablei awrp, giSine, 1, 0, 1
  ares  poscil 1, ifq * (1 + int(k2 * 12)), giSine
  agen  = agen * (1 - k3 * 0.6) + agen * ares * k3 * 0.9
  agen  = agen * (0.4 + k4 * 0.5)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4270
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 129   ; VCO2 -> BODY
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

  ; A band-limited analogue-style pair, detuned. Included as CONTRAST: with everything else
  ; in this file leaning metallic and unstable, one clean harmonic source makes the rest
  ; sound deliberate rather than uniform.
  a1    vco2 0.4, ifq, int(p7 * 3) * 2, 0.5
  a2    vco2 0.4, ifq * (1 + (k2 - 0.5) * 0.03), int(p7 * 3) * 2, 0.5
  agen  = (a1 + a2) * (0.4 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + tanh(agen * (1 + k4 * 8)) * k4 * 0.6

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.1575
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 130   ; VCO2 -> SMEAR
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

  ; A band-limited analogue-style pair, detuned. Included as CONTRAST: with everything else
  ; in this file leaning metallic and unstable, one clean harmonic source makes the rest
  ; sound deliberate rather than uniform.
  a1    vco2 0.4, ifq, int(p7 * 3) * 2, 0.5
  a2    vco2 0.4, ifq * (1 + (k2 - 0.5) * 0.03), int(p7 * 3) * 2, 0.5
  agen  = (a1 + a2) * (0.4 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + tanh(agen * (1 + k4 * 8)) * k4 * 0.6

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2731
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 131   ; VCO2 -> SHIFT
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

  ; A band-limited analogue-style pair, detuned. Included as CONTRAST: with everything else
  ; in this file leaning metallic and unstable, one clean harmonic source makes the rest
  ; sound deliberate rather than uniform.
  a1    vco2 0.4, ifq, int(p7 * 3) * 2, 0.5
  a2    vco2 0.4, ifq * (1 + (k2 - 0.5) * 0.03), int(p7 * 3) * 2, 0.5
  agen  = (a1 + a2) * (0.4 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + tanh(agen * (1 + k4 * 8)) * k4 * 0.6

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 3.4559
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 132   ; VCO2 -> CRUSH
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

  ; A band-limited analogue-style pair, detuned. Included as CONTRAST: with everything else
  ; in this file leaning metallic and unstable, one clean harmonic source makes the rest
  ; sound deliberate rather than uniform.
  a1    vco2 0.4, ifq, int(p7 * 3) * 2, 0.5
  a2    vco2 0.4, ifq * (1 + (k2 - 0.5) * 0.03), int(p7 * 3) * 2, 0.5
  agen  = (a1 + a2) * (0.4 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + tanh(agen * (1 + k4 * 8)) * k4 * 0.6

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2123
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 133   ; SQUINE -> BODY
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

  acps  =  a(ifq)
  aclp  =  a(k1 * 0.95)
  askw  =  a(k2 * 0.95)
  agen, async squinewave acps, aclp, askw
  agen  = agen * (0.35 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + agen * agen * agen * k4 * 0.5

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.7776
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 134   ; SQUINE -> SMEAR
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

  acps  =  a(ifq)
  aclp  =  a(k1 * 0.95)
  askw  =  a(k2 * 0.95)
  agen, async squinewave acps, aclp, askw
  agen  = agen * (0.35 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + agen * agen * agen * k4 * 0.5

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.4213
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 135   ; SQUINE -> SHIFT
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

  acps  =  a(ifq)
  aclp  =  a(k1 * 0.95)
  askw  =  a(k2 * 0.95)
  agen, async squinewave acps, aclp, askw
  agen  = agen * (0.35 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + agen * agen * agen * k4 * 0.5

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.9022
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 136   ; SQUINE -> CRUSH
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

  acps  =  a(ifq)
  aclp  =  a(k1 * 0.95)
  askw  =  a(k2 * 0.95)
  agen, async squinewave acps, aclp, askw
  agen  = agen * (0.35 + k3 * 0.5)
  agen  = agen * (1 - k4 * 0.5) + agen * agen * agen * k4 * 0.5

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.2335
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 137   ; BUZZ -> BODY
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

  ; A band-limited pulse whose partial COUNT is swept — additive brightness with none of
  ; the cost, and it thins to a sine at the bottom.
  agen  gbuzz 0.5, ifq, 1 + int(k1 * 40), int(k2 * 6), 0.2 + k3 * 0.75, giSine
  agen  = agen * (0.4 + k4 * 0.6)

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.9793
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 138   ; BUZZ -> SMEAR
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

  ; A band-limited pulse whose partial COUNT is swept — additive brightness with none of
  ; the cost, and it thins to a sine at the bottom.
  agen  gbuzz 0.5, ifq, 1 + int(k1 * 40), int(k2 * 6), 0.2 + k3 * 0.75, giSine
  agen  = agen * (0.4 + k4 * 0.6)

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.7664
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 139   ; BUZZ -> SHIFT
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

  ; A band-limited pulse whose partial COUNT is swept — additive brightness with none of
  ; the cost, and it thins to a sine at the bottom.
  agen  gbuzz 0.5, ifq, 1 + int(k1 * 40), int(k2 * 6), 0.2 + k3 * 0.75, giSine
  agen  = agen * (0.4 + k4 * 0.6)

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 5.1054
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 140   ; BUZZ -> CRUSH
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

  ; A band-limited pulse whose partial COUNT is swept — additive brightness with none of
  ; the cost, and it thins to a sine at the bottom.
  agen  gbuzz 0.5, ifq, 1 + int(k1 * 40), int(k2 * 6), 0.2 + k3 * 0.75, giSine
  agen  = agen * (0.4 + k4 * 0.6)

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.0888
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 141   ; MINCER -> BODY
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

  ; Read a PADsynth table with an independent pointer: pitch and scan rate come apart, so
  ; the same wavetable can be a drone, a stutter or a smear.
  atim  linseg 0, p3, p3 * (0.1 + p7 * 3)
  agen  mincer atim, 0.6, ifq / 220, giPad, 1, 2048
  agen  = agen * (0.4 + k2 * 0.6)
  agen  = agen * (1 - k3 * 0.5) + agen * poscil(1, ifq * (1 + k4 * 6), giSine) * k3 * 0.7

  ; A resonant body: the feedback delay network used as a physical enclosure, not a reverb.
  abd   = agen * (0.5 + k6 * 0.5)
  adL, adR PhFDN abd * 0.5, 0.004 + k5 * 0.14, 0.2 + k6 * 0.6
  aflt  zdf_2pole agen, 200 + k7 * 9000, 0.7 + k7 * 3, 0
  aL    = aflt * 0.55 + adL * 0.8
  aR    = aflt * 0.55 + adR * 0.8
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 2.9839
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 142   ; MINCER -> SMEAR
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

  ; Read a PADsynth table with an independent pointer: pitch and scan rate come apart, so
  ; the same wavetable can be a drone, a stutter or a smear.
  atim  linseg 0, p3, p3 * (0.1 + p7 * 3)
  agen  mincer atim, 0.6, ifq / 220, giPad, 1, 2048
  agen  = agen * (0.4 + k2 * 0.6)
  agen  = agen * (1 - k3 * 0.5) + agen * poscil(1, ifq * (1 + k4 * 6), giSine) * k3 * 0.7

  ; Streaming phase vocoder: blur the spectrum in TIME, so transients turn into weather.
  fsin  pvsanal agen, 1024, 256, 1024, 1
  fblr  pvsblur fsin, 0.01 + k5 * 0.4, 0.5
  asm   pvsynth fblr
  amix  = agen * (1 - k6) + asm * k6 * 1.4
  aL, aR PhWide amix, 0.2 + k7 * 0.75
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.1088
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 143   ; MINCER -> SHIFT
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

  ; Read a PADsynth table with an independent pointer: pitch and scan rate come apart, so
  ; the same wavetable can be a drone, a stutter or a smear.
  atim  linseg 0, p3, p3 * (0.1 + p7 * 3)
  agen  mincer atim, 0.6, ifq / 220, giPad, 1, 2048
  agen  = agen * (0.4 + k2 * 0.6)
  agen  = agen * (1 - k3 * 0.5) + agen * poscil(1, ifq * (1 + k4 * 6), giSine) * k3 * 0.7

  ; Frequency shifting — not pitch shifting. Every partial moves by the SAME number of hertz,
  ; so a harmonic spectrum becomes inharmonic and metallic in one operation.
  areal, aimag hilbert agen
  ksh   = -400 + k5 * 800
  acos  poscil 1, ksh, giSine, 0.25
  asin2 poscil 1, ksh, giSine, 0
  ashf  = areal * acos - aimag * asin2
  amix  = agen * (1 - k6) + ashf * k6
  alad  moogladder amix, 600 + k7 * 11000, k7 * 0.6
  aL, aR PhWide alad, 0.3 + k7 * 0.5
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 4.5733
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin


instr 144   ; MINCER -> CRUSH
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

  ; Read a PADsynth table with an independent pointer: pitch and scan rate come apart, so
  ; the same wavetable can be a drone, a stutter or a smear.
  atim  linseg 0, p3, p3 * (0.1 + p7 * 3)
  agen  mincer atim, 0.6, ifq / 220, giPad, 1, 2048
  agen  = agen * (0.4 + k2 * 0.6)
  agen  = agen * (1 - k3 * 0.5) + agen * poscil(1, ifq * (1 + k4 * 6), giSine) * k3 * 0.7

  ; Deliberate digital damage: fold, quantise, decimate, then comb. Bounded so it stays a
  ; timbre rather than a fault.
  afld  = tanh(agen * (1 + k5 * 12)) * 0.8
  kstep = 1 / (2 ^ (4 + (1 - k6) * 11))
  iboost = 32
  aqnt  = (int(afld * iboost / kstep) * kstep) / iboost
  adwn  = k6 > 0.5 ? aqnt : afld
  acmb  vdelay3 adwn, 0.3 + k7 * 12, 40
  amix  = adwn * 0.7 + acmb * k7 * 0.7
  aL, aR PhWide amix, 0.25 + k7 * 0.6
  aL     = aL * kenv
  aR     = aR * kenv
  iTrim  = 1.3645
  PhOut aL * iTrim, aR * iTrim, itrack, ichan
endin

; <<< GENERATED ARCHITECTURE MATRIX END >>>
