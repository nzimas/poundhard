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
        self._stop = threading.Event()
        self._built = threading.Event()
        self._last_seq = -1
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
        self._dirty = False                      # state changed since the last autosave
        self._autosaved = False                  # a recovery file exists (for the UI)
        # HEAT macro: mass-mark a fraction of sequenced steps as living (live performance)
        self._heat_on = False                    # macro engaged
        self._heat_pct = 0.5                     # fraction of hits to heat (knob-1 adjustable)
        # SHUFFLE macro: temporarily swap rhythmic structures (pattern/length/rate) BETWEEN
        # tracks. Pure engine-side overlay — the controller's Track state is never touched, so
        # it's automatically temporary and never saved. _shuffle_perm: engine track -> source.
        self._shuffle_on = False
        self._shuffle_perm: dict[int, int] = {}
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
        # builds a rig by assigning engines from the palette. Stopped, no patterns.
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

    def _reset_engine_cell(self, t: int, c: int) -> None:
        """Reset a cell in the engine to its plain, untransformed state (after unmarking)."""
        tr = self.state.tracks[t]
        self.bridge.steplock(t, c, tr.eff_note(c), tr.eff_vel(c), tr.eff_pan(c))
        self.bridge.stepmacro(t, c, [])
        self.bridge.stepratchet(t, c, 1)
        self.bridge.stepsend(t, c, 0)

    # -- SHUFFLE macro ----------------------------------------------------- #
    def _push_track_rhythm(self, engine_track: int, src_track: int) -> None:
        """Send src_track's rhythmic structure (steps + length + rate) to engine_track —
        the target keeps its own SOUND but plays the source's rhythm."""
        src = self.state.tracks[src_track]
        self.bridge.pattern(engine_track, src.pattern)
        self.bridge.length(engine_track, src.length)
        self.bridge.rate(engine_track, src.rate)

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
        "assign", "randtrack", "mute", "solo", "stepset", "steptoggle", "clearpat",
        "setlen", "savepat", "loadpat", "patdel", "patpaste", "genvar", "randpat",
        "fxassign", "fxbypass", "loadproj", "loadauto", "marklive",
    })
    # Commands that change no persisted state — they don't mark the project dirty.
    _NO_STATE = frozenset({
        "editenter", "editexit", "audition", "palettegen", "recpad", "run",
        "patcopy", "patclipclear", "saveproj", "panic", "shuffle",
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
        elif cmd == "assign":                         # hold pad + tap track = assign sound
            idx = int(p.get("engine", -1)); t = int(p.get("track", -1))
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
                    self.bridge.note(t, v)
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
        elif cmd == "stepset":                 # absolute (idempotent) — preferred
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", arg))
            on = 1 if int(p.get("on", 0)) else 0
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                st.tracks[t].pattern[cell] = on
                self.bridge.stepset(t, cell, on)
        elif cmd == "steptoggle":              # legacy relative toggle
            t = int(p.get("track", st.edit_track))
            cell = int(p.get("cell", arg))
            if 0 <= t < N_TRACKS and 0 <= cell < N_STEPS:
                on = st.toggle_step(t, cell)
                self.bridge.stepset(t, cell, on)
        elif cmd == "clearpat":
            t = int(arg)
            if 0 <= t < N_TRACKS:
                st.clear_pattern(t)
                self.bridge.pattern(t, st.tracks[t].pattern)
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
                self.bridge.note(t, n)
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
                           "rate": round(tr.rate, 4), "length": tr.length})
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
            "autoSave": self._autosaved,       # a recovery file exists (Shift+Menu restores it)
            "heat": self._heat_on,             # HEAT macro engaged
            "heatPct": round(self._heat_pct, 3),
            "shuffle": self._shuffle_on,       # SHUFFLE macro engaged
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
