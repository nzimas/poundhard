"""COMPASS — Olivier Creurer's norns script, running.

Not a reimplementation. `controller/compass/compass.lua` is the published script byte for
byte, executed by a real Lua interpreter under a norns-API shim, driving real softcut voices
inside scsynth. This module is the bridge: it starts that process, gives it a clock, relays
the softcut calls it makes to the engine, and plays its keys and encoders.

WHY IT IS DONE THIS WAY. Two earlier versions reimplemented Compass's ideas — one on the
step sequencer, one on softcut — and both were wrong in ways that were obvious the moment
the actual source was read. The script uses two SEPARATE buffers; loop points are integer
seconds inside a 64-second tape, so a loop is never shorter than a second; commands fire
every beat and up to sixteen times a beat; rate changes are SLEWED. Miss any of those and
what comes out is a short modulated delay — a flanger — rather than a tape loop. The only
reliable way to get a script's behaviour is to run the script.

THE PIPE. Lines in, lines out, pipe-separated. No sockets, so nothing to build into Lua:

    ->  tick|<t>            one 1/16-beat tick; the shim's clock.sync rides on these
        phase|<i>|<x>|<t>   softcut's real head position, so update_positions runs
        perform|<t>         one turn of the algorithmic performer
        tempo|<bpm>
    <-  sc|<fn>|<voice>|<v> a softcut call, e.g. sc|rate|1|-1
        scin|<ch>|<v>|<amp> softcut.level_input_cut, the input matrix
        state|<glyph>|<division>|<rate>|<loopStart>|<loopEnd>|<rec>|<steps>
        log|<text>

The tick rate is the interesting part: `clock.sync(1/division)` with division up to 16 means
the command stream can fire sixteen times a beat, so the tick has to be at least that fine.
It is fed from PoundHard's own clock, so the tape's commands land on the sequencer's grid.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

TICKS_PER_BEAT = 16

# The shortest a played chunk may be, in seconds. What sets chunk length is not the loop
# length but how often playback RESTARTS: `1`, `P` and `L` each re-trigger the head, and the
# command clock runs at up to sixteen commands per beat — 31 ms at 120 BPM. Re-triggering
# every 31 ms is a ~32 Hz buzz, not a tape loop, and no amount of loop-point tuning fixes it
# because the loop never gets to play. So the retrigger rate is gated here.
CHUNK_MIN = 0.4
# start + end arrive as one gesture; anything inside this window is the same chunk
_SAME_GESTURE = 0.02
# Everything that changes what you HEAR abruptly. `rate` belongs here and was the miss that
# left the buzzing in: measured over a minute of play it changed 9.7 times a SECOND, and with
# a 0.1 s slew the tape speed never settles — the playback pitch just swings across the whole
# ±2-octave rate table at ~10 Hz, which is a sawtooth, not a tape. Everything else softcut
# already slews for itself: pan over 0.25 s, rec and pre level over 2 s.
_GATED = {"rate", "position", "loop_start", "loop_end"}
LUA = "/data/UserData/poundhard/lua/bin/lua"
SCRIPT_DIR = "/data/UserData/poundhard/compass"

# softcut function -> the synth argument it sets, per voice. Anything not here is either
# handled specially below or is a call the engine has no use for (enable/buffer, which are
# fixed by construction: voice i owns buffer i).
_VOICE_ARG = {
    "rate": "rate", "rate_slew_time": "rateSlew",
    "loop_start": "start", "loop_end": "end", "loop": "loop",
    "position": "cut", "level": "lvl", "pan": "pan",
    "rec_level": "rec", "pre_level": "pre", "recpre_slew_time": "recPreSlew",
    "fade_time": "fade", "phase_quant": "pq", "rec": "recF", "play": "play",
    "pre_filter_dry": "pfDry", "pre_filter_lp": "pfLp", "pre_filter_hp": "pfHp",
    "pre_filter_bp": "pfBp", "pre_filter_br": "pfBr",
}
# not per-voice
_GLOBAL_ARG = {
    "audio_level_cut": "cutLevel",
    "pan_slew_time": "panSlew", "level_slew_time": "levelSlew",
}


class Compass:
    """A running compass.lua, plus the wiring that makes it audible."""

    def __init__(self, bridge, log=None):
        self.bridge = bridge
        self._log = log or (lambda s: None)
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._alive = False
        self._tick_acc = 0.0
        self._last: dict[str, float] = {}
        self._chunk_t = 0.0
        self._pending: dict[tuple, float] = {}
        self.held = 0
        # what the readout shows
        self.glyph = "-"
        self.division = 1
        self.rate = 1.0
        self.loop = (1.0, 65.0)
        self.recording = False
        self.steps = 16

    # ----------------------------------------------------------------- start/stop
    def start(self, tempo: float) -> bool:
        if not os.path.exists(LUA):
            self._log("compass: no lua at %s — run move/build-lua.sh + deploy-bundle.sh" % LUA)
            return False
        host = os.path.join(SCRIPT_DIR, "compass_host.lua")
        if not os.path.exists(host):
            self._log("compass: no %s — run deploy-controller.sh" % host)
            return False
        self.proc = subprocess.Popen(
            [LUA, host], cwd=SCRIPT_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        self._alive = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._send("tempo|%.4f" % tempo)
        # init() runs on load; the first perform arms recording and randomises the sequence,
        # because the script starts with every step set to a command that does nothing
        self._send("perform|%.4f" % time.monotonic())
        return True

    def stop(self) -> None:
        self._alive = False
        if self.proc:
            try:
                self._send("quit")
                self.proc.stdin.close()
                self.proc.wait(timeout=1.0)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    # ----------------------------------------------------------------- to Lua
    def _send(self, line: str) -> None:
        p = self.proc
        if not p or not p.stdin:
            return
        try:
            p.stdin.write(line + "\n")
            p.stdin.flush()
        except Exception:
            self._alive = False

    def advance(self, beats: float) -> None:
        """Feed the command clock. `beats` is how far the sequencer moved since last call."""
        self._tick_acc += beats * TICKS_PER_BEAT
        n = int(self._tick_acc)
        if n <= 0:
            return
        self._tick_acc -= n
        now = time.monotonic()
        for _ in range(min(n, 64)):          # a stall must not fire a thousand commands
            self._send("tick|%.4f" % now)

    def phase(self, p1: float, p2: float) -> None:
        self._flush()
        now = time.monotonic()
        self._send("phase|1|%.4f|%.4f" % (p1, now))
        self._send("phase|2|%.4f|%.4f" % (p2, now))

    def perform(self) -> None:
        self._send("perform|%.4f" % time.monotonic())

    # ----------------------------------------------------------------- from Lua
    def _read_loop(self) -> None:
        p = self.proc
        if not p or not p.stdout:
            return
        for line in p.stdout:
            if not self._alive:
                break
            try:
                self._handle(line.rstrip("\n"))
            except Exception as exc:
                self._log("compass: %s" % exc)

    def _handle(self, line: str) -> None:
        f = line.split("|")
        kind = f[0] if f else ""
        if kind == "sc" and len(f) >= 4:
            self._softcut(f[1], int(float(f[2])), float(f[3]))
        elif kind == "scin" and len(f) >= 4:
            # level_input_cut(channel, voice, amp) -> the synth's in<ch><voice>
            self.bridge.compassset("in%d%d" % (int(float(f[1])), int(float(f[2]))),
                                   float(f[3]))
        elif kind == "state" and len(f) >= 8:
            self.glyph = f[1]
            self.division = int(float(f[2]))
            # f[3] is the script's rate_pos, which is NOT the live rate: rateForward and
            # rateReverse set softcut directly and never touch rate_pos, so a readout built
            # on it says "+1" while the tape is running backwards. The real rate is the last
            # value the script actually sent, tracked below.
            self.loop = (float(f[4]), float(f[5]))
            self.recording = float(f[6]) > 0
            self.steps = int(float(f[7]))
            self._log("compass: %-2s  rate %+.2g  loop %.0f-%.0fs  rec %s  1/%d beat  %d steps"
                      % (self.glyph, self.rate, self.loop[0], self.loop[1],
                         "ON" if self.recording else "FROZEN", self.division, self.steps))
        elif kind == "log":
            self._log("compass.lua: %s" % "|".join(f[1:]))

    def _softcut(self, fn: str, voice: int, value: float) -> None:
        if fn == "buffer_clear":
            self.bridge.compassclear(voice)
            return
        if fn == "rate" and voice == 1:
            self.rate = value
        if fn not in _GATED:
            self._apply(fn, voice, value)
            return
        # --- the gate ---
        now = time.monotonic()
        dt = now - self._chunk_t
        if dt < _SAME_GESTURE:
            self._apply(fn, voice, value)     # same gesture: start+end arrive together
        elif dt < CHUNK_MIN:
            # COALESCE, do not drop. Keeping the latest value and applying it when the gate
            # opens preserves what the script meant, where dropping would leave softcut on a
            # rate the script no longer thinks it has.
            self._pending[(fn, voice)] = value
            self.held += 1
        else:
            self._chunk_t = now
            self._apply(fn, voice, value)

    def _flush(self) -> None:
        """Let held changes through once the minimum chunk has elapsed.

        Driven off the phase poll, which arrives 30 times a second — fine grain against a
        400 ms gate.
        """
        if not self._pending:
            return
        if time.monotonic() - self._chunk_t < CHUNK_MIN:
            return
        self._chunk_t = time.monotonic()
        pending, self._pending = self._pending, {}
        for (fn, voice), value in pending.items():
            self._apply(fn, voice, value)

    def _apply(self, fn: str, voice: int, value: float) -> None:
        arg = _GLOBAL_ARG.get(fn)
        if arg is not None:
            self._set(arg, value)
            return
        arg = _VOICE_ARG.get(fn)
        if arg is None:
            return                            # enable/buffer/rec_offset: fixed or unused
        if voice not in (1, 2):
            return
        name = "%s%d" % (arg, voice)
        if fn == "position":
            # cutToPos is edge-triggered in the UGen, so two jumps to the same second have
            # to look different. Re-arm with the sentinel, then write the value.
            self.bridge.compassset(name, -1.0)
            self._last[name] = -1.0
        self._set(name, value)

    def _set(self, name: str, value: float) -> None:
        # update_positions re-pushes five parameters per voice on every phase poll, 30 times
        # a second. Almost all of it is unchanged, and an OSC message per unchanged value is
        # 300 messages a second for nothing.
        if self._last.get(name) == value:
            return
        self._last[name] = value
        self.bridge.compassset(name, value)
