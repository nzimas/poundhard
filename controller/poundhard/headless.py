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
import signal
import threading
import time
from pathlib import Path

from .catalog import FX_SPECS, N_FX
from .engine_bridge import EngineBridge
from .kits import ROLE_NAMES
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
CONTROL_HZ = float(_env("PH_CONTROL_HZ", "30"))    # control.json poll rate
SNAP_HZ = float(_env("PH_SNAPSHOT_HZ", "5"))       # status.json write rate (lower = less SD I/O)


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
        self._lock = threading.Lock()          # serialize state mutations (dispatch vs bar-cycle)
        self.bridge.on_cycle = self._on_cycle  # apply a queued pattern switch on the bar boundary
        self._proj_slots = [False] * N_PATTERNS  # which project files exist on disk (cached)
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
        # Fresh session: a curated kit loaded, empty patterns, stopped.
        self.state.new_kit()
        self.bridge.start(on_ready=self._on_ready)
        for fn in (self._control_loop, self._status_loop, self._handshake_loop):
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
        try:
            fn()
        except Exception as e:  # a dead loop must not take the process down
            print(f"[poundhard] loop {fn.__name__} died: {e}")

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
        self.bridge.steps(self.state.steps)
        self.bridge.tempo(self.state.tempo)
        for t in range(N_TRACKS):
            self.bridge.clearlocks(t)                       # reset stale per-step locks first
            self.bridge.push_track(t, self.state.tracks[t])
            self._push_step_macros(t)
        # FX macros (all types) then assignments + bypass
        for fx in range(N_FX):
            for arg, val in self.state.macro_values(fx):
                self.bridge.fxset(fx, arg, val)
        for t in range(N_TRACKS):
            for fx in self.state.track_fx[t]:
                self.bridge.fxassign(t, fx, True)
            if self.state.fx_bypass[t]:
                self.bridge.fxbypass(t, True)

    def _push_step_macros(self, t: int) -> None:
        for cell in range(N_STEPS):
            pairs = self.state.step_macro_pairs(t, cell)
            if pairs is not None:
                self.bridge.stepmacro(t, cell, pairs)

    def _push_groove(self) -> None:
        """Push ONLY the groove to the engine (used on a pattern switch): sequences,
        lengths, rates, mutes, and per-step locks — sounds/FX/tempo are untouched."""
        st = self.state
        for t in range(N_TRACKS):
            tr = st.tracks[t]
            self.bridge.clearlocks(t)
            self.bridge.pattern(t, tr.pattern)
            self.bridge.length(t, tr.length)
            self.bridge.rate(t, tr.rate)
            self.bridge.mute(t, tr.muted)
            for cell in range(N_STEPS):
                if (tr.step_note[cell] is not None or tr.step_vel[cell] is not None
                        or tr.step_pan[cell] is not None):
                    self.bridge.steplock(t, cell, tr.eff_note(cell), tr.eff_vel(cell), tr.eff_pan(cell))
            self._push_step_macros(t)

    # -- patterns & projects ----------------------------------------------- #
    def _on_cycle(self) -> None:
        """Bar boundary (from the engine): apply a queued pattern switch, if any."""
        with self._lock:
            st = self.state
            if 0 <= st.pattern_pending < N_PATTERNS and st.patterns[st.pattern_pending] is not None:
                st.commit_current()             # preserve the outgoing pattern's live edits
                st.apply_groove(st.patterns[st.pattern_pending])
                st.pattern_cur = st.pattern_pending
                self._push_groove()
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

    def _rec_finish(self) -> None:
        """Stop the current recording and finalize its file."""
        if self._rec_timer:
            self._rec_timer.cancel()
            self._rec_timer = None
        self.bridge.recstop()
        if 0 <= self._rec_slot < N_RECORDINGS:
            self._rec_slots[self._rec_slot] = True
        self._rec_state = "idle"
        self._rec_slot = -1

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
                self._rec_finish()             # tap the recording pad -> stop
            else:
                self._rec_finish()             # switch to a different slot
                self._rec_arm(slot)
        else:
            self._rec_arm(slot)

    def _rec_timeout(self, slot: int) -> None:
        with self._lock:
            if self._rec_state == "recording" and self._rec_slot == slot:
                self._rec_finish()
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
        # continuous: tempo (deduped)
        tempo = doc.get("tempo")
        if tempo is not None and tempo != self._last_tempo:
            self._last_tempo = tempo
            self.state.tempo = float(tempo)
            self.bridge.tempo(self.state.tempo)
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

    def _dispatch(self, cmd: str, arg, p: dict) -> None:
        st = self.state
        if cmd == "genkit":
            st.new_kit()
            self._push_voices()
        elif cmd == "randtrack":
            t = int(p.get("track", st.edit_track))
            if 0 <= t < N_TRACKS:
                st.randomize_track(t)
                self.bridge.push_track(t, st.tracks[t])
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
        elif cmd == "mute":
            t = int(arg)
            if 0 <= t < N_TRACKS:
                muted = st.toggle_mute(t)
                self.bridge.mute(t, muted)
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
            # transport bounds a recording: armed + Play -> start; recording + Stop -> finish
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
        elif cmd == "savepat":                 # snapshot current machine state -> pattern slot
            slot = int(arg)
            if 0 <= slot < N_PATTERNS:
                st.save_pattern(slot)
        elif cmd == "loadpat":                 # recall a pattern's GROOVE (queued if running)
            slot = int(arg)
            if 0 <= slot < N_PATTERNS and st.patterns[slot] is not None:
                if st.running:
                    st.pattern_pending = slot   # applied at the next bar boundary (/ph/cycle)
                else:
                    st.commit_current()         # preserve the outgoing pattern's live edits
                    st.apply_groove(st.patterns[slot])
                    st.pattern_cur = slot
                    self._push_groove()
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
            # patterns (in-project) + projects (on disk) for the pattern/project views
            "patFilled": [p is not None for p in st.patterns],
            "patCur": st.pattern_cur,
            "patPending": st.pattern_pending,
            "projFilled": list(self._proj_slots),
            # performance recorder
            "recSlots": list(self._rec_slots),
            "recSlot": self._rec_slot,
            "recState": self._rec_state,
            "recElapsed": int(time.monotonic() - self._rec_start) if self._rec_state == "recording" else 0,
            "webPort": WEB_PORT,
            "drumTracks": DRUM_TRACKS,
            "tracks": tracks,
            "types": [tr.type for tr in st.tracks],
            "names": ROLE_NAMES,
            # FX view: per-track prevailing FX + bypass, macro positions, FX names
            "fxTop": [st.fx_top(t) for t in range(N_TRACKS)],
            "fxBypass": [st.fx_bypass[t] for t in range(N_TRACKS)],
            "fxOn": [list(st.track_fx[t]) for t in range(N_TRACKS)],
            "fxMacro": [round(m, 3) for m in st.fx_macro],
            "fxNames": [s.short for s in FX_SPECS],
        }
        if 0 <= st.edit_track < N_TRACKS:
            et = st.tracks[st.edit_track]
            status["edit"] = {
                "steps": et.pattern, "type": et.type,
                "name": ROLE_NAMES[st.edit_track], "note": et.note,
                "length": et.length, "rate": round(et.rate, 4),
                "defVel": round(et.vel, 3), "defPan": round(et.default_pan(), 3),
                # effective per-step values (lock or track default) for the UI readout
                "stepNote": [et.eff_note(c) for c in range(N_STEPS)],
                "stepVel": [round(et.eff_vel(c), 3) for c in range(N_STEPS)],
                "stepPan": [round(et.eff_pan(c), 3) for c in range(N_STEPS)],
                # effective per-step macro position (lock, or the track's macro position)
                "stepMacro": [round(et.step_macro[c] if et.step_macro[c] is not None
                                    else st.voice_macro[st.edit_track], 3) for c in range(N_STEPS)],
            }
        # Change-detection: skip redundant writes to spare SD I/O. The UI freeze is a
        # synchronous host read-stall on the UI side that gets more likely the busier
        # the SD card is, so don't rewrite an identical snapshot. cpu/nodes jitter every
        # tick (live averages) so they're excluded from the comparison; the snapshot is
        # still refreshed at least every 1.5s so its mtime proves the controller is live.
        key = json.dumps({k: v for k, v in status.items() if k not in ("cpu", "nodes")})
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
