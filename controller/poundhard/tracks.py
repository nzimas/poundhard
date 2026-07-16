"""PoundHard project state — 16 tracks, each a voice + a 32-step pattern + mute.

The controller is authoritative for this; the engine mirrors it. Kits set the
voice (type/note/vel/sample/params); patterns and mutes are the performance and
survive kit regeneration.
"""
from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from . import kits
from . import catalog
from .catalog import FX_SPECS, N_FX

N_TRACKS = 16
N_STEPS = 32
N_PATTERNS = 32     # pattern slots per project (and project slots on disk)
DRUM_TRACKS = 6            # tracks 0..5 are DRUM; 6..15 are the other generators
UNDO_LEVELS = 20           # depth of the global undo stack (discrete actions)


@dataclass
class Track:
    type: str = "EMPTY"          # unassigned by default (no engine, no sound)
    note: int = 40
    vel: float = 1.0
    sample: int = -1
    params: dict[str, float] = field(default_factory=dict)
    pattern: list[int] = field(default_factory=lambda: [0] * N_STEPS)
    muted: bool = False
    length: int = N_STEPS           # per-track pattern length (polymeter), 1..32
    rate: float = 1.0               # clock rate vs master (steps per master tick)
    # per-step locks (None = inherit the track default). Performance data — kept
    # across kit regeneration, like patterns.
    step_note: list = field(default_factory=lambda: [None] * N_STEPS)
    step_vel: list = field(default_factory=lambda: [None] * N_STEPS)
    step_pan: list = field(default_factory=lambda: [None] * N_STEPS)
    step_macro: list = field(default_factory=lambda: [None] * N_STEPS)  # per-step voice-macro position

    def load_voice(self, voice: dict) -> None:
        """Apply a generated kit voice (keeps pattern + mute + per-step locks)."""
        self.type = voice["type"]
        self.note = int(voice["note"])
        self.vel = float(voice["vel"])
        self.sample = int(voice.get("sample", -1))
        self.params = dict(voice["params"])

    def default_pan(self) -> float:
        return float(self.params.get(self.type.lower() + ".pan", 0.0))

    def eff_note(self, cell: int) -> int:
        v = self.step_note[cell]
        return int(v) if v is not None else self.note

    def eff_vel(self, cell: int) -> float:
        v = self.step_vel[cell]
        return float(v) if v is not None else self.vel

    def eff_pan(self, cell: int) -> float:
        v = self.step_pan[cell]
        return float(v) if v is not None else self.default_pan()

    def to_dict(self) -> dict:
        # COPY every mutable field — snapshots (patterns) must not share list/dict refs
        # with the live track, or a later edit would silently corrupt a saved pattern.
        return {"type": self.type, "note": self.note, "vel": self.vel,
                "sample": self.sample, "params": dict(self.params),
                "pattern": list(self.pattern), "muted": self.muted,
                "length": self.length, "rate": self.rate,
                "step_note": list(self.step_note), "step_vel": list(self.step_vel),
                "step_pan": list(self.step_pan), "step_macro": list(self.step_macro)}

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        t = cls(type=d.get("type", "EMPTY"), note=int(d.get("note", 40)),
                vel=float(d.get("vel", 1.0)), sample=int(d.get("sample", -1)),
                params=dict(d.get("params", {})), muted=bool(d.get("muted", False)),
                length=int(d.get("length", N_STEPS)), rate=float(d.get("rate", 1.0)))
        pat = list(d.get("pattern", []))[:N_STEPS]
        t.pattern = (pat + [0] * N_STEPS)[:N_STEPS]
        for attr in ("step_note", "step_vel", "step_pan", "step_macro"):
            vals = list(d.get(attr, []))[:N_STEPS]
            setattr(t, attr, (vals + [None] * N_STEPS)[:N_STEPS])
        return t


class Project:
    def __init__(self) -> None:
        self.tracks: list[Track] = [Track() for _ in range(N_TRACKS)]
        self.tempo: float = 120.0
        self.running: bool = False
        self.steps: int = N_STEPS
        self.kit_name: str = ""
        self.edit_track: int = -1          # which track the UI is editing (-1 = tracks view)
        # FX: per-track assignment stacks (last = prevailing colour), bypass, and
        # per-fx-type randomized macros (position 0..1 + a fixed +/-1 direction per param).
        self.track_fx: list[list[int]] = [[] for _ in range(N_TRACKS)]
        self.fx_bypass: list[bool] = [False] * N_TRACKS
        self.fx_macro: list[float] = [0.5] * N_FX
        # per-fx-type dry/wet mix (0 = dry, 1 = wet). Set by Shift + FX macro knob.
        self.fx_wet: list[float] = [0.5] * N_FX
        _rng = random.Random()
        self.fx_dir: list[dict] = [
            {arg: (1 if _rng.random() < 0.5 else -1) for (arg, _lo, _hi) in spec.params}
            for spec in FX_SPECS
        ]
        # per-track voice macro: one knob (knob 3 in track settings) sweeps ALL of the
        # voice's timbral params, each in a random +/- direction (like the FX macros).
        # The directions are re-rolled whenever the track's sound is regenerated.
        self.voice_macro: list[float] = [0.5] * N_TRACKS
        self.voice_dir: list[dict] = [{} for _ in range(N_TRACKS)]
        # PATTERNS: up to 32 saved snapshots (full machine state) within this project.
        # pattern_cur = the slot currently playing; pattern_pending = a queued switch that
        # takes effect at the next bar boundary (-1 = none).
        self.patterns: list[dict | None] = [None] * N_PATTERNS
        self.pattern_cur: int = -1
        self.pattern_pending: int = -1
        # SOLO: -1 = none. A live performance state (not saved into patterns): while a
        # track is soloed every other track is effectively muted, without touching their
        # own mute flags — so un-soloing restores exactly what was muted before.
        self.solo: int = -1
        # ENGINE PALETTE: one freshly-generated candidate sound per assignable engine
        # (top-row pads). Auditioned, re-rolled (Shift+pad) and held-to-assign onto any
        # track. In-memory scratch surface — the assignment lands in the track (which is
        # persisted); the palette itself is regenerated each session.
        self.palette: list[dict] = [kits.gen_palette_voice(e) for e in kits.PALETTE_ENGINES]
        # PATTERN CLIPBOARD: held only while the Copy button is down (see copy/paste).
        self.clipboard: dict | None = None
        # UNDO: a stack of whole-machine states, pushed before each discrete action.
        self.undo_stack: list[dict] = []

    # -- solo -------------------------------------------------------------- #
    def toggle_solo(self, track: int) -> int:
        self.solo = -1 if self.solo == track else track
        return self.solo

    def eff_muted(self, track: int) -> bool:
        """What the ENGINE should mute: the track's own flag, or 'not the soloed track'."""
        return self.tracks[track].muted or (self.solo >= 0 and track != self.solo)

    # -- snapshot / patterns ----------------------------------------------- #
    def snapshot(self) -> dict:
        """Full machine state at this instant (sequences, sounds, FX, tempo, macros)."""
        return {
            "tempo": self.tempo,
            "kit_name": self.kit_name,
            "tracks": [t.to_dict() for t in self.tracks],
            "track_fx": [list(s) for s in self.track_fx],
            "fx_bypass": list(self.fx_bypass),
            "fx_macro": list(self.fx_macro),
            "fx_wet": list(self.fx_wet),
            "fx_dir": [dict(d) for d in self.fx_dir],
            "voice_macro": list(self.voice_macro),
            "voice_dir": [dict(d) for d in self.voice_dir],
        }

    _GROOVE_KEYS = ("pattern", "muted", "length", "rate",
                    "step_note", "step_vel", "step_pan", "step_macro")

    def apply_groove(self, snap: dict) -> None:
        """Apply ONLY the groove (sequences / lengths / rates / mutes / per-step locks).
        Sounds, FX and tempo are left untouched — the live-switch behaviour."""
        for i, td in enumerate(snap.get("tracks", [])[:N_TRACKS]):
            src = Track.from_dict(td)
            dst = self.tracks[i]
            for k in self._GROOVE_KEYS:
                setattr(dst, k, getattr(src, k))

    def apply_full(self, snap: dict) -> None:
        """Restore the ENTIRE machine state (sounds + FX + tempo + groove)."""
        self.tempo = float(snap.get("tempo", self.tempo))
        self.kit_name = snap.get("kit_name", self.kit_name)
        self.tracks = [Track.from_dict(td) for td in snap.get("tracks", [])][:N_TRACKS]
        while len(self.tracks) < N_TRACKS:
            self.tracks.append(Track())
        self.track_fx = [list(s) for s in snap.get("track_fx", self.track_fx)]
        self.fx_bypass = list(snap.get("fx_bypass", self.fx_bypass))
        self.fx_macro = list(snap.get("fx_macro", self.fx_macro))
        self.fx_wet = list(snap.get("fx_wet", self.fx_wet))
        self.fx_dir = [dict(d) for d in snap.get("fx_dir", self.fx_dir)]
        self.voice_macro = list(snap.get("voice_macro", self.voice_macro))
        self.voice_dir = [dict(d) for d in snap.get("voice_dir", self.voice_dir)]

    def save_pattern(self, slot: int) -> None:
        if 0 <= slot < N_PATTERNS:
            self.patterns[slot] = self.snapshot()
            self.pattern_cur = slot           # this slot is now the live pattern

    def commit_current(self) -> None:
        """Write the live state back into its own pattern slot. Called before switching
        patterns or saving a project, so live edits are never lost and the slot never
        goes stale relative to the working state / the project's `base`."""
        if 0 <= self.pattern_cur < N_PATTERNS:
            self.patterns[self.pattern_cur] = self.snapshot()

    # -- pattern delete / copy / paste -------------------------------------- #
    def delete_pattern(self, slot: int) -> bool:
        """Delete a pattern and CLOSE THE GAP: everything to its right shifts one slot
        left, so the bank never has blanks between patterns."""
        if not (0 <= slot < N_PATTERNS) or self.patterns[slot] is None:
            return False
        del self.patterns[slot]
        self.patterns.append(None)
        # slots moved — keep the current/queued pointers on the right patterns
        if self.pattern_cur == slot:
            self.pattern_cur = -1              # the live pattern's slot is gone
        elif self.pattern_cur > slot:
            self.pattern_cur -= 1
        if self.pattern_pending == slot:
            self.pattern_pending = -1
        elif self.pattern_pending > slot:
            self.pattern_pending -= 1
        return True

    def copy_pattern(self, slot: int) -> bool:
        """Copy a pattern to the clipboard (held only while Copy is down)."""
        if 0 <= slot < N_PATTERNS and self.patterns[slot] is not None:
            self.clipboard = self.patterns[slot]
            return True
        return False

    def paste_pattern(self, slot: int) -> bool:
        if self.clipboard is None or not (0 <= slot < N_PATTERNS):
            return False
        # deep copy: the two slots must never alias, or editing one would edit the other
        self.patterns[slot] = copy.deepcopy(self.clipboard)
        return True

    def clear_clipboard(self) -> None:
        self.clipboard = None

    # -- undo (whole-machine states; discrete actions only) ------------------ #
    def _undo_state(self) -> dict:
        """Everything a discrete action can change. `snapshot()` already deep-copies the
        tracks; the pattern snapshots are immutable once stored (always replaced, never
        mutated in place), so a shallow list of them is a safe, cheap capture."""
        return {"base": self.snapshot(), "patterns": list(self.patterns),
                "pattern_cur": self.pattern_cur, "pattern_pending": self.pattern_pending,
                "solo": self.solo}

    def push_undo(self) -> None:
        self.undo_stack.append(self._undo_state())
        if len(self.undo_stack) > UNDO_LEVELS:
            self.undo_stack.pop(0)

    def undo(self) -> bool:
        """Restore the state from before the last discrete action."""
        if not self.undo_stack:
            return False
        s = self.undo_stack.pop()
        self.apply_full(s["base"])
        self.patterns = list(s["patterns"])
        self.pattern_cur = s["pattern_cur"]
        self.pattern_pending = s["pattern_pending"]
        self.solo = s["solo"]
        return True

    def project_to_dict(self) -> dict:
        """A whole project = its 32 pattern slots + the current live sound as `base`
        (so loading a project restores the kit even before a pattern is recalled)."""
        return {"name": self.kit_name, "base": self.snapshot(),
                "patterns": self.patterns, "pattern_cur": self.pattern_cur}

    def project_from_dict(self, d: dict) -> None:
        pats = list(d.get("patterns", []))[:N_PATTERNS]
        self.patterns = (pats + [None] * N_PATTERNS)[:N_PATTERNS]
        self.pattern_pending = -1
        base = d.get("base")
        # restore the full state from `base` (or the current pattern if there's no base)
        self.pattern_cur = int(d.get("pattern_cur", -1))
        snap = base if base is not None else (
            self.patterns[self.pattern_cur] if 0 <= self.pattern_cur < N_PATTERNS
            and self.patterns[self.pattern_cur] else None)
        if snap is not None:
            self.apply_full(snap)

    # -- fx ---------------------------------------------------------------- #
    def toggle_fx(self, track: int, fx: int) -> bool:
        """Assign/unassign FX to a track (toggle). Returns True if now assigned."""
        stack = self.track_fx[track]
        if fx in stack:
            stack.remove(fx)
            return False
        stack.append(fx)               # top of stack -> prevailing colour
        return True

    def fx_top(self, track: int) -> int:
        return self.track_fx[track][-1] if self.track_fx[track] else -1

    def macro_values(self, fx: int) -> list:
        """(arg, value) for every param of FX `fx` at its current macro position.
        Half the params move with the knob, half inverted (fx_dir)."""
        pos = self.fx_macro[fx]
        out = []
        for (arg, lo, hi) in FX_SPECS[fx].params:
            t = pos if self.fx_dir[fx][arg] > 0 else (1.0 - pos)
            out.append((arg, round(lo + t * (hi - lo), 5)))
        return out

    def set_macro(self, fx: int, pos: float) -> list:
        self.fx_macro[fx] = max(0.0, min(1.0, pos))
        return self.macro_values(fx)

    def set_fx_wet(self, fx: int, wet: float) -> float:
        """Dry/wet mix for FX type `fx` (applies to every track using it)."""
        w = max(0.0, min(1.0, float(wet)))
        if 0 <= fx < N_FX:
            self.fx_wet[fx] = w
        return w

    # -- voice macro (one knob sweeps the whole current voice) -------------- #
    def reroll_voice_macro(self, track: int) -> None:
        """Re-randomize the +/- direction per macro param — called whenever the
        track's sound is (re)generated, so the same knob sculpts a new tone each time."""
        rng = random.Random()
        self.voice_dir[track] = {
            arg: (1 if rng.random() < 0.5 else -1)
            for (_pid, arg, _lo, _hi) in catalog.macro_specs(self.tracks[track].type)
        }

    def voice_macro_values(self, track: int) -> list:
        """(full_pid, value) for every macro param of the track at its macro position.
        Half the params move with the knob, half inverted (voice_dir)."""
        tr = self.tracks[track]
        pos = self.voice_macro[track]
        d = self.voice_dir[track]
        out = []
        for (pid, arg, lo, hi) in catalog.macro_specs(tr.type):
            u = pos if d.get(arg, 1) > 0 else (1.0 - pos)
            val = round(lo + u * (hi - lo), 5)
            tr.params[pid] = val                # keep state consistent (status echo, etc.)
            out.append((pid, val))
        return out

    def set_voice_macro(self, track: int, pos: float) -> list:
        self.voice_macro[track] = max(0.0, min(1.0, pos))
        return self.voice_macro_values(track)

    def _macro_pairs_at(self, track: int, pos: float) -> list:
        d = self.voice_dir[track]
        pairs = []
        for (_pid, arg, lo, hi) in catalog.macro_specs(self.tracks[track].type):
            u = pos if d.get(arg, 1) > 0 else (1.0 - pos)
            pairs.append((arg, round(lo + u * (hi - lo), 5)))
        return pairs

    def set_step_macro(self, track: int, cell: int, pos: float) -> list:
        """Per-step macro LOCK: store the step's macro position and return (engine_arg,
        value) pairs (expanded via the track's current macro directions) for the engine.
        These override the voice's timbral params only for this step's hit."""
        pos = max(0.0, min(1.0, pos))
        self.tracks[track].step_macro[cell] = pos
        return self._macro_pairs_at(track, pos)

    def step_macro_pairs(self, track: int, cell: int):
        """(engine_arg, value) pairs for a cell's stored macro lock, or None if unlocked."""
        pos = self.tracks[track].step_macro[cell]
        return None if pos is None else self._macro_pairs_at(track, pos)

    # -- kit --------------------------------------------------------------- #
    def apply_kit(self, kit: dict) -> None:
        self.kit_name = kit.get("name", "")
        for i, voice in enumerate(kit["tracks"][:N_TRACKS]):
            self.tracks[i].load_voice(voice)
            self.reroll_voice_macro(i)          # fresh sound -> fresh macro directions

    def new_kit(self, seed: int | None = None) -> None:
        self.apply_kit(kits.gen_kit(seed))

    def randomize_track(self, track: int) -> None:
        """Re-roll ONE track's sound within its CURRENTLY-ASSIGNED engine (keeps
        pattern/locks). No-op on an empty/unassigned track."""
        tr = self.tracks[track]
        if tr.type not in kits.PALETTE_ROLES:   # EMPTY / unknown -> nothing to re-roll
            return
        tr.load_voice(kits.gen_palette_voice(tr.type))
        self.reroll_voice_macro(track)          # fresh sound -> fresh macro directions

    # -- engine palette ---------------------------------------------------- #
    def palette_voice(self, idx: int) -> dict | None:
        return self.palette[idx] if 0 <= idx < len(self.palette) else None

    def palette_regen(self, idx: int) -> dict | None:
        """Generate a fresh candidate sound for engine pad `idx`."""
        if 0 <= idx < len(self.palette):
            self.palette[idx] = kits.gen_palette_voice(kits.PALETTE_ENGINES[idx])
            return self.palette[idx]
        return None

    def palette_assign(self, idx: int, track: int) -> bool:
        """Assign engine pad `idx`'s current sound to `track` (keeps pattern/locks)."""
        if 0 <= idx < len(self.palette) and 0 <= track < N_TRACKS:
            self.tracks[track].load_voice(self.palette[idx])
            self.reroll_voice_macro(track)
            return True
        return False

    # -- edits ------------------------------------------------------------- #
    def toggle_step(self, track: int, cell: int) -> int:
        tr = self.tracks[track]
        tr.pattern[cell] ^= 1
        return tr.pattern[cell]

    def toggle_mute(self, track: int) -> bool:
        self.tracks[track].muted = not self.tracks[track].muted
        return self.tracks[track].muted

    def clear_pattern(self, track: int) -> None:
        tr = self.tracks[track]
        tr.pattern = [0] * N_STEPS
        tr.step_note = [None] * N_STEPS
        tr.step_vel = [None] * N_STEPS
        tr.step_pan = [None] * N_STEPS

    def set_length(self, track: int, length: int) -> int:
        self.tracks[track].length = max(1, min(N_STEPS, int(length)))
        return self.tracks[track].length

    def set_track_param(self, track: int, param: str, value: float) -> tuple:
        """Set a TRACK default (pitch/vel/pan/rate). Returns (kind, value) to push."""
        tr = self.tracks[track]
        if param == "pitch":
            tr.note = int(max(0, min(127, round(value))))
            return ("note", tr.note)
        if param == "vel":
            tr.vel = float(max(0.0, min(2.0, value)))
            return ("vel", tr.vel)
        if param == "pan":
            key = tr.type.lower() + ".pan"
            tr.params[key] = float(max(-1.0, min(1.0, value)))
            return ("pan", tr.params[key])
        if param == "amp":                          # track volume
            key = tr.type.lower() + ".amp"
            tr.params[key] = float(max(0.0, min(2.0, value)))
            return ("amp", tr.params[key])
        if param == "rate":
            tr.rate = float(max(0.0625, min(8.0, value)))
            return ("rate", tr.rate)
        return ("", 0.0)

    def set_step_param(self, track: int, cell: int, param: str, value: float) -> tuple:
        """Set a per-step lock (pitch/vel/pan). Returns effective (note, vel, pan)."""
        tr = self.tracks[track]
        if param == "pitch":
            tr.step_note[cell] = int(max(0, min(127, round(value))))
        elif param == "vel":
            tr.step_vel[cell] = float(max(0.0, min(2.0, value)))
        elif param == "pan":
            tr.step_pan[cell] = float(max(-1.0, min(1.0, value)))
        return (tr.eff_note(cell), tr.eff_vel(cell), tr.eff_pan(cell))

    # -- persistence ------------------------------------------------------- #
    def to_dict(self) -> dict:
        return {"tempo": self.tempo, "running": self.running, "steps": self.steps,
                "kit_name": self.kit_name,
                "tracks": [t.to_dict() for t in self.tracks]}

    def load_dict(self, d: dict) -> None:
        self.tempo = float(d.get("tempo", 120.0))
        self.steps = int(d.get("steps", N_STEPS))
        self.kit_name = d.get("kit_name", "")
        tl = d.get("tracks", [])
        for i in range(N_TRACKS):
            self.tracks[i] = Track.from_dict(tl[i]) if i < len(tl) else Track()
