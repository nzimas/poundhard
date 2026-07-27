<p align="center">
  <img src="web/poundhard-logo.svg" alt="PoundHard" width="560">
</p>

# PoundHard

**A 16-track groovebox takeover for the Ableton Move** — built for edgy IDM,
rhythmic noise and percussion-centric experimental electronica.

A SuperCollider engine carries the DSP, a Python controller holds the
authoritative musical state, and a Schwung `ui.js` drives the Move's pads, step
buttons, encoders and screen. It began as a fork of the *wildrider* takeover's
plumbing and is now **self-contained**: it ships its own SuperCollider *and* JACK
runtime, so **Schwung is the only thing it needs on the device**.

```
 Move pads / buttons / knobs / screen
        │  ▲
        ▼  │  (ui.js — the Schwung "overtake" module)
   ipc/control.json   ▲ ipc/status.json
        │             │
        ▼   (file bridge, polled)
   controller  (python — poundhard.headless, authoritative Project state)
        │  ▲
        ▼  │   OSC  /ph/…  →  ← /ph/step /ph/cpu /ph/cycle
   engine  (sclang — 19 engines × 16 tracks + TempoClock step sequencer + FX chains)
           running on SUPERNOVA (multicore SC server; ParGroups spread tracks over cores)
        │
        ▼
   supernova → jackd → Move speaker / output
           (both vendored in PoundHard's own runtime bundle)
```

---

## Contents

- [The instrument](#the-instrument)
- [Sound engines](#sound-engines)
- [Controls](#controls)
  - [Tracks view](#tracks-view-default)
  - [Edit view](#edit-view-per-track)
    - [Cycle frequency](#cycle-frequency)
    - [Track filter](#track-filter)
    - [Per-step FX](#per-step-fx)
  - [FX view](#fx-view)
  - [Pattern view](#pattern-view)
  - [Project view](#project-view)
  - [Recorder view](#recorder-view)
- [Sounds & the engine palette](#sounds--the-engine-palette)
- [Patterns & projects](#patterns--projects)
- [The chaos macro](#the-chaos-macro-knob-8)
- [Living steps & the HEAT button](#living-steps--the-heat-button)
- [Autosave](#autosave)
- [Recording & the web UI](#recording--the-web-ui)
- [Deploy to the Move](#deploy-to-the-move)
- [Develop off-device](#develop-off-device)
- [Architecture & internals](#architecture--internals)
- [Wire protocols](#wire-protocols)
- [Repository layout](#repository-layout)
- [Gotchas](#gotchas)
- [License & disclaimer](#license--disclaimer)

---

## The instrument

- **16 tracks**, one per step button. Tracks start **empty** (dark, silent); you
  build your rig by assigning engines from the **engine palette** (see below). Any
  engine can go on any track, and the assignment is **per pattern** — two patterns can
  carry completely different rigs.
- **19 assignable engines** on the palette pads — the first 16 fill the top two rows (row 1
  DRUM..ICARUS, row 2 PLAITS..CHAOS) and **WTABLE**/**BYTEBEAT**/**SAMPLE** sit on row 3
  (cells 16-18), each in its own colour:

  | Pad | Engine | Colour | Character |
  |--------|--------|--------|-----------|
  | 1 | **DRUM** | 🟡 yellow | digital drum — kick/snare/hat/metal/clap/tom/noise |
  | 2 | **FM7** | 🟢 green | real 6-operator FM — bells / e-pianos / clangs / FM bass / stabs |
  | 3 | **BUCHLOID** | 🟣 magenta | Buchla complex osc — drone / noise texture |
  | 4 | **MOLLY** | 🔵 blue | gritty Moog-ladder subtractive lead/pad |
  | 5 | **RINGS** | 🩵 cyan | Mutable Rings modal / sympathetic resonator |
  | 6 | **BEN** | 🟠 orange | Benjolin — chaotic generative machine |
  | 7 | **NOIZEOP** | 🩷 pink | 4-sine / 6-algorithm glitch-noise machine |
  | 8 | **ICARUS** | 🟪 violet | dreamcrusher drone / pad (VarSaw + FB delay) |
  | 9 | **PLAITS** | 🟩 lime | Mutable Plaits — 16-model macro-oscillator |
  | 10 | **SHAKER** | 🟨 amber | STK Shakers — 23 shaker/scraper models (maraca, cabasa, tambourine…) |
  | 11 | **MEMBRANE** | 🟥 warm red | struck 2D-waveguide membrane — tunable drums / frame drums / gongs |
  | 12 | **MALLET** | 🟡 gold | STK ModalBar — marimba / vibraphone / agogo / wood / bells |
  | 13 | **BOWED** | 🟦 teal | STK BandedWG — bowed/struck metal bars, glass harmonica, Tibetan bowl |
  | 14 | **PLUCK** | 🟩 spring | DWG plucked stiff string — koto / clav / harp / muted plucks |
  | 15 | **TUBE** | 🟦 sky | TwoTube waveguide — hollow formant plucks / reedy tones |
  | 16 | **CHAOS** | 🟥 red | chaotic-map oscillator — FBSine / Latoocarfian / Henon / Standard / Cusp (glitch/noise) |
  | 17 | **WTABLE** | 🟪 violet | Ableton Wavetable rebuild — two morphing wavetable oscillators over the Move's own factory sprites |
  | 18 | **BYTEBEAT** | 🟢 green | ByteBeat UGen — 8-bit algorithmic expressions (`t*(t>>5\|t>>8)` …) evaluated at audio rate |
  | 19 | **SAMPLE** | 🌹 rose | capture engine — records another engine, mangles it through a **Csound** opcode graph, plays it back |

- **Engine palette** (top row of pads, default view): **short-press** a pad to
  audition its current sound; **Shift + pad** to regenerate it; **hold a pad and
  tap a track** (step button) to assign that engine + sound to the track. Assigning
  keeps the track's existing sequence — only the sound changes.
- **16-step sequencer per track**, each with independent length and clock rate
  (**polymeter** — tracks phase against each other), and a per-step **cycle frequency** so
  a step can fire once every 2-8 repetitions.
- **Per-step locks** on pitch, velocity, pan, a **voice macro**, the **FX chain** and —
  on SAMPLE tracks — the **slice of the buffer** a step plays. Each step can carry its own
  tone, its own effects and its own fragment of the sample.
- **A multimode filter on every track** (cutoff / resonance / LP-HP) that keeps its bass
  and its level as resonance rises — see [Track filter](#track-filter).
- **Living steps** — mark steps (or hit **HEAT** for the whole rig) and they
  **transform themselves** as you play: ratchets, timbre lurches, pitch leaps, pan
  throws and per-step delay/reverb. A live-performance engine (see
  [Living steps & the HEAT button](#living-steps--the-heat-button)).
- **Copy gestures** — hold **Copy** and a step with data goes to the clipboard, an empty
  one receives it; hold Copy and press **Track 1 / Track 2** to grab or paste a whole
  **row** of eight steps. Everything travels: locks, living flags, ratchets, FX masks and
  cycle dividers.
- **Re-roll a track's sound** in place with **Shift + Track 1** while it's open —
  a fresh sound within its assigned engine. Patterns, mutes and locks survive.
- **Patterns are self-contained** — engines, every parameter, FX, mutes and sequences.
  Up to 32 per project, with projects saved to disk and an
  [autosave](#autosave) recovery file — see [Patterns & projects](#patterns--projects).

The step buttons for tracks that contain events **pulse at the pace of their
sequence**; assigned-but-empty tracks glow steady-dim in their engine hue, and
unassigned tracks are dark — so you can read the whole rig at a glance.

---

## Sound engines

All voices are **spawned per hit and self-free** (see [voice model](#voice-model)).

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

  The per-step trigger fires Plaits' own envelope and low-pass gate (`decay`,
  `lpgColour`), which is exactly PoundHard's per-hit voice model. Its two outputs are
  **OUT and AUX** — two *different* signals per model, not a stereo pair (the same trap
  that broke RINGS' panning) — so they're blended by an `aux` knob and then panned.

  **Each model is targeted, not randomised.** `model` doesn't merely change the timbre,
  it redefines what the three macro knobs *do*: `harm` is oscillator detune in the VA
  model, chord type in the chord model, grain density in the cloud, and punch in the
  bass drum. So every model has its own role in
  [`kits.py`](controller/poundhard/kits.py) — the job it does in a kit, the register it
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

> Csound ships as a **self-contained offline renderer** at `$PH/csound` (6.18, aarch64,
> 19 opcode plugins, ~10 MB). It needs only `OPCODE6DIR64` + `LD_LIBRARY_PATH`, and **no
> capabilities** — unlike supernova, it never touches the audio thread. Renders run on a
> background thread: a mangle takes seconds and must never stall the sequencer or the UI.

> **BYTEBEAT** needs a native plugin: `supercollider/plugins/ByteBeat/ByteBeat.so` is a
> **prebuilt aarch64 UGen** (static libstdc++, needs only GLIBC_2.17 — loads on the CM4's scsynth
> 3.13). `deploy-controller.sh` ships it to `$PH/plugins` and the `ByteBeat.sc` class to the SC
> Extensions dir. Rebuild it from source with `move/build-bytebeat.sh` (arm64 Docker).

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
| **Hold HEAT pad + Knob 1** | set the HEAT amount (% of hits marked) |
| **Play** (lit green while running) | start / stop the sequencer |
| **Knob 1** | master tempo (BPM) |
| **Knob 8** | **chaos macro** — sweeps every param of every assigned engine (see below) |
| **Shift + touch Knob 8** | snap back to the chaos macro's **safe zone** |
| **Undo** | step back one discrete action (20 levels, works in any view) |
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
| **Knob 4** (on a step) | **living period** — cycles between transforms (also marks the step living) |
| **Hold a step + row 3** | that step's **cycle frequency**: pad 1 = every pattern repetition (default), pad 2 = every second, … pad 8 = every eighth. Row 3 is dark unless a step is held |
| **Copy + step pad** | a step **with data** goes to the clipboard; an **empty** step **receives** it — copy and paste without letting go of Copy. Carries everything: the note/velocity/pan/macro locks, living flag and period, ratchet, send and per-step FX |
| **Copy + Track 1 / Track 2** | the same for a whole **row** of steps — row 1 is steps 1-8, row 2 is steps 9-16. The first row press of a Copy hold **grabs** that row; every press after it **pastes** onto the row pressed, empty or not. Release Copy to grab again |
| **Shift + step pads** | **select** steps for the per-step FX editor (selected = bright red) |
| **Shift + bottom row** | add / remove that effect on every selected step |
| **Shift + master knob touch + pad** | set that pad as the **last step** (polymeter, up to 16) |
| **Jog wheel** | track pitch (re-pitches ringing voices live) |
| **Knob 1 / 2** | track volume / pan |
| **Knob 3** | **voice macro** — one knob sweeps every timbral param of the voice, each in a random direction; the directions re-roll whenever the track's sound is regenerated |
| **Knob 4 / 5 / 6** | the track **filter**: cutoff · resonance · LP/HP (see [Track filter](#track-filter)) |
| **Knob 4 / 5** *(SAMPLE tracks)* | the sample's **playable window**: start / end, as a percentage of the buffer |
| **Knob 6 / 7 / 8** *(SAMPLE tracks)* | the filter, shifted by two so the window keeps 4 and 5 |
| **Hold a step + knob 4 / 5** *(SAMPLE)* | that **step's own** slice of the buffer — one step plays the attack, the next the tail. Unlocked steps follow the track. (The living period moves to knob 6 here) |
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

The counters reset when the transport starts, so a divided step lands on the downbeat and
then every Nth repetition after it. The divider travels with the step: it is saved with the
pattern, carried by the [copy gestures](#edit-view-per-track), and cleared with the pattern.

#### Track filter

Every track has a **multimode filter** ahead of its FX chain — knobs **4 / 5 / 6** for
cutoff, resonance and LP/HP, shifted to **6 / 7 / 8** on SAMPLE tracks where 4 and 5 are
already the sample window. It is transparent at its defaults (open lowpass, no resonance),
and it filters the *track*, not the reverb tails, because it sits before the inserts.

The UGen choice is the whole point. Ask a ladder (`MoogFF`) or a Butterworth `RLPF` for
resonance and you get 1970s behaviour: the passband is attenuated as Q rises, so a lowpass
drains its own bass and the level sags — you cannot sweep it without riding the volume
afterwards. PoundHard uses **RBJ biquads** (`BLowPass` / `BHiPass`), whose passband stays
at unity for any Q: resonance adds a peak at the corner without taking anything away below
it (LP) or above it (HP).

Measured on the device, 1 kHz lowpass, resonance 0 → maximum, with a 60 Hz probe:

| filter | bass at 60 Hz | output level |
|---|---|---|
| **RBJ biquad** (what PoundHard uses) | **+0.0 dB** | **+0.2 dB** |
| MoogFF ladder (for comparison) | −13.8 dB | −12.5 dB |

The peak itself is bounded by a soft clip on the way out, so a full-resonance sweep cannot
run away — and with the filter open and no resonance the dry signal is passed through
untouched rather than through a biquad's approximation of it.

#### Per-step FX

The bottom pad row of the edit view carries the same eight effects as the
[FX view](#fx-view) — `OD · AMP · CRSH · RING · CLDS · RESO · GREY · VERB` — and locks
them **per step**.

Hold **Shift**, tap the steps you want (they light **bright red**), then — still holding
Shift — tap effects on the bottom row. An effect lights **red** if *any* selected step
carries it; tapping it turns it **on everywhere** if it was missing anywhere, else **off
everywhere**, so mixed selections resolve predictably. Releasing Shift clears the
selection. Steps that carry FX stay marked in **dark red**.

A step's lock is a mask over the eight insert slots and **overrides the track's own FX
assignment for that hit only** — a step can switch effects on that the track doesn't have,
or mute ones it does. An effect that only a step uses is instantiated in the track's chain
**disabled**, and opened just for the locked hits, so nothing is spent on it otherwise.
Steps without a lock restore the track's normal chain, so a lock never leaks into the
following hits.

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

**Track 3** opens the pattern view — the 32 pads become **32 pattern slots**.

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

| Control | Action |
|---|---|
| **Shift + pad** | save the whole project to that slot |
| **Pad — tap** | load that project (restores every pattern and the live state) |
| **Shift + Menu** | restore the **autosave** recovery file (see below) |
| **Knob 1** | tempo of the selected pattern |

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
[Recording & the web UI](#recording--the-web-ui) for downloads.

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
[`controller/poundhard/kits.py`](controller/poundhard/kits.py) — that's the
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

**One archetype per pattern.** A pattern is built to a single identity rather than from
uniform randomness — `MINIMAL`, `BROKEN`, `NOISE`, `HYPNOTIC`, `TEXTURAL` or
`PERCUSSIVE`. Each sets its own size, density, ensemble bias and rhythmic character.
That's what makes one pattern feel *intentional* while the set stays *diverse*: a
different identity every time. The archetype names the kit (`BROK-035`, `TEXT-670`…).

- **Parts interlock with the kick** rather than doubling it — a secondary part's hits
  are pushed off the kick onto free steps. This is the single biggest thing that makes
  a generated groove sound arranged instead of merely layered.
- every voice comes from a **curated role** ([`kits.py`](controller/poundhard/kits.py)),
  so all notes are drawn from the same low phrygian scale over the same root — it is
  always in key, and roles fix the register so voices don't mask each other
- **levels and stereo placement** are set per category (kick and bass centred and
  forward; textures and pads sat back), so the mix stays readable
- **at most 2 FX inserts and only ever one reverb**, at moderate wet
- a **density cap** thins the busiest non-kick voices when the whole thing gets too full

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
(in palette order — DRUM · FM7 · BUCHLOID · MOLLY · RINGS · BEN · NOIZEOP · ICARUS · PLAITS · SHAKER · MEMBRANE · MALLET · BOWED · PLUCK · TUBE · CHAOS · WTABLE · BYTEBEAT · SAMPLE,
with roles in musical order inside each block). Since the step buttons are coloured by
engine, a generated rig reads as **contiguous colour blocks** rather than a scatter.

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
pulse **pink**). Each carries its own **period** — how many of *its own plays* pass between
transforms — set with **knob 4** on that step (marking it live if it isn't). The period is
counted in **step plays, not bars**: a step on a 2-bar loop still transforms every *N* times
you actually hear it, so the count holds no matter the track's length or clock rate.

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
next transform](controller/poundhard/tracks.py) (`reroll_living` / `tick_living`), holding it
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
([`controller/poundhard/variations.py`](controller/poundhard/variations.py)): which
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

## Recording & the web UI

The [recorder view](#recorder-view) captures the master output (post-limiter, what
you hear) to **stereo 16-bit WAV** via a `DiskOut` synth in the engine, capped at
**7 minutes** per take, into `/data/UserData/poundhard/recordings/`.

Finishing a take enters a **tail** phase: the engine keeps writing while it reports
the master level to the controller (`/ph/amp`, ~10 Hz), and the file is only closed
once the signal has stayed below the silence threshold for a beat — so reverb and
delay tails are preserved. Tune it with `PH_REC_SILENCE` (default `0.004`; music
typically sits around `0.1–0.4`).

The controller runs a small **web UI** at **`http://move.local:7177`** where every
recording has a **▶ Play** button (audition in the browser) and a **Download**
button. The address is deliberately a general
PoundHard endpoint — more functions will live there over time. The port is
configurable via the `PH_WEB_PORT` environment variable.

---

## Deploy to the Move

**On the device you need Schwung** (PoundHard is a Schwung *overtake* module, and Schwung
supplies the shadow JACK driver). Nothing else: the SuperCollider engine **and** the JACK
server ship in PoundHard's own runtime bundle — no wildrider, no RNBO.

```bash
cd move
./deploy.sh [move-host]      # default host: move.local
# then on the Move: Schwung menu → overtake → PoundHard
```

`deploy.sh` runs three steps you can also run individually:

1. **`deploy-bundle.sh`** — installs PoundHard's **self-contained** audio runtime under
   `/data/UserData/poundhard`. The whole runtime — supernova, scsynth, sclang, **jackd
   and libjack**, every UGen plugin it uses (**mi-UGens** for RINGS/PLAITS/CLDS,
   **sc3-plugins** for many engines and the RESO/GREY effects, STK, ByteBeat…), the
   SuperCollider class library + Extensions, and a self-contained `sclang_conf` — is
   vendored in this repo at `move/bundle/poundhard-sc-runtime.tar.gz` and pointed at
   PoundHard's own dirs. **No other project (wildrider, RNBO) needs to be on the
   device** — only Schwung, which supplies the shadow JACK driver and hosts the module.

   It finishes with a **preflight**: every RT binary is executed once with an *empty*
   environment. That is exactly the state the loader puts them in at runtime (below), so
   an unreachable library fails here, at deploy time, instead of leaving the device sitting
   on "starting…" with the reason buried in a log.

   > **Why RPATH, not `LD_LIBRARY_PATH`.** `scsynth`, `supernova` and `jackd` carry RT file
   > capabilities, and glibc runs a capability-carrying binary in **secure-execution mode**,
   > where `LD_LIBRARY_PATH` is **discarded** — the RPATH compiled into the binary is the
   > only search path they have. The vendored runtime was originally copied out of a
   > *wildrider* install and kept **its** RPATH, so on a device without wildrider `scsynth`
   > died with `libsndfile.so.1: cannot open shared object file` even though that library was
   > sitting in `$PH/lib` (issue #3). The bundle's binaries are now patched to point at
   > PoundHard's own lib. An RPATH can be **shortened** in place but never lengthened, which
   > is why `jackd` — whose original path had no room — points at `/data/UserData/phlib`, a
   > symlink the deploy creates. Regenerating the bundle from a device means re-patching the
   > RPATHs, or you ship whatever paths that device happened to have.
2. **`deploy-controller.sh`** — the Python controller, vendored `python-osc`, the
   engine `.scd` files, and the `run-*.sh` scripts.
3. **`deploy-module.sh`** — the Schwung overtake module (`module.json` + `ui.js`
   + `exit-hook.sh`) under `/data/UserData/schwung/modules/overtake/poundhard`.

> Do **not** disable the Move's update services (`swupdate` / `UpdateDBusService`) to
> block auto-updates — `MoveControlModeHandler`, a boot-critical step, hangs forever
> when they're absent and the device won't finish booting (SSH still works). An
> earlier `disable-updates.sh` did this and had to be reverted.

> After a controller change, do a **full relaunch** (exit and re-enter) so the
> launcher starts the new controller — an old process from a prior session is
> otherwise reused.

---

## Develop off-device

The controller runs headless with no engine (OSC sends become no-ops), so kit
generation, pattern/project logic and the control/status protocol can be
exercised on any machine:

```bash
cd controller
PYTHONPATH="$PWD:$PWD/vendor" python3 -m poundhard.headless
# writes status.json, polls control.json (paths from $PH_SHARE)
```

---

## Architecture & internals

**The controller is authoritative** for musical state (a `Project`: 16 tracks ×
{engine type, note, velocity, parameters, pattern + per-step locks — pitch, velocity,
pan, voice macro, ratchet, living flag/period, FX mask, **cycle divider** and the
**per-step sample window** — mute, length, rate, **filter**}, plus FX assignment/bypass/macros, tempo, and 32 pattern slots). A track
is at most **16 steps**; the per-step arrays are 32 wide for headroom and for projects
saved before the cap. It reads `control.json`, writes `status.json`, generates kits,
and pushes state to the engine over OSC.

**Startup is a handshake, not a race.** The controller pings until the engine answers
`/ph/ready`, and until then it dispatches nothing — including whatever was left in
`control.json` by the previous session, whose high-water mark it adopts on its first
read rather than replaying. Pushing a machine's worth of state at a half-built graph
floods the server with messages for nodes that do not exist yet and can leave it
running-but-silent, which is a failure mode worth designing out rather than debugging
twice.

**The engine owns the step clock and the DSP.** The clock is a `TempoClock`
routine in `engine.scd`: it advances a per-track accumulator (so each track runs
at its own rate and length — polymeter), counts each track's repetitions so a step
carrying a **cycle divider** only fires on every Nth pass, spawns each active/unmuted
step's voice, streams the playhead back as `/ph/step`, and fires `/ph/cycle` on each
16-step bar boundary for queued pattern switching. Python stays at a relaxed rate for
UI/status only.

### Voice model

Voices are **spawned per hit, not persistent.** Each active/unmuted step spawns a
fresh one-shot synth from the track's stored params; it plays its envelope and
frees itself (`Line.kr … doneAction:2`). Persistent always-on voices were the
first design and **froze the Move** — 16 always-on synths overloaded the ARM even
at idle. Two guards keep it robust under dense IDM/noise patterns:

- **Per-track polyphony cap** (`~maxPoly = 3`, steal oldest) — without it dense
  patterns spawn faster than voices free, growing nodes unbounded until a freeze.
- **Per-mode DRUM defs** (`phDrumKick … phDrumNoise`, picked by the track's
  `mode`) — a hit runs only its mode's DSP, several times cheaper than an
  all-modes-then-`Select` voice.

**BYTEBEAT is the one exception**, and it is forced by the UGen rather than chosen: it
parses its expression *per instance* and starts on an `Undefined` expression that
evaluates to 0, so a freshly spawned instance is silent until its asynchronous `/eval`
lands. Spawning one per hit raced the parse against the note — long notes won it, short
ones came out inaudible, and the same sound was not reproducible twice. That track keeps
**one live voice**, parsed once and re-triggered per step (`t_trig`, `doneAction: 0`),
with a free-running counter — which is what bytebeat is anyway.

Each track has a **private stereo bus**; its voices write there, its FX chain
processes in place (each FX `ReplaceOut`s the bus in canonical order), and a send
sums it to the master. Node order: `gClear → gVoices → gFilt → gFx → gSend → gMaster`
(`gFilt` is the per-track multimode filter, one always-on insert per track).
Under supernova `gVoices` is a **ParGroup** with a serial subgroup per track, so tracks
render in parallel while each track's own chain stays ordered.

### The Move UI (ui.js) and file I/O

ui.js can't open sockets, so everything crosses the `ipc/{control,status}.json`
file bridge. The host's file I/O is **synchronous and can stall the frame**, so
the UI reads/writes as little as possible (change-detected status writes, reads
~5 Hz, coalesced control writes) and redraws only on visible change. Big values
use a **custom block-glyph renderer** (`drawBig` + `FONT`) because the host
`print` maxes at size 2 — the instrument is built for a user with a severe sight
impairment, so param / rate / macro / tempo readouts are drawn large and stay up
while a knob is touched.

---

## Wire protocols

### control.json (ui.js → controller)

A `cmds` queue de-duped by `seq` (a single-slot mailbox lost commands when the UI wrote
twice between polls). The queue left behind by a previous session is **never replayed** —
on its first read the controller takes the high-water mark and runs nothing — and no
command is dispatched until the engine reports ready.

| Group | Commands |
|---|---|
| engine palette | `audition`, `palettegen`, `assign`, `randtrack`, `genkit`, `drumaudition` / `drummode` (DRUM type picker), `smparm` (arm the SAMPLE capture) |
| tracks | `mute`, `solo`, `trackset` (pitch/amp/pan/rate), `voicemacro`, `voiceparam` (one named voice param — SAMPLE's window knobs), `trackfilter` (cutoff/res/type), `note`, `setlen`, `clearpat` |
| steps | `stepset` / `steptoggle`, `steplock`, `stepmacro`, `stepfx` (per-step FX mask), `stepcycle` (fire every Nth repetition), `stepwindow` (per-step sample slice), `marklive` / `liveperiod` (living steps) |
| clipboard | `stepcopy` / `steppaste`, `rowcopy` / `rowpaste` (the Copy-button gestures) |
| FX | `fxassign`, `fxbypass`, `fxmacro`, `fxwet` |
| macros | `heat` / `heatpct`, `shuffle`, `chaos` / `chaosreset` |
| patterns & projects | `savepat` / `loadpat`, `patdel`, `patcopy` / `patpaste` / `patclipclear`, `genvar`, `randpat`, `saveproj` / `loadproj`, `loadauto` |
| transport & system | `run`, `editenter` / `editexit`, `recpad`, `undo`, `panic` |

`tempo` is a continuous field applied on change, not a queued command.

### status.json (controller → ui.js)

Carries `ready / engine / cpu / nodes / running / tempo / step / editTrack / solo / kit /
webPort`, per-track `muted / active / note / vel / pan / amp / rate / length` plus
`start / end` (SAMPLE's playable window) and `fcut / fres / ftype` (the track filter), the engine `types` / role `names` and
`drumTracks / drumMode`, the FX view state (`fxTop / fxBypass / fxOn / fxMacro / fxWet /
fxNames`), and the open track's `edit` block: `steps`, the effective per-step
`stepNote / stepVel / stepPan / stepMacro`, `living / period / ratchet / active`,
`fx` (per-step FX masks), `cycle` (per-step dividers) and `stepStart / stepEnd` (the
effective per-step sample window).

Also the pattern/project state (`patFilled / patCur / patPending / projFilled`), the
`autoSave` flag, the HEAT / SHUFFLE / chaos macro state (`heat / heatPct / shuffle /
chaos`), the SAMPLE capture state (`smpState / smpSrc / smpChain`), the recorder
(`recState / recSlot / recSlots / recElapsed / recAmp`), and `clipStep / clipRow` — whether
the Copy-gesture clipboard is holding a step or a row.

### OSC (controller → engine, sclang langPort 57120)

`/ph/tempo` · `/ph/run` · `/ph/steps` · `/ph/track t typeIdx` (**-1=empty** 0=DRUM
1=FM7 2=BUCHLOID 3=MOLLY 4=RINGS 5=BEN 6=NOIZEOP 7=ICARUS 8=PLAITS 9=SHAKER 10=MEMBRANE 11=MALLET 12=BOWED 13=PLUCK 14=TUBE 15=CHAOS 16=WTABLE 17=BYTEBEAT 18=SAMPLE) ·
`/ph/param t "name" val` (WTABLE's `wt1`/`wt2` are sprite selectors — the engine (re)loads that oscillator's wavetable buffer instead of setting a synth arg; BYTEBEAT's `expr` is a bank index — the engine re-parses its **persistent** voice with the plugin's `/eval` unit command, sent a few control blocks after the node is created, never in the same instant) ·
`/ph/preview typeIdx note vel mode [name val …]` (audition one voice → master) ·
`/ph/pattern` · `/ph/stepset` · `/ph/steplock` · `/ph/stepmacro` · `/ph/clearlocks` ·
`/ph/stepratchet t cell k` · `/ph/stepsend t cell on` · `/ph/stepfx t cell mask`
(per-step FX: a bitmask over the 8 insert slots, **-1 = no lock**) ·
`/ph/stepcycle t cell n` (fire on every **n**-th repetition of the pattern, 1-8) ·
`/ph/stepsmp t cell start end` (per-step SAMPLE window, **-1 = inherit the track's**) ·
`/ph/filter t cutoff res type` (per-track multimode filter, type 0=LP 1=HP) ·
`/ph/livingfx dTime dFb dMix vMix vRoom vDamp`
(living-step ratchet / per-step FX-send routing / send-bus params) ·
`/ph/smparm t thresh` (arm the threshold capture) · `/ph/smpwrite \"path\"` · `/ph/smpload \"path\"` ·
`/ph/smpassign t \"path\"` (give the track its OWN buffer, release the pad) · back: `/ph/smprec`
`/ph/smpdone` `/ph/smpwritten` `/ph/smpready` ·
`/ph/mute` · `/ph/note` · `/ph/vel` · `/ph/length` · `/ph/rate` · `/ph/edittrack` ·
`/ph/fxassign` · `/ph/fxbypass` · `/ph/fxset` · `/ph/fxclear` · `/ph/recstart "path"` ·
`/ph/recstop` · `/ph/mastergain` · `/ph/masterfilter` · `/ph/panic` · `/ph/ping`.

### Telemetry (engine → controller, port 57140)

`/ph/ready` (once) · `/ph/step n` (per step, −1 = stopped) · `/ph/cycle` (each
16-step bar boundary) · `/ph/cpu avg peak nodes`.

---

## Repository layout

```
controller/poundhard/   catalog.py  kits.py  variations.py  tracks.py  engine_bridge.py  headless.py  webserver.py  params.py
controller/vendor/      pythonosc (vendored — no pip on the device)
supercollider/          boot.scd  engine.scd  synthdefs.scd
move/                   run-*.sh  stop-stack.sh  deploy*.sh  sc/ph-boot.scd
move/schwung-module/poundhard/   module.json  ui.js  exit-hook.sh
web/                    poundhard-logo.svg   (brand mark — also served by the web UI)
```

The wordmark uses **[Chakra Petch](https://fonts.google.com/specimen/Chakra+Petch)** —
an angular, industrial typeface that suits the hard, percussion-centric aesthetic.

---

## Gotchas

- **ui.js has no sockets** → everything goes through the `ipc/*.json` files, and
  the host's synchronous file I/O can stall the UI, so I/O is kept minimal.
- **LED calls differ:** pads/steps use `setLED` (Note On); the Play and track-row
  buttons use `setButtonLED` (CC). The knob CCs (71–78) and Play CC (85) fall in
  the same numeric range as the pad notes — handlers must match on message type,
  not just number.
- **The server is supernova, not scsynth.** `PH_THREADS` (run-engine.sh, default **3**)
  picks it: >0 = supernova with N DSP threads, 0 = scsynth. Supernova loads **only**
  `*_supernova.so` plugins (both sets ship in the bundle) and needs
  `cap_ipc_lock,cap_sys_nice,cap_sys_resource` on its binary or its parallel DSP threads
  can't go realtime — `chown` clears those caps, so `deploy-controller.sh` re-applies them.
  It also needs its lib path baked in as `DT_RPATH` (a capped binary ignores
  `LD_LIBRARY_PATH`). **GREY is server-conditional**: `GreyholeRaw` won't register on
  supernova, so under it GREY is rebuilt from core UGens (same knobs).
- **Parallelism comes from ParGroups, not from supernova alone.** `~gVoices` is a ParGroup
  of per-track groups and `~gFx` a ParGroup of per-track chains — safe because each track
  owns a private bus. Anything writing a SHARED bus stays serial: voices within one track,
  living-FX hits and palette auditions (`~gSharedVoices`), and the sends/master.
- **Engine boot needs `HOME=/data/UserData`** (a menu launch has HOME unset);
  scsynth & jackd need RT file-caps (re-applied on every deploy).
- **sclang OSC string args arrive as Symbols** — the engine uses
  `.asSymbol` / `.asInteger`.
- **No fallbacks:** a required dependency (a UGen, plugin, file) is called
  unconditionally and fails loudly if absent — features work or they don't.
- **Forwards compatibility:** older projects load into the current stack. A `FMTONE`
  track is remapped to **FM7** at load (the old 2-op params don't map onto 6-op, so it
  comes back as a default FM7 to re-roll), and an FX macro reads its direction with
  `.get(arg, 1)` so a project saved before a param was added won't `KeyError` mid-load —
  which used to crash the load and freeze the instrument. **FX are saved by SLOT INDEX**, so
  the chain can't be reordered silently: snapshots carry an `fx_layout` version, and a
  pre-VERB (v1) project is remapped on load — the flanger is dropped and CLDS/RESO/GREY
  slide down one slot, each carrying its own macro / wet / direction. Without that, a
  track's CLDS would have come back as RING.
- **A unit command sent with the node is lost.** `/u_cmd` delivered in the same instant as
  the `/s_new` that creates its node hits a node the server has not instantiated yet and is
  dropped — silently. That is how BYTEBEAT ended up mute: the ByteBeat UGen starts on an
  `Undefined` expression (silent) and only speaks once its `/eval` lands, so every voice was
  a coin flip. Defer the unit command a few control blocks after creating the node.
- **`Synth:onFree` only fires for a REGISTERED node.** Without `.register` the callback never
  runs, so a reference to a freed synth (panic frees everything under `~gVoices`) lives on and
  every later `.set` goes to a dead node — a track that is silent *forever* with nothing in the
  log but `node not found`.
- **`control.json` outlives the session.** The queue is on disk, so a restarting controller
  would replay the previous session's commands at an engine that is still booting. That wedges
  the graph: `ready` is true, `nodes` is 0, and nothing sounds. The controller now adopts the
  queue's high-water mark on its first read and holds every command until `/ph/ready`.
- **`ready: true` with `nodes: 0` means the graph is gone, not that your feature is broken.**
  Usually an orphaned supernova that survived a kill: the new sclang attaches to it, never runs
  `initTree`, and the default group (node 1) does not exist. Restart properly — and note that
  `pgrep -f "<pattern>"` inside an ssh command matches the ssh command line itself, so the
  remote shell kills its own session and the stack survives. Bracket the pattern
  (`bin/sclan[g]`) and verify with `ps` before starting again.
- **The engine recorder taps hardware bus 0**, so a capture includes anything else the Move is
  playing. If MoveOriginal has audio running, absolute levels are meaningless — verify DSP
  offline instead (`scsynth -N` with `-U plugins`), where the render is isolated and repeatable.
- **A spawned voice's args can be SHADOWED by stale `~pstore` entries.** `~pstore[t]` is
  never cleared when a track changes engine, so appending an arg *after* `merged.getPairs`
  in `~spawn` can lose to an older entry of the same name. This made SAMPLE tracks play the
  1024-frame silent buffer while auditioning worked perfectly (the preview path puts `buf`
  *before* the params). Set such values **into `merged`** — it's a dictionary, so a key can
  only hold one value. Symptom to watch for: correct-looking spawn logs but silence.
- **Only one takeover runs at a time**, and the ports are **shared** with the sibling
  takeovers (57110 scsynth/supernova · 57120 sclang · 57140 controller telemetry). A
  clean exit tears the stack down, but an **unclean** exit leaves a sibling's engine
  running — which both holds those ports and (before the fix) matched PoundHard's
  `pgrep -f "bin/sclang"` start-guard, so the engine silently never started and you got
  a half-stack (controller up, no sound). `run-stack.sh` now matches its **own** sclang
  by full path and clears any **foreign** SC engine/controller first (never `jackd` —
  that's the shared shadow server it reuses).

---

## License & disclaimer

> **Plain-language summary:** PoundHard is a free, unofficial, hobbyist project. It is
> **not** an Ableton product, it comes with **no warranty of any kind**, and running it
> **modifies your Move at your own risk**. It builds on other people's free software,
> whose licenses you must also honour. Nothing here is legal advice — where this section
> and an upstream license disagree, the upstream license governs.

### PoundHard's own code

The original PoundHard material in this repository — the SuperCollider synthdefs
(`supercollider/*.scd`), the Python controller (`controller/poundhard/`), the Schwung
overtake module (`move/schwung-module/`), and the deploy/build scripts (`move/*.sh`) —
is released by its author(s) under the **MIT License** (© the PoundHard contributors).
You may use, copy, modify and redistribute *that* material under MIT terms.

**However, PoundHard does not run in isolation.** It links against, bundles, and is
distributed together with third-party software under **copyleft (GPL) licenses** (below).
When PoundHard is conveyed as a working system — or when any GPL component is
redistributed with it — the terms of those licenses (including source-availability and
copyleft obligations) apply to the combined/aggregate work. In practice, treat a
redistributed PoundHard bundle as **governed by the GPL (v3)**, and keep this notice and
the upstream license texts intact.

### Third-party components

PoundHard depends on, embeds, or ships the following. Copyrights belong to their
respective authors; consult each project for authoritative and current license terms.
To the author's best knowledge:

| Component | Role in PoundHard | License (see upstream) |
|---|---|---|
| **SuperCollider** (scsynth / sclang) | the audio engine + language | GPL-3.0-or-later |
| **sc3-plugins** (incl. FM7, Greyhole, JPverb, Streson, DiodeRingMod, chaos & glitch UGens, DWG, TwoTube…) | many of the synthesis/FX UGens | GPL-2.0-or-later / GPL-3.0 (mixed) |
| **mi-UGens** — SuperCollider ports of **Mutable Instruments** *Plaits, Rings, Clouds* | the PLAITS / RINGS / CLOUDS engines | Mutable Instruments DSP © Émilie Gillet (**MIT**); SC UGen wrapper **GPL-3.0** |
| **STK — the Synthesis ToolKit** (Perry R. Cook & Gary P. Scavone) | SHAKER / MEMBRANE / MALLET / BOWED voices (+ bundled `rawwaves/`) | STK permissive free license |
| **ByteBeat** (github.com/midouest/bytebeat) | the BYTEBEAT engine (prebuilt `.so` shipped) | **GPL-3.0** (see `supercollider/plugins/ByteBeat/LICENSE`) |
| **JACK2** (`jackd`, `libjackserver`, `libjack`) | the audio server the engine runs on — **shipped in the runtime bundle** so no other project has to provide it | server **GPL-2.0-or-later**, client library **LGPL-2.1-or-later** |
| **python-osc** (vendored under `controller/vendor/`) | OSC transport in the controller | Unlicense / public domain |
| **Csound** | investigated for a future "Csound edition" — **not shipped** in this repo | LGPL-2.1-or-later |
| **Schwung** / move-anything (and its `wildrider` SC bundle) | the host takeover framework PoundHard runs *inside* — **not part of this repo** | © its author; separate project & terms |

The prebuilt `ByteBeat.so` is an aarch64 binary of GPL-3.0 source; its corresponding
source is upstream at github.com/midouest/bytebeat, and `move/build-bytebeat.sh`
reproduces the build.

The runtime bundle likewise ships prebuilt aarch64 binaries of GPL software —
SuperCollider (`scsynth`, `supernova`, `sclang`) and JACK2 (`jackd`, `libjackserver`,
`libjack`), the latter taken from the Move's own JACK build. Their corresponding sources
are the upstream projects named above; the binaries carry only a patched RPATH (the
library search path), no code changes.

### Ableton — no affiliation, trademarks, and device content

PoundHard is an **independent, unofficial** project. It is **not** created, sponsored,
endorsed by, or affiliated with **Ableton AG** in any way. *"Ableton"*, *"Move"*,
*"Live"*, *"Wavetable"*, and related names and logos are trademarks of Ableton AG, used
here **only nominatively** to describe interoperability. No trademark or other rights in
them are claimed.

PoundHard is a **"takeover"** that runs on Ableton Move hardware alongside Ableton's own
software. It does **not** contain, copy, or redistribute Ableton's proprietary firmware,
application binaries, or content. Where it uses on-device Ableton resources — most
notably the **WTABLE** engine reading the Move's factory **Wavetable sprites** from
`/opt/move/Dsp/Vector/Sprites/` — it does so **only at runtime, on the end user's own
device**, reading files that already ship on the hardware you bought. Nothing proprietary
to Ableton is included in, or distributed by, this repository. Use PoundHard only on a
Move you own, and only with software you are licensed to run.

### No warranty · use entirely at your own risk

PoundHard is provided **"AS IS", without warranty of any kind**, express or implied,
including but not limited to the warranties of merchantability, fitness for a particular
purpose, and non-infringement. **In no event shall the authors or copyright holders be
liable for any claim, damages, or other liability** arising from, out of, or in
connection with PoundHard or its use.

Be specifically aware that PoundHard:

- **modifies the runtime behaviour of a commercial device** and rides on top of a
  reverse-engineered takeover of its software;
- involves **root access and changes to the device filesystem**, which can render the
  device unbootable — this project has, in development, temporarily **bricked the boot**
  (recoverable over SSH; see the git history and the warning against disabling the Move's
  update services);
- **may void your warranty**, may be affected or removed by official firmware updates,
  and may stop working on future device revisions;
- is an **experimental hobbyist instrument**, not a supported product.

If any of that is not acceptable to you, **do not install or run PoundHard.** By using
it, you accept full responsibility for what happens to your device and your data.
