"""OSC bridge: controller -> SC engine (/ph/...) and engine -> controller telemetry.

Sends are no-ops if the client can't be built, so the whole controller runs
headless (no engine) for development. Liveness is a heartbeat: `connected` is
true while telemetry (/ph/step, /ph/cpu, /ph/ready) arrives within a timeout.
"""
from __future__ import annotations

import threading
import time

from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

from .catalog import TYPE_INDEX, engine_arg


class EngineBridge:
    def __init__(self, sc_host: str, sc_port: int,
                 listen_host: str = "127.0.0.1", listen_port: int = 57140,
                 heartbeat_timeout: float = 4.0):
        self.sc_host, self.sc_port = sc_host, sc_port
        self.listen_host, self.listen_port = listen_host, listen_port
        self.heartbeat_timeout = heartbeat_timeout
        self._client: SimpleUDPClient | None = None
        self._server: ThreadingOSCUDPServer | None = None
        self._thread: threading.Thread | None = None
        self._last_beat = 0.0
        self._ready = False
        self.cpu = {"avg": 0.0, "peak": 0.0, "nodes": 0}
        self.step = -1
        self._on_ready = None
        self.on_cycle = None      # called on each /ph/cycle (bar boundary) — set by the controller

    # -- lifecycle --------------------------------------------------------- #
    def start(self, on_ready=None) -> None:
        self._on_ready = on_ready
        try:
            self._client = SimpleUDPClient(self.sc_host, self.sc_port)
        except Exception:
            self._client = None
        disp = Dispatcher()
        disp.map("/ph/ready", self._h_ready)
        disp.map("/ph/step", self._h_step)
        disp.map("/ph/cpu", self._h_cpu)
        disp.map("/ph/cycle", self._h_cycle)
        try:
            # Blocking (single-threaded) server: telemetry handlers are trivial and
            # fast, so we avoid spawning a thread per incoming /ph/step datagram.
            self._server = BlockingOSCUDPServer((self.listen_host, self.listen_port), disp)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        except Exception:
            self._server = None

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass

    @property
    def connected(self) -> bool:
        return (time.monotonic() - self._last_beat) < self.heartbeat_timeout

    @property
    def ready(self) -> bool:
        return self._ready and self.connected

    # -- inbound telemetry ------------------------------------------------- #
    def _beat(self):
        self._last_beat = time.monotonic()

    def _h_ready(self, _addr, *_a):
        self._beat()
        was = self._ready
        self._ready = True
        if not was and self._on_ready:
            self._on_ready()

    def _h_step(self, _addr, *a):
        self._beat()
        self.step = int(a[0]) if a else -1

    def _h_cycle(self, _addr, *_a):
        cb = self.on_cycle
        if cb:
            cb()

    def _h_cpu(self, _addr, *a):
        self._beat()
        if len(a) >= 3:
            self.cpu = {"avg": float(a[0]), "peak": float(a[1]), "nodes": int(a[2])}

    # -- outbound ---------------------------------------------------------- #
    def send(self, addr: str, *args) -> None:
        if self._client is None:
            return
        try:
            self._client.send_message(addr, list(args))
        except Exception:
            pass

    def ping(self):                    self.send("/ph/ping")
    def tempo(self, bpm):              self.send("/ph/tempo", float(bpm))
    def run(self, on):                 self.send("/ph/run", 1 if on else 0)
    def steps(self, n):                self.send("/ph/steps", int(n))
    def set_type(self, t, type_name):  self.send("/ph/track", int(t), TYPE_INDEX.get(type_name, 0))
    def param(self, t, pid, val):      self.send("/ph/param", int(t), engine_arg(pid), float(val))
    def pattern(self, t, cells):       self.send("/ph/pattern", int(t), *[int(x) for x in cells])
    def stepset(self, t, cell, on):    self.send("/ph/stepset", int(t), int(cell), 1 if on else 0)
    def mute(self, t, on):             self.send("/ph/mute", int(t), 1 if on else 0)
    def note(self, t, n):              self.send("/ph/note", int(t), float(n))
    def length(self, t, n):            self.send("/ph/length", int(t), int(n))
    def rate(self, t, r):              self.send("/ph/rate", int(t), float(r))
    def edittrack(self, t):            self.send("/ph/edittrack", int(t))
    def vel(self, t, v):               self.send("/ph/vel", int(t), float(v))
    def samp(self, t, idx):            self.send("/ph/samp", int(t), int(idx))
    def steplock(self, t, cell, note, vel, pan):
        self.send("/ph/steplock", int(t), int(cell), float(note), float(vel), float(pan))
    def stepmacro(self, t, cell, pairs):
        """pairs = [(engine_arg, value), ...] — per-step voice-macro param overrides."""
        flat = []
        for arg, val in pairs:
            flat += [str(arg), float(val)]
        self.send("/ph/stepmacro", int(t), int(cell), *flat)
    def clearlocks(self, t):           self.send("/ph/clearlocks", int(t))
    def recstart(self, path):          self.send("/ph/recstart", str(path))
    def recstop(self):                 self.send("/ph/recstop")
    def fxassign(self, t, fx, on):     self.send("/ph/fxassign", int(t), int(fx), 1 if on else 0)
    def fxbypass(self, t, on):         self.send("/ph/fxbypass", int(t), 1 if on else 0)
    def fxset(self, fx, arg, val):     self.send("/ph/fxset", int(fx), str(arg), float(val))
    def mastergain(self, g):           self.send("/ph/mastergain", float(g))
    def masterfilter(self, cut, res):  self.send("/ph/masterfilter", float(cut), float(res))
    def panic(self):                   self.send("/ph/panic")

    def push_track(self, t: int, track) -> None:
        """Push a whole track's voice (type -> params -> note/vel/sample) + pattern
        + mute. Order matters: set the voice TYPE first (rebuilds the synth), then
        params/sample land on the fresh voice."""
        self.set_type(t, track.type)
        for pid, val in track.params.items():
            self.param(t, pid, val)
        self.note(t, track.note)
        self.vel(t, track.vel)
        if track.type == "SAMPLER" and track.sample >= 0:
            self.samp(t, track.sample)
        self.pattern(t, track.pattern)
        self.mute(t, track.muted)
        self.length(t, track.length)
        self.rate(t, track.rate)
        # re-send any per-step locks so a rebuilt engine mirrors them
        for cell in range(len(track.pattern)):
            if (track.step_note[cell] is not None or track.step_vel[cell] is not None
                    or track.step_pan[cell] is not None):
                self.steplock(t, cell, track.eff_note(cell), track.eff_vel(cell), track.eff_pan(cell))
