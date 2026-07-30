"""PoundHard headless controller (runs on the Move).

Bridges the Schwung ui.js hardware layer (which can't open sockets) to the SC
engine:

    ui.js  --writes-->  share/control.json  --polled by--> this controller
    ui.js  <--reads--   share/status.json   <--written by-- this controller
    this controller  --OSC /ph/...-->  sclang engine (127.0.0.1:57120)

The controller owns the authoritative musical state (Project); the engine owns
the step clock + DSP and streams back /ph/step (playhead) + /ph/cpu telemetry.
"""
from __future__ import annotations

import json
import os
import random
import signal
import sys
import threading
import time
import traceback
from pathlib import Path

from . import catalog
from .catalog import FX_SPECS, N_FX
from .engine_bridge import EngineBridge
from .tracks import DRUM_TRACKS, N_PATTERNS, N_STEPS, N_TRACKS, Project


def _env(k: str, d: str) -> str:
    v = os.environ.get(k)
    return v if v not in (None, "") else d


SC_HOST = _env("SC_HOST", "127.0.0.1")
SC_PORT = int(_env("SC_PORT", "57120"))
TELEMETRY_PORT = int(_env("CONTROLLER_PORT", "57140"))
SHARE = Path(_env("PH_SHARE", "/data/UserData/poundhard/share"))
CONTROL_FILE = SHARE / "control.json"
STATUS_FILE = SHARE / "status.json"
PROJECT_FILE = SHARE / "project.json"
PROJECTS_DIR = Path(_env("PH_PROJECTS", "/data/UserData/poundhard/projects"))
RECORDINGS_DIR = Path(_env("PH_RECORDINGS", "/data/UserData/poundhard/recordings"))
WEB_PORT = int(_env("PH_WEB_PORT", "7177"))        # http://move.local:7177 (download recordings)
N_RECORDINGS = 8                                   # recording slots
REC_MAX_SEC = 420.0                                # hard cap: 7 minutes per recording
REC_TAIL_MAX_SEC = 30.0                            # safety: cut the tail if it never goes silent
REC_SILENCE_THRESH = float(_env("PH_REC_SILENCE", "0.004"))   # master level counted as "silent"
REC_SILENCE_SEC = 1.2                              # ...must stay below it this long to end the take
CONTROL_HZ = float(_env("PH_CONTROL_HZ", "30"))    # control.json poll rate
SNAP_HZ = float(_env("PH_SNAPSHOT_HZ", "5"))       # status.json write rate (lower = less SD I/O)
# AUTOSAVE: a recovery file, deliberately SEPARATE from the 32 user project slots — it
# never overwrites anything you saved by hand. Written only when something changed, and
# not often: a whole project is a chunky JSON and SD churn is what makes the Move's UI
# stall. Restore it with Shift+Menu in the project view.
AUTOSAVE_FILE = PROJECTS_DIR / "autosave.json"
AUTOSAVE_SEC = float(_env("PH_AUTOSAVE_SEC", "30"))


class Controller:
    def __init__(self) -> None:
        self.state = Project()
        self.bridge = EngineBridge(SC_HOST, SC_PORT, "127.0.0.1", TELEMETRY_PORT)
        self.bridge.on_smprec = self._smp_on_rec
        self.bridge.on_smpdone = self._smp_on_done
        self.bridge.on_smpwritten = self._smp_on_written
        self.bridge.on_smpready = self._smp_on_ready
        self._stop = threading.Event()
        self._built = threading.Event()
        self._last_seq = -1
        # control.json survives a restart, so the queue we first read belongs to the PREVIOUS
        # session. Replaying it dumped a whole machine's worth of commands onto an engine that
        # was still booting — which floods the server with messages for nodes that don't exist
        # yet and can leave the graph wedged (ready, but silent). Adopt the file's high-water
        # mark on the first read instead of executing it.
        self._seq_primed = False
        # STEP / ROW CLIPBOARD (Copy-button gestures in the edit view). Not persisted: it is
        # a performance tool, not project state.
        self._gen_note = ""
        self._step_clip: dict | None = None
        self._row_clip: list | None = None
        self._last_tempo = None
        self._last_status_key: str | None = None
        self._last_status_write = 0.0
        self._threads: list[threading.Thread] = []
        # RLock (not Lock): re-entrant, so a nested acquire can never self-deadlock the
        # control loop. A deadlocked dispatch is indistinguishable from a dead instrument.
        self._lock = threading.RLock()         # serialize state mutations (dispatch vs telemetry)
        self.bridge.on_cycle = self._on_cycle  # apply a queued pattern switch on the bar boundary
        self.bridge.on_amp = self._on_amp      # master level while recording -> ends the tail
        self._quiet_since: float | None = None
        self._proj_slots = [False] * N_PATTERNS  # which project files exist on disk (cached)
        self._proj_cur = -1                      # which project slot is LOADED (-1 = none)
        self._dirty = False                      # state changed since the last autosave
        self._autosaved = False                  # a recovery file exists (for the UI)
        # SAMPLE engine capture lifecycle: idle -> armed -> recording -> processing -> ready.
        # The pad holds ONE take; assigning it to a track releases the pad for the next one.
        self._smp_state = "idle"
        self._smp_src = -1                 # engine pad being sampled (for the readout)
        self._smp_chain: list[str] = []     # the Csound stages the take went through
        self._smp_thresh = 0.02
        # HEAT macro: mass-mark a fraction of sequenced steps as living (live performance)
        self._heat_on = False                    # macro engaged
        self._heat_pct = 0.5                     # fraction of hits to heat (knob-1 adjustable)
        # SHUFFLE macro: temporarily swap rhythmic structures (pattern/length/rate) BETWEEN
        # tracks. Pure engine-side overlay — the controller's Track state is never touched, so
        # it's automatically temporary and never saved. _shuffle_perm: engine track -> source.
        self._shuffle_on = False
        self._shuffle_perm: dict[int, int] = {}
        # QUAKE: an engine-only overlay of lengths + clock ratios. _quake_saved holds each
        # touched track's OWN (length, rate) so toggling off restores exactly, without the
        # pattern ever having been modified.
        self._quake_on = False
        self._quake_saved: dict[int, tuple[int, float]] = {}
        # CHURN: a background pipeline. _churn_ready holds slots that have a transformed
        # fragment loaded and a remaining play budget; the worker keeps refilling them while
        # the bar callback spends them. Nothing here is ever written to a track.
        self._churn_on = False
        self._churn_thread: threading.Thread | None = None
        self._churn_stop = threading.Event()
        self._churn_ready: dict[int, int] = {}      # slot -> plays remaining
        self._churn_gain: dict[int, float] = {}     # slot -> level-matching gain
        self._churn_lock = threading.Lock()
        self._churn_note = ""
        # BREAK: every N pattern cycles, one cycle is transformed and then handed straight
        # back. _break_active holds what was overridden so the restore is exact; the pattern
        # data is never touched, so restoring is just re-pushing the controller's own state.
        self._break_on = False
        self._break_every = 4                    # pattern cycles between breaks
        self._break_cycles = 0
        self._break_active = False
        self._break_last = ""
        self._break_touched: dict = {}
        # PER-PARAMETER STEP RANDOMIZERS. {track: {param}} — each one independent, each an
        # OVERLAY: the programmed per-step values are never written, so switching one off
        # is just re-pushing the track's own state.
        self._rand: dict[int, set] = {}
        # COMPASS: a command sequencer improvising on one or two tracks. Same overlay
        # primitives as QUAKE and BREAK (rate, length, step list, pan), so it joins their
        # mutual-exclusion group rather than fighting them for the same parameters.
        self._compass_on = False
        self._compass = None
        self._rand_debug = False
        # performance recording
        self._rec_state = "idle"                 # idle | armed | recording
        self._rec_slot = -1                      # armed / recording slot
        self._rec_start = 0.0                    # monotonic start time
        self._rec_timer: threading.Timer | None = None
        self._rec_slots = [False] * N_RECORDINGS # which slots have a .wav on disk

    # -- lifecycle --------------------------------------------------------- #
    def start(self) -> None:
        SHARE.mkdir(parents=True, exist_ok=True)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self._proj_slots = [(PROJECTS_DIR / f"proj_{s:02d}.json").exists() for s in range(N_PATTERNS)]
        self._scan_recordings()
        # web UI (download recordings) — daemon thread, survives on its own
        from . import webserver
        webserver.serve(WEB_PORT, RECORDINGS_DIR, N_RECORDINGS)
        # Fresh session: all 16 tracks start EMPTY (no engine, silent) — the user
        # builds a rig by assigning engines from the palette.
        #
        # But there is ALWAYS a pattern. PoundHard used to open with no pattern at all and
        # `pattern_cur = -1`, so the pattern view showed 32 dead slots and the first thing
        # you had to do was save one before anything could be written down. Slot 1 is
        # seeded with the empty machine and made current, so whatever you play, generate or
        # assign lands somewhere from the first press — and is carried into a project when
        # you save one, because saving folds the live state into its own slot first.
        self.state.save_pattern(0)
        self._autosaved = AUTOSAVE_FILE.exists()
        self.bridge.start(on_ready=self._on_ready)
        for fn in (self._control_loop, self._status_loop, self._handshake_loop,
                   self._autosave_loop):
            t = threading.Thread(target=self._safe_loop, args=(fn,), daemon=True)
            t.start()
            self._threads.append(t)

    def run(self) -> None:
        while not self._stop.is_set():
            time.sleep(0.1)

    def stop(self, *_a) -> None:
        self._stop.set()
        self.bridge.stop()

    def _safe_loop(self, fn) -> None:
        """Run a loop forever. A crash must NOT permanently kill it — a dead control loop
        means no transport, no sound and no project loading (the whole instrument bricks
        until relaunch). So: log loudly, then restart the loop."""
        while not self._stop.is_set():
            try:
                fn()
                return                                   # clean exit (stop requested)
            except Exception:
                print(f"[poundhard] LOOP CRASHED: {fn.__name__} — restarting", flush=True)
                traceback.print_exc()
                sys.stdout.flush()
                sys.stderr.flush()
                time.sleep(0.5)                          # brief backoff, then resume

    def _handshake_loop(self) -> None:
        # The engine may boot after us; ping until it answers /ph/ready.
        while not self._stop.is_set():
            if not self._built.is_set():
                self.bridge.ping()
            time.sleep(1.0)

    def _on_ready(self) -> None:
        self._built.set()
        self._push_all()

    # -- push authoritative state to the engine ---------------------------- #
    def _push_all(self) -> None:
        # a full-machine replacement (pattern/project load) drops the HEAT + SHUFFLE toggles —
        # the living flags now come from the freshly-loaded pattern, and push_track below sends
        # each track's OWN (original) rhythm, so any shuffle overlay is naturally undone.
        self._heat_on = False
        self._shuffle_on = False
        self._shuffle_perm = {}
        self.state.shuffle_perm = {}
        self._quake_on = False
        self._quake_saved = {}
        self.bridge.steps(self.state.steps)
        self.bridge.tempo(self.state.tempo)
        for t in range(N_TRACKS):
            self.bridge.clearlocks(t)                       # reset stale per-step locks first
            self.bridge.push_track(t, self.state.tracks[t])
            self._push_step_macros(t)
        # FX macros + dry/wet (all types) then assignments + bypass
        for fx in range(N_FX):
            for arg, val in self.state.macro_values(fx):
                self.bridge.fxset(fx, arg, val)
            self.bridge.fxset(fx, "wet", self.state.fx_wet[fx])
        self.bridge.fxclear()   # drop any FX the engine still holds from a previous state
        for t in range(N_TRACKS):
            for fx in self.state.track_fx[t]:
                self.bridge.fxassign(t, fx, True)
            if self.state.fx_bypass[t]:
                self.bridge.fxbypass(t, True)
        self._push_mutes()      # push_track sent raw mutes; correct them for solo

    def _push_mutes(self) -> None:
        """Push EFFECTIVE mutes (own mute OR 'not the soloed track') for every track."""
        for t in range(N_TRACKS):
            self.bridge.mute(t, self.state.eff_muted(t))

    def _push_step_cell(self, t: int) -> None:
        """Push one track's whole per-step state after a clipboard paste — the pattern plus
        every lock — so the engine plays the pasted step exactly like its source."""
        tr = self.state.tracks[t]
        self.bridge.pattern(t, tr.pattern)
        for cell in range(N_STEPS):
            if (tr.step_note[cell] is not None or tr.step_vel[cell] is not None
                    or tr.step_pan[cell] is not None):
                self.bridge.steplock(t, cell, tr.eff_note(cell), tr.eff_vel(cell), tr.eff_pan(cell))
            self.bridge.stepfx(t, cell, tr.step_fx[cell])
            self.bridge.stepfxcycle(t, cell, tr.step_fxcycle[cell])
            self.bridge.stepcycle(t, cell, tr.step_cycle[cell])
            self.bridge.stepsmp(t, cell,
                                -1.0 if tr.step_start[cell] is None else tr.step_start[cell],
                                -1.0 if tr.step_end[cell] is None else tr.step_end[cell])
            fl = tr.step_filt[cell]
            self.bridge.stepfilt(t, cell, -1.0 if fl is None else fl[0],
                                 0.0 if fl is None else fl[1], 0 if fl is None else fl[2])
            self.bridge.stepratchet(t, cell, tr.step_ratchet[cell])
            self.bridge.stepsend(t, cell, bool(tr.step_send[cell]))
        self._push_step_macros(t)

    def _push_notes(self, t: int) -> None:
        """Re-push only what a transposition changes: the track note and every pitched step
        lock. Velocity, pan, FX, cycle intervals and living marks are left alone."""
        tr = self.state.tracks[t]
        self.bridge.note(t, tr.eff_track_note())
        for cell in range(N_STEPS):
            if (tr.step_note[cell] is not None or tr.step_vel[cell] is not None
                    or tr.step_pan[cell] is not None):
                self.bridge.steplock(t, cell, tr.eff_note(cell), tr.eff_vel(cell), tr.eff_pan(cell))

    def _push_step_macros(self, t: int) -> None:
        for cell in range(N_STEPS):
            pairs = self.state.step_engine_macro(t, cell)   # living transform takes precedence
            if pairs is not None:
                self.bridge.stepmacro(t, cell, pairs)
            r = self.state.tracks[t].step_ratchet[cell]
            if r != 1:
                self.bridge.stepratchet(t, cell, r)
            if self.state.tracks[t].step_send[cell]:
                self.bridge.stepsend(t, cell, True)

    def _push_living_cell(self, t: int, c: int) -> None:
        """Push a single living step's freshly-rolled transform to the engine."""
        tr = self.state.tracks[t]
        self.bridge.steplock(t, c, tr.eff_note(c), tr.eff_vel(c), tr.eff_pan(c))
        self.bridge.stepmacro(t, c, self.state.step_engine_macro(t, c) or [])
        self.bridge.stepratchet(t, c, tr.step_ratchet[c])
        self.bridge.stepsend(t, c, tr.step_send[c])

    def _clear_engine_cell(self, t: int, c: int) -> None:
        """Wipe one step slot in the engine — the mirror of Project.clear_step."""
        self.bridge.clearcell(t, c)
        self.bridge.stepmacro(t, c, [])

    def _reset_engine_cell(self, t: int, c: int) -> None:
        """Reset a cell in the engine to its plain, untransformed state (after unmarking)."""
        tr = self.state.tracks[t]
        self.bridge.steplock(t, c, tr.eff_note(c), tr.eff_vel(c), tr.eff_pan(c))
        self.bridge.stepmacro(t, c, [])
        self.bridge.stepratchet(t, c, 1)
        self.bridge.stepsend(t, c, 0)

    # -- SAMPLE engine: capture -> Csound mangle -> audition -> assign ------ #
    def _smp_paths(self):
        d = RECORDINGS_DIR / "sample"
        d.mkdir(parents=True, exist_ok=True)
        return d / "take_raw.wav", d / "take_mangled.wav"

    def _smp_arm(self, src: int) -> None:
        """Hold SAMPLE + tap engine `src`: arm a threshold capture on that track's bus."""
        self._smp_state = "armed"
        self._smp_src = int(src)
        self._smp_chain = []
        self._dirty = True
        self.bridge.smparm(src, self._smp_thresh)

    def _smp_on_rec(self) -> None:
        if self._smp_state == "armed":
            self._smp_state = "recording"
            self._dirty = True

    def _smp_on_done(self) -> None:
        """Capture synth freed: either the buffer filled or it timed out with nothing."""
        if self._smp_state == "recording":
            self._smp_state = "processing"
            self._dirty = True
            raw, _ = self._smp_paths()
            self.bridge.smpwrite(raw)          # flush the take, then mangle it
        elif self._smp_state == "armed":
            self._smp_state = "idle"           # nothing ever crossed the threshold
            self._dirty = True

    def _smp_on_written(self, path: str) -> None:
        if not path:
            self._smp_state = "idle"
            self._dirty = True
            return
        threading.Thread(target=self._smp_mangle, args=(path,), daemon=True).start()

    def _smp_mangle(self, raw: str) -> None:
        """Run the take through a freshly assembled Csound opcode graph. Off-thread: a
        render takes seconds and must never stall the sequencer or the UI bridge."""
        _, dst = self._smp_paths()
        try:
            from . import csoundfx
            self._smp_chain = csoundfx.render(raw, str(dst))
            self.bridge.smpload(dst)           # engine loads it -> on_smpready
        except Exception as exc:               # a failed mangle must not wedge the engine
            print(f"[poundhard] sample mangle failed: {exc}")
            self._smp_state = "idle"
            self._dirty = True

    def _smp_on_ready(self, dur: float) -> None:
        self._smp_state = "ready"
        self._dirty = True

    def _smp_release(self) -> None:
        """Assigned to a track: the track owns the buffer now, so the pad is free again."""
        self._smp_state = "idle"
        self._smp_src = -1
        self._smp_chain = []
        self._dirty = True

    # -- SHUFFLE macro ----------------------------------------------------- #
    def _push_track_rhythm(self, engine_track: int, src_track: int) -> None:
        """Send src_track's rhythmic structure (steps + length + rate) to engine_track —
        the target keeps its own SOUND but plays the source's rhythm."""
        src = self.state.tracks[src_track]
        self.bridge.pattern(engine_track, src.pattern)
        self.bridge.length(engine_track, src.length)
        self.bridge.rate(engine_track, src.rate)

    # -- CHURN: capture -> CDP -> place ------------------------------------- #
    CHURN_SLOTS = 4

    def _churn_dir(self):
        d = RECORDINGS_DIR / "churn"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _churn_worker(self) -> None:
        """Keep the slots stocked with freshly transformed fragments.

        One fragment is captured, transformed and loaded while the ones already loaded are
        still being played, which is what makes the stream continuous rather than a stutter
        of silence between ornaments. The loop is deliberately unhurried: a chain takes ~0.13
        s but there is no value in generating faster than the bar callback can spend them.
        """
        from . import churn
        rng = random.Random()
        work = self._churn_dir()
        slot = 0
        while not self._churn_stop.is_set():
            try:
                with self._churn_lock:
                    # only refill a slot that is spent — a fragment mid-budget is still wanted
                    free = [k for k in range(self.CHURN_SLOTS)
                            if self._churn_ready.get(k, 0) <= 0]
                if not free or not self.state.running:
                    self._churn_stop.wait(0.5)
                    continue
                slot = free[0]
                raw = work / ("cap%d.wav" % slot)
                out = work / ("orn%d.wav" % slot)
                try:
                    raw.unlink()
                except OSError:
                    pass
                dur = rng.uniform(0.5, 1.6)
                self.bridge.churncap(raw, dur)
                # wait for the engine to finish writing — the file appears only once
                # Buffer.write's callback fires, so its presence IS the finalisation signal
                deadline = time.monotonic() + dur + 4.0
                while time.monotonic() < deadline and not self._churn_stop.is_set():
                    if raw.exists() and raw.stat().st_size > 4000:
                        break
                    self._churn_stop.wait(0.05)
                if self._churn_stop.is_set() or not raw.exists():
                    continue
                # A SILENT capture must never become an ornament. The file is well-formed
                # and full-length, so nothing downstream can tell — CDP transforms silence
                # into silence and Churn plays it, which is indistinguishable from the
                # feature being broken. Check the audio, not the file.
                if churn.peak(raw) < 0.004:
                    self._churn_stop.wait(0.4)
                    continue
                desc = churn.transform(raw, out, work, rng)
                if not desc:
                    continue
                if churn.peak(out) < 0.004:        # and the transform can silence it too
                    continue
                if churn.clipped(out):
                    # A transform that came back clipped is distortion, not ornamentation,
                    # and no amount of level-matching downstream can undo it.
                    print("[poundhard] churn: discarded a clipped ornament (%s)" % desc,
                          flush=True)
                    continue
                self.bridge.churnload(out, slot)
                time.sleep(0.25)                 # let the buffer read land
                # LEVEL-MATCH. CDP output ranges over tens of dB between transforms, so a
                # fixed playback amp makes half the ornaments inaudible under the mix and
                # the other half jump out. Measure this one and derive the gain that lands
                # it at a consistent level.
                pk = churn.peak(out)
                gain = 1.0 if pk <= 0.01 else min(8.0, 0.7 / pk)
                with self._churn_lock:
                    # how long an ornament stays in rotation. Long enough to become
                    # musically meaningful, short enough not to turn into a loop.
                    self._churn_ready[slot] = rng.choice((1, 2, 2, 3, 3, 4))
                    self._churn_gain[slot] = gain
                self._churn_note = desc
                print("[poundhard] churn slot %d: %s" % (slot + 1, desc), flush=True)
            except Exception as e:                # a worker must never take the stack down
                print("[poundhard] churn worker: %r" % (e,), flush=True)
                self._churn_stop.wait(1.0)

    def _churn_spend(self) -> None:
        """Bar boundary: drop a ready ornament into a gap, if there is one worth using.

        Placement comes from `churn.gaps`, which ranks steps by how much is already
        happening on them. Churn is meant to fill space, not compete, so it takes from the
        quiet end of that ranking — and not every bar, or it stops being ornamentation.
        """
        from . import churn
        if not self._churn_on or not self.state.running:
            return
        with self._churn_lock:
            live = [k for k, n in self._churn_ready.items() if n > 0]
        if not live:
            return
        if random.random() < 0.15:                 # leave the occasional bar alone
            return
        slot = random.choice(live)
        order = churn.gaps(self.state)
        step = random.choice(order[:5])            # one of the five quietest places
        st = self.state
        step_dur = (60.0 / max(20.0, st.tempo)) / 4.0
        delay = step * step_dur
        # level-matched to the ornament's own peak, then set UNDER the music
        with self._churn_lock:
            g = self._churn_gain.get(slot, 1.0)
        # Loud enough to be heard against a full mix. At 0.30-0.55 of the matched level
        # the ornaments measured ~10 dB under the music and read as "not working"; this is
        # ornamentation, so it still sits below the pattern, but audibly so.
        amp = g * random.uniform(0.55, 0.95)
        pan = random.uniform(-0.85, 0.85)
        rate = random.choice((1.0, 1.0, 0.5, 2.0, 1.5))
        hp = random.uniform(140.0, 320.0)          # keep every ornament out of the kick's way

        def fire():
            self.bridge.churnplay(slot, amp, pan, rate, hp)
            print("[poundhard] churn PLAY slot %d step %d amp %.2f rate %.2g hp %d"
                  % (slot + 1, step, amp, rate, hp), flush=True)
            with self._churn_lock:
                if self._churn_ready.get(slot, 0) > 0:
                    self._churn_ready[slot] -= 1

        t = threading.Timer(delay, fire)
        t.daemon = True
        t.start()

    def _churn_start(self) -> None:
        from . import churn
        if not churn.available():
            print("[poundhard] churn: CDP not installed — nothing to do", flush=True)
            return
        self._churn_stop.clear()
        self._churn_ready = {}
        self._churn_gain = {}
        self._churn_thread = threading.Thread(target=self._churn_worker, daemon=True)
        self._churn_thread.start()

    def _churn_end(self) -> None:
        """Stop generating and free everything. Nothing to restore: Churn only ever added
        playback events, so silence is the original state."""
        self._churn_stop.set()
        self._churn_thread = None
        self._churn_ready = {}
        self._churn_gain = {}
        self.bridge.churnclear()

    # -- COMPASS: the norns command sequencer, driving a softcut tape loop ---- #
    def _compass_tick(self) -> None:
        """One pattern cycle of the command sequencer."""
        if not self._compass_on or not self._compass or not self.state.running:
            return
        line, args = self._compass.tick()
        if line is None:
            return
        for k, v in args.items():
            self.bridge.compassset(k, v)
        print("[poundhard] " + line, flush=True)

    def _compass_end(self) -> None:
        """Take the tape loop down. Nothing to restore: Compass records the master and
        plays into the master, so it never touched a track, a pattern or a parameter."""
        self.bridge.compass(False)
        self._compass = None

    # -- per-parameter step randomizers ------------------------------------- #
    def _rand_active(self, t: int) -> set:
        return self._rand.get(t, set())

    def _rand_toggle(self, t: int, param: str) -> bool:
        """Flip one randomizer on one track. Returns the new state."""
        from . import steprand
        cur = self._rand.setdefault(t, set())
        if param in cur:
            cur.discard(param)
            # restore the PROGRAMMED values for this track — they were never modified, so
            # this is exact, and any other randomizer still on will re-apply next cycle
            self._push_step_cell(t)
            if not cur:
                self._rand.pop(t, None)
            return False
        cur.add(param)
        self._rand_apply(t)                      # audible immediately, not next bar
        return True

    def _rand_apply(self, t: int) -> None:
        """Push one fresh set of values for every randomizer active on this track."""
        from . import steprand
        active = self._rand_active(t)
        if not active:
            return
        st = self.state
        tr = st.tracks[t]
        rng = random.Random()
        # velocity / pan / pitch all live in the same steplock message, so they are
        # collected first and pushed once per cell — three separate pushes would each
        # overwrite the previous two with the cell's programmed values.
        lock = {}
        for param in ("vel", "pan", "pitch"):
            if param in active:
                lock[param] = steprand.generate(param, tr, st, rng)
        if lock:
            cells = set()
            for d in lock.values():
                cells |= set(d)
            sent = []
            for c in cells:
                nn = lock.get("pitch", {}).get(c, tr.eff_note(c))
                vv = lock.get("vel", {}).get(c, tr.eff_vel(c))
                pp = lock.get("pan", {}).get(c, tr.eff_pan(c))
                self.bridge.steplock(t, c, nn, vv, pp)
                sent.append((c, nn, round(vv, 2)))
            if self._rand_debug:
                print("[poundhard] rand T%d -> %s" % (t + 1, sent), flush=True)
        if "macro" in active:
            for c, pos in steprand.generate("macro", tr, st, rng).items():
                self.bridge.stepmacro(t, c, st._macro_pairs_at(t, pos))
        # cutoff and resonance share the per-step filter triple, same reasoning as above
        if "fcut" in active or "fres" in active:
            base = steprand.generate("fcut" if "fcut" in active else "fres", tr, st, rng)
            if "fcut" in active and "fres" in active:
                other = steprand.generate("fres", tr, st, rng)
                base = {c: (v[0], other.get(c, (0, v[1]))[1], v[2]) for c, v in base.items()}
            for c, (cut, res, ty) in base.items():
                self.bridge.stepfilt(t, c, cut, res, ty)
        if "start" in active or "end" in active:
            which = "start" if "start" in active else "end"
            for c, (s0, e0) in steprand.generate(which, tr, st, rng).items():
                self.bridge.stepsmp(t, c, s0, e0)

    def _rand_tick(self) -> None:
        """A new set of values every pattern cycle, for every track that has any."""
        if not self._rand or not self.state.running:
            return
        for t in list(self._rand):
            self._rand_apply(t)

    # -- BREAK: automatic, musically-placed breakdowns ---------------------- #
    def _break_tick(self) -> None:
        """Called on every pattern cycle. Ends a break that is running, or starts one.

        A break lasts exactly ONE cycle and both edges land on a cycle boundary, which is
        what makes it sound placed rather than dropped in: the pattern goes away at the top
        of a bar and comes back at the top of the next.
        """
        if not self._break_on:
            return
        if self._break_active:
            self._break_end()
            return
        if not self.state.running:
            return
        self._break_cycles += 1
        if self._break_cycles < max(1, self._break_every):
            return
        self._break_cycles = 0
        self._break_start()

    def _break_start(self) -> None:
        from . import breaks
        pl = breaks.plan(self.state, avoid=self._break_last)
        if not pl:
            return
        st = self.state
        touched = {"mute": [], "pattern": [], "rate": [], "filter": []}
        for t in set(pl["mute"]):
            self.bridge.mute(t, True)
            touched["mute"].append(t)
        for t, steps in pl["pattern"].items():
            self.bridge.pattern(t, steps)
            touched["pattern"].append(t)
        for t, r in pl["rate"].items():
            self.bridge.rate(t, r)
            touched["rate"].append(t)
        for t, (cut, res, ty) in pl["filter"].items():
            self.bridge.filter(t, cut, res, ty)
            touched["filter"].append(t)
        self._break_touched = touched
        self._break_active = True
        self._break_last = pl["name"]
        print("[poundhard] " + breaks.describe(pl), flush=True)

    def _break_end(self) -> None:
        """Put back exactly what was overridden, from the controller's own state — which
        the break never modified, so this cannot drift."""
        st = self.state
        tch = self._break_touched or {}
        for t in tch.get("pattern", []):
            self.bridge.pattern(t, st.tracks[t].pattern)
        for t in tch.get("rate", []):
            self.bridge.rate(t, st.tracks[t].rate)
        for t in tch.get("filter", []):
            tr = st.tracks[t]
            self.bridge.filter(t, tr.filt_cutoff, tr.filt_res, tr.filt_type)
        if tch.get("mute"):
            self._push_mutes()                   # effective mutes, so solo stays correct
        self._break_touched = {}
        self._break_active = False

    def _apply_quake(self) -> None:
        """Push a fresh Quake configuration: different lengths (polymeter) and ratio clock
        rates (polyrhythm) per track. The controller's state is NOT touched — the originals
        are saved here and pushed back on toggle-off."""
        from . import quake
        cfg = quake.plan(self.state)
        self._quake_saved = {}
        for t, (length, rate) in cfg.items():
            tr = self.state.tracks[t]
            self._quake_saved[t] = (int(tr.length), float(tr.rate))
            self.bridge.length(t, length)
            self.bridge.rate(t, rate)
        print("[poundhard] " + quake.describe(self.state, cfg), flush=True)

    def _clear_quake(self) -> None:
        """Put every touched track back on its own length and rate."""
        for t, (length, rate) in self._quake_saved.items():
            self.bridge.length(t, length)
            self.bridge.rate(t, rate)
        self._quake_saved = {}

    def _apply_shuffle(self) -> None:
        """Roll a fresh shuffle: a random DERANGEMENT of the sequenced tracks so every
        participant plays a different track's rhythm. Engine-only overlay (controller state
        untouched). The more sequenced tracks, the more configurations."""
        st = self.state
        parts = [t for t in range(N_TRACKS)
                 if st.tracks[t].type != "EMPTY" and any(st.tracks[t].pattern)]
        if len(parts) < 2:
            self._shuffle_perm = {}
            return
        srcs = parts[:]
        for _ in range(30):                      # random derangement (nobody keeps their own)
            random.shuffle(srcs)
            if all(srcs[i] != parts[i] for i in range(len(parts))):
                break
        self._shuffle_perm = {parts[i]: srcs[i] for i in range(len(parts))}
        for t, src in self._shuffle_perm.items():
            self._push_track_rhythm(t, src)

    def _clear_shuffle(self) -> None:
        """Restore each shuffled track's OWN rhythm from the (untouched) controller state."""
        for t in self._shuffle_perm:
            self._push_track_rhythm(t, t)
        self._shuffle_perm = {}

    # -- patterns & projects ----------------------------------------------- #
    def _on_cycle(self) -> None:
        self._churn_spend()
        self._break_tick()
        self._rand_tick()
        self._compass_tick()
        """Bar boundary (from the engine): fire any living steps whose period has elapsed
        (transient model — they revert next cycle), then apply a queued pattern switch."""
        with self._lock:
            st = self.state
            for t in range(N_TRACKS):
                changed, living_fx = st.tick_living(t)   # fired/reverted cells + send params
                for c in changed:
                    self._push_living_cell(t, c)
                if living_fx is not None:
                    self.bridge.livingfx(*living_fx)     # set delay/reverb params for this fire
            if 0 <= st.pattern_pending < N_PATTERNS and st.patterns[st.pattern_pending] is not None:
                st.commit_current()             # preserve the outgoing pattern's live edits
                # patterns are self-contained: restore the WHOLE machine — engines,
                # params, FX, mutes, sequences AND the pattern's own tempo.
                st.apply_full(st.patterns[st.pattern_pending])
                st.pattern_cur = st.pattern_pending
                self._push_all()
            st.pattern_pending = -1

    def _save_project_file(self, slot: int) -> None:
        self.state.commit_current()             # fold live edits into the current pattern first
        path = PROJECTS_DIR / f"proj_{slot:02d}.json"
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(self.state.project_to_dict()))
            tmp.replace(path)
            self._proj_slots[slot] = True
            self._proj_cur = slot                # saving makes it the project you are in
        except OSError:
            pass

    # -- autosave (recovery file; never touches the user's project slots) ----- #
    def _autosave_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(AUTOSAVE_SEC)
            if self._stop.is_set() or not self._dirty:
                continue
            with self._lock:
                self.state.commit_current()      # fold live edits into the current pattern
                doc = self.state.project_to_dict()
                self._dirty = False
            tmp = AUTOSAVE_FILE.with_suffix(".json.tmp")
            try:
                tmp.write_text(json.dumps(doc))
                tmp.replace(AUTOSAVE_FILE)       # atomic: a torn file would be worse than none
                self._autosaved = True
            except OSError:
                self._dirty = True               # failed — try again next tick

    def _load_autosave(self) -> None:
        try:
            d = json.loads(AUTOSAVE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return
        self.state.pattern_pending = -1
        self.state.project_from_dict(d)
        self._push_all()
        print("[poundhard] restored autosave", flush=True)

    def _load_project_file(self, slot: int) -> None:
        path = PROJECTS_DIR / f"proj_{slot:02d}.json"
        try:
            d = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        self.state.pattern_pending = -1
        self.state.project_from_dict(d)
        # a project with no patterns is still a project you have to be able to work in
        if all(p is None for p in self.state.patterns):
            self.state.save_pattern(0)
        self._proj_cur = slot                    # this is the project you are now in
        self._push_all()

    # -- performance recording --------------------------------------------- #
    def _rec_path(self, slot: int) -> Path:
        return RECORDINGS_DIR / f"rec_{slot:02d}.wav"

    def _scan_recordings(self) -> None:
        self._rec_slots = [self._rec_path(s).exists() for s in range(N_RECORDINGS)]

    def _rec_begin(self, slot: int) -> None:
        """Actually start the DiskOut recording on `slot` (engine already running)."""
        self.bridge.recstart(self._rec_path(slot))
        self._rec_state = "recording"
        self._rec_slot = slot
        self._rec_start = time.monotonic()
        self._rec_slots[slot] = True
        if self._rec_timer:
            self._rec_timer.cancel()
        self._rec_timer = threading.Timer(REC_MAX_SEC, self._rec_timeout, args=(slot,))
        self._rec_timer.daemon = True
        self._rec_timer.start()

    def _rec_hard_stop(self) -> None:
        """Stop and finalize the take immediately (no tail)."""
        if self._rec_timer:
            self._rec_timer.cancel()
            self._rec_timer = None
        self.bridge.recstop()
        if 0 <= self._rec_slot < N_RECORDINGS:
            self._rec_slots[self._rec_slot] = True
        self._rec_state = "idle"
        self._rec_slot = -1

    def _rec_finish(self) -> None:
        """Enter TAIL mode: the engine keeps writing while we watch the master level
        (/ph/amp). Once it stays below the silence threshold long enough, the take is
        finalized — so reverb / delay tails land in the file instead of being cut off."""
        if self._rec_state != "recording":
            return
        if self._rec_timer:
            self._rec_timer.cancel()
        self._rec_state = "tail"          # engine keeps writing; we just don't stop it yet
        self._quiet_since = None
        self._rec_timer = threading.Timer(REC_TAIL_MAX_SEC, self._rec_tail_timeout,
                                          args=(self._rec_slot,))
        self._rec_timer.daemon = True
        self._rec_timer.start()

    def _on_amp(self, amp: float) -> None:
        """Master level (~10Hz, only while recording). Ends a take once its tail dies away."""
        if self._rec_state != "tail":
            self._quiet_since = None
            return
        now = time.monotonic()
        if amp >= REC_SILENCE_THRESH:
            self._quiet_since = None
            return
        if self._quiet_since is None:
            self._quiet_since = now
        elif (now - self._quiet_since) >= REC_SILENCE_SEC:
            self._quiet_since = None
            with self._lock:
                if self._rec_state == "tail":
                    self._rec_hard_stop()          # tail has died away -> finalize the file

    def _rec_tail_timeout(self, slot: int) -> None:
        with self._lock:
            if self._rec_state == "tail" and self._rec_slot == slot:
                self._rec_hard_stop()          # tail never went quiet (a drone) -> cut it

    def _rec_arm(self, slot: int) -> None:
        """Press on `slot`: start now if playing, else arm for the next Play."""
        if self.state.running:
            self._rec_begin(slot)
        else:
            self._rec_state = "armed"
            self._rec_slot = slot

    def _rec_pad(self, slot: int) -> None:
        if self._rec_state == "recording":
            if slot == self._rec_slot:
                self._rec_finish()             # tap the recording pad -> let the tail run out
            else:
                self._rec_hard_stop()          # switching slots -> cut it
                self._rec_arm(slot)
        elif self._rec_state == "tail":
            was = self._rec_slot
            self._rec_hard_stop()              # tapping during the tail cuts it short
            if slot != was:
                self._rec_arm(slot)
        else:
            self._rec_arm(slot)

    def _rec_timeout(self, slot: int) -> None:
        """7-minute hard cap."""
        with self._lock:
            if self._rec_state in ("recording", "tail") and self._rec_slot == slot:
                self._rec_hard_stop()
        self.bridge.run(self.state.running)

    def _push_voices(self) -> None:
        """After a kit regen: re-send voice sounds (type/params/note/vel/sample).
        Patterns + mutes are unchanged, but push_track re-sends them harmlessly."""
        for t in range(N_TRACKS):
            self.bridge.push_track(t, self.state.tracks[t])

    # -- control.json (UI -> controller) ----------------------------------- #
    def _control_loop(self) -> None:
        period = 1.0 / max(10.0, CONTROL_HZ)
        while not self._stop.is_set():
            self._read_control()
            time.sleep(period)

    def _read_control(self) -> None:
        try:
            raw = CONTROL_FILE.read_text()
        except OSError:
            return
        if not raw:
            return
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            return  # partial write; try again next poll
        # The UI's top-level seq monotonically rises within a session but RESETS to a low
        # value when the module reloads (ui.js seq -> 0). If it dropped, the UI restarted its
        # counter — resync the dedup, or we'd silently drop every post-reload command whose
        # seq is now below our high-water mark (mutes, assigns, everything appear dead).
        ui_seq = doc.get("seq")
        if isinstance(ui_seq, (int, float)) and ui_seq < self._last_seq:
            self._last_seq = -1
        # continuous: tempo (deduped)
        tempo = doc.get("tempo")
        if tempo is not None and tempo != self._last_tempo:
            self._last_tempo = tempo
            self.state.tempo = float(tempo)
            self.bridge.tempo(self.state.tempo)
            self._dirty = True
        # one-shot commands: a queue so rapid commands aren't lost when the UI
        # overwrites control.json between polls. Process every entry newer than
        # the last seq we handled (de-dup by seq), in order.
        cmds = doc.get("cmds")
        if not self._seq_primed:
            # first read after startup: take the queue's high-water mark, run nothing
            self._seq_primed = True
            seqs = [e.get("seq", 0) for e in cmds] if isinstance(cmds, list) else []
            if isinstance(ui_seq, (int, float)):
                seqs.append(ui_seq)
            if seqs:
                self._last_seq = max(seqs)
            return
        # Until the engine answers /ph/ready there is no graph to talk to: a command issued
        # now would be sent into the void, and pushing state at a half-booted server is what
        # wedges it. The UI is showing "starting…" at this point anyway.
        if not self._built.is_set():
            if isinstance(cmds, list) and cmds:
                self._last_seq = max([self._last_seq] + [e.get("seq", 0) for e in cmds])
            return
        if isinstance(cmds, list):
            newest = self._last_seq
            for e in cmds:
                s = e.get("seq", 0)
                if s > self._last_seq:
                    with self._lock:
                        self._dispatch(e.get("cmd", ""), e.get("arg", -1), e.get("p") or {})
                    newest = max(newest, s)
            self._last_seq = newest
        else:  # legacy single-command form
            seq = doc.get("seq", 0)
            if seq != self._last_seq:
                self._last_seq = seq
                with self._lock:
                    self._dispatch(doc.get("cmd", ""), doc.get("arg", -1), doc.get("p", {}))

    # Discrete, structural actions get an undo level each. Continuous streams (knobs:
    # trackset / voicemacro / fxmacro / fxwet / steplock / stepmacro / note / tempo) are
    # deliberately excluded — they'd flood the 20-level stack with sub-gesture noise.
    _UNDOABLE = frozenset({
        "assign", "randtrack", "mute", "solo", "stepset", "steptoggle", "clearpat", "stepfx",
        "setlen", "savepat", "loadpat", "patdel", "patpaste", "genvar", "randpat",
        "fxassign", "fxbypass", "loadproj", "loadauto", "marklive",
        "steppaste", "rowpaste", "stepcycle", "stepfxcycle", "trackfilter", "stepwindow",
        "stepfilter",
        "stepgen", "trackcopy",
    })
    # Commands that change no persisted state — they don't mark the project dirty.
    _NO_STATE = frozenset({
        "editenter", "editexit", "audition", "palettegen", "drummode", "drumaudition",
        "smparm",
        "recpad", "run",
        "patcopy", "patclipclear", "saveproj", "panic", "shuffle", "quake", "churn",
        "break", "steprand", "compass",
        "stepcopy", "rowcopy",
    })

    def _dispatch(self, cmd: str, arg, p: dict) -> None:
        st = self.state
        if cmd in self._UNDOABLE:
            st.push_undo()                     # capture the state BEFORE the action
        if cmd not in self._NO_STATE:
            self._dirty = True                 # something worth autosaving changed
        if cmd == "genkit":
            st.new_kit()
            self._push_voices()
        elif cmd == "randtrack":
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                st.randomize_track(t)                 # re-rolls the track's assigned engine
                self.bridge.push_track(t, st.tracks[t])
        elif cmd == "audition":                       # engine palette: short-press a pad
            v = st.palette_voice(int(arg))
            if v is not None:
                self.bridge.preview(v)                # one-shot preview -> master
        elif cmd == "palettegen":                     # engine palette: Shift+pad = re-roll
            st.palette_regen(int(arg))
        elif cmd == "drumaudition":            # tapping a type pad while holding DRUM:
            v = st.drum_type_example(int(arg))  # hear that TYPE (stable reference sound),
            if v is not None:                   # no commit yet — the pick lands on release
                self.bridge.preview(v)
        elif cmd == "drummode":                # DRUM pad RELEASED after picking a type ->
            st.set_drum_mode(int(arg))         # commit: lock it + roll the pad as that drum
        elif cmd == "smparm":                  # hold SAMPLE pad + tap an engine pad
            self._smp_arm(int(arg))
        elif cmd == "assign":                         # hold pad + tap track = assign sound
            idx = int(p.get("engine", -1)); t = int(p.get("track", -1))
            if idx == catalog.TYPE_INDEX.get("SAMPLE") and 0 <= t < N_TRACKS:
                # hand the captured buffer to the track, then RELEASE the pad
                self.bridge.smpassign(t, self._smp_paths()[1])
                self._smp_release()
            if st.palette_assign(idx, t):
                self.bridge.push_track(t, st.tracks[t])
                self._push_mutes()                    # keep effective mutes correct (solo)
        elif cmd == "steplock":
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1))
            param = p.get("param", "")
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS and param in ("pitch", "vel", "pan"):
                nn, vv, pp = st.set_step_param(t, cell, param, float(p.get("value", 0)))
                self.bridge.steplock(t, cell, nn, vv, pp)
                if param == "pitch":           # hand-entered notes can define the key too
                    st.ensure_scale([nn])
        elif cmd == "stepmacro":               # per-step voice-macro lock (knob 3 on a held step)
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                self.bridge.stepmacro(t, cell, st.set_step_macro(t, cell, float(p.get("pos", 0.5))))
        elif cmd == "marklive":                # Rec + pad: mark/unmark a step as living
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                on = st.toggle_living(t, cell)
                if on:
                    self._push_living_cell(t, cell)     # roll + push its first transform
                else:                                    # reverted to a plain step
                    self.bridge.steplock(t, cell, st.tracks[t].eff_note(cell),
                                         st.tracks[t].eff_vel(cell), st.tracks[t].eff_pan(cell))
                    self.bridge.stepmacro(t, cell, [])
                    self.bridge.stepratchet(t, cell, 1)
        elif cmd == "stepfxcycle":             # row 4 on a held step WITH fx: how often it goes wet
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                self.bridge.stepfxcycle(t, cell, st.set_step_fxcycle(t, cell, int(p.get("x", 1))))
        elif cmd == "liveperiod":              # knob 4 while holding a living step: X cycles
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                st.set_step_period(t, cell, int(p.get("x", 4)))
        elif cmd == "heat":                    # Heat pad (default view): toggle the mass-living macro
            on = int(arg) != 0
            if on and not self._heat_on:       # engaging: snapshot the clean base BEFORE marking
                st.heat_snapshot()             # so disengaging restores the pattern exactly
            for (t, c) in st.heat_clear():  # restore + reset the engine for EVERY heated cell
                self._reset_engine_cell(t, c)
            if on:
                st.heat_apply(self._heat_pct)
            self._heat_on = on
        elif cmd == "heatpct":                 # hold Heat + knob1: set the heat fraction (re-heats live)
            self._heat_pct = max(0.05, min(1.0, float(p.get("x", 0.5))))
            if self._heat_on:                  # already engaged -> reshuffle at the new density
                for (t, c) in st.heat_clear():
                    self._reset_engine_cell(t, c)
                st.heat_apply(self._heat_pct)
        elif cmd == "randdebug":               # diagnostic: log every generated value set
            self._rand_debug = int(arg) != 0
        elif cmd == "compass":                 # Compass pad: the softcut tape loop
            # No lock any more. Compass records the master and plays into the master, so
            # unlike QUAKE and BREAK it owns no track's rate, length or step list and has
            # nothing to fight them over.
            on = int(arg) != 0
            if on:
                from . import compass
                self._compass = compass.Compass()
                self.bridge.compass(True)
            else:
                self._compass_end()
            self._compass_on = on
        elif cmd == "steprand":                # Shift + touch a control: toggle its randomizer
            from . import steprand
            t = int(p.get("track", st.edit_track))
            param = str(p.get("param", ""))
            if 0 <= t < N_TRACKS and param in steprand.PARAMS:
                on = self._rand_toggle(t, param)
                print("[poundhard] randomizer %s T%d %s"
                      % (steprand.PARAMS[param], t + 1, "ON" if on else "OFF"), flush=True)
        elif cmd == "break":                   # Break pad (right of Churn): automatic breakdowns
            on = int(arg) != 0
            # BREAK and QUAKE are mutually exclusive. Both temporarily own a track's length
            # and rate, and Break's restore re-pushes the controller's originals — so with
            # both engaged Break silently wipes Quake's overlay every time it ends. Rather
            # than pick a winner per parameter, only one may hold the rig at a time.
            if on and self._quake_on:
                print("[poundhard] break refused: quake holds the rig", flush=True)
            else:
                if not on and self._break_active:
                    self._break_end()           # never leave a break hanging
                self._break_on = on
                self._break_cycles = 0
        elif cmd == "breakint":                # hold Break + jog: cycles between breaks
            self._break_every = max(1, min(32, int(p.get("n", 4))))
        elif cmd == "churn":                   # Churn pad (right of Quake): CDP ornamentation
            on = int(arg) != 0
            if on and not self._churn_on:
                self._churn_start()
            elif not on and self._churn_on:
                self._churn_end()
            self._churn_on = on
        elif cmd == "quake":                   # Quake pad (right of Shuffle): polymeter + polyrhythm
            on = int(arg) != 0
            if on and self._break_on:          # one holder at a time
                print("[poundhard] quake refused: break holds the rig", flush=True)
            else:
                self._clear_quake()            # idempotent: drop any current overlay first
                if on:
                    self._apply_quake()        # roll + push a fresh configuration
                self._quake_on = on and bool(self._quake_saved)
        elif cmd == "shuffle":                 # Shuffle pad (right of Heat): swap rhythms between tracks
            on = int(arg) != 0
            self._clear_shuffle()              # idempotent: undo any current shuffle first
            if on:
                self._apply_shuffle()          # roll + apply a fresh configuration
            self._shuffle_on = on and bool(self._shuffle_perm)
            st.shuffle_perm = dict(self._shuffle_perm)   # HEAT + living steps read the current perm
            if self._heat_on:                  # HEAT follows the shuffle: re-mark on the NEW rhythm
                for (t, c) in st.heat_clear():
                    self._reset_engine_cell(t, c)
                st.heat_apply(self._heat_pct)
        elif cmd == "mute":
            t = int(arg)
            if 0 <= t < N_TRACKS:
                st.toggle_mute(t)
                self._push_mutes()             # effective mutes (solo may be active)
        elif cmd == "solo":                    # double-tap a step button
            t = int(arg)
            if 0 <= t < N_TRACKS:
                st.toggle_solo(t)
                self._push_mutes()
        elif cmd == "editenter":
            t = int(arg)
            if 0 <= t < N_TRACKS:
                st.edit_track = t
                self.bridge.edittrack(t)
        elif cmd == "editexit":
            st.edit_track = -1
            self.bridge.edittrack(-1)
        elif cmd == "setlen":
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                ln = st.set_length(t, int(p.get("len", N_STEPS)))
                self.bridge.length(t, ln)
        elif cmd == "trackset":
            t = int(p.get("track", -1))
            if 0 <= t < N_TRACKS:
                kind, v = st.set_track_param(t, p.get("param", ""), float(p.get("value", 0)))
                if kind == "note":
                    self.bridge.note(t, st.tracks[t].eff_track_note())
                elif kind == "vel":
                    self.bridge.vel(t, v)
                elif kind == "pan":
                    self.bridge.param(t, st.tracks[t].type.lower() + ".pan", v)
                elif kind == "amp":
                    self.bridge.param(t, st.tracks[t].type.lower() + ".amp", v)
                elif kind == "rate":
                    self.bridge.rate(t, v)
        elif cmd == "chaos":                   # knob 8 (tracks view): sweep EVERY engine's params
            for t, pid, val in st.set_chaos(float(p.get("pos", 0.5))):
                self.bridge.param(t, pid, val)
        elif cmd == "chaosreset":              # Shift + touch knob 8: back to the safe zone
            for t, pid, val in st.chaos_reset():
                self.bridge.param(t, pid, val)
        elif cmd == "voicemacro":              # one knob sweeps the whole current voice
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                for pid, val in st.set_voice_macro(t, float(p.get("pos", 0.5))):
                    self.bridge.param(t, pid, val)
        elif cmd == "stepgen":                 # Shift + volume touch + Track 1: new sequence
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                from . import stepgen
                info = stepgen.generate(st, t)
                if info.get("ok"):
                    self.bridge.push_track(t, st.tracks[t])
                    self._push_step_cell(t)
                    self._push_step_macros(t)
                    for c in range(N_STEPS):        # generated living steps arrive transformed
                        if st.tracks[t].step_living[c]:
                            self._push_living_cell(t, c)
                    self._gen_note = "%s %d/%d%s" % (info["algo"], info["hits"], info["steps"],
                                                     " L%d" % info["living"] if info["living"] else "")
        elif cmd == "trackcopy":               # Copy + source track + destination track
            src = int(p.get("src", -1)); dst = int(p.get("dst", -1))
            if st.copy_track(src, dst):
                # rebuild the destination from nothing: drop its locks and its whole FX chain
                # first, or the clone would inherit leftovers the source never had
                self.bridge.clearlocks(dst)
                for fx in range(N_FX):
                    self.bridge.fxassign(dst, fx, False)
                self.bridge.push_track(dst, st.tracks[dst])
                self._push_step_cell(dst)
                for fx in st.track_fx[dst]:
                    self.bridge.fxassign(dst, fx, True)
                self.bridge.fxbypass(dst, st.fx_bypass[dst])
                for c in range(N_STEPS):       # living cells carry a transform right now
                    if st.tracks[dst].step_living[c]:
                        self._push_living_cell(dst, c)
                if st.tracks[dst].type == "SAMPLE":
                    self.bridge.smpcopy(src, dst)   # the engine gives it its OWN buffer
                self._push_mutes()
        elif cmd == "transpose":               # Shift + jog wheel: shift the sequence in semitones
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                st.transpose_track(t, int(p.get("d", 0)))
                self._push_notes(t)
        elif cmd == "trackfilter":             # knobs 4/5/6 (6/7/8 on SAMPLE): the track filter
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                cut, rs, ty = st.set_filter(
                    t,
                    cutoff=p.get("cutoff"), res=p.get("res"), ftype=p.get("type"))
                self.bridge.filter(t, cut, rs, ty)
        elif cmd == "stepfilter":              # hold a step + the filter knobs: lock it there
            t = int(p.get("track", st.edit_track)); cell = int(p.get("cell", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                cut, rs, ty = st.set_step_filter(
                    t, cell, cutoff=p.get("cutoff"), res=p.get("res"), ftype=p.get("type"))
                self.bridge.stepfilt(t, cell, cut, rs, ty)
        elif cmd == "stepwindow":              # hold a step (SAMPLE) + knob 4/5: its own slice
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1)); which = str(p.get("param", ""))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS and which in ("start", "end"):
                a, b = st.set_step_window(t, cell, which, float(p.get("value", 0.0)))
                self.bridge.stepsmp(t, cell, a, b)
        elif cmd == "stepcycle":               # hold a step + row-3 pad: fire every Nth cycle
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1)); every = int(p.get("every", 1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                n = st.set_step_cycle(t, cell, every)
                self.bridge.stepcycle(t, cell, n)
        elif cmd == "stepcopy":                # Copy + a step that HAS data: to the clipboard
            t = int(p.get("track", st.edit_track)); cell = int(p.get("cell", -1))
            clip = st.copy_step(t, cell)
            if clip is not None:
                self._step_clip = clip
        elif cmd == "steppaste":               # Copy + an EMPTY step: paste onto it
            t = int(p.get("track", st.edit_track)); cell = int(p.get("cell", -1))
            if self._step_clip and st.paste_step(t, cell, self._step_clip):
                self._push_step_cell(t)
        elif cmd == "rowcopy":                 # Copy + Track 1/2: that row of steps
            t = int(p.get("track", st.edit_track)); row = int(p.get("row", -1))
            clip = st.copy_row(t, row)
            if clip is not None:
                self._row_clip = clip
        elif cmd == "rowpaste":                # Copy + Track 1/2 again: paste the row
            t = int(p.get("track", st.edit_track)); row = int(p.get("row", -1))
            if self._row_clip and st.paste_row(t, row, self._row_clip):
                self._push_step_cell(t)
        elif cmd == "voiceparam":              # a knob bound to ONE named param of the voice
            t = int(p.get("track", st.edit_track))
            name = str(p.get("param", ""))
            if 0 <= t < N_TRACKS and name:
                pid = f"{st.tracks[t].type.lower()}.{name}"
                spec = catalog.param_spec(st.tracks[t].type, pid)
                if spec is not None:
                    val = max(spec.rmin, min(spec.rmax, float(p.get("value", 0.0))))
                    st.tracks[t].params[pid] = val
                    self.bridge.param(t, pid, val)
        elif cmd == "stepfx":                  # Shift + steps + FX pads: per-step FX lock
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", -1)); mask = int(p.get("mask", -1))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                st.tracks[t].step_fx[cell] = mask
                self.bridge.stepfx(t, cell, mask)
        elif cmd == "stepset":                 # absolute (idempotent) — preferred
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", arg))
            on = 1 if int(p.get("on", 0)) else 0
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                was = st.tracks[t].pattern[cell]
                st.tracks[t].pattern[cell] = on
                if on == 0 and was:            # deleting a step empties its whole slot
                    st.clear_step(t, cell)
                    self._clear_engine_cell(t, cell)
                self.bridge.stepset(t, cell, on)
        elif cmd == "steptoggle":              # legacy relative toggle
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", arg))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                on = st.toggle_step(t, cell)   # clears the slot itself when it turns off
                if on == 0:
                    self._clear_engine_cell(t, cell)
                self.bridge.stepset(t, cell, on)
        elif cmd == "clearpat":
            t = int(arg)
            if 0 <= t < N_TRACKS:
                st.clear_pattern(t)
                self.bridge.pattern(t, st.tracks[t].pattern)
                self.bridge.clearlocks(t)       # every lock, not just fx + cycle
                for c in range(N_STEPS):
                    self.bridge.stepmacro(t, c, [])
        elif cmd == "run":
            st.running = bool(int(arg))
            self.bridge.run(st.running)
            # transport bounds a recording: armed + Play -> start. Stopping does NOT cut the
            # take dead — it enters TAIL mode so reverb/delay tails are captured.
            if st.running and self._rec_state == "armed":
                self._rec_begin(self._rec_slot)
            elif (not st.running) and self._rec_state == "recording":
                self._rec_finish()
        elif cmd == "note":
            t = int(p.get("track", -1)); n = int(p.get("note", 40))
            if 0 <= t < N_TRACKS:
                st.tracks[t].note = n
                self.bridge.note(t, st.tracks[t].eff_track_note())
        elif cmd == "fxassign":
            t = int(p.get("track", -1)); fx = int(p.get("fx", -1))
            if 0 <= t < N_TRACKS and 0 <= fx < N_FX:
                on = st.toggle_fx(t, fx)
                self.bridge.fxassign(t, fx, on)
                if on:                                 # push the macro params to the new instance
                    for arg, val in st.macro_values(fx):
                        self.bridge.fxset(fx, arg, val)
        elif cmd == "fxbypass":
            t = int(p.get("track", int(arg)))
            if 0 <= t < N_TRACKS:
                st.fx_bypass[t] = not st.fx_bypass[t]
                self.bridge.fxbypass(t, st.fx_bypass[t])
        elif cmd == "fxmacro":
            fx = int(p.get("fx", -1))
            if 0 <= fx < N_FX:
                for arg, val in st.set_macro(fx, float(p.get("pos", 0.5))):
                    self.bridge.fxset(fx, arg, val)
        elif cmd == "fxwet":                   # Shift + FX macro knob = dry/wet of that FX
            fx = int(p.get("fx", arg))
            if 0 <= fx < N_FX:
                w = st.set_fx_wet(fx, float(p.get("wet", 0.5)))
                self.bridge.fxset(fx, "wet", w)   # 'wet' is a stored FX synth arg
        elif cmd == "savepat":                 # snapshot current machine state -> pattern slot
            slot = int(arg)
            if 0 <= slot < N_PATTERNS:
                st.save_pattern(slot)
        elif cmd == "loadpat":                 # tap a pad: load a pattern, or SELECT an empty slot
            slot = int(arg)
            if 0 <= slot < N_PATTERNS:
                if st.patterns[slot] is not None:
                    if st.running:
                        st.pattern_pending = slot   # applied at the next bar boundary (/ph/cycle)
                    else:
                        st.commit_current()     # preserve the outgoing pattern's live edits
                        st.apply_full(st.patterns[slot])
                        st.pattern_cur = slot
                        self._push_all()
                else:
                    # EMPTY slot -> just SELECT it as the destination for whatever you do
                    # next (generate, or write a pattern by hand). Nothing to load and
                    # nothing sounds different: the live state keeps playing and now
                    # belongs to this slot. Immediate even while running.
                    st.commit_current()         # the outgoing slot keeps its edits
                    st.pattern_cur = slot
                    st.pattern_pending = -1
        elif cmd == "patdel":                  # hold X + pattern pad: delete, closing the gap
            slot = int(arg)
            if st.delete_pattern(slot):
                print(f"[poundhard] deleted pattern {slot + 1} (bank compacted)", flush=True)
        elif cmd == "patcopy":                 # hold Copy + pattern pad: take a copy
            st.copy_pattern(int(arg))
        elif cmd == "patpaste":                # ...still holding Copy: paste into another pad
            st.paste_pattern(int(arg))
        elif cmd == "patclipclear":            # Copy button released -> clipboard is forgotten
            st.clear_clipboard()
        elif cmd == "undo":                    # Undo button: step back one discrete action
            if st.undo():
                self._push_all()               # re-push the restored machine to the engine
                print("[poundhard] undo", flush=True)
        elif cmd == "redo":                    # Shift + Undo: step forward again
            if st.redo():
                self._push_all()
                print("[poundhard] redo", flush=True)
        elif cmd == "randpat":                 # Shift + volume touch + Track3: randomise this pattern
            from . import variations
            names = variations.random_pattern(st)
            self._push_all()                   # includes the algorithm's chosen tempo
            print(f"[poundhard] randomised pattern {st.pattern_cur + 1} "
                  f"@ {st.tempo:.0f} BPM: {names}", flush=True)
        elif cmd == "loadauto":                # Shift+Menu in project view: restore the autosave
            self._load_autosave()
        elif cmd == "genvar":                  # Shift+Track3 in pattern view: ONE variation
            from . import variations
            added, slots = variations.generate(st, count=1)
            if slots:
                print(f"[poundhard] variation of pattern {st.pattern_cur + 1} -> slot {slots[0] + 1}"
                      + (f", added track {[t + 1 for t in added]}" if added else ""), flush=True)
        elif cmd == "saveproj":                # write the 32 pattern slots + kit to disk
            slot = int(arg)
            if 0 <= slot < N_PATTERNS:
                self._save_project_file(slot)
        elif cmd == "loadproj":                # read a project from disk (restores full state)
            slot = int(arg)
            if 0 <= slot < N_PATTERNS:
                self._load_project_file(slot)
        elif cmd == "recpad":                  # recorder view: press a slot pad
            slot = int(arg)
            if 0 <= slot < N_RECORDINGS:
                self._rec_pad(slot)
        elif cmd == "panic":
            self.bridge.panic()

    # -- status.json (controller -> UI) ------------------------------------ #
    def _status_loop(self) -> None:
        period = 1.0 / max(1.0, SNAP_HZ)
        while not self._stop.is_set():
            self._write_status()
            time.sleep(period)

    def _write_status(self) -> None:
        st = self.state
        tracks = []
        for tr in st.tracks:
            tracks.append({"muted": tr.muted, "active": any(tr.pattern),
                           "note": tr.note, "vel": round(tr.vel, 3),
                           "pan": round(tr.default_pan(), 3),
                           "amp": round(tr.params.get(tr.type.lower() + ".amp", 0.8), 3),
                           "rate": round(tr.rate, 4), "length": tr.length,
                           # SAMPLE's playable window — knobs 4/5 in the edit view
                           "start": round(tr.params.get("sample.start", 0.0), 4),
                           "end": round(tr.params.get("sample.end", 1.0), 4),
                           # per-track multimode filter (knobs 4/5/6, or 6/7/8 on SAMPLE)
                           "transpose": tr.transpose,
                           "fcut": round(tr.filt_cutoff, 1),
                           "fres": round(tr.filt_res, 3),
                           "ftype": tr.filt_type})
        status = {
            "ready": self._built.is_set(),
            "engine": self.bridge.connected,
            "cpu": self.bridge.cpu["avg"],
            "nodes": self.bridge.cpu["nodes"],
            "running": st.running,
            "tempo": round(st.tempo, 1),
            "step": self.bridge.step,
            "editTrack": st.edit_track,
            "kit": st.kit_name,
            "solo": st.solo,
            # patterns (in-project) + projects (on disk) for the pattern/project views
            "patFilled": [p is not None for p in st.patterns],
            "patCur": st.pattern_cur,
            "patPending": st.pattern_pending,
            "projFilled": list(self._proj_slots),
            "projCur": self._proj_cur,           # which project is loaded (-1 = none)
            "canUndo": len(st.undo_stack) > 0,
            "canRedo": len(st.redo_stack) > 0,
            "autoSave": self._autosaved,       # a recovery file exists (Shift+Menu restores it)
            "heat": self._heat_on,             # HEAT macro engaged
            "heatPct": round(self._heat_pct, 3),
            # the project's scale, once something pitched has established it
            "scale": (None if st.scale_name is None
                      else {"root": st.scale_root, "name": st.scale_name}),
            "clipStep": self._step_clip is not None,   # Copy-gesture clipboard state
            "clipRow": self._row_clip is not None,
            "smpState": self._smp_state,        # idle/armed/recording/processing/ready
            "smpSrc": self._smp_src,
            "smpChain": list(self._smp_chain),
            "drumMode": st.drum_mode,          # DRUM palette pad locked to a type (-1 = any)
            "shuffle": self._shuffle_on,       # SHUFFLE macro engaged
            "quake": self._quake_on,           # QUAKE macro engaged
            "churn": self._churn_on,           # CHURN macro engaged
            "brk": self._break_on,             # BREAK macro engaged
            "brkEvery": self._break_every,     # cycles between breaks
            "brkNow": self._break_active,      # a break is running this cycle
            "compass": self._compass_on,       # COMPASS macro engaged
            # performance recorder
            "recSlots": list(self._rec_slots),
            "recSlot": self._rec_slot,
            "recState": self._rec_state,
            "recElapsed": int(time.monotonic() - self._rec_start) if self._rec_state in ("recording", "tail") else 0,
            "recAmp": round(self.bridge.amp, 5),
            "webPort": WEB_PORT,
            "drumTracks": DRUM_TRACKS,
            "tracks": tracks,
            "types": [tr.type for tr in st.tracks],
            # per-track label: the assigned engine (or "" for an empty/unassigned track).
            # Tracks no longer have fixed roles — the engine palette assigns them.
            "names": ["" if tr.type == "EMPTY" else tr.type for tr in st.tracks],
            # FX view: per-track prevailing FX + bypass, macro positions, FX names
            "fxTop": [st.fx_top(t) for t in range(N_TRACKS)],
            "fxBypass": [st.fx_bypass[t] for t in range(N_TRACKS)],
            "fxOn": [list(st.track_fx[t]) for t in range(N_TRACKS)],
            "fxMacro": [round(m, 3) for m in st.fx_macro],
            "fxWet": [round(w, 3) for w in st.fx_wet],
            "chaos": round(st.chaos_pos, 3),   # knob-8 macro position (0.5 == safe zone)
            "fxNames": [s.short for s in FX_SPECS],
        }
        if 0 <= st.edit_track < N_TRACKS:
            et = st.tracks[st.edit_track]
            status["edit"] = {
                "steps": et.pattern, "type": et.type,
                "name": "" if et.type == "EMPTY" else et.type, "note": et.note,
                "length": et.length, "rate": round(et.rate, 4),
                "transpose": et.transpose,
                # which per-step randomizers are live on this track (persistent indicator)
                "rand": sorted(self._rand_active(st.edit_track)),
                "defVel": round(et.vel, 3), "defPan": round(et.default_pan(), 3),
                # effective per-step values (lock or track default) for the UI readout
                "stepNote": [et.eff_note(c) for c in range(N_STEPS)],
                "stepVel": [round(et.eff_vel(c), 3) for c in range(N_STEPS)],
                "stepPan": [round(et.eff_pan(c), 3) for c in range(N_STEPS)],
                # effective per-step macro position (lock, or the track's macro position)
                "stepMacro": [round(et.step_macro[c] if et.step_macro[c] is not None
                                    else st.voice_macro[st.edit_track], 3) for c in range(N_STEPS)],
                # LIVING STEPS: which cells are marked, their period (cycles), current ratchet,
                # and which are firing (transformed) this cycle (transient model)
                "living": list(et.step_living),
                "fx": list(et.step_fx),        # per-step FX mask (-1 = no lock)
                "fxCycle": list(et.step_fxcycle),  # how often that mask is applied, in plays

                "cycle": list(et.step_cycle),  # fire every Nth pattern repetition
                # effective per-step SAMPLE window (the step's own lock, else the track's)
                # effective per-step filter (its own lock, else the track's)
                "stepFcut": [round(st.eff_filter(st.edit_track, c)[0], 1) for c in range(N_STEPS)],
                "stepFres": [round(st.eff_filter(st.edit_track, c)[1], 3) for c in range(N_STEPS)],
                "stepFtype": [st.eff_filter(st.edit_track, c)[2] for c in range(N_STEPS)],
                "stepStart": [round(st.eff_start(st.edit_track, c), 4) for c in range(N_STEPS)],
                "stepEnd": [round(st.eff_end(st.edit_track, c), 4) for c in range(N_STEPS)],
                "period": list(et.step_period),
                "ratchet": list(et.step_ratchet),
                "active": list(et.step_active),
            }
        # Change-detection: skip redundant writes to spare SD I/O. The UI freeze is a
        # synchronous host read-stall on the UI side that gets more likely the busier
        # the SD card is, so don't rewrite an identical snapshot. cpu/nodes jitter every
        # tick (live averages) so they're excluded from the comparison; the snapshot is
        # still refreshed at least every 1.5s so its mtime proves the controller is live.
        key = json.dumps({k: v for k, v in status.items() if k not in ("cpu", "nodes", "recAmp")})
        now = time.monotonic()
        if key == self._last_status_key and (now - self._last_status_write) < 1.5:
            return
        self._last_status_key = key
        self._last_status_write = now
        tmp = STATUS_FILE.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(status))
            tmp.replace(STATUS_FILE)
        except OSError:
            pass


def main() -> None:
    ctl = Controller()
    signal.signal(signal.SIGTERM, ctl.stop)
    signal.signal(signal.SIGINT, ctl.stop)
    ctl.start()
    ctl.run()


if __name__ == "__main__":
    main()
