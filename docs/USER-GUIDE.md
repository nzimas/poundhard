<p align="center">
  <img src="../web/poundhard-logo.svg" alt="PoundHard" width="480">
</p>

# PoundHard — User Guide

**A tutorial and a manual.** Part 1 walks you from an empty machine to a track that
plays itself, in about twenty minutes at the device. Everything after it is reference:
every view, every control, every engine, every modifier.

If you have never used PoundHard, start at [Your first pattern](#part-1--your-first-pattern)
and do it at the machine rather than reading it through. If you are looking something up,
the [manual contents](#part-2--the-manual) is below it.

> **One thing to know before you start.** Almost nothing in PoundHard is modal in the way a
> DAW is. Tracks hold a sound *and* a sequence; patterns hold the whole rig including which
> engines are on which tracks; and the performance modifiers never edit anything — they are
> overlays the engine plays *instead*, so switching one off gives you back exactly what you
> programmed. You can hold a pad down and turn a knob almost anywhere and something useful
> will happen.

---

## Contents

**[Part 1 — Your first pattern](#part-1--your-first-pattern)** *(the tutorial)*

1. [Get sound out of it](#1-get-sound-out-of-it)
2. [Build a rig](#2-build-a-rig)
3. [Write a sequence](#3-write-a-sequence)
4. [Make a step interesting](#4-make-a-step-interesting)
5. [Let the machine write](#5-let-the-machine-write)
6. [Make it move on its own](#6-make-it-move-on-its-own)
7. [Perform it](#7-perform-it)
8. [Keep it](#8-keep-it)

**[Part 2 — The manual](#part-2--the-manual)** *(reference)*

- [The six views, and how to move between them](#the-six-views)
- [Sound engines](#sound-engines) — all twenty, what each is for
- [Controls](#controls) — every view, every gesture
- [Sounds & the engine palette](#sounds--the-engine-palette)
- [Patterns & projects](#patterns--projects)
- [Pattern generation](#randomise-a-whole-pattern) — the eighteen recipes
- [Performance modifiers](#quake) — HEAT, SHUFFLE, QUAKE, CHURN, BREAK, STROBE
- [Modulation](#modulation-view) — the 32-LFO bank
- [Living steps & HEAT](#living-steps--the-heat-button)

---

# Part 1 — Your first pattern

Work through this at the machine. Each step takes a minute or two and leaves you with
something audible.

## 1. Get sound out of it

Power on, open **Schwung → overtake → PoundHard**, and wait for the screen to stop saying
`starting…`. The engine boots its own SuperCollider and JACK, which takes a few seconds.

You are now in the **tracks view** — the default. The top two rows of pads are the
**engine palette**; the sixteen **step buttons** down the side are your sixteen tracks.

Everything starts empty. Nothing will make a sound yet, which is correct.

**Short-press pad 1** (yellow, `DRUM`). You hear a drum sound — that is an *audition*.
It plays the palette's current sound for that engine without assigning it anywhere.

**Shift + pad 1** re-rolls it. Do that a few times. Every press generates a genuinely new
drum sound, not a preset.

## 2. Build a rig

A track needs an engine before it can do anything.

**Hold pad 1 and tap step button 1.** That assigns DRUM — and the exact sound you were
auditioning — to track 1. Step button 1 now glows in the engine's colour.

Do it three more times, so you have something to work with:

| Hold this pad | Tap this track | You get |
|---|---|---|
| Pad 1 `DRUM` | Track 1 | a drum |
| Pad 5 `RINGS` | Track 2 | a resonator |
| Pad 7 `NOIZEOP` | Track 3 | glitch noise |
| Pad 9 `PLAITS` | Track 4 | a macro-oscillator |

Audition and re-roll (**Shift + pad**) before you assign, until you like what you hear.
Assigning to a track that already has a sequence **keeps the sequence** — only the sound
changes, so you can swap engines under a part you have already written.

## 3. Write a sequence

**Hold step button 1** for a moment. That opens the **edit view** for track 1, and the 32
pads become its step grid.

**Tap pads** to place hits. Try 1, 5, 9 and 13 — four on the floor, as a starting point you
will immediately want to ruin.

**Press Play.** It runs.

While it plays, **hold a step pad and turn knob 1** — that step's pitch. Knob 2 is its
velocity, knob 3 its pan. These are **per-step locks**: one step can be quieter, lower and
further left than its neighbours, and nothing else in the sequence is touched.

**Press Track 1** to get back to the tracks view when you are done.

## 4. Make a step interesting

Still in the edit view for a track, with it playing:

- **Hold a step + knob 4** sets how often that step *fires* — every play, or every 2nd,
  3rd… 8th repetition. A sequence with two or three of these stops being a loop.
- **Rec + a step pad** marks it as a **living step**. A living step re-rolls its own
  character — timbre, filter, pitch leap, pan throw, ratchet, delay send — every few
  repetitions, on its own. Mark two or three, not ten.
- **Shift + touch a knob** turns on a **per-parameter step randomizer**: that one
  parameter animates across the sequence while everything else holds still.

## 5. Let the machine write

You do not have to program anything.

**Shift + hold the volume knob + Track 3** generates an entire pattern — engines, sounds,
sequences, lengths, clock rates, velocities, pan, register, effects and tempo — built to one
of **eighteen compositional recipes**. Each recipe is a brief with a real identity: `SPARSE`
is mostly silence, `WALL` is power noise with no air in it, `POLYMETER` runs tracks of
different lengths against each other, `PROCESSION` is slow and ceremonial.

Press it a few times. It generates several candidates internally, scores them against the
ways patterns go wrong, repairs the weakest track and gives you the best one — so most
presses land somewhere usable.

**Shift + hold the volume knob + Track 1** does the same for the *open track only*: a new
sequence in the project's scale, leaving everything else alone.

## 6. Make it move on its own

**Press Track 4** for the **modulation view**. Thirty-two pads, each one an LFO that the
machine has already assigned to a parameter for you — you never route anything.

- Pads 1–16 are **sample-and-hold** (stepped, irregular) in amber.
- Pads 17–32 are **sine** (smooth) in cyan.
- Dim = assigned and idle. Bright = running. Dark = no target available.

**Tap a few.** Every LFO is locked to the pattern tempo, no two ever share a parameter, and
engine *pitch* is deliberately never a target. Tapping a lit pad switches it off and the
parameter returns instantly to what you programmed — nothing is overwritten, ever.

**Shift + Track 4** re-rolls the whole bank against the current project.

## 7. Perform it

The bottom row of pads holds **six modifiers**. None of them edits your pattern; each is an
overlay the engine plays instead.

| Modifier | What it does |
|---|---|
| **HEAT** | makes a proportion of every sequenced hit *living* at once |
| **SHUFFLE** | re-orders steps |
| **QUAKE** | rhythmic destruction — waits for a musical seam before it engages |
| **CHURN** | recycles recorded audio back into the mix |
| **BREAK** | drops and re-enters |
| **STROBE** | tempo-synced gating and microlooping across the mix |

Switch them on, switch them off. Your sequence is exactly as you left it.

**QUAKE is worth understanding**: press its pad and it changes colour but nothing happens
yet — it is *armed*. It waits for a phrase boundary the music can absorb, then starts, and
blinks while it is taking effect. Press again and it leaves at the next seam. This is the
only modifier that waits.

**Cursor up/down** transposes every track together in semitones. **Cursor left/right** sets
the open track's clock rate.

## 8. Keep it

- **Track 3** opens the **pattern view** — 32 slots. **Shift + pad** saves the current
  pattern to that slot, **pad** loads one. Patterns are self-contained: engines, sounds,
  sequences, effects and mutes all travel.
- **Menu** opens the **project view**, which saves to disk.
- There is an **autosave** running regardless. **Shift + Menu** in the project view restores
  it, which is what you want after a crash or an accidental overwrite.

That is the whole instrument in outline. Everything below is the detail.

---

# Part 2 — The manual

## The six views

PoundHard has six views. Exactly one is ever open, and one button always gets you back.

| Button | Opens | Press again |
|---|---|---|
| **Track 1** | *(returns to the tracks view from anywhere)* | — |
| **Track 2** | FX view | back to tracks |
| **Track 3** | Pattern view *(Shift: recorder)* | back to tracks |
| **Track 4** | Modulation view | back to tracks |
| **Menu** | Project view | back to tracks |
| *hold a step button* | Edit view for that track | Track 1 to leave |

**Track 1 always returns to the tracks view**, from any view, at any time. Pressing a view's
own button a second time also returns. Pressing a *different* view's button goes straight
there — you never have to back out first.

---

## Sound engines

Most voices are **spawned per hit and self-free** (see [voice model](../README.md#voice-model)).
**BYTEBEAT** and **CSOUND** are the two exceptions and keep one persistent voice per
track — for reasons particular to each, explained there.

- **DRUM** — a full digital drum voice with 7 modes (kick / snare / hihat /
  metal / clap / tom / noise); generating a drum sound rolls the mode and pitches it
  to suit.
- **FM7** — a real **6-operator FM** voice (the `FM7` UGen from sc3-plugins). Six
  operators, each tuned to a ratio of the note, wired through one of **6 modulation
  topologies** (`algo`): three parallel 2-op stacks (e-piano/bell), a 6-op chain
  (metallic clang), a 4-carrier additive organ, a carrier+modulator+sub (FM bass), a
  3-modulator inharmonic bell cluster, and two stacked branches (brass stab). A
  modulator-index envelope makes the tone brighten then dull — classic FM movement.
  The generator picks an algorithm first, then targets its six operator ratios + index +
  feedback to that role (see `kits._FM7_SPEC`), so it never rolls the operators blind.
- **BUCHLOID** — Buchla-flavoured complex-oscillator/wavefolder voice for
  drones and noise textures.
- **MOLLY** — a Moog-ladder (`MoogFF`) subtractive synth, built for **grit** rather
  than politeness: oscillator cross-FM, a pre-filter **wavefolder**, an asymmetric
  (biased) drive stage, **bit-crush + sample-rate reduction**, and a crackle/dust
  layer. Leads and pads that corrode.
- **RINGS** — **Mutable Instruments Rings** (`MiRings`, from mi-UGens) modal /
  sympathetic-string resonator; one strike per step, summed to mono then panned.
- **BEN** — a **Benjolin** (Rob Hordijk), following the signal flow of the
  [Benjolis](https://github.com/scazan/benjolis) SC engine (after Alberto de Campo).
  Two oscillators feed a **rungler**: an 8-stage shift register clocked by osc 2 and
  fed by osc 1's comparator. Its weighted 8-bit DAC is scaled to a MIDI value and run
  through `.midicps`, yielding a *frequency* that is **added** to both oscillator
  frequencies and to the filter cutoff. That additive, `midicps`-scaled feedback (not
  exponential modulation) is what produces the stepped, self-patterning chaos — a
  generative machine rather than a note-player.

  Osc 2 is usually **sub-audio** (a few Hz): it clocks the register, so it sets the
  pace of the stepped sequences. Four filter types (LP / HP / SVF / DFM1) and seven
  output taps (tri1 · osc1 · tri2 · osc2 · pwm · sh0 · filter) are selectable, and the
  kit role rolls all of them.
- **NOIZEOP** — a faithful port of deeg's
  [NoizeOp](https://github.com/deeg-deeg-deeg/noizeop) Norns engine. **Four sine
  oscillators** are combined through **six nonlinear "algorithms"** (products, ratios,
  a truncation/quantizer, a hypotenuse, and a sum-of-squares), mixed by per-algorithm
  weight, then run through a **hipass → lowpass → resonz** filter bank. The ratios
  divide through zero constantly, so the output is spiky, glitchy, rhythmic noise —
  that *is* the instrument. The only adaptation for PoundHard: the four oscillator
  frequencies are **note-relative ratios** (so the sequencer transposes the whole
  cluster while keeping the ratios that give it its character), and a per-hit amp
  envelope replaces the original's continuous drone. Denominators carry a tiny bias
  and the operators are magnitude-clamped, so the spikes survive but infinities and
  NaNs never reach the DAC. All core UGens — no plugin dependency.
- **ICARUS** — a faithful port of schollz's
  [Icarus](https://github.com/schollz/icarus) Norns engine, a "dreamcrusher" drone/pad.
  A **VarSaw** main oscillator and a **Pulse** sub, both with LFO-modulated pulse-width
  and slow randomized detune, feed a **feedback delay network** (OnePole tilt → Rotate2 →
  DelayC → softclip), a **MoogLadder** low-pass, and a Dust-gated "destruction" dropout.
  Excellent for evolving drones and pads. Adaptation for the spawn-per-hit model: the
  original is gate-driven; here the note fires a one-shot cubic AR envelope whose length
  is set by attack/decay/release (long values give sustained pads), and the voice
  self-frees. Needs **MoogLadder** (BhobUGens, from sc3-plugins).

- **PLAITS** — **Mutable Instruments Plaits**, the real **`MiPlaits`** UGen from
  [v7b1/mi-UGens](https://github.com/v7b1/mi-UGens) — the actual ported DSP, same plugin
  family as RINGS, not a reconstruction. A **16-model macro-oscillator** spanning the
  whole instrument: virtual-analog, waveshaping, 2-op FM, granular formant, additive,
  wavetable, chords, **speech**, granular cloud, filtered noise, particle noise,
  inharmonic string, modal resonator, and analog **bass drum / snare / hi-hat**.

  **Plaits is a MODULE, and held still it is only half of one.** Its three macros mean
  different things in every engine, and on hardware nobody sets timbre and morph and then
  leaves them there — they are patched to envelopes and LFOs, and that movement is most of
  what the thing sounds like. Every voice now gets a **per-note contour** and **two
  uncorrelated slow drifts** on `harm`/`timbre`/`morph`, plus the three modulation CVs the
  UGen has and this synthdef previously left at zero (`fm_mod`, `timb_mod`, `morph_mod`).
  The contour's shape is signed: a fast fall for a pluck's timbre collapsing, a slow swell
  for a pad opening.

  **The movement is specified per model**, because sweeping `timbre` on the waveshaper is a
  fold opening, on the speech model a formant shift, and on the hi-hat the difference
  between a hat and a cymbal — 113 movement bands across the 16 models. The chord engine's
  `harm` deliberately holds still (moving it arpeggiates); the string and modal engines
  sweep brightness *downward* as struck things do; the drum models get a short downward
  transient and drive for weight.

  A **tone stage** follows: asymmetric soft saturation (`drive`) and a gentle spectral lean
  (`tilt`), both defaulting to zero so a model that wants to stay clean is untouched. A bare
  oscillator is a waveform, not yet a sound.

  The per-step trigger fires Plaits' own envelope and low-pass gate (`decay`,
  `lpgColour`), which is exactly PoundHard's per-hit voice model. Its two outputs are
  **OUT and AUX** — two *different* signals per model, not a stereo pair (the same trap
  that broke RINGS' panning) — so they're blended by an `aux` knob and then panned.

  **Each model is targeted, not randomised.** `model` doesn't merely change the timbre,
  it redefines what the three macro knobs *do*: `harm` is oscillator detune in the VA
  model, chord type in the chord model, grain density in the cloud, and punch in the
  bass drum. So every model has its own role in
  [`kits.py`](../controller/poundhard/kits.py) — the job it does in a kit, the register it
  wants, and bands that suit what those knobs actually control in *that* model. The
  generator reaches for the speech model when it wants a texture and the modal model
  when it wants a mallet; it never rolls the three knobs blind.

  **Levels are normalised per model.** Measured by recording each one: Plaits' models
  differ by ~**16×** in level (`string` peaked at 0.059, `chord`/`noise` at 0.95), so
  the synthdef applies a per-model output trim (now all ≈0.7 peak). Without it a string
  voice would simply vanish under a chord and the mix logic would be meaningless.

- **SHAKER** — **STK Shakers** (`StkShakers`, from sc3-plugins): 23 stochastic
  shaker/scraper physical models — maraca, cabasa, sekere, guiro, water drops, bamboo
  chimes, tambourine, sleigh bells, sand paper, rocks, tuned bamboo. `instr` picks the
  model; energy / system-decay / object-count / resonance shape the gesture. Each hit
  injects a burst of shake energy (enveloped) that decays to one shake, and the note
  tilts the resonance. The generator picks a model first, then targets its parameters to
  that instrument (see `kits._SHAKER_SPEC`). STK's output is quiet, so the voice applies
  a fixed output boost to sit at engine level.
- **MEMBRANE** — a struck **2D-waveguide membrane** (`MembraneCircle`, from sc3-plugins):
  tunable drums, frame drums, warped skins, gongs. A short filtered-noise **strike**
  excites the mesh; `tension` sets the pitch/character and `loss` the ring time — so the
  note tunes the drum along a tom→gong continuum. It frees on silence (the membrane's own
  decay) with a hard time cap, so long gong rings land but nothing leaks. Three targeted
  roles (tom / frame / gong) drive the generator.
- **MALLET** — **STK ModalBar** (`StkModalBar`, from sc3-plugins): struck modal bars —
  marimba, vibraphone, agogo, wood block, reso, beats/bells. Pitched by the note (`freq`
  in Hz); one strike at spawn and a perc amp envelope sets how long it rings (short =
  damped mallet, long = ringing vibraphone). Per-instrument targeting in `kits._MALLET_SPEC`.
- **BOWED** — **STK BandedWG** (`StkBandedWG`, from sc3-plugins): a banded waveguide —
  uniform/tuned bar, glass harmonica, Tibetan bowl. `striking` toggles struck vs bowed, so
  it does both percussive metal and evolving bowed-glass/metal drones. Pitched by the note.
- **PLUCK** — a **digital-waveguide plucked string with stiffness** (`DWGPluckedStiff`,
  from sc3-plugins): inharmonic plucks — koto, clavinet, harp, muted string. A short noise
  burst excites the string; pluck position / decay / damping / brightness shape it. Pitched
  by the note; frees on silence. (Pure waveguide — no rawwaves needed.)
- **TUBE** — a **two-tube waveguide** (`TwoTube`, from sc3-plugins): hollow, vocal-tract-ish
  formant plucks and reedy tones. The tube lengths (set from the note) fix the resonance;
  `balance` splits them and `k` sets the junction. A short burst excites it.
- **CHAOS** — a voice built from SuperCollider's audio-rate **chaos generators** (feedback
  sine + iterated maps: Latoocarfian, Henon, Standard, Cusp). `type` picks the map; the note
  sets the iteration frequency and `chaosA`/`chaosB` steer the attractor from pitched tone to
  full noise, then a wavefolder and resonant filter shape it. Glitch/noise from core UGens —
  no plugin — in the spirit of BEN and NOIZEOP.
- **WTABLE** — a full **SuperCollider rebuild of Ableton's Wavetable** that plays the Move's
  **own factory wavetables** (the *sprites* under `/opt/move/Dsp/Vector/Sprites/` — each a bank
  of single-cycle 1024-sample frames). Two oscillators read a sprite each and **morph** through
  their frames as they play; `wt1`/`wt2` pick the sprites, `pos1`/`pos2` set the start frame,
  and — the signature Wavetable move — a per-hit **position envelope** (`posenv`) plus an LFO
  (`poslfoRate`/`poslfoAmt`) sweep the read position over the note. A **sub oscillator** and
  **noise** thicken it, a **mode-morph filter** (low/band/high-pass) with its own envelope and
  **drive** carve it, and an AR/sustain amp envelope frees the voice. No reverb/delay — those
  are Ableton *devices*, not part of the synth, so PoundHard's own FX chain covers that ground.
  The engine loads each sprite as one buffer on demand and reads it with a `BufRd` 2D-morph
  (interpolating both within a cycle and between adjacent frames); the controller and engine
  sort the sprite list identically so `wt1`/`wt2` select the same wavetable on both sides.
- **BYTEBEAT** — midouest's **ByteBeat UGen** ([github.com/midouest/bytebeat](https://github.com/midouest/bytebeat)),
  a real compiled scsynth plugin (not a reimplementation). Bytebeat synthesis evaluates a single
  integer expression over a sample counter `t` (`t*(t>>5|t>>8)` …) and emits the classic 8-bit
  algorithmic stream. `expr` picks one of the engine's 19 curated expressions — pushed to the
  voice with the plugin's `/eval` unit command right after it spawns (it's a bank index, not a
  synth arg). `rate` is the bytebeat clock — its "sample rate", the master control of pitch,
  speed and lo-fi crunch — and the note scales it (floored so a low note can't go subsonic). A
  lowpass + drive + a real AR envelope shape and free each hit. Glitch/texture, in the
  BEN/NOIZEOP/CHAOS family.

  The voice is **persistent, not spawned per hit** — one per track, plus one for auditions.
  That is forced by the UGen: it parses its expression **per instance** and starts on an
  `Undefined` expression that evaluates to 0, so a freshly spawned instance is *silent* until
  its asynchronous `/eval` lands. Spawning one per note raced the parse against the note —
  long notes won it and screamed, percussive hits were over before it arrived and came out
  inaudible, and re-auditioning "the same" sound built a different instance that usually lost.
  The engine now builds the voice once, parses it once (a few control blocks **after** the
  node is created — a unit command sent in the same instant is delivered to a node the server
  has not instantiated yet and is dropped), and each step just **re-triggers its envelope**.
  Its counter free-runs, which is what bytebeat actually is.

  `origin` is **where in the stream the voice starts**, and it matters more than it sounds like
  it should. A bytebeat expression is a function of a free-running counter, and most of the bank
  is *silent* near `t=0`: `t*(42&t>>10)` emits nothing until `t` passes 1024, `t&t>>8` until 256.
  A voice counting from zero replays the dead head of the stream on every hit — measured
  offline, **7 of the 19 expressions produced not one audible hit in a 16-step bar**. Each
  track starts at its own `origin` and the counter runs on from there, so a pattern walks
  through the expression the way bytebeat is meant to be heard. The bank is also chosen for
  *duty* — the fraction of stream positions a hit can land on and still be heard — with the
  three worst expressions (0.67) replaced; the bank's minimum is now 0.92.

- **SAMPLE** — the **capture engine**, and the only one whose sound you *make* rather than
  generate. **Hold its pad and tap another engine's pad**: that engine auditions, a
  **threshold-gated recorder** captures it (recording begins when the signal actually
  crosses the threshold, so the take starts at the transient, not in the silence before
  it), and the take is then rendered through **Csound** — offline, on the device. The
  result becomes the pad's sound: audition it like any engine, and **hold + tap a track**
  to assign it. Assigning gives that track **its own** copy of the buffer and **releases
  the pad**, so you can immediately capture the next one and build up several tracks each
  playing a different mangled sample. Playback is note-resampled, with filter, drive and
  an AR envelope, and plays a **window** of the buffer — `start` and `end`, live on
  **knobs 4 and 5** of that track's edit view, and lockable **per step** (hold a step and
  use the same two knobs), so one step can trigger the attack and another the tail (PlayBuf has no end point, so the window is
  closed by a hold-then-4ms-fade envelope sized to exactly how long it takes to play at the
  current rate). A **short press** of the pad just triggers the take — only a **hold**
  arms recording.

> **The Csound mangling is a modular opcode graph, not a preset chain.** Every take is
> rendered through a freshly assembled signal path: each stage is a typed module (audio or
> spectral) tagged with a domain, and the builder wires a random chain of 2-4 of them,
> inserting the `pvsanal`/`pvsynth` bridges automatically whenever the chain crosses into
> or out of the spectral domain. Following the reference manual's central rule — *the most
> characteristic results come from chaining unlike domains* — **two consecutive stages
> never share a domain**. 22 stages over five domains: **spectral** (`pvsblur`,
> `pvsfreeze`, `pvscale`, `pvswarp`, `pvshift`, `pvstrace`, `pvsmooth`), **granular**
> (`syncgrain`, `mincer`), **resonant** (inharmonic `mode` banks, `resonx`, `streson`),
> **nonlinear** (`powershape`, `distort1`, `chebyshevpoly`, `fold`, stacked `clip`) and
> **delay/recursion** (`comb`, `alpass`, `vcomb`, `multitap`, `flanger`). Real chains from
> the device: `syncgrain+pvsfreeze+alpass+powershape`, `pvshift+vcomb`,
> `modebank+pvstrace+vcomb`. Renders are normalised toward a target RMS (peak-capped) —
> resonators and spectral freezes vary wildly in level — and a silent render is an error,
> not a dead sample. See `controller/poundhard/csoundfx.py`.

> Csound ships as a **self-contained runtime** at `$PH/csound` (6.17, aarch64, 20 opcode
> plugins including `librtjack.so`, ~16 MB) and serves **two** engines: these offline
> renders, and the realtime [CSOUND engine](#csound--engine-20). Mangles run on a
> background thread — one takes seconds and must never stall the sequencer or the UI.
>
> It was an offline-only build until engine 20: no JACK module, a partial opcode set, no
> capabilities. It now carries RT capabilities and joins the realtime graph, which is why
> its binaries are RPATH'd rather than relying on `LD_LIBRARY_PATH` (see
> [Deploy to the Move](../README.md#deploy-to-the-move)).

- **CSOUND** — the realtime **Csound** engine (engine 20), and the only voice whose audio
  is generated by a *separate process*: Csound runs as its own JACK client and writes a
  stereo pair per track into supernova's inputs, which an SC voice carries onto the track
  bus — so it goes through the per-track filter, the FX chain, the living-FX sends and the
  master like everything else. 26 architectures behind one contract, each a mix of
  generators and processors rather than an oscillator with effects after it: inharmonic
  PM into modal resonators, granular into spectral blur, a noise-excited mode bank,
  feedback-FM chaos, waveguide models through a feedback delay network,
  analysis/resynthesis, phase distortion with deliberate quantisation artefacts,
  correlated noise through steep dynamic filters, inharmonic additive, and PADsynth
  wavetables. A track's sound is an architecture plus **eight normalised macros** whose
  meaning changes completely between architectures. Full detail:
  [CSOUND — engine 20](#csound--engine-20).

> **BYTEBEAT** needs a native plugin: `supercollider/plugins/ByteBeat/ByteBeat.so` is a
> **prebuilt aarch64 UGen** (static libstdc++, needs only GLIBC_2.17 — loads on the CM4's scsynth
> 3.13). `deploy-controller.sh` ships it to `$PH/plugins` and the `ByteBeat.sc` class to the SC
> Extensions dir. Rebuild it from source with `move/build-bytebeat.sh` (arm64 Docker).

> <a name="native-plugins"></a>**COMPASS** needs a native plugin too:
> `supercollider/plugins/Softcut/PhSoftcut.so` wraps **monome's softcut-lib** as a UGen (one
> instance = one softcut voice), built the same way — static libstdc++, GLIBC_2.17. Both a
> plain and a `_supernova` variant are shipped, because **supernova loads only
> `*_supernova.so`**. Its input list is the norns softcut API *completely*, deliberately: it
> exists to run real norns scripts unmodified, and a script calls whatever it calls.
> Rebuild with `move/build-softcut.sh`.
>
> **COMPASS also needs Lua**, to run that script. The Move does ship `/usr/bin/lua`, but that
> lives on the 463 MB root partition Ableton's firmware owns and keeps ~99% full, so
> PoundHard vendors its own: `move/build-lua.sh` → `move/bundle/poundhard-lua.tar.gz` →
> `$PH/lua/bin/lua`, shipped by `deploy-bundle.sh`.

> **WTABLE** reads the Move's factory **wavetable sprites** straight from `/opt/move/Dsp/Vector/
> Sprites/` on the device — nothing is bundled or redeployed; the engine enumerates them at boot.

> Both **MALLET** and **BOWED** are STK physical models that load excitation wavetables
> (e.g. `marmstk1.raw`) — the **STK rawwaves** are bundled under `supercollider/rawwaves/`
> and deployed to `$PH/rawwaves`, with the path set at engine boot via a `StkGlobals`
> synth. (SHAKER is stochastic and needs no rawwaves.)

> RINGS and **PLAITS** need the **mi-UGens** plugins (as does the **CLOUDS** FX);
> **SHAKER**, **MEMBRANE**, **MALLET**, **BOWED**, the **RING** / **RESO** / **GREY** FX, **ICARUS**
> (`MoogLadder`) and **BEN** (`PulseDPW`/`SVF`/`DFM1`) need **sc3-plugins** present in the
> SuperCollider bundle on the device. There are **no silent fallbacks** — a missing
> dependency fails loudly at build.

---

---

## Controls

Views are switched with the buttons to the left of the pad grid and the Menu
button. Knob readouts are drawn in a **giant block font** and stay on screen the
whole time the knob is **touched** (not just while turning) — the same rule
everywhere.

**Undo** works anywhere: the dedicated **Undo** button steps back through the last
**20 discrete actions** — step edits, mutes/solos, engine assigns and sound re-rolls,
pattern save/load/delete/paste, generated variations, FX assign/bypass, project
loads. It restores the *whole machine* (sounds, grooves, FX, the pattern bank) and
re-pushes it to the engine. Continuous knob moves (tempo, pan, macros, dry/wet) are
deliberately **not** undoable — they'd flood the 20 levels with sub-gesture noise.

### Tracks view (default)

The **top row of pads** is the **engine palette** — one pad per assignable engine,
in its engine colour.

| Control | Action |
|---|---|
| **Engine pad — short-press** | audition that engine's current sound (one hit) |
| **Engine pad — Shift + press** | regenerate that engine's sound |
| **Hold engine pad + tap a step button** | **assign** that engine + sound to the track |
| **Hold the SAMPLE pad + tap an engine pad** | **capture** that engine: it auditions and is threshold-recorded, then mangled through a Csound opcode graph |
| **Hold the SAMPLE pad + tap a step button** | assign the mangled take to that track (the track gets its own copy; the pad is **released** for the next capture) |
| **Hold the DRUM pad + tap a pad to its right** | **audition** that pad's fixed drum type (kick · snare · hihat · metal · clap · tom · noise, in DRUM's own colour); **lift to commit** it to the engine |
| **Copy + step button, then another step button** | **duplicate a whole track** — see [Copying a track](#copying-a-track) |
| **Step button — tap** | mute / unmute that track |
| **Step button — double-tap** | **solo** that track (double-tap again to un-solo) |
| **Step button — long-press** | open that track in the [Edit view](#edit-view-per-track) |
| **Track 2 button** | open the [FX view](#fx-view) |
| **Track 3 button** | open the [Pattern view](#pattern-view) |
| **Shift + Track 3 button** | open the [Recorder view](#recorder-view) |
| **Menu button** | open the [Project view](#project-view) |
| **Shift + Track 1** | re-roll the **open** track's sound (within its engine) |
| **Shift + hold volume knob + Track 3** | **fully randomise** the current pattern (4–10 tracks) |
| **Bottom-row first pad** | **HEAT** — mass-mark [living steps](#living-steps--the-heat-button) across the whole rig (toggle) |
| **Bottom-row 2nd pad** | **SHUFFLE** — temporarily swap rhythmic structures between tracks (toggle; each ON rolls a fresh config) |
| **Bottom-row 3rd pad** | **QUAKE** — temporarily reshape the rhythm with polymeter + polyrhythm (toggle; each ON rolls a fresh config). See [Quake](#quake) |
| **Bottom-row 4th pad** | **CHURN** — the music listens to itself: fragments of the master are transformed through CDP and dropped back into the gaps (toggle). See [Churn](#churn) |
| **Bottom-row 5th pad** | **BREAK** — automatic breakdowns every N cycles (toggle). See [Break](#break). **Mutually exclusive with QUAKE** — whichever is off goes **grey** while the other holds the rig |
| **Hold BREAK + jog wheel** | how many pattern cycles between breaks (1…32, default **4**) |
| **Bottom-row 6th pad** | **STROBE** — tempo-locked gating + microlooping on a shifting subset of tracks (toggle). See [Strobe](#strobe) |
| **Hold HEAT pad + Knob 1** | set the HEAT amount (% of hits marked) |
| **Play** (lit green while running) | start / stop the sequencer |
| **Knob 1** | master tempo (BPM) |
| **Knob 8** | **chaos macro** — sweeps every param of every assigned engine (see below) |
| **Shift + touch Knob 8** | snap back to the chaos macro's **safe zone** |
| **Undo** | step back one discrete action (20 levels, works in any view) |
| **Shift + Undo** | **redo** — step forward again into what undo left behind. Doing anything new discards the redo trail, so there is never a question of which future you are in |
| **Back** | exit the takeover (tears the stack down) |

Step buttons are lit in their **engine colour**; a track with events pulses, an
assigned-but-empty track sits steady-dim, an **unassigned track is dark**, the open
edit track is white. Soloing a track dims every other one — without touching their
own mute flags, so un-soloing restores exactly what was muted before.

> Solo is on **double-tap**, not Shift+step: **Shift + step button 13** is a fatal
> Move firmware combo (it floods MIDI and the module gets watchdog-killed), so Shift
> is deliberately never used on the step buttons.

### Edit view (per track)

A **long-press** on a step button opens its editor. The **first two pad rows are the
track's 16 steps**; the **bottom row is the 8-effect chain** (per-step FX, below), and
the jog/knobs/cursors edit that track's settings — all in one place.

| Control | Action |
|---|---|
| **Pad — tap** (rows 1–2) | toggle that step (in-length pads dim, active bright) |
| **Pad — hold (active step)** | **per-step lock** — jog = pitch, knob 1 = velocity, knob 2 = pan, knob 3 = macro |
| **Rec + pad** | mark / unmark that step as a **[living step](#living-steps--the-heat-button)** (self-transforming; pulses pink) |
| **Hold a step + row 3** | that step's **cycle frequency**: pad 1 = every pattern repetition (default), pad 2 = every second, … pad 8 = every eighth. Row 3 is dark unless a step is held |
| **Step pad — tap an active step** | delete it. The slot is **emptied**, not just silenced: pitch, velocity, pan, macro, FX mask, cycle divider, filter, sample window, ratchet, send and any living mark all go. Drawing a step there again gives a brand-new step |
| **Copy + step pad** | a step **with data** goes to the clipboard; an **empty** step **receives** it — copy and paste without letting go of Copy. Carries everything: the note/velocity/pan/macro locks, living flag and period, ratchet, send and per-step FX |
| **Copy + Track 1 / Track 2** | the same for a whole **row** of steps — row 1 is steps 1-8, row 2 is steps 9-16. The first row press of a Copy hold **grabs** that row; every press after it **pastes** onto the row pressed, empty or not. Release Copy to grab again |
| **Shift + step pads** | **select** steps for the per-step FX editor (selected = bright red) |
| **Shift + bottom row** | add / remove that effect on every selected step |
| **Shift + master knob touch + pad** | set that pad as the **last step** (polymeter, up to 16) |
| **Shift + touch the volume knob + Track 1** | **generate a new sequence** for this track — rhythm, velocities, pans, pitches, cycle dividers and living steps (see [Generating a sequence](#generating-a-sequence)) |
| **Shift + jog wheel — turn** | **transpose the sequence**, one semitone per detent, ±24 (see [Transposing](#transposing)) |
| **Shift + jog wheel — touch** | toggle the **pitch randomizer**. Touch and turn are separate events, so this and the transpose above never collide (see [Per-parameter step randomizers](#per-parameter-step-randomizers)) |
| **Shift + touch any knob** | toggle the **randomizer** for the parameter that knob edits — velocity, pan, macro, filter cutoff, resonance, sample window. Turning the knob still edits the value |
| **Jog wheel** | track pitch (re-pitches ringing voices live) |
| **Knob 1 / 2** | track volume / pan |
| **Knob 3** | **voice macro** — one knob sweeps every timbral param of the voice, each in a random direction; the directions re-roll whenever the track's sound is regenerated |
| **Knob 4 / 5 / 6** | the track **filter**: cutoff · resonance · LP/HP (see [Track filter](#track-filter)) |
| **Knob 4 / 5** *(SAMPLE tracks)* | the sample's **playable window**: start / end, as a percentage of the buffer |
| **Knob 6 / 7 / 8** *(SAMPLE tracks)* | the filter, shifted by two so the window keeps 4 and 5 |
| **Hold a step + knob 4 / 5** *(SAMPLE)* | that **step's own** slice of the buffer — one step plays the attack, the next the tail. Unlocked steps follow the track |
| **Hold a step + the filter knobs** | the filter **for that step only** — same knobs as the track filter (4/5/6, or 6/7/8 on SAMPLE). Unlocked steps play the track's filter |
| **Hold a LIVING step + row 4** | that step's **living interval** — how often it transforms, counted in **its own plays** (pad 1 = every play … pad 8 = every eighth) |
| **Hold a step WITH FX + row 4** | that step's **effect interval** — how often its effects are applied, counted in its own plays, exactly as above. A living step keeps row 4 for its transform |
| **Left / Right cursor** | clock rate / division: `/8 /4 /2 1 x2 x4 x8` (bipolar readout) |
| **Track 1 button** | back to Tracks view |

#### Cycle frequency

Row 3 of the edit view — visible **only while a step is held** — sets how often that step is
allowed to fire, counted in **repetitions of the pattern**: the leftmost pad is every cycle
(the default), the rightmost every eighth. A step set to 4 plays once, then stays silent for
three passes, then plays again.

It is what lets a short pattern behave like a long one: 16 steps carrying a few different
dividers take 8 repetitions before they repeat themselves exactly, so the part evolves
without the step count — or your reading of the grid — ever growing. Tracks are capped at
**16 steps**; this is how you get past that without getting lost.

Row 4 then sets how often the step's **special behaviour** happens, counted in plays of
that step — so the two rows multiply. It means the same thing whichever behaviour the step
has: for a **living step** it is how often it *transforms*, and for a step carrying
**effects** it is how often those effects are *applied* (see
[Per-step FX](#per-step-fx)). One model, one gesture, one row.

The counters reset when the transport starts, so a divided step lands on the downbeat and
then every Nth repetition after it. The divider travels with the step: it is saved with the
pattern, carried by the [copy gestures](#edit-view-per-track), and cleared with the pattern.

#### CSOUND — engine 20

Csound, running for real and in realtime. Not the offline opcode graph the SAMPLE engine
mangles captures through — a synthesis engine that generates sound from nothing, with **26
architectures** behind one contract. The first ten are single hand-written designs:

| | |
|---|---|
| **fmmetal** | inharmonic phase modulation into a waveshaper and modal resonators — struck metal that is pitched but never harmonic |
| **granclouds** | granular over an inharmonic wavetable, spectrally blurred, thrown through a feedback delay network |
| **modalstrike** | a noise burst into six detuned modes; the excitation is gone in milliseconds and the body is the sound |
| **chaosdrone** | feedback FM at sample rate — below a threshold a harmonic timbre, above it period-doubling into genuine chaos |
| **waveguide** | plucked and bowed models pushed past their polite range, into an FDN body |
| **spectral** | analysis, warping and resynthesis as the instrument — the electroacoustic one |
| **phasedist** | phase distortion and hard waveshaping, with deliberate quantisation artefacts |
| **noisemachine** | correlated noise through steep dynamic filters, gated hard |
| **additive** | inharmonic partials, each with its own decay and a slow random walk |
| **padwave** | PADsynth wavetables, cross-modulated and diffused |

A track's sound is an architecture plus **eight normalised macros** whose meaning changes
completely from one architecture to the next. That is deliberate: it means the voice macro,
the chaos macro, per-step macro locks and living-step transforms all drive this engine
without knowing anything about it. Re-roll the sound (**Shift + Track 1**) and you land on
a different architecture, not a variation of the same one.

The processing is *inside* the voices — dynamic filters, resonator banks, spectral blur,
waveshapers, ring and cross modulation, frequency shifting, delay networks and diffusion,
stereo imaging, random and chaotic modulation — rather than bolted on afterwards.

Every track's voices sum onto a bus and pass a **limiter** before they leave Csound. A
per-voice ceiling cannot stop a track clipping — each voice was individually under the
limit and four overlapping hits summed straight past it. The limiter rides gain from the
block peak, is transparent below the ceiling, and only ever pulls down.

**How it is plumbed.** Csound runs as a separate JACK client and writes one stereo pair per
track into supernova's inputs; an SC voice carries that pair onto the track bus. So a
Csound track is an ordinary PoundHard track: the per-track filter, the 8-slot FX chain, the
living-FX sends, mute, solo and the master all apply. Measured on the device: a 12 kHz
highpass on the track filter drops a Csound track by **31 dB**, and muting it gives digital
silence — it is genuinely inside the signal path, not mixed in beside it.

Notes fire as `$`-prefixed score events over Csound's UDP port. supernova boots with 36
input channels: 1-2 are the microphone, 3-34 are the 16 stereo returns, and 35-36 are the
audition pair the palette pad plays through — the engine has to be able to make a sound on
a track that does not exist yet.

Csound's realtime thread runs at priority 68, above supernova's DSP threads (65) and below
jackd (70), pinned to core 3. It feeds supernova within the same JACK cycle, so it has to
finish first; at equal priority and free to migrate across all four cores it competed with
the very threads waiting on it, which is where the XRuns came from. The runtime is a
second bundle (`move/build-csound.sh`) — the Csound previously on the device was an offline
build with no JACK module, able to render the SAMPLE mangler's files and nothing else.

#### There is always a pattern

PoundHard opens with **pattern 1 already live**, even with no project loaded. It used to
open on nothing — 32 dead slots and `no current pattern` — so the first thing you had to do
was save an empty pattern before any of the work could be written down.

That startup pattern is a real one: assign engines, draw or generate steps, set parameters,
and it all lands in slot 1 from the first press. When you eventually **save a project**, the
live state is folded into its own slot first, so the temporary pattern and everything in it
becomes pattern 1 of that project — nothing is lost in the transition from "just playing"
to "this is a piece". Loading a project that somehow contains no patterns seeds one the
same way, so there is no route back to a blank state.

#### Per-parameter step randomizers

**Shift + touch a control** in the edit view toggles a randomizer for whatever per-step
parameter that control edits. Each one is independent, stays on until you switch it off,
and generates a fresh set of values **every pattern cycle**.

| Touch (with Shift) | Randomizes |
|---|---|
| **Knob 1** | velocity |
| **Knob 2** | pan |
| **Knob 3** | voice macro |
| **Knob 4 / 5** (SAMPLE tracks) | sample window start / end |
| **Knob 4 / 5** (or 6 / 7 on SAMPLE) | filter cutoff / resonance |
| **Jog wheel — touch** | pitch |

Touch, not turn: the jog's touch and its turn are separate events, so **Shift + touching**
the jog toggles the pitch randomizer while **Shift + turning** it still
[transposes](#transposing). Turning any knob still edits its value as before.

A big `VELOCITY RANDOMIZER / ON` takes the screen for a moment on every toggle, and the
edit view carries a persistent `RND VEL PAN PIT` line, so you never have to toggle one to
find out whether it is on. A control that edits no per-step data says `NO RANDOMIZER`
rather than switching on something with no audible effect.

**Every parameter has its own algorithm**, because "randomise" means something different
for each one — and all of them vary around the value you programmed rather than replacing
it, which is what keeps the sequence recognisable:

- **velocity** moves each hit by a bounded ratio around its *own* value, so a step written
  loud stays the loud one and the phrasing survives; the occasional hit is ghosted.
- **pan** draws every step from one slow contour across the bar, with a fresh phase and
  width each cycle. Independent random pans read as a fault in the signal path; a sweep
  reads as movement.
- **pitch** moves in *scale degrees* around the programmed note and quantises to the
  project's [scale](#the-projects-scale), so the line keeps its shape and every result
  belongs to the piece.
- **cutoff** varies as a *ratio*, because cutoff is heard logarithmically — a linear jitter
  is inaudible at the top and slams shut at the bottom.
- **resonance** gets a deliberately tighter range than the rest and never reaches the top of
  the control.
- **sample start and end** move together whatever you touched, because a start past its end
  is not a variation, it is silence.

**Non-destructive.** The programmed values are never written — the randomizer is an overlay
pushed at the engine, so switching it off re-pushes your own sequence exactly, and switching
one off leaves every other one running.

> There is no per-step **microtiming** parameter in PoundHard, so there is no randomizer for
> it. The step grid is the timing; groove would have to be added as a per-step field first.

#### Copying a track

**Hold Copy, press the track you want, then press where you want it.** The clone lands
immediately. Keep holding Copy and press more tracks to spread the same source across
several at once; releasing Copy forgets it. The grabbed source burns violet while the hold
is live, and the screen says which half of the gesture you're in.

Everything comes across, because a track is more than its notes: the engine and every one
of its parameters, the sound, the sample (the clone gets its **own copy** of the buffer,
not a shared reference), the sequence, every per-step lock — pitch, velocity, pan, macro,
FX mask, cycle divider, sample window, filter, ratchet, send — living marks with their
intervals and current transforms, the track filter, the transpose, length, rate, mute, the
FX chain and its bypass, and the voice-macro position with its randomised directions.

Then the two go their own way. Nothing is shared: assign a different engine to the clone,
generate it a new sequence, load another sample, rewrite its effects, replace the sound
outright — the original does not move. That is the whole point. Duplicate the track you
like, keep it as the reference, and take the copy somewhere you might not want to come
back from.

One thing deliberately does *not* travel: **HEAT** marks. HEAT is a live overlay backed by
a snapshot taken when it engaged, and a track created afterwards isn't in that snapshot —
carrying its marks across would leave cells that toggling HEAT off could never restore. The
clone gets those steps as they were underneath. Hand-placed and generated living steps come
across in full.

#### Generating a sequence

**Shift + touch the volume knob + Track 1** writes the open track a new 16-step part.
(Shift + Track 1 *without* the knob touch still re-rolls that track's **sound** — the knob
touch is what separates "new part" from "new voice".)

It is not a random grid. One of six algorithms is chosen per generation:

| | |
|---|---|
| **euclid** | even distribution of *k* over *n*, rotated — the reliable spine |
| **euclid pair** | two Euclids combined with AND / OR / XOR — polyrhythm folded into one bar |
| **asymmetric** | additive grouping (3+3+2, 5+3, 7+5+4…), accents on the group heads |
| **burst** | dense clusters separated by gaps — the rhythmic-noise shape |
| **sieve** | a residue rule (every 3rd from offset 1, layered) — irregular against the grid but perfectly periodic |
| **fracture** | a Euclid whose hits are displaced a step at a time — off the grid, not off the rails |

Then each hit is written with material, not noise: **velocity** follows a contour with
accents on group heads and the occasional ghost; **pan** sweeps across the bar rather than
scattering; **cycle dividers** put some hits on every 2nd–8th repetition so the bar unfolds
over a longer span; and pitched engines get a **scale-aware line** (below). Measured over 300
generations: all six algorithms appear, 2–12 hits per bar (median 6), and two consecutive
generations produced the same rhythm twice in 300.

Finally a few hits are made **living steps** — the same living steps you place by hand with
Rec + pad, written through the same code, so they edit, save and behave identically. Each
generated one gets a living interval (row 4) and one or two per-step effects, and then does
what living steps do: re-roll its own character, filter, pitch leap, pan, ratchet and
delay/reverb send every time its interval comes round. That is what stops a generated bar
from being a loop.

They stay scarce on purpose. At most a quarter of the hits and never more than four, never
on the downbeat (the ear's anchor), and always on the weak steps where a transform colours
the bar instead of fighting the pulse. The intervals within a bar are made *distinct*, so
the marked steps transform on different repetitions rather than lurching together — and
since each one multiplies by that step's own cycle divider, a bar can take dozens of
repetitions to come back round to where it started. Over 400 generations: 17% of bars get
none at all, the rest average 29% of their hits, and no generated living step ever landed on
step 1.

A living step now also **remembers what it was**. Between transforms it returns to its own
velocity, pan and pitch rather than to the bare track defaults — which matters little for a
step marked by hand on an empty grid, but everything for a generated one that arrives with
material already written.

#### Transposing

**Cursor up / down transposes the WHOLE PROJECT**, one semitone per press, up to ±24. It is
an offset laid over every track, so the relative tuning between tracks is preserved and
returning to zero restores every original pitch exactly. The giant readout shows the amount
with its sign while you move it, and a `+5st` marker stays on the status line for as long as
you are off concert pitch. It is saved with the project and re-applied on load.

**Shift + turn the jog wheel** transposes the open track's sequence, one semitone per
detent, up to ±24. The screen shows the amount in the giant readout while you turn (`+5`,
`-12`, `±0`) and keeps it beside the key in the edit view for as long as it isn't zero — a
transposed sequence should never be silently transposed.

It is an offset, not a rewrite. The step locks keep the pitches the generator or your hands
put there, so step placement, velocity, pan, living marks, effects and cycle intervals are
untouched, and turning back to zero restores the original pitches exactly.

#### The project's scale

There is no key selector, and there should not be one. **The first pitched material decides
what the piece is in** — whether you enter notes by hand or generate them — and every track
generated afterwards answers to it. The scale is detected from the notes actually played:
the candidate root and mode that best explain them, preferring the tightest set that fits
(so a minor triad reads as a pentatonic rather than as "chromatic"), with the most-repeated
note weighted as the likely tonic. The palette is deliberately dark — phrygian, locrian,
aeolian, dorian, harmonic minor, octatonic, whole tone, minor pentatonic, in sen.

A later track's generated pitches are then shaped by three things: the scale, the **pitch
classes the other tracks already use** (when two scale tones are equally close, the one
already in play wins — that is what makes a new part sound *related* rather than merely
legal), and the **register others occupy** (a new line leans away from a crowded one).
Dissonance is still available: a small per-note `tension` licence lets a line step outside
the scale on purpose — 96% of generated notes land in scale, and the rest are chosen grit
rather than accident. The scale travels with the pattern, so switching pattern switches key.

#### Track filter

Every track has a **multimode filter** ahead of its FX chain — knobs **4 / 5 / 6** for
cutoff, resonance and LP/HP, shifted to **6 / 7 / 8** on SAMPLE tracks where 4 and 5 are
already the sample window. It is transparent at its defaults (open lowpass, no resonance),
and it filters the *track*, not the reverb tails, because it sits before the inserts.

The UGen choice is the whole point. Ask a ladder (`MoogFF`) or a Butterworth `RLPF` for
resonance and you get 1970s behaviour: the passband is attenuated as Q rises, so a lowpass
drains its own bass and the level sags — you cannot sweep it without riding the volume
afterwards. PoundHard uses a **state-variable filter** (`SVF`), whose lowpass has unity DC
gain at any resonance: the peak appears at the corner without taking anything away below
it (LP) or above it (HP).

Measured on the device, 1 kHz lowpass, resonance 0 → maximum, with a 60 Hz probe:

| filter | bass at 60 Hz | output level |
|---|---|---|
| **State-variable** (what PoundHard uses) | **±0.1 dB** | **±0.3 dB** |
| MoogFF ladder (for comparison) | −13.8 dB | −12.5 dB |

The peak itself is bounded by a soft clip on the way out, so a full-resonance sweep cannot
run away — and with the filter open and no resonance the dry signal is passed through
untouched rather than through the filter's approximation of it.

**Nothing about it is allowed to step**, because per-step locks change these values between
steps while the previous note is still ringing. A biquad recomputes its coefficients per
control block and does not interpolate them, so stepping a cutoff mid-note is a
discontinuity in the output — measured on a sine, a jump **4400×** the signal's own
curvature, which is exactly the click you hear. Three things fix it:

- the **state-variable** core, whose state stays continuous under modulation (a biquad's
  coefficient snap does not);
- every control reaching it through an **audio-rate** slew (~30 ms), so it moves per sample
  rather than per block, with cutoff gliding in *log* frequency so a sweep is musical;
- **LP and HP crossfaded**, never switched — both always run, so this costs nothing.

And the change is handed over **early**: the next step's values are scheduled one glide
before that step arrives, so the transition happens during the previous note's tail (where a
glide is what you want) and the new hit starts with its filter already in place, attack
uncoloured. Measured on the worst case — steps alternating between a 250 Hz resonant lowpass
and a 6 kHz highpass under a sustaining sample — the largest sample-to-sample jump in the
output is **2.2×** the signal's own 99.9th-percentile slew, i.e. inside its normal dynamics,
while the steps still read as clearly different (≈1150 vs ≈750 zero crossings).

**Hold a step and the same knobs scope to that step**: a locked step plays through its own
cutoff / resonance / type and an unlocked one plays the track's, exactly like the per-step
FX mask. Because the filter is one insert per track, the lock is applied at step time and
the track's own values are restored by the next unlocked hit, so a lock can never leak
forward. The layout is identical held or not — 4/5/6, and 6/7/8 on SAMPLE tracks where the
sample window owns 4 and 5.

#### Per-step FX

The bottom pad row of the edit view carries the same eight effects as the
[FX view](#fx-view) — `OD · AMP · CRSH · RING · CLDS · RESO · GREY · VERB` — and locks
them **per step**.

Hold **Shift**, tap the steps you want (they light **bright red**), then — still holding
Shift — tap effects on the bottom row. An effect lights **red** if *any* selected step
carries it; tapping it turns it **on everywhere** if it was missing anywhere, else **off
everywhere**, so mixed selections resolve predictably. Releasing Shift clears the
selection. Steps that carry FX stay marked in **dark red**.

**The effects need not fire every time the step does.** Hold a step that carries FX and
row 4 becomes its **effect interval**, counted in plays of that step — the same row, the
same gesture and the same meaning as a living step's transform interval. Row 3 says how
often the step plays; row 4 says how often it goes wet; the two multiply:

> **Effect interval = step playback interval × effect cycle interval**

A step on **row 3 = 2** with **row 4 = 3** plays every second pattern cycle and goes wet on
every third of those plays — dry, dry, wet, dry, dry, wet — so the effects land every
**sixth** pattern cycle. Verified on the device with that exact setting: the step played
every 2 s and the effects landed every 6 s, on plays 2, 5, 8 and 11.

Like the living interval, the phase follows the running cycle counter rather than resetting
when you dial the interval in, so the first wet play after you set it can come sooner than
the full interval; the spacing from then on is exact.

A step's lock is a mask over the eight insert slots and **overrides the track's own FX
assignment for that hit only** — a step can switch effects on that the track doesn't have,
or mute ones it does. On a play where the effect interval says *dry*, the lock simply does
not apply and the step falls back to the track's own chain. An effect that only a step uses is instantiated in the track's chain
**disabled**, and opened just for the locked hits, so nothing is spent on it otherwise.
Steps without a lock restore the track's normal chain, so a lock never leaks into the
following hits.

> **A disabled insert is a WIRE**, and that has to be exact: its dry path is passed through
> untouched — not faded toward the wet, not routed through a DC blocker, not panned by an
> equal-power law. Each of those quietly cost level, and because a step-locked effect leaves
> its insert sitting in the chain for *every* step, the cost landed on the whole track.
> Measured with white noise, a disabled insert of any type now changes the track by **±0.03
> dB**; on the device, three effects locked onto a step that never even plays leave the track
> within **0.1 dB** — its own take-to-take noise floor.

### FX view

**Track 2** opens the FX view. The top two pad rows are the 16 tracks; the bottom
row is an 8-effect chain — `OD · AMP · CRSH · RING · CLDS · RESO · GREY · VERB`
(the space-makers sit at the end: **GREY**, a diffuse feedback delay, feeds **VERB**, the
cathedral reverb that closes the chain), each a distinct colour.

**CLDS** is **MiClouds** — Mutable Instruments **Clouds** (mi-UGens) as a live granular
texture processor (granular mode): grain size / density / texture / read-position, stereo
spread, an internal reverb and feedback. Its macro is deliberately kept in **granular**
territory — density stays high (a continuous cloud, not sparse echoes), the read position
near the write head (live, not a long delay tap), feedback low, and **no global pitch
shift** — so it smears and thickens the track into an evolving cloud rather than a
pitch-shifted delay.

**RESO** is **Streson** (sc3-plugins) — a **tuned string resonator** (a comb with feedback)
that rings the input at a set frequency, imposing a pitched, metallic/wooden resonant **body**
on anything: a kick becomes a tone, noise becomes a pitched wash. Its macro sweeps the resonant
`freq`, `res` (sharpness/decay) and a damping top-cut — a transforming resonance rather
than more space (GREY and VERB, after it, supply that).

**GREY** is a diffuse, pitch-modulated **feedback delay** (after ValhallaDSP's Greyhole) —
the dark, smeary IDM space-maker, sitting second-to-last so it feeds the reverb. Its macro
sweeps delay time, feedback, size, diffusion, damping and modulation together.

> GREY is **server-conditional**. Under scsynth it is the real `Greyhole` UGen (sc3-plugins).
> Under **supernova** — the default server — `GreyholeRaw` refuses to register, so GREY is
> rebuilt from core UGens on the same knobs: a cross-coupled, modulated feedback delay through
> an allpass diffusion chain with damped regeneration. It is drier than the plugin (Greyhole's
> reverb-ish blur is gone) — which is why the chain now ends in a dedicated reverb.

**VERB** is the **reverb** that closes the chain, so it reverberates everything upstream
of it. It's a **feedback delay network** built from core UGens: a bandwidth filter → **eight
series allpass diffusers** spanning 0.7-24 ms (the early field) → **eight modulated delay
lines**, each carrying its own allpass and damping low-pass, recirculated through an 8×8
**Hadamard** matrix. The matrix is orthogonal — it redistributes energy without adding or
losing any — which is what lets the tail run long and smooth instead of fluttering.

The wet output is the **diffuser output plus the network**, and an allpass passes its input
through directly, so there is energy in the tail from the first sample: measured on an
offline impulse render, **0 ms pre-delay**, every 1 ms bin of the first 30 ms carrying
energy, and an RT60 of **7.9 s to 17.8 s** across the decay range — cathedral scale, for
ambient work. Its macro sweeps decay, size, damping, early diffusion, bandwidth, the
modulation and stereo width.

> This replaced a Dattorro plate that took its wet output from the *end* of each tank half,
> ~150 ms down the delay chain: the reverb arrived as a discrete slap — a pre-delay in
> everything but name.

> Core UGens are not a compromise here: **both** `JPverbRaw` and `GreyholeRaw` refuse to
> register on supernova, so SC's third-party reverbs are unavailable on the server PoundHard
> runs. `decay` is clamped at **0.85** — past that the tank reaches unity gain, runs away and
> the safety clipper mangles it, making the tail *shorter* (0.80 → 2.2 s, but 0.99 → 0.38 s).

**RING** is **DiodeRingMod** (sc3-plugins) — an analog-style diode ring modulator, gnarlier
and more metallic than a clean multiply (asymmetric diode shaping adds extra sidebands). Its
macro sweeps the carrier frequency and a `drive` that pushes the signal harder into the diodes.


**OD** is not a polite tube sim: tilt EQ → asymmetric (biased) drive → a
**wavefolder** that reflects peaks back for metallic bite → a hard-clip **grit**
stage for fizz and breakup, plus a **SineShaper** sinusoidal fold and a **GlitchRHPF**
screaming resonant highpass. Its macro sweeps drive/tone/fold/bias/grit/shape/glitch together.

| Control | Action |
|---|---|
| **Hold an FX pad + tap tracks** | assign that FX to those tracks (their pad takes the FX colour) |
| repeat to unassign | stacked FX peel off one layer at a time; the top FX's colour prevails |
| **Tap a track pad** (no FX held) | bypass / un-bypass that track's FX chain (grey = bypassed) |
| **Knobs 1–8** | a randomized **macro** per FX — some params move with the knob, some inverted |
| **Shift + Knob 1–8** | **dry/wet mix** of that FX (0–100 %, shown big while turning) |

FX start at 50 % wet / 50 % dry. Both the macro and the dry/wet mix are **per FX
type** — they apply to every track using that effect — and both are saved with
patterns and projects.

### Pattern view

**Track 3** opens the pattern view. The 32 pads are **not** a flat bank — they are a
hierarchy of compositional ideas:

| | |
|---|---|
| **Pads 1–16 — SEEDS** | the canonical version of an idea, programmed, generated or refined |
| **Pads 17–32 — EXPANSIONS** | variations of *one* seed: alternative developments of a single idea |

A seed is the version you keep. Its expansions are where you develop alternatives for
different sections of a performance, without ever putting the original at risk.

**Opening a seed's expansions: hold REC and tap the seed.** Two things happen at once — rows
3 and 4 become that seed's expansion row, and its **first expansion is loaded**. The first
time you do this, expansion 1 is created as an exact copy of the seed, so there is always
something to develop *from* rather than an empty row.

From that moment the expansion is a **fully independent pattern**. Edit the sequence, change
engines, replace sounds, generate new material, apply performance edits — none of it can
reach back into the seed or into any other expansion. They are deep copies, not references.

| Control | Action |
|---|---|
| **Pad 1–16 — tap** | load that **seed**, exactly as before |
| **REC + pad 1–16** | open that seed's expansions and load its **first expansion** |
| **Pad 17–32** | load / select an expansion of the open seed |
| **Copy + source, then destinations** | the clipboard stays live while Copy is held, so one pattern can be pasted into several expansion slots in a row — the fast way to build a family |

**Reading the grid.** The seeds are the cool blue family and the expansions a warm amber
one, so the two halves never look like one bank of 32 — including *before* a seed is opened,
which is when the distinction matters most:

| | |
|---|---|
| very dark yellow | expansion row, **no seed open** — inert; an expansion has to belong to something |
| dark amber | this seed's row, slot free |
| amber | holds a variation |
| white pulse | the expansion playing now |

A pad flashes **white the moment you save or paste into it**, before the controller has
confirmed — pressing four destinations in a row, you need to see each one land as it happens
rather than a beat later.

The screen states the live pattern as its address: `S3` is seed 3, `S3.4` is expansion 4 of
seed 3.

> **Expansion rows are allocated only when used.** A pattern snapshot is around 53 KB, so
> eagerly reserving all 16 rows would mean a 14 MB project file and an autosave that hitches.
> A project with three seeds and four expansions costs what those seven patterns cost.

> **Projects saved before the hierarchy existed** used a flat 32, and there are only 16 seed
> pads now. Patterns 17–32 are migrated into **seed 1's expansion row** on load rather than
> becoming unreachable — lossless, and somewhere you can actually find them.

| Control | Action |
|---|---|
| **Shift + pad** | save the current machine state to that slot |
| **Pad — tap** (holds a pattern) | load that pattern |
| **Pad — tap** (empty) | **select** that slot as the destination for what you do next |
| **X (Delete) + pad** | **delete** that pattern — the slot clears, other patterns **stay put** (see below) |
| **Copy + pad** | **copy** that pattern; **further pads paste it** while Copy is held |
| **Shift + Track 3** | **generate a variation** of the current pattern (see below) |
| **Shift + hold volume knob + Track 3** | **fully randomise** this pattern in place (see below) |

**Delete is in place.** Deleting a pattern clears **only that slot** — every other
pattern keeps its position in the bank, so nothing shuffles under you. If you delete the
pattern you're *on*, it simply detaches (the live state keeps playing, it's just no longer
tied to a slot).

**Copy/paste is a held gesture.** Hold **Copy** and tap a pattern to take it; keep
holding and tap any other pads to paste it there. **Releasing Copy forgets the
clipboard** — it never persists between gestures. Pasted patterns are deep-copied, so
the two slots are fully independent.

Loading a pattern while the sequencer is **playing queues the switch**: it takes
effect on the next **16-step bar** boundary (the queued slot pulses until then).
Loading while stopped switches immediately. Slot colours: **periwinkle** = saved,
white = currently playing, **light grey** = an empty slot you've selected, pulsing =
queued, dim = empty.

**Empty pads are selectable.** Tapping one picks it as the destination for whatever you
do next — generate a pattern into it, or write one by hand — so you decide *where* a
pattern lands before making it. Nothing loads and nothing sounds different: the live
state keeps playing and now belongs to that slot, and the pattern you came from keeps
its own edits. It's immediate even while running (there's nothing to queue).

Patterns are **entirely self-contained** — loading one restores the whole machine,
**tempo included** (see [Patterns & projects](#patterns--projects)).

### Project view

**Menu** opens the project view — the same 32-slot grid for whole projects,
which persist to disk.

**The project you are in is white and breathing**, against the flat blue of every other
slot, and the screen names it (`IN 7`) or says `unsaved` when you have not saved yet. Every
slot used to look identical, so the only way to find out which project was loaded was to
load one and see what happened.

| Control | Action |
|---|---|
| **Shift + pad** | save the whole project to that slot |
| **Pad — tap** | load that project (restores every pattern and the live state) |
| **Shift + Menu** | restore the **autosave** recovery file (see below) |
| **Knob 1** | tempo of the selected pattern |

The highlight follows both loading *and* saving: saving to a slot puts you **in** that
project, so a fresh piece stops being "unsaved" the moment you write it down.

| Control | Action |
|---|---|
| **Shift + pad** | save the project (its 32 patterns + kit) to that slot on disk |
| **Pad — tap** | load that project (restores the full state — sounds included) |
| **Knob 1** | master tempo of the selected project (giant readout) |

Saved projects are blue; empty slots are dim. Projects survive power cycles.

### Recorder view

**Shift + Track 3** opens the recorder — the first 8 pads are **8 recording slots**
that capture the master output to **stereo 16-bit WAV** (up to **7 minutes** each).

| Control | Action |
|---|---|
| **Pad — tap** | if the sequencer is playing, start recording that slot immediately; if stopped, **arm** it |
| **Play** (when armed) | begin the armed recording |
| **Pad — tap the recording slot**, or **Play** | **finish** the take — see the tail behaviour below |

**Tails are captured.** Finishing a take does *not* cut the audio dead: the recorder
keeps running and only closes the file once the master output has actually fallen
silent, so **reverb and delay tails land in the recording**. The pad glows amber
while the tail runs (tap it again to cut the tail short). A 30 s safety limit ends a
tail that never decays (e.g. a drone).

Slot colours: dark-grey = empty, green = holds a take, blinking amber = armed
(waiting for Play), pulsing red = recording, pulsing amber = capturing the tail. The
screen shows a giant `M:SS` counter. See
[Recording & the web UI](../README.md#recording--the-web-ui) for downloads.

---

---

### Modulation view

**Track 4** opens it. Thirty-two pads, each one an **LFO that the system has already
assigned to a parameter for you**. There is no routing step and no target menu — the point
of the view is that sophisticated modulation is as immediate as everything else here.

| | |
|---|---|
| **Pads 1–16** | **sample-and-hold** — stepped, irregular, evolving. Amber. |
| **Pads 17–32** | **sine** — smooth, continuous, gradual. Cyan. |
| **Pad dim** | assigned to a parameter, idle |
| **Pad bright** | running |
| **Pad dark** | no target available for this slot |
| **Shift + Track 4** | re-roll the whole bank against the current project |

**Each pad is an independent toggle.** Pressing one switches that LFO on or off and touches
nothing else.

**Everything is tempo-synced.** Rates are musical divisions of the bar — 8 bars, 4 bars,
2 bars, a bar, 1/2, 1/4, 1/8, 1/16, plus dotted and triplet forms. Nothing free-runs: an
LFO's phase is derived from the bar position, so changing the tempo carries the whole bank
with it, and an LFO set to *one cycle per four bars* is still exactly in phase with the
pattern an hour later. LFOs freeze while the sequencer is stopped.

**Assignment is analysed, not arbitrary.** Before generating the bank the system looks at the
project: only tracks that are unmuted *and* actually have hits contribute, only parameters
that are safe to modulate are eligible, and each LFO swings **around the value you have
programmed** rather than replacing it. Targets are ranked by how much they repay modulation —
filter cutoff, timbre, morph, harmonics, index, fold, drive — and then dealt round-robin
across tracks, so one track with a lot of knobs cannot take six pads.

**No two LFOs ever share a parameter.** If the project offers fewer than 32 usable targets,
the remaining pads stay **dark and inert** rather than doubling up — two LFOs fighting over
one parameter is worse than an empty pad. A single-track project typically assigns around 26.

**Engine pitch is never a target.** Continuously sweeping pitch produces the laser-gun effect
that has nothing to do with this instrument; pitch belongs to the sequencer and the scale.
Excluded by name across every engine: detune, sub-pitch, sub-octave, transpose, portamento,
pitch-mod and the oscillator frequencies. *Not* excluded, because they are not pitch: filter
cutoff and resonance, LFO/PWM/vibrato **rates**, FM ratio (which is the timbre of an FM
voice), and a drum's pitch-envelope time.

**Amp and pan are held down deliberately** — they swing far less of their range than timbral
parameters do, because a deep amplitude LFO is a gate rather than a modulation, and a deep
pan LFO makes the whole mix seasick.

**It is completely non-destructive.** An enabled LFO drives the engine directly and writes
nothing to the project. Switching it off returns the parameter to its programmed value
immediately. Nothing you have set is ever overwritten, and saving a pattern while LFOs are
running saves what you programmed, not where an LFO happened to be.

> **On percussive engines you hear it hit-to-hit.** Voices are spawned per hit, so a
> modulated parameter is heard on the *next* strike; sustained sources (CSOUND, BYTEBEAT,
> pads, drones) move continuously. On drums this reads as hit-to-hit variation, which is
> usually the more musical result.

---

## Sounds & the engine palette

Tracks start **empty**. You build a rig by assigning engines from the **engine
palette** (the top row of pads in the default view): audition a pad, re-roll it
until you like it, then hold the pad and tap a track to drop the sound there. Any
engine can go on any track, as many times as you like.

Each engine generates its sound from a **generic role** — musical parameter bands
that keep the voice idiomatic while randomizing the rest (drums roll every mode;
tonal voices draw notes from a low phrygian scale; BEN keeps its second oscillator
sub-audio so the rungler clocks; NOIZEOP spreads its four ratios; ICARUS leans long
and evolving). Tune the roles in
[`controller/poundhard/kits.py`](../controller/poundhard/kits.py) — that's the
aesthetic dial.

- **Short-press an engine pad** — audition its current sound.
- **Shift + engine pad** — regenerate that engine's sound.
- **Hold engine pad + tap a track** — assign the engine + sound to that track.
- **Hold the DRUM pad + tap a pad to its right** — **audition and pick the drum type**.
  The seven pads to its right light in DRUM's own colour (they belong to that engine) and
  each holds one fixed type — left to right: kick · snare · hihat · metal · clap · tom ·
  noise. Tapping one **auditions that type** (the same reference sound every press, so a
  pad reads as "hihat" rather than a new random drum each time); the picked one shows
  white and the screen names it in big type. **Lifting your hand commits the choice** to
  the engine, and the pad is rolled as that drum — ready to assign to a track. From then
  on **Shift + DRUM pad** generates fresh variations *of that type*. Useful when you want
  another hat rather than whatever the dice give you.
- **Hold the SAMPLE pad + tap an engine pad** — **capture** that engine into the sample
  engine: it auditions, a threshold-gated recorder grabs it, and the take is mangled
  through a freshly assembled Csound opcode graph. The screen narrates it (`ARMED` →
  `REC` → `CSOUND` → `READY`, naming the chain). Then **hold + tap a track** to assign
  it — the track takes **its own copy** and the pad is **released**, so several tracks can
  each hold a different mangled sample. A short press of the pad just triggers the take.
- **Shift + Track 1** (while a track is open) — re-roll that track's sound within
  its assigned engine.

Assigning or re-rolling a sound keeps the track's pattern, mutes and per-step locks.

---

---

## Patterns & projects

A **pattern is an entirely self-contained unit.** Saving one snapshots the whole
machine at that instant, and loading one restores all of it:

- **which engine sits on which track** — the engine-to-track assignment is
  pattern-level, so two patterns can have completely different rigs
- every **engine parameter** of every voice, plus notes, velocities and pans
- the **FX** state — chains per track, bypass, the macros and the dry/wet mixes
- **mutes**, sequences, lengths, clock rates and every per-step lock — pitch, velocity,
  pan, voice macro, ratchet, living flag and period, FX mask and cycle divider

**Tempo is per pattern too.** Each pattern carries its own BPM, so switching pattern
switches tempo with it and sections can run at different speeds. Set the selected
pattern's tempo with **knob 1** (in the tracks, pattern or project view); the giant
readout shows the whole time the knob is touched.

A **project** is a collection of up to 32 patterns plus the current state, written to
`/data/UserData/poundhard/projects/proj_NN.json`.

The queued pattern switch is bar-accurate: the engine fires `/ph/cycle` on the last
step of each fixed 16-step bar, and the controller restores the pending pattern right
before the downbeat.

### Randomise a whole pattern

**Shift + hold the volume knob + Track 3** fully randomises the **currently selected
pattern**, in place — it replaces that pattern rather than generating new ones.

It builds a complete rig from nothing: an ensemble of **up to 8 tracks**, engines
assigned, sounds generated, idiomatic parts written, and a little FX. The aesthetic
target is between **IDM and rhythmic noise** — and the rules that keep it from turning
into cacophony (or into XRuns) are the point:

**One recipe per pattern.** A pattern is built to a single compositional brief rather than
from uniform randomness. There are **eighteen**, and each has an identity you could name:

| Recipe | What it is |
|---|---|
| `GRID` | one relentless pulse, everything locked to it |
| `BROKEN` | the pulse is displaced and never lands where expected |
| `POLYMETER` | tracks of different lengths drifting against each other |
| `POLYRHYTHM` | one bar, several clock divisions running through it |
| `SPARSE` | mostly silence; every event has to earn its place |
| `WALL` | power noise — dense, interlocking, no air left in it |
| `DRONEBED` | a held bed with sparse events over it |
| `CALL` | two voices answering each other across the bar |
| `MUTATION` | a short figure that rewrites itself as it repeats |
| `TEXTURAL` | no groove — spectral movement is the content |
| `MACHINE` | industrial, mechanical, hard on the grid |
| `STAGGER` | asymmetric bars that never quite resolve |
| `SWARM` | many sparse voices adding up to one moving mass |
| `CONTRAST` | half the bar crowded, half of it empty |
| `SUBBASS` | built from the bottom up; the low end is the subject |
| `GLITCH` | fractured, stuttering, deliberately unstable |
| `PROCESSION` | slow, heavy, ceremonial |
| `INTERLOCK` | parts that only make sense together |

The recipe names the kit (`SPAR-035`, `PROC-670`…), and it decides across the whole pattern
rather than per track: per-role density, which rhythm algorithms may be used, a length policy,
a clock policy, a register map, an accent shape, a pan strategy, pitch relationships, how much
of the pattern rewrites itself over time, and which roles must not sound together.

**Roles are jobs, not engine categories.** Each track is assigned one of *pulse, counter,
fill, texture, sustain, lead, accent* — so the pulse can land on a bass, and a percussion
voice can serve as texture, instead of every pattern being a drum kit with decoration.

- **Parts are generated against each other**, not independently: they interlock with the
  pulse according to their role, are given opposite halves of the bar where the recipe
  forbids a collision, and are holed out where it asks for contrast.
- every voice comes from a **curated role** ([`kits.py`](../controller/poundhard/kits.py)),
  so all notes are drawn from the same low phrygian scale over the same root — it is
  always in key, and **register is placed on purpose** so low, middle and high are occupied
  deliberately rather than by whatever the voices came with
- **velocity is structure**: each recipe shapes accents as downbeat, backbeat, a rolling
  crescendo, deliberately eroded, or flat
- **pan is allocated across the pattern**, not drawn per track, so two textures cannot stack
  in the same place
- **the pattern varies over repeats** — living steps and step-cycle conditions mean a bar is
  longer than its bar
- **at most 2 FX inserts and only ever one reverb**, at moderate wet
- a **density cap** thins the busiest non-pulse voices when the whole thing gets too full

**It judges its own work.** Several candidates are built to the chosen recipe and scored
against the ways these patterns actually fail — everything sounding at once, no rhythmic
contrast, near-dead tracks, two tracks doing the same job, everything in one register, no
accent variation, nothing changing over repeats, one effect everywhere, and density having
drifted from the brief. The weakest track is regenerated, and the best candidate is kept.
The recipe itself is chosen *before* that loop, so scoring picks the best take **at** a brief
rather than quietly preferring the briefs that score well.

**The CPU budget** (this is what fixes the XRuns). FX are per-track *inserts*, not
sends, and voices are spawned per hit — so a wide, expensive pattern could genuinely
overrun the audio thread. Every engine and effect was **measured on the device**
(`scsynth /status`, one track at density 0.5, over a 4.9% idle baseline):

| Engine | %CPU/track | | FX | %CPU each |
|---|---|---|---|---|
| DRUM | 5.3 | | CRSH | 0.8 |
| FM7 | ~8.5* | | RING | ~1.5* |
| BUCHLOID | 6.0 | | VERB | ~5.5* |
| RINGS / SHAKER | 9.6 / ~7* | | AMP | 1.7 |
| BEN | 9.7 | | GREY | ~4.5* |
| MOLLY | 11.7 | | OD | 2.5 |
| NOIZEOP | 12.0 | | CLDS | ~6.0* |
| ICARUS | 13.2 | | RESO | ~2.0* |
| MEMBRANE / MALLET / BOWED | ~9 / ~7 / ~8* | | | |
| PLUCK / TUBE / CHAOS | ~7 / ~7 / ~8* | | | |
| WTABLE | ~9.5* | | | |
| BYTEBEAT | ~6* | | | |
| SAMPLE | ~3* | | | |
| CSOUND | ~0 (SC side)† | | | |

† CSOUND costs the SC server almost nothing — its voice is a two-channel passthrough. The
work happens in the Csound process, which is not in this budget at all: it is a separate
JACK client on its own core, measured at roughly 20-25% of one core with four Csound
tracks running.

Reverb costs as much as an entire ICARUS voice, and ten expensive tracks with three
reverbs came to **~160% CPU** — which is exactly what XRuns sound like. The generator
now estimates cost from these numbers (scaled by density, since concurrent voices
saturate at the poly cap) and **thins, then drops, the priciest non-kick voices until
it fits a 52% budget** — leaving ~45% headroom for peaks. Measured across 10 generated
patterns on the device: **worst sustained 47%, worst peak 50%**.
- **Tempo is the algorithm's call**, judged against what it just built: a busy,
  texture-heavy pattern lands slower so it stays legible; a sparse one can run fast.
  It spans roughly 85–175 BPM (with the occasional outlier for character), and becomes
  **that pattern's own tempo**.

The generated tracks are laid out **contiguously from track 1 and grouped by engine**
(in palette order — DRUM · FM7 · BUCHLOID · MOLLY · RINGS · BEN · NOIZEOP · ICARUS · PLAITS · SHAKER · MEMBRANE · MALLET · BOWED · PLUCK · TUBE · CHAOS · WTABLE · BYTEBEAT · SAMPLE · CSOUND,
with roles in musical order inside each block). Since the step buttons are coloured by
engine, a generated rig reads as **contiguous colour blocks** rather than a scatter.

### Phrase-quantised arming (QUAKE only)

[QUAKE](#quake) swaps the rhythmic structure itself, and engaging that mid-phrase is what
makes a good effect sound like a mistake — the ear hears the seam rather than the effect. So
a QUAKE press states an intent and `phrase.py` picks the bar, on the way in and on the way
out.

It was tried on [SHUFFLE](#shuffle), [BREAK](#break) and [STROBE](#strobe) too and removed:
those three either carry their own timing already (Break counts cycles) or read as an effect
being switched rather than a structure being replaced, so making them wait only delays the
press without making the seam sound better. They engage immediately, as does
[CHURN](#churn) and the [step randomizers](#per-parameter-step-randomizers).

**The phrase is computed from the pattern, not assumed to be a bar.** Every track has its own
length and its own clock rate, so 12 steps at rate 1 against 16 at 3:2 does not come back
round for three bars — and the moment they all realign is the one place in the piece where a
change costs nothing. That is the LCM of the per-track cycles, taken in **exact rationals** so
a 3:2 rate is not rounded into a cycle that never lines up, then snapped to a musical length
(an exact LCM of 11 bars is arithmetically right and musically useless).

**Seam quality** ranks the candidates — phrase boundary, half, quarter, plain barline — and
**onset density** adjusts it: a change *into* a sparse bar or *out of* a busy one is masked by
the music either way. Density is found by replaying each track's own clock across the phrase,
since under polymeter the bars of a phrase are genuinely not interchangeable.

**The threshold decays**, so nothing armed can hang: it starts out holding for a phrase
boundary and by one full phrase accepts any barline. **The longest anything waits is one
phrase.**

**The QUAKE pad tells you which of the three states it is in, and it tracks the AUDIO rather
than your thumb** — there is a gap of seconds between the press and the sound, so it has to:

| | pad |
|---|---|
| pressed, waiting for the phrase | **steady amber** |
| taking effect | **blinking** |
| pressed again, still taking effect | **still blinking** |
| finished | **off** |

Pressing again *while armed* cancels rather than queueing — the gesture means "no, not that".
**Shift + pad** engages immediately: waiting is right nine times out of ten and wrong on
stage. The pad deliberately does **not** flip optimistically on the press the way the other
modifier pads do; that would blink instantly and then correct itself back to armed a frame
later, which is exactly the wrong story.

Measured on the device: SHUFFLE, BREAK and STROBE engage in **0.40–0.41 s** with nothing
armed. QUAKE: press → `armed`, engaged 1.02 s later; press again → still engaged and armed;
released 4.68 s later. Zero controller errors.

### Quake

The third temporary modifier, beside HEAT and SHUFFLE, and like them an **engine-only
overlay**: it never touches the pattern. Toggle it off and every track is back on its own
length and clock, immediately, with nothing to undo.

It reshapes the rhythm two ways at once:

**Polymeter** — tracks are given different lengths. A 15-step track against a 16-step one
shifts by a step every bar and comes back into phase after 16; a 12-step track realigns
after 4. Quake deliberately mixes lengths that *share* a factor with 16 (12, 14, 20, 24 —
you hear them resolve) against lengths *coprime* with it (11, 13, 15, 17, 19 — they walk
all the way round), so some relationships close quickly while others keep moving underneath.

**Polyrhythm** — tracks are given ratio clock rates: 3:2, 4:3, 5:4, 7:5, 7:4, 9:8 and their
inversions, applied as multipliers on the track's *existing* rate so a track already at x2
stays fast. The engine's clock is a float accumulator, so these are as native as a power of
two — the knob ladder only exposes /8…x8, and this reaches between them.

What keeps it musical rather than arbitrary:

- **An anchor is never moved.** The busiest drum-like track keeps its own length and rate,
  so there is still a pulse to hear everything else against.
- **Density decides how hard a track is hit.** A busy track gets a small length change *or*
  a mild ratio, never both — a dense part under a 7:4 clock is mush. A sparse track can take
  the wild end, where it reads as counter-rhythm.
- **At least one drum always moves.** Exempting the whole rhythm section left the change
  happening underneath the part the ear actually tracks, and it barely registered.
- **No two tracks get the same transformation**, or they move together instead of against
  each other, which is the one thing this is for.

Measured on the device: bar-to-bar similarity **+0.81 with Quake off, +0.33 with it on, and
+0.80 again after switching off** — the pattern stops repeating per bar while it is engaged
and goes straight back afterwards. Still clearly positive, not near zero: the material stays
recognisable, which is the point.

### Churn

The fourth temporary modifier. Churn records short fragments of the **master output**,
transforms them with **CDP** (the Composers Desktop Project), and drops the results back
into the performance where there is room — so the piece is continuously ornamented with
mutated versions of itself.

It is the only route into a whole class of sound the rest of the instrument cannot make.
CDP's processes are *offline* — spectral blurs and averages, waveset mangles, brassage,
time warps — and cannot run in an audio callback at all. Churn puts them in a live set.

**The loop.** One fragment is captured (0.5-1.6 s), transformed, and loaded while the
fragments already loaded are still being played, so the stream never gaps. Four slots are
in rotation; each ornament is played **1-4 times** before being discarded and replaced —
long enough to register, short enough not to become a loop. Measured on the device: a chain
takes ~0.13 s, which is what makes a continuous pipeline affordable at all.

**The transforms** are grouped into families — spectral (blur, scatter, average, time
stretch), waveset (repeat, multiply, reverse, average), time/pitch (varispeed, brassage) and
granular (bounce) — and a chain draws its two stages from *different* families, because a
blur on a blur is still a blur while a waveset mangle on a spectral smear is a new sound.

**Placement is the point.** An ornament goes where there is space: every step is scored by
how many tracks hit it (plus the step after, because the tail is still sounding), beats and
bar lines are penalised even when empty, and Churn takes from the quiet end of that ranking
— and not every bar. It fills gaps rather than competing, and it sits **under** the music at
a fraction of full level.

**Non-destructive by construction.** Churn never writes to a track: it reads the master bus
and plays into the master bus. Toggling off frees its buffers and the ornaments simply stop
— there is nothing to restore. Verified on the device: the whole machine's state
fingerprint is identical before, during and after a run.

> CDP is vendored in the repo (`move/bundle/poundhard-cdp.tar.gz`, built by
> `move/build-cdp.sh`) and installed to `$PH/cdp` — 220 aarch64 programs built from source,
> since CDP has no distribution package. It bundles its own soundfile library, so its only
> runtime dependencies are libc/libm/libstdc++ and there is nothing to vendor alongside it.
>
> One trap worth knowing if you extend this: **CDP refuses to overwrite an existing output
> file**, exiting non-zero and writing nothing. Reuse a destination path and it works
> exactly once, then fails silently forever — which on a continuous loop looks like the
> feature switching itself off.

### Break

The fifth temporary modifier. Every N pattern cycles Break takes over for **one cycle**,
transforms what the rig is playing, and hands it straight back. **Hold the pad and turn the
jog wheel** to set the interval — 1, 2, 3, 4, 6, 8, 12, 16, 24 or 32 cycles, default 4. A
hold that changes the interval is not also a toggle, so dialling the rate in doesn't flip
the mode on the way out. The pad goes **solid white on the bar a break is actually running**,
so you can see it happen rather than only that the mode is armed.

Both edges land on a cycle boundary, which is what makes a break sound *placed*: the pattern
goes away at the top of a bar and comes back at the top of the next.

**Break and Quake lock each other out.** Both temporarily own a track's length and rate, and
Break's restore re-pushes the controller's originals — so with both engaged Break silently
wiped Quake's overlay every time a break ended. Rather than pick a winner parameter by
parameter, only one may hold the rig at a time: engage either and the other's pad turns
**grey**, and pressing it says which one is holding it rather than doing nothing. Switching
the holder off releases the lock immediately. Grey means the same thing on both pads, so it
reads as one rule rather than a per-pad quirk.

Nine break types, chosen from what the pattern can actually support and never the same one
twice running:

| | |
|---|---|
| **dropout** | the melodic material goes; what's left is what the ear was keeping time with |
| **kick only** | stripped to the pulse — the drum whose hits sit most on the beat |
| **percussion only** | the inverse: the kit exposed, sometimes without even the kick |
| **stutter** | the bar folded down to a 2, 3 or 4-step loop — same material, phrase gone |
| **displacement** | tracks rotated against each other; nothing removed, the bar just lands wrong |
| **pause** | a hole for the last beat or two, so the downbeat after it lands hardest |
| **filtered** | the rig keeps playing but loses its top, so the return is a lift |
| **half time** | the rhythm section dragged to half speed |
| **build-up** | thin at the top of the bar, everything by the end — it leads back *in* |

It is built from four primitives the engine already has, none of which edits a sequence:
mute, a temporarily-pushed step list, clock rate, and the per-track filter. Pushing a
different step list to the engine leaves the pattern data completely alone, so restoring is
just re-pushing the controller's own state — it cannot drift.

Measured on the device with breaks every 2 cycles: bar-to-bar similarity sits at **+0.73
with Break off** (the pattern repeating as programmed) and falls to **+0.30 with it on**,
dipping to **−0.76** on the strongest breaks — bars that share almost nothing with the one
before. The machine's state fingerprint is identical before, during and after.

### Whim

**The seventh pad on the bottom row.** Whim's defining feature is **tempo modulation**: it
does not touch the master tempo, it continuously modulates the playback *speed* of a subset
of the active tracks. The groove breathes, sways and bends — parts rush ahead and linger
behind and then fall back into place — while everything stays locked to the master clock.

**Whim never adds notes.** Ratchets and rapid repetitions are another modifier's job. Whim
expresses itself by reshaping the flow of time, not by filling it.

**The tempo modulation**

- **A subset of tracks, re-chosen every few bars.** Not everything: if every track wobbles,
  nothing is wobbling *against* anything and the result just sounds like an unsteady tempo.
  Holding some parts firm is what makes the modulated ones audibly elastic.
- **Each selected track gets its own modulator** — its own waveform, its own division of the
  bar, its own depth and **its own phase**. Without independent phases every track would
  reach its fastest point at the same instant and the whole pattern would surge together.
  Re-selection re-rolls the curve, so being picked twice never means the same wobble twice.
- **Waveforms are sine, triangle and a smooth multi-sine wobble** — continuous curves, no
  abrupt jumps in playback speed.
- **Every rate is a division of the bar** — 4 bars, 2 bars, a bar, 1/2, 1/2 dotted, 1/2
  triplet. Nothing free-runs, so a tempo change carries the whole modifier with it.

> **Why "smooth random" is not actual random.** True random-smooth interpolation is the
> obvious choice here and it is wrong: its average over a cycle is not zero, so a track gains
> or loses a little time every cycle and walks away from the grid permanently. The `wobble`
> curve adds two quiet harmonics at their own phases — the same wandering, never-quite-
> repeating character — while integrating to *exactly* zero. Elasticity without drift.

**Gestures, decided once per bar** (temporal ones weighted highest, since that is the point):

| | |
|---|---|
| **slow** | the track hesitates, then runs on and lands back on the grid |
| **surge** | it pushes ahead, then settles back |
| **stop** | a short hole — a sixteenth up to a quarter of the bar |
| **colour** | one parameter thrown somewhere else for the duration of the gesture |

**Alongside it**, per-track filter cutoff moves within a few octaves of what you programmed,
on a sine, triangle, random-smooth or sample-and-hold curve. Resonance is *nudged*, never
swept: a resonant filter driven hard by an LFO self-oscillates and stops being a filter.

**Why it does not fall apart**

- **Time modulation is zero-mean, and so are the gestures.** The slow/surge envelope is a
  *full* sine, which integrates to exactly zero — the track hesitates, then runs on by
  precisely what it lost. A half-sine would steal phase it never recovers.
- **Gestures are budgeted** — at most three tracks doing something disruptive at once.
- **The pulse is protected.** Whatever carries the beat is selected for wobble far less
  often and largely spared stops — measured, it receives about 5% of gestures where an even
  share would be 20%. Bending the beat now and then is lovely; bending it constantly just
  sounds like a bad clock.
- **It reads the room.** Intensity falls from 0.93 on a sparse pattern to 0.70 on a dense one
  and to 0.48 with three other modifiers running, never below 0.35.

**Non-destructive**, like every modifier here. Whim writes nothing to the project; rate,
filter, mute and parameter changes go to the engine and every one is remembered. Switching it
off — or a track simply leaving the modulated subset — restores the programmed value exactly.

---

### Strobe

The sixth temporary modifier: **rhythmic gating** and **microlooping** on the track buses,
together or apart.

| | |
|---|---|
| **GATE** | rhythmic amplitude gating — `gDiv` gates per bar, `gDuty` of each one open, `gDepth` how far it shuts |
| **MICROLOOP** | a slice of bar/`lDiv` seconds recirculated in the engine, so a fragment repeats |

**Everything is a division of the bar.** The engine publishes a single bar-phase signal
(`\phSync`, an audio-rate phasor at the head of the graph) and every Strobe insert derives
its own sub-phase from it. Nothing is ever given a rate in hertz or seconds. That is what
keeps a 3-per-bar gate on one track and a 1/16 microloop on another locked to the bar *and to
each other*, at audio rate, and makes both follow a tempo change without being rebuilt.
Divisions are deliberately not restricted to powers of two — 3, 5, 6 and 7 per bar are
exactly as locked as 8 or 16, they just land somewhere more interesting.

**It is a per-track insert, not a master effect**, sitting between the per-track FX and the
send. That is what lets it take a subset: gating everything at once is a tremolo on the mix,
gating three of sixteen tracks is an arrangement.

Three things keep it from being applied uniformly:

- **Targeting** — a subset of tracks, re-chosen every few bars. Occasionally everything, more
  often a handful. Tracks carrying the pattern (the drums, or anything more than half full)
  are weighted *down* rather than excluded: gating the kick occasionally is an effect, gating
  it every bar is just the beat.
- **Distribution** — each effect owns a **window within the bar** (`gFrom`/`gSpan`,
  `lFrom`/`lSpan`), quantised to sixteenths, so it can take the last quarter of the bar or the
  middle eighth rather than running end to end. Windows move independently per track, which is
  what stops sixteen gated tracks sounding like one gated mix. Each track also gets its own
  gate `gSkew`, so several gated tracks interlock instead of pumping in unison.
- **Density** — how many tracks, how wide the windows and how deep the effect all move
  together on a slow cycle of 8–24 bars, so it breathes rather than chattering at a constant
  rate.

**Non-destructive**: the inserts live on the track buses and touch no pattern, parameter or
track state. Switching off frees them and the tracks are exactly as they were — so, like the
modifier it replaces, it does **not** join the [Quake](#quake)/[Break](#break) lock.

**How much of the time it is actually on** is a design parameter, and the first version got
it badly wrong: roughly two of five tracks, a mode that often chose nothing, and windows as
short as 6% of the bar. Multiplied together the effect was present about **5%** of the time —
inaudible, which is not the same as subtle. Every targeted track now always gets at least one
effect, the density floor is 0.4, windows are mostly half a bar or more, and a **SLAM** fires
now and then: every live track, full bar, full depth. Coverage measured offline over 200 bars
went from ~0.05 to **0.79** effect-bar-fractions per track-bar.

**Nothing reaches the audio path as a step.** `gWin`/`lWin` are comparisons on the bar
phase, so they are hard 0/1 signals and a window opening mid-bar stepped the gain instantly;
`gMix`/`gDepth`/`lMix` arrive over OSC between bars and were applied raw, so a track going
from clean to gated jumped by the full depth in one sample; and `lTime` jumped whenever the
algorithm chose a new division, which is a delay line being asked to teleport. All three were
clicks. Each is slewed now — the window fades slowest, because 12 ms of equal-power fade is
inaudible as a fade and very audible as an edge.

**The bar phase is re-synced every downbeat**, from the same code path that fires the
downbeat's notes. `\phSync` is a sample-accurate phasor and the sequencer runs off a
TempoClock: they agree on average, but nothing corrected the error between them, so the
windows crept away from the pattern over a run — and a tempo change re-rated the phasor
without re-aligning its phase at all. When it is already in sync the phasor is wrapping to 0
at that instant anyway, so the correction is a no-op rather than a jump.

Measured on the device, off / on / off again: bar-to-bar similarity **+0.70 / +0.34 /
+0.68**, RMS **−9.0 / −11.0 / −9.1 dB**, and envelope **modulation depth −4.4 / −9.2 /
−4.6 dB** — the gate is cutting holes more than twice as deep as the music's own dynamics.
Peak **0.950 with zero full-scale samples** throughout, no controller errors, and it restores
exactly.

**Transients:** large sample-to-sample steps run at **5.2/s with Strobe on against 11.0/s for
the dry pattern**, and the largest steps are *smaller* with it engaged (0.129 vs 0.159) — it
adds no discontinuities of its own.

**Sync:** with a gate forced to 4 per bar at 123 BPM (expected period 0.4878 s), the
strongest periodicity in the recorded audio is at **0.4876 s — 0.2 ms off, and it is the
global maximum**, with no drift across a 30-second take (first half +0.455, second half
+0.484).

> **Softcut is still in the tree but unused.** `PhSoftcut`, `move/build-softcut.sh`, the Lua
> runtime and `controller/compass/` remain built and deployed; nothing calls them. The COMPASS
> modifier that used them was abandoned — it never reproduced its input (see the commit
> history), and Strobe replaces it on the same pad.

### Csound architectures and recipes

Engine 20 has **26 architectures**. Ten are the hand-written designs listed above; the
other sixteen are **chains**: a generator core followed by an ordered sequence of shapers.

**The chain is the architecture's identity as much as the core is.** There are twelve
shapers — resonant filter, spectral blur, frequency shift, bitcrush, ring modulation, tuned
comb, wavefolder, sub-octave, inharmonic resonator bank, stutter, decimation and spectral
freeze — and the *order* is load-bearing. `METALBANK → CRUSH` is a struck body that is then
damaged; `CRUSH → METALBANK` is damage given a body to ring in. They are different
architectures and they do not measure as one. Each shaper also carries constants baked from
its architecture's seed, so a shaper appearing in two chains never sounds the same twice.

> **If you used PoundHard before this was fixed, you never heard any of them.** The engine
> clipped the architecture index to a bound written when ten was all there was, and clipping
> *pins* rather than drops — so every architecture from ten upward played as one instrument:
> two detuned oscillators into a feedback-delay wash. Since the palette weights the newer
> architectures more heavily, the majority of every draw was that single washed instrument.
> "Variations of white noise and not much else" was an exact description of what the code
> did. Fixed, with a build-time check that now fails if the orchestra, the engine and the
> controller ever disagree about how many architectures exist.

**Recipes name points, not boxes.** The variety problem was never the *number* of
architectures but **how the eight macros were drawn**. A uniform draw in eight dimensions
lands near the middle of the box virtually every time — measured over 4000 rolls, the mean
per-macro distance from centre was **0.20 of a possible 0.40**, and only **1.2%** of rolls
got even half their macros near an extreme. So each *pole* is a complete eight-macro vector
known to be a distinct sound in that architecture; a roll picks a pole, wanders a little way
off it, and occasionally rides one or two macros the rest of the way out. The extremes are
reachable because they are aimed at rather than hoped for.

| | before | after |
|---|---|---|
| architectures | 10 | **26** |
| recipes | 10 | **40+** |
| mean per-macro distance from centre | 0.201 | **0.278** (max 0.40) |
| rolls with 4+ macros at an extreme | 1.2% | **36.2%** |

**Levels are now matched.** Every architecture is peak-trimmed to the same target from a
measured render — the spread across all 26 is **1.0×**, where it had been over 30×. (Getting
there required fixing the measurement itself three times: probe notes were spaced closer than
the envelope releases so every note summed into its neighbour's window; the output stage
soft-clips, so scaling a clipped measurement is not invertible; and the trim file's columns
were being read in the wrong order, which applied each raw peak *as* its own trim — the one
error that makes a loud voice louder.)

### The chaos macro (knob 8)

In the tracks view, **knob 8 sweeps every parameter of every engine currently assigned
to a track**, all at once. Each parameter gets its own **random direction**, so a single
turn pushes some values up and others down regardless of which way you turn the knob —
one gesture smears the whole machine.

**Position 0.5 is the safe zone**: exactly the stored state, captured the moment you
first move the knob. Turning either way drifts away from it, and the two directions
give different deviations.

Two ways back:
- **turn knob 8 back to centre** — the values return to where they were, or
- **Shift + touch knob 8** — jump straight back to the safe zone.

Each parameter's excursion is scaled by its own musical range and clamped to its
absolute limits, and **amp/pan are excluded** — so chaos re-voices the machine without
blowing up levels or collapsing the stereo image. Loading a pattern, assigning an engine
or randomising re-takes the safe zone, since the old baseline no longer means anything.
The readout stays on screen the whole time the knob is **touched**.

### Living steps & the HEAT button

A **living step** plays normally most of the time, then — every so often — **transforms
itself**: a fresh, randomly-rolled mutation of that one hit, held for a single repeat and
then reverted, so the groove keeps re-inventing its own accents. It's built for live
performance: mark a few steps and the pattern stays recognisable but never quite repeats.

**Mark a step** in the [edit view](#edit-view-per-track) with **Rec + pad** (living steps
pulse **pink**). Then **hold that step**: row 3 sets how often it *plays*, row 4 how often it
*transforms* — the same eight-pad, cycle-counting gesture for both, which is what makes the
pair easy to reason about.

Row 4 is counted in **plays of that step**, not bars, so the two multiply:

| Row 3 (plays) | Row 4 (transforms) | Result |
|---|---|---|
| 1 | 4 | plays every cycle, transforms every 4th play — every 4 cycles |
| 2 | 2 | plays every 2nd cycle, transforms every 2nd play — every 4 cycles |
| 3 | 2 | plays every 3rd cycle, transforms every 2nd play — every 6 cycles |
| 4 | 3 | plays every 4th cycle, transforms every 3rd play — every 12 cycles |

You decide **when the step speaks**, then independently **how often it says something new**.
Because the count is in plays rather than bars, it holds whatever the track's length or clock
rate — a step on a 2-bar loop still transforms every *N* times you actually hear it.

When a living step fires, one or more **flavours** are stacked and driven hard for something
you can actually hear — never a timid nudge:

- **character / filter** — the engine's own defining params slammed toward their rails
  (Plaits `morph`/`harmonics`, Rings `structure`/`position`, MOLLY's fold/crush/drive, a
  filter sweep). Tonal engines get a genuine timbre lurch, not a whisper.
- **pitch** — octave/fifth leaps, snapped back into the scale (skipped on drums, which spend
  that flavour on more character instead)
- **ratchet** — an occasional 2–4× retrigger with a velocity taper
- **pan** — a hard stereo throw
- **delay / reverb** — the hit is routed through a dedicated **per-step send bus**
  (`phLivingFx`: a feedback `DelayC` + `FreeVerb2`), with randomised time / feedback / room.
  Because it's a private bus keyed to that one step, the tail lands **only** on the marked
  hit — no bleed onto the rest of the track.

The engine fires `/ph/cycle` each bar; the controller [analyses the pattern and rolls the
next transform](../controller/poundhard/tracks.py) (`reroll_living` / `tick_living`), holding it
armed for a **full loop** so the marked step is guaranteed to sound while the mutation is live.

**HEAT** — the **first pad of the bottom row** in the tracks view — is the whole thing as a
one-touch live macro. A **short press toggles it**: when on, **~50 % of every sequenced
track's hits** become living steps at once, each with a period spread over **2–6** (with
variety inside each track) and **staggered phases** so they don't all mutate on the same bar
— the performance gradually comes to a boil rather than lurching. **Hold the HEAT pad and
turn knob 1** to set the amount (giant `HEAT %` readout); raising it re-heats live at the new
density. HEAT is **strictly non-destructive**: engaging it snapshots the exact per-step base
state, and **toggling off restores the pattern precisely** — every marked cell's note/velocity/
pan locks, ratchet and send are reverted to their pre-HEAT values and reset in the engine (all
of them, not just the ones mid-transform), so nothing vestigial survives. The next press rolls
a fresh configuration. The pad glows a **fire pulse** while engaged, and the tracks-view screen
shows `HEAT %`.

> HEAT is a **temporary performance overlay**: its marks are never saved with a pattern, and
> it leaves any **hand-placed** (Rec+pad) living steps alone — toggling HEAT off clears only
> what HEAT added. Save a pattern with HEAT blazing and you get back the clean pattern, heat
> not baked in.

### SHUFFLE

The **second pad of the bottom row** (right of HEAT) is **SHUFFLE** — a live remix of the
current pattern's *rhythm*. Toggling it **on** swaps the **steps, length and clock rate**
between the sequenced tracks (a random **derangement** — every track plays a *different*
track's rhythm, keeping its own sound). Each track becomes someone else's groove: the kick's
four-on-the-floor lands on a hat, a busy hat pattern drives the bass, and so on. **The more
tracks you have playing, the more configurations** are possible (N tracks → up to !N
derangements), and **every toggle-on rolls a fresh one**. Toggling **off** restores the
original rhythm exactly.

Like HEAT, SHUFFLE is a **temporary, engine-side overlay** — it never touches the stored
pattern, so it's not saved and can't corrupt your work; switching patterns or loading a
project drops it. The pad glows a **cyan pulse** while engaged, and the tracks-view screen
shows `SHUF`.

**HEAT and SHUFFLE compose.** With both engaged, HEAT **follows** the shuffle: its living
steps re-mark onto the *migrated* rhythm each engine track now plays (using that track's own
sound), so the heat transforms fire on the cells that actually sound — in either order, and
every time the shuffle re-rolls.

### Autosave

The controller **autosaves the whole project** (all 32 patterns plus the live state) to
a **recovery file** — `projects/autosave.json`, deliberately separate from your 32
project slots, so it **never overwrites anything you saved by hand**. It writes only
when something actually changed, and no more than once every 30 s (`PH_AUTOSAVE_SEC`):
a project is a chunky JSON and SD churn is what makes the Move's UI stall.

**Shift + Menu** in the project view restores it. The project view shows whether a
recovery file exists.

### Generate a variation

In the pattern view, **Shift + Track 3** generates **one** new pattern derived from the
**reference pattern** (the one currently selected), into the next empty slot — related
enough to read as another **part of the same piece**, distinct enough to be its own.

Because it returns a *single* pattern, it can't lean on "one of eight will land".
Instead it builds a **pool of 14 candidates** and keeps only the **best-scoring** one.
The score is what a good variation actually is: **distinct** (a groove distance near
0.38 — barely-changed and unrecognisable are both punished), **arranged** (its parts
interlock with the anchor rather than doubling it), **sane** (density in range, no
voice silenced), and **affordable** (candidates over the CPU budget are rejected
outright, never returned). It also rewards a variation for saying something new — a
moved melody, or an introduced instrument. Measured over 300 seeds, scoring lifts the
result from a mean of 28.9 to 55.9 versus a single unscored draw.

It **analyses before it generates**
([`controller/poundhard/variations.py`](../controller/poundhard/variations.py)): which
tracks play and how densely, each track's onsets and role (the kick becomes the
**anchor** and is held nearly fixed), and the piece's **pitch material** gathered
across every saved pattern — so new melodic material stays in key. Each candidate then
gets its own intensity and its own choice of additions, so the pool genuinely varies
before the best is picked:

- **Rhythm** — Euclidean re-interpretation at similar density, rotation/displacement,
  thinning, off-beat thickening (syncopation), end-of-phrase fills; the anchor barely
  moves and no track is ever emptied.
- **Melody** — expressed as **per-step pitch locks** (never the track's default note,
  so the *sound* is untouched): the line is transposed by a consonant interval and/or
  given stepwise contour, everything **snapped back into the scale**.
- **Feel & structure** — light velocity accents, the odd mute for contrast, an
  occasional polymetric length change on a non-anchor voice.
- **New instruments (sparingly)** — when there's a clear gap and empty tracks, it may
  add **0–2 complementary voices** (e.g. an ICARUS pad, or a NOIZEOP / hi-hat shimmer).
  Because patterns are self-contained, a variation simply **carries that instrument's
  sound itself** — your seed pattern is never touched, and the instrument appears only
  in the sections that use it.

The variation carries the seed's sounds **verbatim** and transforms only its groove —
that's the family resemblance — and inherits the reference pattern's tempo. Generating
is **non-destructive**: the pattern you're on is left exactly as it was.

---
