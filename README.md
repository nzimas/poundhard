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
   engine  (sclang — 20 engines × 16 tracks + TempoClock step sequencer + FX chains)
           running on SUPERNOVA (multicore SC server; ParGroups spread tracks over cores)
        │
        ▼
   supernova → jackd → Move speaker / output
           (both vendored in PoundHard's own runtime bundle)
```

---

## 📖 [Read the User Guide →](docs/USER-GUIDE.md)

**The [User Guide](docs/USER-GUIDE.md) is both a tutorial and the manual.** It opens with
*Your first pattern* — twenty minutes from an empty machine to a track that plays itself —
and then documents every view, control, engine and modifier in full.

This README covers what PoundHard *is*, how to get it onto the device, and how it works
inside. For how to **play** it, go to the guide.

---

## Contents

- [What it is](#what-it-is)
- [The twenty engines](#the-twenty-engines)
- [Deploy to the Move](#deploy-to-the-move)
- [Develop off-device](#develop-off-device)
- [Architecture & internals](#architecture--internals)
- [Wire protocols](#wire-protocols)
- [Repository layout](#repository-layout)
- [Gotchas](#gotchas)
- [License & disclaimer](#license--disclaimer)

---

## What it is

- **16 tracks**, one per step button. Tracks start **empty**; you build your rig by
  assigning engines from the **engine palette**. Any engine can go on any track, and the
  assignment is **per pattern** — two patterns can carry completely different rigs.
- **20 assignable engines**, from digital drums and 6-operator FM through Mutable-style
  resonators and macro-oscillators to chaotic maps, bytebeat, wavetables, a sampler that
  mangles its captures through Csound, and a realtime **Csound** synth with 26 architectures.
- **A 16-step sequencer per track**, each with its own length and clock rate
  (**polymeter**), plus a per-step **cycle frequency** so a step can fire once every 2–8
  repetitions.
- **Per-step locks** on pitch, velocity, pan, a voice macro, the FX chain and — on SAMPLE
  tracks — the slice of the buffer a step plays.
- **A multimode filter on every track** that keeps its bass and its level as resonance rises.
- **Pattern generation with eighteen compositional recipes** — `SPARSE`, `WALL`,
  `POLYMETER`, `GLITCH`, `PROCESSION`, `INTERLOCK` and more. Each is a brief covering roles,
  density, register, accent shape, pan, pitch relationships and variation over time, and the
  generator **scores its own output** and repairs the weakest track before handing it over.
- **32 auto-assigned, tempo-synced LFOs** in the modulation view — sample-and-hold and sine,
  each on a unique parameter, never on engine pitch, and completely non-destructive.
- **Seven non-destructive performance modifiers** — **HEAT**, **SHUFFLE**, **QUAKE**,
  **CHURN**, **BREAK**, **STROBE** and **WHIM**. None of them edits a pattern: every one is an overlay
  the engine plays instead, so a single sequence can evolve all night and switching them off
  gives you back exactly what you programmed.
- **Living steps** — mark steps and they **transform themselves** as you play: ratchets,
  timbre lurches, pitch leaps, pan throws and per-step delay/reverb.
- **Patterns are self-contained** — engines, every parameter, FX, mutes and sequences — and
  organised as a hierarchy: **16 pattern seeds**, each with its own row of **16 expansions**
  for developing variations on one idea without risking the original. Projects save to disk
  with an autosave recovery file.

The step buttons for tracks that contain events **pulse at the pace of their sequence**;
assigned-but-empty tracks glow steady-dim in their engine hue, and unassigned tracks are
dark — so you can read the whole rig at a glance.

> Full detail on all of the above, plus how to actually drive it, is in the
> **[User Guide](docs/USER-GUIDE.md)**.

---

## The twenty engines

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
| 10 | **SHAKER** | 🟨 amber | STK Shakers — 23 shaker/scraper models |
| 11 | **MEMBRANE** | 🟥 warm red | struck 2D-waveguide membrane — tunable drums / frame drums / gongs |
| 12 | **MALLET** | 🟡 gold | STK ModalBar — marimba / vibraphone / agogo / wood / bells |
| 13 | **BOWED** | 🟦 teal | STK BandedWG — bowed/struck metal bars, glass harmonica, Tibetan bowl |
| 14 | **PLUCK** | 🟩 spring | DWG plucked stiff string — koto / clav / harp / muted plucks |
| 15 | **TUBE** | 🟦 sky | TwoTube waveguide — hollow formant plucks / reedy tones |
| 16 | **CHAOS** | 🟥 red | chaotic-map oscillator — FBSine / Latoocarfian / Henon / Standard / Cusp |
| 17 | **WTABLE** | 🟪 violet | Ableton Wavetable rebuild over the Move's own factory sprites |
| 18 | **BYTEBEAT** | 🟢 green | ByteBeat UGen — 8-bit algorithmic expressions evaluated at audio rate |
| 19 | **SAMPLE** | 🌹 rose | capture engine — records another engine, mangles it through a **Csound** opcode graph, plays it back |
| 20 | **CSOUND** | 🩵 turquoise | realtime **Csound** macro-synth — 26 architectures (chained generator cores and shapers) |

Each engine's parameters, character and per-model detail are documented in the
[User Guide → Sound engines](docs/USER-GUIDE.md#sound-engines).

---

## Recording & the web UI

The [recorder view](docs/USER-GUIDE.md#recorder-view) captures the master output (post-limiter, what
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

   It also installs the **Csound runtime** (`move/bundle/poundhard-csound.tar.gz`) that the
   CSOUND engine runs as a JACK client: the binary, `librtjack.so` and a curated 20-plugin
   opcode set, plus two small tools the device lacks — **`ph-jackconnect`** (there is no
   `jack_connect`, and letting Csound auto-connect by port enumeration order would silently
   mis-wire all 34 channels the day another client joins the graph) and **`ph-rtsched`**
   (neither `chrt` nor `taskset` may touch a SCHED_FIFO thread without `CAP_SYS_NICE`, and
   the stack runs as `ableton`). Rebuild it with `move/build-csound.sh` (arm64 Docker).

   > The same RPATH rule bites Csound, and harder. It carries RT capabilities too, so its
   > `LD_LIBRARY_PATH` is discarded — it could either find its libraries **or** run
   > realtime, never both, and silently chose the former by dropping every capability. Its
   > binaries are RPATH'd to `/data/UserData/pcslib` **and** `/data/UserData/phlib`: the
   > second is not optional, because `librtjack.so` links `libjack`, which is deliberately
   > *not* vendored into the Csound bundle (it has to be the same build the running `jackd`
   > speaks). Miss it and the JACK module fails to load, which surfaces as the thoroughly
   > misleading `could not connect to JACK server`.
2. **`deploy-controller.sh`** — the Python controller, vendored `python-osc`, the
   engine `.scd` files, the CSOUND orchestra (`csound/ph-engine.orc`), and the
   `run-*.sh` scripts.

   > It **re-asserts the RT capabilities** on every deploy. It used to run
   > `chown -R ableton:users` over the whole install, and chown **clears file
   > capabilities** — so deploying the controller silently stripped `cap_sys_nice` off
   > `jackd`, with nothing in the output to say so. It now chowns only what it ships.
   It also installs **CDP** (`move/bundle/poundhard-cdp.tar.gz`), the ~400-program set
   behind [Churn](docs/USER-GUIDE.md#churn), built from source by `move/build-cdp.sh`. No capabilities and
   nothing vendored alongside it: CDP only ever processes files, off the audio thread.
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

---

## Architecture & internals

**The controller is authoritative** for musical state (a `Project`: 16 tracks ×
{engine type, note, velocity, parameters, pattern + per-step locks — pitch, velocity,
pan, voice macro, ratchet, living flag/period, FX mask, **cycle divider**, the **per-step
sample window** and the **per-step filter** — mute, length, rate, **filter**}, plus FX assignment/bypass/macros, tempo, and the pattern bank — 16 seeds, each with a
lazily-allocated row of 16 expansions). A track
is at most **16 steps**; the per-step arrays are 32 wide for headroom and for projects
saved before the cap. It reads `control.json`, writes `status.json`, generates kits,
and pushes state to the engine over OSC.

**Modulation runs in the controller, not the engine.** `/ph/param` writes the engine's
per-track parameter store *and* sets the value on any ringing voice, but never touches the
controller's `Project` — so the 32-LFO bank can drive parameters continuously while nothing
is stored, and switching an LFO off simply re-sends the programmed value. Phase comes from
the bar position (`bars × cycles_per_bar`), resynced on the engine's own `/ph/cycle`, so
nothing free-runs and a tempo change carries the whole bank. Measured on the device, all 32
LFOs active cost **+0.6% DSP** — they send parameter messages and spawn no synths.

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

**BYTEBEAT and CSOUND are the two exceptions.** BYTEBEAT's is forced by the UGen rather
than chosen: it
parses its expression *per instance* and starts on an `Undefined` expression that
evaluates to 0, so a freshly spawned instance is silent until its asynchronous `/eval`
lands. Spawning one per hit raced the parse against the note — long notes won it, short
ones came out inaudible, and the same sound was not reproducible twice. That track keeps
**one live voice**, parsed once and re-triggered per step (`t_trig`, `doneAction: 0`),
with a free-running counter — which is what bytebeat is anyway.

**CSOUND's** is structural: its audio is generated by a separate process and arrives over
JACK, so there is nothing to spawn per hit. Its SC voice is a permanent carrier reading
that track's input pair onto the track bus, and a hit is a score event sent to Csound. The
carrier is deliberately left alone once running — setting gain on it, or moving it between
buses for a per-step send, is heard as a step in the middle of whatever is still ringing,
including a reverb tail fed from it.

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
| steps | `stepset` / `steptoggle`, `steplock`, `stepmacro`, `stepfx` (per-step FX mask), `stepcycle` (fire every Nth repetition), `stepwindow` (per-step sample slice), `stepfilter` (per-step filter lock), `marklive` / `liveperiod` (living steps — the period is in PLAYS of the step, 1-8) |
| clipboard | `stepcopy` / `steppaste`, `rowcopy` / `rowpaste`, `trackcopy` (the Copy-button gestures) |
| generation | `stepgen` (a new sequence for one track, scale-aware) |
| performance | `heat`, `shuffle`, `quake`, `churn`, `break` + `breakint`, `strobe`, `whim` (the seven temporary overlays) |
| randomizers | `steprand` (toggle one per-step parameter's randomizer), `randdebug` |
| transpose | `transpose` (one track's sequence), `transposeall` (project-wide, the cursor keys) |
| FX | `fxassign`, `fxbypass`, `fxmacro`, `fxwet` |
| modulation | `lfoenter` (assign/refresh the bank), `lfopad` (toggle one LFO), `lfogen` (re-roll all 32) |
| macros | `heat` / `heatpct`, `shuffle`, `quake`, `churn`, `break`, `chaos` / `chaosreset` |
| patterns & projects | `savepat` / `loadpat`, `patdel`, `patcopy` / `patpaste` / `patclipclear`, `expenter` / `expfirst` (open a seed's expansions), `genvar`, `randpat`, `saveproj` / `loadproj`, `loadauto` |
| transport & system | `run`, `editenter` / `editexit`, `recpad`, `undo`, `panic` |

`tempo` is a continuous field applied on change, not a queued command.

### status.json (controller → ui.js)

Carries `ready / engine / cpu / nodes / running / tempo / step / editTrack / solo / kit /
webPort`, per-track `muted / active / note / vel / pan / amp / rate / length` plus
`start / end` (SAMPLE's playable window) and `fcut / fres / ftype` (the track filter), the engine `types` / role `names` and
`drumTracks / drumMode`, the FX view state (`fxTop / fxBypass / fxOn / fxMacro / fxWet /
fxNames`), and the open track's `edit` block: `steps`, the effective per-step
`stepNote / stepVel / stepPan / stepMacro`, `living / period / ratchet / active`,
`fx` (per-step FX masks), `cycle` (per-step dividers), `stepStart / stepEnd` (the effective per-step sample window)
and `stepFcut / stepFres / stepFtype` (the effective per-step filter), plus the project's
`scale` (`{root, name}`, or null until something pitched establishes it).

Also the pattern bank, which is a hierarchy rather than a flat 32: `patFilled` is the
**16 seeds**, `expFilled` the open seed's **16 expansions**, `expSeed` which seed's row is
open (-1 = none) and `expCur` which expansion is live (-1 = the seed itself), alongside
`patCur / patPending / projFilled`. Then the `autoSave` flag, `projCur` (which project is
loaded) and `canUndo / canRedo`, the seven performance modifiers (`heat / heatPct / shuffle /
quake / churn / brk / brkEvery / brkNow / strobe / whim`), the modulation bank (`lfo`, 32
per-pad states of 0 none / 1 assigned / 2 active, and `lfoOn`) and the chaos macro (`chaos`), the SAMPLE capture state (`smpState / smpSrc / smpChain`), the recorder
(`recState / recSlot / recSlots / recElapsed / recAmp`), and `clipStep / clipRow` — whether
the Copy-gesture clipboard is holding a step or a row. The edit block also carries `rand`,
the list of per-step randomizers live on the open track.

### OSC (controller → engine, sclang langPort 57120)

`/ph/tempo` · `/ph/run` · `/ph/steps` · `/ph/track t typeIdx` (**-1=empty** 0=DRUM
1=FM7 2=BUCHLOID 3=MOLLY 4=RINGS 5=BEN 6=NOIZEOP 7=ICARUS 8=PLAITS 9=SHAKER 10=MEMBRANE 11=MALLET 12=BOWED 13=PLUCK 14=TUBE 15=CHAOS 16=WTABLE 17=BYTEBEAT 18=SAMPLE 19=CSOUND) ·
`/ph/param t "name" val` (WTABLE's `wt1`/`wt2` are sprite selectors — the engine (re)loads that oscillator's wavetable buffer instead of setting a synth arg; BYTEBEAT's `expr` is a bank index — the engine re-parses its **persistent** voice with the plugin's `/eval` unit command, sent a few control blocks after the node is created, never in the same instant; CSOUND's `arch` picks one of the ten architectures and its `m1`..`m8` are that architecture's macros — both travel to Csound in the score event, not to a synth) ·
`/ph/preview typeIdx note vel mode [name val …]` (audition one voice → master) ·
`/ph/pattern` · `/ph/stepset` · `/ph/steplock` · `/ph/stepmacro` · `/ph/clearlocks` ·
`/ph/clearcell t cell` (empty ONE step slot — what deleting a step sends, so the slot
carries nothing into the next step drawn there) ·
`/ph/stepratchet t cell k` · `/ph/stepsend t cell on` · `/ph/stepfx t cell mask`
(per-step FX: a bitmask over the 8 insert slots, **-1 = no lock**) ·
`/ph/stepcycle t cell n` (fire on every **n**-th repetition of the pattern, 1-8) ·
`/ph/stepfxcycle t cell n` (apply the step's FX mask on every **n**-th PLAY of the step,
1-8 — multiplies with `/ph/stepcycle` the way a living step's period does) ·
`/ph/stepsmp t cell start end` (per-step SAMPLE window, **-1 = inherit the track's**) ·
`/ph/filter t cutoff res type` (per-track multimode filter, type 0=LP 1=HP) ·
`/ph/stepfilt t cell cutoff res type` (per-step filter lock, **cutoff < 0 = follow the track**) ·
`/ph/livingfx dTime dFb dMix vMix vRoom vDamp`
(living-step ratchet / per-step FX-send routing / send-bus params) ·
`/ph/smparm t thresh` (arm the threshold capture) · `/ph/smpwrite \"path\"` · `/ph/smpload \"path\"` ·
`/ph/smpassign t \"path\"` (give the track its OWN buffer, release the pad) ·
`/ph/smpcopy src dst` (duplicate a track's sample buffer — a COPY, so the two tracks can
diverge; what Copy-track sends) ·
`/ph/churncap "path" dur` (record `dur` seconds of the master POST-limiter and write a
finalised WAV — the file appearing is the completion signal) ·
`/ph/churnload "path" slot` · `/ph/churnplay slot amp pan rate hp` · `/ph/churnclear` ·
back: `/ph/smprec`
`/ph/smpdone` `/ph/smpwritten` `/ph/smpready` ·
`/ph/mute` · `/ph/note` · `/ph/vel` · `/ph/length` · `/ph/rate` · `/ph/edittrack` ·
`/ph/fxassign` · `/ph/fxbypass` · `/ph/fxset` · `/ph/fxclear` · `/ph/recstart "path"` ·
`/ph/recstop` · `/ph/mastergain` · `/ph/masterfilter` · `/ph/panic` · `/ph/ping`.

### Telemetry (engine → controller, port 57140)

`/ph/ready` (once) · `/ph/step n` (per step, −1 = stopped) · `/ph/cycle` (each
16-step bar boundary) · `/ph/cpu avg peak nodes`.

---

---

## Repository layout

```
controller/poundhard/   catalog.py    parameter specs for every engine (ranges, musical bands, modulatable)
                        kits.py       sound generation — roles, engine palettes, voice rolls
                        recipes.py    the 18 pattern-generation briefs + candidate scoring
                        variations.py whole-pattern generation and per-pattern variations
                        stepgen.py    the six rhythm algorithms
                        lfo.py        the 32-LFO modulation bank (targets, sync, non-destructive output)
                        strobe.py  churn.py  phrase.py  compass.py   performance modifiers
                        tracks.py     Project / Track — the authoritative musical state
                        engine_bridge.py  OSC to the engine   headless.py  the controller loop
                        csoundfx.py   the SAMPLE engine's offline Csound mangler
                        webserver.py  params.py
controller/vendor/      pythonosc (vendored — no pip on the device)
supercollider/          boot.scd  engine.scd  synthdefs.scd
supercollider/plugins/  ByteBeat, PhSoftcut, PhMicIn — native UGens built for the CM4
csound/                 build-orc.py  ph-engine.orc  trims.txt   (engine 20's orchestra)
docs/                   USER-GUIDE.md — the tutorial and manual
move/                   run-*.sh  stop-stack.sh  deploy*.sh  sc/ph-boot.scd
move/schwung-module/poundhard/   module.json  ui.js  exit-hook.sh  dsp/
web/                    poundhard-logo.svg   (brand mark — also served by the web UI)
```

The wordmark uses **[Chakra Petch](https://fonts.google.com/specimen/Chakra+Petch)** —
an angular, industrial typeface that suits the hard, percussion-centric aesthetic.

---

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
- **A process the teardown forgets is worse than one that dies.** `stop-stack.sh` used to
  kill `sclang`, `scsynth` and `jackd` but neither `supernova` nor `csound`. A surviving
  supernova makes the next boot attach to an **orphan server** — `ready` true, zero nodes,
  no audio. A surviving Csound loses its JACK client with `jackd` and then lingers
  *dead-but-present*, which was enough to make `run-csound.sh` skip starting a live one, so
  the CSOUND engine came back silent. Both are killed now, and `run-csound.sh` **replaces**
  any existing instance rather than adopting it.
- **`set -e` will skip the tail of a launch script.** The Csound launch used to sit at the
  end of `run-engine.sh`; any non-zero command above it ended the script first, so engine 20
  never started and nothing in the log said why. It is launched from `run-stack.sh` now, in
  its own subshell that waits for the server's ports and cannot be skipped by an unrelated
  failure upstream. A launcher that can silently not-launch is worth restructuring.
- **Realtime placement matters as much as realtime priority.** Csound came up at priority
  **65 — exactly supernova's DSP threads** — and unpinned across all four cores, so it
  competed with the very threads that consume its audio in the same JACK cycle and migrated
  between them mid-callback. That was the XRuns. It runs at **68**, above the DSP threads
  and below `jackd`, pinned to core 3. Measured: 0 XRuns over 25 s with four Csound tracks
  and reverbs at 43% CPU, where the same rig XRan before.
- **A limiter has to be after the sum, not on each voice.** Every Csound voice was
  individually under the ceiling and four overlapping hits on one track summed straight
  past it. Voices accumulate onto a per-track bus and one limiter runs after the sum. The
  same trap in miniature: that limiter is a UDO called once per track **by name**, because
  its detector and held gain are state and a runtime loop would reuse one instance for all
  17 pairs — a single loud track would have ducked every other one.
- **Deleting something must delete its state, not just its visible part.** Turning a step
  off removed the hit and left its pitch, velocity, pan, macro, FX mask, cycle divider,
  filter, window, ratchet, send and living mark in the slot, which the next step drawn
  there inherited. The fix derives the field list from the `Track` dataclass rather than
  writing it out, so a per-step parameter added later is cleared automatically — the
  hand-written list in `clear_pattern` had already drifted and was missing five fields.

---

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
| **Csound** | the **CSOUND engine (20)** and the SAMPLE engine's offline mangler — **shipped in the runtime bundle** (`move/bundle/poundhard-csound.tar.gz`, 20 opcode plugins incl. `librtjack`) | LGPL-2.1-or-later |
| **Composers Desktop Project (CDP8)** | the transform engine behind the **CHURN** modifier — **shipped**, built from source (`move/bundle/poundhard-cdp.tar.gz`, ~220 aarch64 programs) | see `CDP8/LICENSE.txt` (LGPL-2.1 for the library, per-program notices) |
| **softcut-lib** (github.com/monome/softcut-lib) | the tape engine under **COMPASS**, built as the `PhSoftcut` UGen (prebuilt `.so` shipped) | **GPL-3.0** (monome) |
| **Compass** (github.com/oliviercreurer/compass) by Olivier Creurer, w/ contributions from @justmat + @gonecaving | `controller/compass/compass.lua` is vendored **verbatim** and executed, not reimplemented. The COMPASS modifier built on it was **retired** — it never reproduced its input convincingly on this hardware — and STROBE now occupies that pad. The script and its softcut infrastructure remain in the tree, unused, and the attribution stands. | no licence file upstream; © its author, vendored unmodified with attribution |
| **Lua** (5.4) | the interpreter COMPASS runs that script under — **shipped in the runtime bundle** (`move/bundle/poundhard-lua.tar.gz`) | MIT |
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
