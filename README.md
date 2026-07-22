<p align="center">
  <img src="web/poundhard-logo.svg" alt="PoundHard" width="560">
</p>

# PoundHard

**A 16-track groovebox takeover for the Ableton Move** — built for edgy IDM,
rhythmic noise and percussion-centric experimental electronica.

A SuperCollider engine carries the DSP, a Python controller holds the
authoritative musical state, and a Schwung `ui.js` drives the Move's pads, step
buttons, encoders and screen. It runs on the same on-device stack as the
*wildrider* takeover — reused plumbing, brand-new instrument.

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
   engine  (sclang — 18 engines × 16 tracks + TempoClock step sequencer + FX chains)
        │
        ▼
   scsynth → jackd → Move speaker / output
```

---

## Contents

- [The instrument](#the-instrument)
- [Sound engines](#sound-engines)
- [Controls](#controls)
  - [Tracks view](#tracks-view-default)
  - [Edit view](#edit-view-per-track)
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

---

## The instrument

- **16 tracks**, one per step button. Tracks start **empty** (dark, silent); you
  build your rig by assigning engines from the **engine palette** (see below). Any
  engine can go on any track, and the assignment is **per pattern** — two patterns can
  carry completely different rigs.
- **18 assignable engines** on the palette pads — the first 16 fill the top two rows (row 1
  DRUM..ICARUS, row 2 PLAITS..CHAOS) and **WTABLE**/**BYTEBEAT** sit on row 3 (cells 16-17), each in its own colour:

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

- **Engine palette** (top row of pads, default view): **short-press** a pad to
  audition its current sound; **Shift + pad** to regenerate it; **hold a pad and
  tap a track** (step button) to assign that engine + sound to the track. Assigning
  keeps the track's existing sequence — only the sound changes.
- **32-step sequencer per track**, each with independent length and clock rate
  (**polymeter** — tracks phase against each other).
- **Per-step locks** on pitch, velocity, pan, and a **voice macro** — each step
  can carry its own tone.
- **Living steps** — mark steps (or hit **HEAT** for the whole rig) and they
  **transform themselves** as you play: ratchets, timbre lurches, pitch leaps, pan
  throws and per-step delay/reverb. A live-performance engine (see
  [Living steps & the HEAT button](#living-steps--the-heat-button)).
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

A **long-press** on a step button opens its editor. The pads become its 32-step
sequencer, and the jog/knobs/cursors edit that track's settings — all in one
place.

| Control | Action |
|---|---|
| **Pad — tap** | toggle that step (in-length pads dim, active bright) |
| **Pad — hold (active step)** | **per-step lock** — jog = pitch, knob 1 = velocity, knob 2 = pan, knob 3 = macro |
| **Rec + pad** | mark / unmark that step as a **[living step](#living-steps--the-heat-button)** (self-transforming; pulses pink) |
| **Knob 4** (on a step) | **living period** — cycles between transforms (also marks the step living) |
| **Shift + pad** | set that pad as the **last step** (polymeter); pads past it go dark |
| **Jog wheel** | track pitch (re-pitches ringing voices live) |
| **Knob 1 / 2** | track volume / pan |
| **Knob 3** | **voice macro** — one knob sweeps every timbral param of the voice, each in a random direction; the directions re-roll whenever the track's sound is regenerated |
| **Left / Right cursor** | clock rate / division: `/8 /4 /2 1 x2 x4 x8` (bipolar readout) |
| **Track 1 button** | back to Tracks view |

### FX view

**Track 2** opens the FX view. The top two pad rows are the 16 tracks; the bottom
row is an 8-effect chain — `OD · AMP · CRSH · RING · FLNG · CLDS · RESO · GREY`
(**GREY** — the diffuse delay/reverb — sits last, giving the chain its space), each a
distinct colour.

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
`freq`, `res` (sharpness/decay) and a damping top-cut. It **replaces the reverb** — a
transforming resonance rather than more space (the last slot, GREY, already provides that).

**GREY** is **Greyhole** (sc3-plugins), now the **last** effect in the chain — a diffuse,
pitch-modulated feedback delay that blurs toward reverb as its diffusion and size rise (after
ValhallaDSP's Greyhole). Its macro sweeps delay time, feedback, size, diffusion, damping and
modulation together — the dark, smeary IDM space-maker that gives the chain its tail.

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
- **mutes**, sequences, lengths, clock rates and every per-step lock

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
| BUCHLOID | 6.0 | | FLNG | 1.1 |
| RINGS / SHAKER | 9.6 / ~7* | | AMP | 1.7 |
| BEN | 9.7 | | GREY | ~4.5* |
| MOLLY | 11.7 | | OD | 2.5 |
| NOIZEOP | 12.0 | | CLDS | ~6.0* |
| ICARUS | 13.2 | | RESO | ~2.0* |
| MEMBRANE / MALLET / BOWED | ~9 / ~7 / ~8* | | | |
| PLUCK / TUBE / CHAOS | ~7 / ~7 / ~8* | | | |
| WTABLE | ~9.5* | | | |
| BYTEBEAT | ~6* | | | |

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
(in palette order — DRUM · FM7 · BUCHLOID · MOLLY · RINGS · BEN · NOIZEOP · ICARUS · PLAITS · SHAKER · MEMBRANE · MALLET · BOWED · PLUCK · TUBE · CHAOS · WTABLE · BYTEBEAT,
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

```bash
cd move
./deploy.sh [move-host]      # default host: move.local
# then on the Move: Schwung menu → overtake → PoundHard
```

`deploy.sh` runs three steps you can also run individually:

1. **`deploy-bundle.sh`** — provisions the scsynth/sclang runtime under
   `/data/UserData/poundhard`. PoundHard's voices are pure SuperCollider, so it
   **reuses the wildrider bundle** (`bin/ lib/ plugins/ share/`); deploy
   wildrider's bundle first if it isn't already on the device. The bundle must
   include **mi-UGens** (for RINGS / PLAITS / CLDS) and **sc3-plugins** (for many
   engines and the RESO / GREY effects).
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
{engine type, note, velocity, parameters, 32-step pattern + per-step locks, mute,
length, rate}, plus FX assignment/bypass/macros, tempo, and 32 pattern slots). It
reads `control.json`, writes `status.json`, generates kits, and pushes state to
the engine over OSC.

**The engine owns the step clock and the DSP.** The clock is a `TempoClock`
routine in `engine.scd`: it advances a per-track accumulator (so each track runs
at its own rate and length — polymeter), spawns each active/unmuted step's voice,
streams the playhead back as `/ph/step`, and fires `/ph/cycle` on each 16-step
bar boundary for queued pattern switching. Python stays at a relaxed rate for
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

Each track has a **private stereo bus**; its voices write there, its FX chain
processes in place (each FX `ReplaceOut`s the bus in canonical order), and a send
sums it to the master. Node order: `gClear → gVoices → gFx → gSend → gMaster`.

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

A `cmds` queue de-duped by `seq` (a single-slot mailbox lost commands when the UI
wrote twice between polls). Commands include: `audition` / `palettegen` / `assign`
(engine palette), `randtrack`, `mute`, `solo`, `editenter` / `editexit`, `stepset`,
`steplock`, `stepmacro`, `setlen`, `trackset`, `voicemacro`,
`fxassign` / `fxbypass` / `fxmacro` / `fxwet`, `marklive` / `liveperiod` (living steps),
`heat` / `heatpct` (the HEAT macro), `shuffle` (the SHUFFLE macro), `run`, `note`, `savepat` / `loadpat`,
`patdel` / `patcopy` / `patpaste` / `patclipclear`, `undo`, `chaos` / `chaosreset`
(knob-8 macro), `genvar` (generate
variations), `randpat` (randomise this pattern), `saveproj` / `loadproj`, `loadauto`
(restore the autosave), `recpad`, `panic`. `tempo` is a continuous field applied on
change.

### status.json (controller → ui.js)

Carries `ready / engine / cpu / nodes / running / tempo / step / editTrack / kit`,
per-track `muted / active / note / vel / pan / amp / rate / length`, the engine
`types` / role `names`, the FX view state (`fxTop / fxBypass / fxOn / fxMacro /
fxWet / fxNames`), the open track's `edit` block (`steps`, per-step `stepNote / stepVel /
stepPan / stepMacro`, plus `living / period` for living steps, and defaults), the
pattern/project state (`patFilled / patCur / patPending / projFilled`), the `autoSave`
flag, and the HEAT / SHUFFLE macro state (`heat / heatPct / shuffle`).

### OSC (controller → engine, sclang langPort 57120)

`/ph/tempo` · `/ph/run` · `/ph/steps` · `/ph/track t typeIdx` (**-1=empty** 0=DRUM
1=FM7 2=BUCHLOID 3=MOLLY 4=RINGS 5=BEN 6=NOIZEOP 7=ICARUS 8=PLAITS 9=SHAKER 10=MEMBRANE 11=MALLET 12=BOWED 13=PLUCK 14=TUBE 15=CHAOS 16=WTABLE 17=BYTEBEAT) ·
`/ph/param t "name" val` (WTABLE's `wt1`/`wt2` are sprite selectors — the engine (re)loads that oscillator's wavetable buffer instead of setting a synth arg; BYTEBEAT's `expr` is a bank index — the engine pushes that expression to the voice's ByteBeat UGen via the plugin's `/eval` unit command) ·
`/ph/preview typeIdx note vel mode [name val …]` (audition one voice → master) ·
`/ph/pattern` · `/ph/stepset` · `/ph/steplock` · `/ph/stepmacro` · `/ph/clearlocks` ·
`/ph/stepratchet t cell k` · `/ph/stepsend t cell on` · `/ph/livingfx dTime dFb dMix vMix vRoom vDamp`
(living-step ratchet / per-step FX-send routing / send-bus params) ·
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
  which used to crash the load and freeze the instrument.
- Only one takeover runs at a time; the exit hook kills the whole stack, so there
  is no port conflict with wildrider (shared langPort 57120 / telemetry 57140).
```
