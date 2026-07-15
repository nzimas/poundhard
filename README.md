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
   engine  (sclang — 16 voices + TempoClock step sequencer + FX chains)
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
- [Kits](#kits)
- [Patterns & projects](#patterns--projects)
- [Recording & the web UI](#recording--the-web-ui)
- [Deploy to the Move](#deploy-to-the-move)
- [Develop off-device](#develop-off-device)
- [Architecture & internals](#architecture--internals)
- [Wire protocols](#wire-protocols)
- [Repository layout](#repository-layout)
- [Gotchas](#gotchas)

---

## The instrument

- **16 tracks**, one per step button, grouped by sound engine into contiguous,
  colour-coded blocks:

  | Tracks | Engine | Colour | Voices |
  |--------|--------|--------|--------|
  | 1–6 | **DRUM** | 🟡 yellow | kick · snare · closed hat · open hat · clap · metallic/glitch perc |
  | 7–8 | **RINGS** | 🩵 cyan | mallet/bell · sympathetic pluck (Mutable Rings) |
  | 9 | **BEN** | 🟠 orange | Benjolin — chaotic generative machine |
  | 10–11 | **BUCHLOID** | 🟣 magenta | drone · noise texture |
  | 12 | **NOIZEOP** | 🩷 pink | 4-sine / 6-algorithm glitch-noise machine |
  | 13–14 | **FMTONE** | 🟢 green | bass · metallic ornament |
  | 15–16 | **MOLLY** | 🔵 blue | gritty lead/stab · corroded pad |

- **32-step sequencer per track**, each with independent length and clock rate
  (**polymeter** — tracks phase against each other).
- **Per-step locks** on pitch, velocity, pan, and a **voice macro** — each step
  can carry its own tone.
- **Kits** re-roll every voice within its fixed role, so a kit is always fresh
  but idiomatic. Patterns and mutes survive kit regeneration.
- **Up to 32 patterns per project**, and projects saved to disk — see
  [Patterns & projects](#patterns--projects).

The step buttons for tracks that contain events **pulse at the pace of their
sequence**, so you can read at a glance what each track is doing.

---

## Sound engines

All voices are **spawned per hit and self-free** (see [voice model](#voice-model)).

- **DRUM** — a full digital drum voice with 7 modes (kick / snare / hihat /
  metal / clap / tom / noise); the role fixes the mode per track.
- **FMTONE** — 2-operator FM with feedback, wavefolding and a filter.
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

> RINGS needs the **mi-UGens** plugins and the reverb FX needs **sc3-plugins**
> (`JPverb`) present in the SuperCollider bundle on the device. There are **no
> silent fallbacks** — a missing dependency fails loudly at build.

---

## Controls

Views are switched with the buttons to the left of the pad grid and the Menu
button. Knob readouts are drawn in a **giant block font** and stay on screen the
whole time the knob is **touched** (not just while turning) — the same rule
everywhere.

### Tracks view (default)

| Control | Action |
|---|---|
| **Step button — tap** | mute / unmute that track |
| **Step button — double-tap** | **solo** that track (double-tap again to un-solo) |
| **Step button — long-press** | open that track in the [Edit view](#edit-view-per-track) |
| **Track 2 button** | open the [FX view](#fx-view) |
| **Track 3 button** | open the [Pattern view](#pattern-view) |
| **Shift + Track 3 button** | open the [Recorder view](#recorder-view) |
| **Menu button** | open the [Project view](#project-view) |
| **Shift + Track 1** | randomize the **selected** track's sound |
| **Shift + hold master-volume knob + Track 1** | randomize the whole 16-track kit |
| **Play** (lit green while running) | start / stop the sequencer |
| **Knob 1** | master tempo (BPM) |
| **Back** | exit the takeover (tears the stack down) |

Step buttons are lit in their **engine colour**; a track with events pulses,
a muted or empty track sits steady-dim, the open edit track is white. Soloing a
track dims every other one — without touching their own mute flags, so un-soloing
restores exactly what was muted before.

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
| **Shift + pad** | set that pad as the **last step** (polymeter); pads past it go dark |
| **Jog wheel** | track pitch (re-pitches ringing voices live) |
| **Knob 1 / 2** | track volume / pan |
| **Knob 3** | **voice macro** — one knob sweeps every timbral param of the voice, each in a random direction; the directions re-roll whenever the track's sound is regenerated |
| **Left / Right cursor** | clock rate / division: `/8 /4 /2 1 x2 x4 x8` (bipolar readout) |
| **Track 1 button** | back to Tracks view |

### FX view

**Track 2** opens the FX view. The top two pad rows are the 16 tracks; the bottom
row is an 8-effect chain — `OD · AMP · CRSH · RING · FLNG · GRN · DLY · VRB`
(reverb always last/rightmost), each a distinct colour.

**OD** is not a polite tube sim: tilt EQ → asymmetric (biased) drive → a
**wavefolder** that reflects peaks back for metallic bite → a hard-clip **grit**
stage for fizz and breakup. Its macro sweeps drive/tone/fold/bias/grit together.

| Control | Action |
|---|---|
| **Hold an FX pad + tap tracks** | assign that FX to those tracks (their pad takes the FX colour) |
| repeat to unassign | stacked FX peel off one layer at a time; the top FX's colour prevails |
| **Tap a track pad** (no FX held) | bypass / un-bypass that track's FX chain (grey = bypassed) |
| **Knobs 1–8** | a randomized **macro** per FX — some params move with the knob, some inverted |

All FX default to 50 % wet / 50 % dry.

### Pattern view

**Track 3** opens the pattern view — the 32 pads become **32 pattern slots**.

| Control | Action |
|---|---|
| **Shift + pad** | save the current machine state to that slot |
| **Pad — tap** | load that pattern |

Loading a pattern while the sequencer is **playing queues the switch**: it takes
effect on the next **16-step bar** boundary (the queued slot pulses until then).
Loading while stopped switches immediately. Slot colours: **periwinkle** = saved,
white = currently playing, pulsing = queued, dim = empty.

A live pattern load applies the **groove only** — step patterns, lengths, rates,
mutes, and all per-step locks. Sounds, FX and tempo stay put, so you switch the
groove without disrupting the sound.

### Project view

**Menu** opens the project view — the same 32-slot grid for whole projects,
which persist to disk.

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

## Kits

A **kit** is the 16 voice *sounds* (engine type, note, and parameters). There are
**16 fixed roles** — track 1 is always a kick, track 7 always a Rings mallet, and
so on. Generating a kit re-rolls every voice within its role's musical bands, so
allocation is deterministic but the sound is always fresh. Notes for tonal voices
are drawn from a low phrygian scale. Tune the roles in
[`controller/poundhard/kits.py`](controller/poundhard/kits.py) — that's the
aesthetic dial.

- **Shift + Track 1** re-rolls the selected track's sound only.
- **Shift + hold master-volume knob + Track 1** re-rolls the whole kit.

Patterns, mutes and per-step locks survive kit regeneration.

---

## Patterns & projects

- A **pattern** is a full machine snapshot (sequences, sounds, FX, tempo, all
  locks) at save time. A live pattern *load* applies the **groove only** so the
  sound is left alone.
- A **project** is a collection of up to 32 patterns plus the kit, written to
  `/data/UserData/poundhard/projects/proj_NN.json`. Loading a project restores
  the **entire** machine state.

The queued pattern switch is bar-accurate: the engine fires `/ph/cycle` on the
last step of each fixed 16-step bar, and the controller applies the pending
pattern's groove right before the downbeat.

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
   include **mi-UGens** (for RINGS) and **sc3-plugins** (for the reverb).
2. **`deploy-controller.sh`** — the Python controller, vendored `python-osc`, the
   engine `.scd` files, and the `run-*.sh` scripts.
3. **`deploy-module.sh`** — the Schwung overtake module (`module.json` + `ui.js`
   + `exit-hook.sh`) under `/data/UserData/schwung/modules/overtake/poundhard`.

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
wrote twice between polls). Commands include: `genkit`, `randtrack`, `mute`,
`editenter` / `editexit`, `stepset`, `steplock`, `stepmacro`, `setlen`,
`trackset`, `voicemacro`, `fxassign` / `fxbypass` / `fxmacro`, `run`, `note`,
`savepat` / `loadpat`, `saveproj` / `loadproj`, `recpad`, `panic`. `tempo` is a
continuous field applied on change.

### status.json (controller → ui.js)

Carries `ready / engine / cpu / nodes / running / tempo / step / editTrack / kit`,
per-track `muted / active / note / vel / pan / amp / rate / length`, the engine
`types` / role `names`, the FX view state (`fxTop / fxBypass / fxOn / fxMacro /
fxNames`), the open track's `edit` block (`steps`, per-step `stepNote / stepVel /
stepPan / stepMacro`, defaults), and the pattern/project state (`patFilled /
patCur / patPending / projFilled`).

### OSC (controller → engine, sclang langPort 57120)

`/ph/tempo` · `/ph/run` · `/ph/steps` · `/ph/track t typeIdx` (0=DRUM 1=FMTONE
2=BUCHLOID 3=MOLLY 4=RINGS 5=BEN 6=NOIZEOP) · `/ph/param t "name" val` · `/ph/pattern` ·
`/ph/stepset` · `/ph/steplock` · `/ph/stepmacro` · `/ph/clearlocks` · `/ph/mute` ·
`/ph/note` · `/ph/vel` · `/ph/length` · `/ph/rate` · `/ph/edittrack` ·
`/ph/fxassign` · `/ph/fxbypass` · `/ph/fxset` · `/ph/recstart "path"` ·
`/ph/recstop` · `/ph/mastergain` · `/ph/masterfilter` · `/ph/panic` · `/ph/ping`.

### Telemetry (engine → controller, port 57140)

`/ph/ready` (once) · `/ph/step n` (per step, −1 = stopped) · `/ph/cycle` (each
16-step bar boundary) · `/ph/cpu avg peak nodes`.

---

## Repository layout

```
controller/poundhard/   catalog.py  kits.py  tracks.py  engine_bridge.py  headless.py  webserver.py  params.py
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
- Only one takeover runs at a time; the exit hook kills the whole stack, so there
  is no port conflict with wildrider (shared langPort 57120 / telemetry 57140).
```
