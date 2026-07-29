"""PoundHard project state — 16 tracks, each a voice + a 32-step pattern + mute.

The controller is authoritative for this; the engine mirrors it. Kits set the
voice (type/note/vel/sample/params); patterns and mutes are the performance and
survive kit regeneration.
"""
from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass, field

from . import kits
from . import catalog
from .catalog import FX_SPECS, N_FX

N_TRACKS = 16
N_STEPS = 32
DEFAULT_STEPS = 16              # what a fresh track loops over (the editor's step grid)
MAX_STEPS = 16                  # the LONGEST a track may be. The per-step arrays are still
                                # N_STEPS wide (older projects, and headroom), but nothing
                                # may set a length beyond the 16 steps the editor shows.
N_PATTERNS = 32     # pattern slots per project (and project slots on disk)


# Keyword buckets for living-step flavours — a param's engine-arg name is matched
# against these substrings to decide what kind of movement it produces. The order
# matters: fx/filter/env are claimed first, everything else falls through to "tone".
_KW_FX = ("fold", "crush", "down", "grit", "ring", "drive", "dist", "wavefold",
          "destruction", "feedback", "morph", "harm", "struct", "fmamt", "fm1", "fm2",
          "rungler", "a_mod", "a_vol", "mul", "scale", "pwm", "aux", "bits", "res")
_KW_FILTER = ("cutoff", "lpf", "ffreq", "filt", "freq", "bright", "damp", "timbre",
              "peak", "tone", "pos", "runglerfilt")
_KW_ENV = ("attack", "decay", "release", "hold", "sustain", "arel", "asus", "adecay",
           "ampdecay", "pitchdecay", "noisedecay", "life")


def _classify_params(specs) -> dict:
    """Group (pid, arg, rmin, rmax, mlo, mhi) tuples into fx / filter / env / tone by the
    engine-arg name. Returns {group: {arg: (rmin, rmax, mlo, mhi)}}."""
    groups: dict = {"fx": {}, "filter": {}, "env": {}, "tone": {}}
    for (_pid, arg, rmin, rmax, mlo, mhi) in specs:
        a = arg.lower()
        if any(k in a for k in _KW_ENV):
            g = "env"
        elif any(k in a for k in _KW_FILTER):
            g = "filter"
        elif any(k in a for k in _KW_FX):
            g = "fx"
        else:
            g = "tone"
        groups[g][arg] = (rmin, rmax, mlo, mhi)
    return groups


def _snap_scale(note: int, pcs: set) -> int:
    """Nearest note whose pitch-class is in the scale set."""
    if not pcs:
        return note
    for d in range(0, 12):
        for cand in (note - d, note + d):
            if cand % 12 in pcs:
                return cand
    return note
DRUM_TRACKS = 6            # tracks 0..5 are DRUM; 6..15 are the other generators
UNDO_LEVELS = 20           # depth of the global undo stack (discrete actions)


def _step_field_defaults() -> tuple[tuple[str, ...], dict]:
    """Every per-step field on Track, and the value one slot holds by default.

    Read off a pristine Track rather than written out by hand — the single source of truth
    for "what does an empty step look like", used by clear_step and clear_pattern.
    """
    from dataclasses import fields as _fields
    proto = Track()
    names, defaults = [], {}
    for f in _fields(Track):
        if not f.name.startswith("step_"):
            continue
        val = getattr(proto, f.name)
        if isinstance(val, list) and len(val) == N_STEPS:
            names.append(f.name)
            defaults[f.name] = val[0]
    return tuple(names), defaults


def _clamp_note(n: int) -> int:
    return max(0, min(127, int(n)))


@dataclass
class Track:
    type: str = "EMPTY"          # unassigned by default (no engine, no sound)
    note: int = 40
    vel: float = 1.0
    sample: int = -1
    params: dict[str, float] = field(default_factory=dict)
    pattern: list[int] = field(default_factory=lambda: [0] * N_STEPS)
    muted: bool = False
    length: int = DEFAULT_STEPS     # per-track pattern length (polymeter), 1..32
                                    # (the editor shows/edits 16; the model still allows 32)
    rate: float = 1.0               # clock rate vs master (steps per master tick)
    # SEQUENCE TRANSPOSE (Shift + jog wheel), in semitones, -24..+24. An OFFSET rather than a
    # rewrite: the step locks keep the pitches the generator or the player put there, so
    # transposing away and back is exact and every other per-step parameter is untouched.
    transpose: int = 0
    # per-step locks (None = inherit the track default). Performance data — kept
    # across kit regeneration, like patterns.
    step_note: list = field(default_factory=lambda: [None] * N_STEPS)
    step_vel: list = field(default_factory=lambda: [None] * N_STEPS)
    step_pan: list = field(default_factory=lambda: [None] * N_STEPS)
    step_macro: list = field(default_factory=lambda: [None] * N_STEPS)  # per-step voice-macro position
    # LIVING STEPS: user-marked steps that re-transform every `step_period` cycles (bars).
    # step_ratchet / step_xmacro hold the CURRENT transform (re-rolled at runtime); step_cyc
    # is a runtime bar counter (not persisted).
    step_living: list = field(default_factory=lambda: [False] * N_STEPS)
    step_period: list = field(default_factory=lambda: [4] * N_STEPS)     # cycles between transforms
    # What a living cell returns to BETWEEN transforms: (note, vel, pan) as they were when the
    # step became living. Without it a living step forgets any lock it had — which mattered
    # little when living steps were only ever placed by hand on bare steps, but a GENERATED
    # living step arrives with velocity/pan/pitch already written and must keep them.
    step_lbase: list = field(default_factory=lambda: [None] * N_STEPS)
    step_ratchet: list = field(default_factory=lambda: [1] * N_STEPS)    # retriggers per hit
    step_send: list = field(default_factory=lambda: [0] * N_STEPS)       # route hit -> living delay/reverb
    # PER-STEP FX: bitmask over the 8 insert slots, -1 = no lock (use the track's chain).
    # Performance data like the other step locks, so it survives kit regeneration.
    step_fx: list = field(default_factory=lambda: [-1] * N_STEPS)
    # CYCLE FREQUENCY: how often a step is allowed to fire, in pattern repetitions.
    # 1 = every cycle (the default), 4 = once every four times the pattern comes round.
    # It is what lets a 16-step pattern evolve over a much longer span than 16 steps.
    step_cycle: list = field(default_factory=lambda: [1] * N_STEPS)
    # PER-STEP SAMPLE WINDOW (SAMPLE tracks). None = inherit the track's own start/end, so a
    # step can play a different slice of the same buffer without touching the others.
    step_start: list = field(default_factory=lambda: [None] * N_STEPS)
    step_end: list = field(default_factory=lambda: [None] * N_STEPS)
    # PER-STEP FILTER lock: None = follow the track, else [cutoff, res, type]. The filter is
    # one insert per track, so a locked step sets it for its own hit and an unlocked step
    # restores the track's own values — the same p-lock shape as the per-step FX mask.
    step_filt: list = field(default_factory=lambda: [None] * N_STEPS)
    # PER-TRACK MULTIMODE FILTER, ahead of the FX chain. Defaults are transparent.
    filt_cutoff: float = 18000.0
    filt_res: float = 0.0
    filt_type: int = 0            # 0 = lowpass, 1 = highpass
    step_xmacro: list = field(default_factory=lambda: [None] * N_STEPS)  # transform's param overrides
    step_cyc: list = field(default_factory=lambda: [0] * N_STEPS)        # runtime bar counter
    step_active: list = field(default_factory=lambda: [False] * N_STEPS)  # runtime: transformed last cycle
    step_heat: list = field(default_factory=lambda: [False] * N_STEPS)   # runtime: marked live by the HEAT macro (never saved)

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
        return _clamp_note((int(v) if v is not None else self.note) + self.transpose)

    def eff_track_note(self) -> int:
        """The track's own note as the engine should hear it (transpose applied)."""
        return _clamp_note(self.note + self.transpose)

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
                "step_pan": list(self.step_pan), "step_macro": list(self.step_macro),
                # HEAT is a temporary performance overlay — its marks (step_heat) are never
                # persisted, so a snapshot stores only the hand-placed (Rec+pad) living steps.
                "step_living": [lv and not ht for lv, ht in zip(self.step_living, self.step_heat)],
                "step_period": list(self.step_period),
                "step_lbase": [None if v is None else list(v) for v in self.step_lbase],
                "transpose": self.transpose,
                "step_ratchet": list(self.step_ratchet), "step_send": list(self.step_send),
                "step_fx": list(self.step_fx),
                "step_cycle": list(self.step_cycle),
                "step_start": list(self.step_start),
                "step_filt": [None if v is None else list(v) for v in self.step_filt],
                "step_end": list(self.step_end),
                "filt": [self.filt_cutoff, self.filt_res, self.filt_type],
                "step_xmacro": [list(x) if x else None for x in self.step_xmacro]}

    @classmethod
    def from_dict(cls, d: dict) -> "Track":
        raw_type = d.get("type", "EMPTY")
        params = dict(d.get("params", {}))
        if raw_type == "FMTONE":            # legacy compat: FMTONE was replaced by FM7 (same
            raw_type = "FM7"                # track index). 2-op params don't map onto 6-op FM,
            params = {}                     # so the track loads as a default FM7 to be re-rolled.
        t = cls(type=raw_type, note=int(d.get("note", 40)),
                vel=float(d.get("vel", 1.0)), sample=int(d.get("sample", -1)),
                params=params, muted=bool(d.get("muted", False)),
                length=max(1, min(MAX_STEPS, int(d.get("length", DEFAULT_STEPS)))),
                rate=float(d.get("rate", 1.0)))
        pat = list(d.get("pattern", []))[:N_STEPS]
        t.pattern = (pat + [0] * N_STEPS)[:N_STEPS]
        for attr in ("step_note", "step_vel", "step_pan", "step_macro", "step_xmacro"):
            vals = list(d.get(attr, []))[:N_STEPS]
            setattr(t, attr, (vals + [None] * N_STEPS)[:N_STEPS])
        t.step_living = ([bool(x) for x in d.get("step_living", [])][:N_STEPS] + [False] * N_STEPS)[:N_STEPS]
        t.step_period = ([int(x) for x in d.get("step_period", [])][:N_STEPS] + [4] * N_STEPS)[:N_STEPS]
        lb = [None if v is None else tuple(v) for v in d.get("step_lbase", [])][:N_STEPS]
        t.step_lbase = (lb + [None] * N_STEPS)[:N_STEPS]
        t.transpose = max(-24, min(24, int(d.get("transpose", 0))))
        t.step_ratchet = ([int(x) for x in d.get("step_ratchet", [])][:N_STEPS] + [1] * N_STEPS)[:N_STEPS]
        t.step_send = ([int(x) for x in d.get("step_send", [])][:N_STEPS] + [0] * N_STEPS)[:N_STEPS]
        t.step_fx = ([int(x) for x in d.get("step_fx", [])][:N_STEPS] + [-1] * N_STEPS)[:N_STEPS]
        t.step_cycle = ([max(1, min(8, int(x))) for x in d.get("step_cycle", [])][:N_STEPS]
                        + [1] * N_STEPS)[:N_STEPS]
        raw = d.get("step_filt", [])
        fl = [None if v is None else [float(v[0]), float(v[1]), int(v[2])] for v in raw][:N_STEPS]
        t.step_filt = (fl + [None] * N_STEPS)[:N_STEPS]
        for name in ("step_start", "step_end"):
            raw = d.get(name, [])
            vals = [None if x is None else max(0.0, min(1.0, float(x))) for x in raw][:N_STEPS]
            setattr(t, name, (vals + [None] * N_STEPS)[:N_STEPS])
        fl = d.get("filt")
        if isinstance(fl, (list, tuple)) and len(fl) == 3:
            t.filt_cutoff = max(20.0, min(19000.0, float(fl[0])))
            t.filt_res = max(0.0, min(1.0, float(fl[1])))
            t.filt_type = 1 if int(fl[2]) else 0
        t.step_cyc = [0] * N_STEPS
        t.step_heat = [False] * N_STEPS       # HEAT is never restored from disk (performance-only)
        return t


# FX CHAIN LAYOUT VERSION. v1 was  OD AMP CRSH RING FLNG CLDS RESO GREY.
# v2 dropped the flanger and appended the plate reverb, keeping 8 slots:
#     OD AMP CRSH RING CLDS RESO GREY VERB
# Saved projects store FX by SLOT INDEX, so a v1 snapshot loaded as-is would silently
# shift every effect (a track's CLDS would come back as RING). Snapshots written from
# now on carry "fx_layout"; anything without it is v1 and is remapped on load.
_FX_LAYOUT = 2
_FX_V1_TO_V2 = {0: 0, 1: 1, 2: 2, 3: 3, 5: 4, 6: 5, 7: 6}   # 4 (FLNG) no longer exists



_STEP_FIELDS_ALL, _STEP_DEFAULTS = _step_field_defaults()

class Project:
    def __init__(self) -> None:
        self.tracks: list[Track] = [Track() for _ in range(N_TRACKS)]
        self.tempo: float = 120.0
        self.running: bool = False
        self.steps: int = N_STEPS
        self.kit_name: str = ""
        self.edit_track: int = -1          # which track the UI is editing (-1 = tracks view)
        # The project's scale, established by the FIRST pitched material and respected by
        # every generated track afterwards. None until something pitched exists.
        self.scale_root: int | None = None
        self.scale_name: str | None = None
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
        # SHUFFLE: engine track -> source track whose rhythm it currently plays (runtime,
        # set by the controller's shuffle overlay). Empty = no shuffle. HEAT and the living
        # steps read it so they operate on the rhythm each engine track ACTUALLY plays.
        self.shuffle_perm: dict[int, int] = {}
        # DRUM TYPE LOCK: the drum type (0..6 = kick/snare/hihat/metal/clap/tom/noise) the
        # DRUM palette pad is pinned to, chosen by holding that pad and tapping one of the
        # pads to its right. -1 = unlocked (roll any type). A performance preference —
        # runtime only, never saved.
        self.drum_mode: int = -1
        # HEAT snapshot: the exact per-cell BASE state captured when the HEAT macro engages,
        # so disengaging restores the pattern EXACTLY (locks, ratchets, sends) with no trace.
        self._heat_snap: list | None = None
        # ENGINE PALETTE: one freshly-generated candidate sound per assignable engine
        # (top-row pads). Auditioned, re-rolled (Shift+pad) and held-to-assign onto any
        # track. In-memory scratch surface — the assignment lands in the track (which is
        # persisted); the palette itself is regenerated each session.
        self.palette: list[dict] = [kits.gen_palette_voice(e) for e in kits.PALETTE_ENGINES]
        # CHAOS MACRO (knob 8, tracks view): one knob sweeps EVERY param of EVERY
        # assigned engine at once, each in its own random direction. Position 0.5 is the
        # SAFE ZONE — the stored state captured when the knob was first engaged; turning
        # either way drifts away from it, turning back (or Shift+touch) returns to it.
        self.chaos_pos: float = 0.5
        self.chaos_base: dict | None = None      # {track: {pid: value}} — the safe zone
        self.chaos_dir: list[dict] = [{} for _ in range(N_TRACKS)]
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
            "fx_layout": _FX_LAYOUT,
            "track_fx": [list(s) for s in self.track_fx],
            "fx_bypass": list(self.fx_bypass),
            "fx_macro": list(self.fx_macro),
            "fx_wet": list(self.fx_wet),
            "fx_dir": [dict(d) for d in self.fx_dir],
            "voice_macro": list(self.voice_macro),
            "voice_dir": [dict(d) for d in self.voice_dir],
            # the piece's scale travels with the pattern: switching pattern switches key
            "scale": None if self.scale_name is None else [self.scale_root, self.scale_name],
        }

    def apply_full(self, snap: dict) -> None:
        """Restore the ENTIRE machine state — **tempo**, every engine's params, the
        engine-to-track assignment, FX (chains, bypass, macros, dry/wet), mutes,
        sequences and per-step locks. Patterns are self-contained units and **tempo is
        per pattern**, so switching pattern switches BPM with it."""
        self.tempo = float(snap.get("tempo", self.tempo))
        self.chaos_invalidate()               # new sounds -> the old safe zone is void
        self.kit_name = snap.get("kit_name", self.kit_name)
        sc = snap.get("scale")
        if isinstance(sc, (list, tuple)) and len(sc) == 2:
            self.scale_root, self.scale_name = int(sc[0]), str(sc[1])
        else:                                  # a project saved before scales existed
            self.scale_root, self.scale_name = None, None
        self.tracks = [Track.from_dict(td) for td in snap.get("tracks", [])][:N_TRACKS]
        while len(self.tracks) < N_TRACKS:
            self.tracks.append(Track())
        track_fx = [list(s) for s in snap.get("track_fx", self.track_fx)]
        fx_macro = list(snap.get("fx_macro", self.fx_macro))
        fx_wet = list(snap.get("fx_wet", self.fx_wet))
        fx_dir = [dict(d) for d in snap.get("fx_dir", self.fx_dir)]
        if int(snap.get("fx_layout", 1)) < _FX_LAYOUT:
            # pre-VERB project: drop any flanger and slide CLDS/RESO/GREY down one slot,
            # carrying each effect's own macro/wet/direction with it. VERB (slot 7) starts
            # at defaults — the project never had one.
            track_fx = [[_FX_V1_TO_V2[i] for i in stack if i in _FX_V1_TO_V2] for stack in track_fx]
            m, w, d = list(self.fx_macro), list(self.fx_wet), [dict(x) for x in self.fx_dir]
            for old_i, new_i in _FX_V1_TO_V2.items():
                if old_i < len(fx_macro):
                    m[new_i] = fx_macro[old_i]
                if old_i < len(fx_wet):
                    w[new_i] = fx_wet[old_i]
                if old_i < len(fx_dir):
                    d[new_i] = dict(fx_dir[old_i])
            fx_macro, fx_wet, fx_dir = m, w, d
        self.track_fx = track_fx
        self.fx_bypass = list(snap.get("fx_bypass", self.fx_bypass))
        self.fx_macro = fx_macro
        self.fx_wet = fx_wet
        self.fx_dir = fx_dir
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

    # -- chaos macro (knob 8, tracks view) ---------------------------------- #
    def chaos_invalidate(self) -> None:
        """Forget the safe zone — the underlying sounds changed, so the old baseline is
        meaningless. The next knob move captures a fresh one."""
        self.chaos_base = None
        self.chaos_pos = 0.5

    def _chaos_capture(self) -> None:
        """Snapshot every assigned engine's params: this is the safe zone to return to."""
        rng = random.Random()
        base: dict = {}
        for t in range(N_TRACKS):
            tr = self.tracks[t]
            specs = catalog.macro_specs(tr.type)
            if not specs:
                continue
            base[t] = {pid: float(tr.params.get(pid, 0.0)) for (pid, _a, _lo, _hi) in specs}
            # a random +/- per param: the knob pushes some up and some down at once,
            # whichever way it's turned
            self.chaos_dir[t] = {arg: (1 if rng.random() < 0.5 else -1)
                                 for (_pid, arg, _lo, _hi) in specs}
        self.chaos_base = base

    def set_chaos(self, pos: float) -> list[tuple[int, str, float]]:
        """Sweep every param of every assigned engine away from the safe zone.
        Returns [(track, pid, value)] to push. pos 0.5 == exactly the stored state."""
        pos = max(0.0, min(1.0, float(pos)))
        if self.chaos_base is None:
            self._chaos_capture()
        self.chaos_pos = pos
        dev = (pos - 0.5) * 2.0                  # -1..+1
        out: list[tuple[int, str, float]] = []
        for t, params in self.chaos_base.items():
            tr = self.tracks[t]
            spec = catalog.VOICES.get(tr.type)
            if spec is None:
                continue
            metas = {m.id: m for m in spec.params}
            for (pid, arg, lo, hi) in catalog.macro_specs(tr.type):
                if pid not in params or pid not in metas:
                    continue
                d = self.chaos_dir[t].get(arg, 1)
                # excursion is scaled by the param's own musical span, then clamped to
                # its absolute range — at dev == 0 this is exactly the baseline
                val = metas[pid].clamp(params[pid] + d * dev * (hi - lo) * 0.5)
                tr.params[pid] = round(val, 5)
                out.append((t, pid, tr.params[pid]))
        return out

    def chaos_reset(self) -> list[tuple[int, str, float]]:
        """Shift + touch knob 8: jump straight back to the safe zone."""
        out: list[tuple[int, str, float]] = []
        for t, params in (self.chaos_base or {}).items():
            for pid, v in params.items():
                self.tracks[t].params[pid] = v
                out.append((t, pid, v))
        self.chaos_invalidate()
        return out

    # -- pattern delete / copy / paste -------------------------------------- #
    def delete_pattern(self, slot: int) -> bool:
        """Delete a pattern IN PLACE: only that slot is cleared; every other pattern keeps
        its position in the bank (no gap-closing shift)."""
        if not (0 <= slot < N_PATTERNS) or self.patterns[slot] is None:
            return False
        self.patterns[slot] = None
        if self.pattern_cur == slot:
            self.pattern_cur = -1              # the live pattern's slot is gone (state keeps playing)
        if self.pattern_pending == slot:
            self.pattern_pending = -1
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
            # .get(arg, 1): a project saved with an OLDER FX param set has no direction for
            # params added since — default to +1 (moves with the knob) instead of KeyError,
            # which would crash the load mid-push. Forwards compatibility.
            t = pos if self.fx_dir[fx].get(arg, 1) > 0 else (1.0 - pos)
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

    # -- living steps (self-transforming) ---------------------------------- #
    def step_engine_macro(self, track: int, cell: int):
        """Flat [(arg, val)] to push for a cell: a living step's transform override takes
        precedence over the user's manual macro-position lock."""
        xm = self.tracks[track].step_xmacro[cell]
        if xm is not None:
            return list(xm)
        return self.step_macro_pairs(track, cell)

    def toggle_living(self, track: int, cell: int) -> bool:
        """Mark / unmark a step as living. Marking fires one transform immediately (audible
        feedback) and marks it active, so it reverts next cycle and then fires periodically.
        Unmarking reverts the cell to a plain step."""
        tr = self.tracks[track]
        tr.step_living[cell] = not tr.step_living[cell]
        if tr.step_living[cell]:
            # remember what the step WAS, so every revert between transforms returns it to
            # its own locks rather than to the bare track defaults
            tr.step_lbase[cell] = (tr.step_note[cell], tr.step_vel[cell], tr.step_pan[cell])
            self.reroll_living(track, cell)     # one-shot feedback; fx sends wait for tick
            tr.step_active[cell] = True
            tr.step_cyc[cell] = 1               # already armed at phase 0 -> next tick is phase 1
        else:                                   # back to a plain, untransformed step
            self._revert_living_cell(track, cell)
            tr.step_lbase[cell] = None
            tr.step_active[cell] = False
        return tr.step_living[cell]

    def set_step_period(self, track: int, cell: int, period: int) -> int:
        """How often the living transform fires, counted in PLAYS OF THIS STEP (1-8, the
        row-4 pads). It multiplies with the step's own playback divider: a step that plays
        every 3rd pattern cycle with a living interval of 2 transforms every 6th cycle."""
        self.tracks[track].step_period[cell] = max(1, min(8, int(period)))
        return self.tracks[track].step_period[cell]

    # -- copy a whole track -------------------------------------------------- #
    def copy_track(self, src: int, dst: int) -> bool:
        """Make `dst` an exact, INDEPENDENT clone of `src`. Returns False if it can't.

        Everything a track is: engine and its params, note/velocity/sample, the sequence and
        every per-step lock (pitch, velocity, pan, macro, FX mask, cycle divider, sample
        window, filter, ratchet, send), living marks with their intervals and current
        transforms, the track filter, transpose, length, rate, mute, the FX chain and its
        bypass, and the voice-macro position with its randomised directions.

        Deep-copied, so the two tracks share nothing afterwards — re-assigning the engine,
        generating a new sequence or editing any step on one cannot reach the other. The
        SAMPLE buffer lives in the engine and is duplicated there (`/ph/smpcopy`); the
        controller only owns the state below.
        """
        if not (0 <= src < N_TRACKS and 0 <= dst < N_TRACKS) or src == dst:
            return False
        self.tracks[dst] = copy.deepcopy(self.tracks[src])
        self.track_fx[dst] = list(self.track_fx[src])
        self.fx_bypass[dst] = self.fx_bypass[src]
        self.voice_macro[dst] = self.voice_macro[src]
        self.voice_dir[dst] = dict(self.voice_dir[src])
        # HEAT is a live overlay owned by a snapshot taken when it engaged, and the clone is
        # not in that snapshot — carrying its marks across would leave cells no toggle-off
        # could restore. The clone gets the steps as they were underneath.
        d = self.tracks[dst]
        for c in range(N_STEPS):
            if d.step_heat[c]:
                self._revert_living_cell(dst, c)
                d.step_heat[c] = False
                d.step_living[c] = False
                d.step_active[c] = False
                d.step_lbase[c] = None
        return True

    # -- transpose ---------------------------------------------------------- #
    def transpose_track(self, track: int, delta: int) -> int:
        """Shift a whole sequence by semitones (Shift + jog). Returns the new total, -24..+24.

        Nothing is rewritten: the offset rides on top of the step locks, so step placement,
        velocity, pan, living marks, FX and cycle intervals are all untouched, and coming back
        to 0 restores the original pitches exactly.
        """
        tr = self.tracks[track]
        tr.transpose = max(-24, min(24, tr.transpose + int(delta)))
        return tr.transpose

    def _revert_living_cell(self, track: int, cell: int) -> None:
        """Return a living cell to its plain, untransformed state (keeps the living mark)."""
        tr = self.tracks[track]
        tr.step_xmacro[cell] = None
        tr.step_ratchet[cell] = 1
        tr.step_send[cell] = 0
        base = tr.step_lbase[cell]
        tr.step_note[cell], tr.step_vel[cell], tr.step_pan[cell] = base or (None, None, None)

    def reroll_living(self, track: int, cell: int):
        """Roll ONE fresh transformation for a living step (fired periodically — see
        tick_living). Picks distinct FLAVOURS and drives them HARD for obvious, varied
        movement: each engine's own character/fx params (bitcrush, wavefold, ringmod, drive;
        Plaits morph/harmonics; Rings structure/pos), a filter sweep, pitch (octave leaps),
        panning, ratchets, and a DELAY/REVERB send (routes just this hit through the living-FX
        bus — no bleed). Returns the living-FX params (dTime,dFb,dMix,vMix,vRoom,vDamp) if a
        send was chosen, else None. Envelope moves were dropped (mostly inaudible)."""
        rng = random
        tr = self.tracks[track]
        specs = catalog.macro_specs_full(tr.type)
        by_kw = _classify_params(specs)
        self._revert_living_cell(track, cell)
        pairs: dict[str, float] = {}

        def drive(group, n, extreme):
            items = list(by_kw.get(group, {}).items())
            if not items:
                return
            rng.shuffle(items)
            for arg, (rmin, rmax, mlo, mhi) in items[:n]:
                if extreme and rng.random() < 0.85:
                    # slam to a rail of the FULL range for unmistakable character
                    v = rmin if rng.random() < 0.5 else rmax
                    v = v * 0.92 + (rmax if v == rmin else rmin) * 0.08
                else:
                    v = rng.uniform(mlo, mhi)
                pairs[arg] = round(v, 5)

        # ALWAYS start from a strongly-audible PRIMARY flavour (never pan alone — pan is barely
        # perceptible on a sustained tone), then STACK spice on top. "delay"/"reverb" route the
        # hit through the living-FX send bus (per-step, no bleed). envelope moves were dropped.
        primary = ["fx", "fx", "filter", "filter", "pitch", "delay", "reverb"]
        extras = ["fx", "filter", "pitch", "pan", "delay", "reverb"]
        chosen = {rng.choice(primary)}
        while rng.random() < 0.6 and len(chosen) < 4:       # usually 2-3 stacked flavours
            chosen.add(rng.choice(extras))

        # pitch leaps are meaningless on DRUM/EMPTY — spend that flavour on hard character instead
        if "pitch" in chosen and tr.type in ("EMPTY", "DRUM"):
            chosen.discard("pitch")
            chosen.add("fx")

        if "fx" in chosen:
            drive("fx", rng.randint(2, 4), extreme=True)    # more params, harder
        if "filter" in chosen:
            drive("filter", rng.randint(1, 2), extreme=rng.random() < 0.8)
        drive("tone", 1, extreme=rng.random() < 0.4)        # a little extra movement

        if rng.random() < 0.3:                              # ratchet: occasional
            tr.step_ratchet[cell] = rng.choice([2, 2, 3, 4])

        if "pitch" in chosen and tr.type not in ("EMPTY", "DRUM"):
            # a living leap belongs to the piece: use the project's own scale once something
            # has established one, and only fall back to the kit default before that
            if self.scale_name is not None:
                from . import scales
                pcs = scales.pitch_classes(self.scale_root, self.scale_name)
            else:
                pcs = {(kits._ROOT + s) % 12 for s in kits._SCALE}
            cand = tr.note + rng.choice([-24, -12, -12, -7, -5, 5, 7, 12, 12, 19, 24])
            tr.step_note[cell] = max(24, min(96, _snap_scale(cand, pcs)))

        if "pan" in chosen:
            tr.step_pan[cell] = round(rng.choice([-1, 1]) * rng.uniform(0.6, 1.0), 3)
        elif rng.random() < 0.35:
            tr.step_pan[cell] = round(rng.uniform(-0.7, 0.7), 3)

        if rng.random() < 0.6:
            tr.step_vel[cell] = round(max(0.25, min(1.35, tr.vel * rng.uniform(0.6, 1.3))), 3)

        tr.step_xmacro[cell] = [(a, v) for a, v in pairs.items()] or None

        # --- DELAY / REVERB send (per-step, via the living-FX bus) ---
        want_delay = "delay" in chosen
        want_verb = "reverb" in chosen
        if want_delay or want_verb:
            tr.step_send[cell] = 1
            dtime = round(rng.uniform(0.09, 0.5), 3)
            dfb = round(rng.uniform(0.3, 0.7), 3)
            dmix = round(rng.uniform(0.4, 0.7) if want_delay else rng.uniform(0.05, 0.2), 3)
            vmix = round(rng.uniform(0.4, 0.65) if want_verb else rng.uniform(0.05, 0.2), 3)
            vroom = round(rng.uniform(0.55, 0.9), 3)
            vdamp = round(rng.uniform(0.2, 0.5), 3)
            return (dtime, dfb, dmix, vmix, vroom, vdamp)
        return None

    def tick_living(self, track: int):
        """Advance one bar for a track's living steps. Returns (changed_cells, living_fx).

        /ph/cycle fires every 16 GLOBAL steps (one bar), but a marked step only SOUNDS once
        per track LOOP (= length/rate global steps = length/(16*rate) bars). The old model
        armed a transform for a single bar, so on any track whose loop spans >1 bar the step
        usually never played while armed — you'd hear nothing for many repeats, then a hit.

        Fix: hold the transform armed for a FULL loop (`loop_bars`, rounded UP so the window
        always covers at least one play). Any window that long is guaranteed to contain
        exactly one play of the step, regardless of phase — so a fire is ALWAYS audible.

        The period is counted in PLAYS OF THE STEP, and a step's cycle divider decides how
        often that is: one play takes `step_cycle * loop_bars` bars, so a living interval of
        N fires every `N * step_cycle` plays-worth of bars. Row 3 (when it plays) and row 4
        (how often it transforms) multiply — which is the whole point of driving both from
        the same cycle-counting model."""
        tr = self.tracks[track]
        # under SHUFFLE, engine track `track` plays `src`'s rhythm — time the living period to
        # the loop it actually plays, not this track's own length/rate.
        src = self.tracks[self.shuffle_perm.get(track, track)]
        loop_bars = max(1, math.ceil(src.length / (16.0 * max(src.rate, 0.0625))))
        changed = []
        living_fx = None
        for c in range(N_STEPS):
            if not tr.step_living[c]:
                continue
            play_bars = max(1, int(tr.step_cycle[c])) * loop_bars   # bars between two PLAYS
            eff = max(1, int(tr.step_period[c])) * play_bars        # bars between transforms
            phase = tr.step_cyc[c] % eff
            if phase == 0:                        # start of a period -> arm a fresh transform
                fx = self.reroll_living(track, c)
                tr.step_active[c] = True
                changed.append(c)
                if fx is not None:
                    living_fx = fx
            elif phase == play_bars and tr.step_active[c]:   # one PLAY later -> back to plain
                self._revert_living_cell(track, c)
                tr.step_active[c] = False
                changed.append(c)
            tr.step_cyc[c] = (phase + 1) % eff
        return changed, living_fx

    # -- HEAT macro -------------------------------------------------------- #
    def _heat_periods(self, n: int) -> list:
        """n transform periods spread over 2..6 with guaranteed in-track VARIETY
        (at least two distinct values whenever n >= 2)."""
        if n <= 0:
            return []
        vals = [random.randint(2, 6) for _ in range(n)]
        if n >= 2 and len(set(vals)) == 1:
            i = random.randrange(n)
            vals[i] = random.choice([p for p in range(2, 7) if p != vals[i]])
        return vals

    def heat_snapshot(self) -> None:
        """Capture the EXACT base per-cell state of every track (the fields a living transform
        mutates), so heat_clear can restore the pattern with zero trace — including hand-set
        step locks that a transform would otherwise overwrite. Taken once, when HEAT engages."""
        self._heat_snap = [
            [(tr.step_note[c], tr.step_vel[c], tr.step_pan[c], tr.step_ratchet[c],
              tr.step_send[c], list(tr.step_xmacro[c]) if tr.step_xmacro[c] else None)
             for c in range(N_STEPS)]
            for tr in self.tracks]

    def heat_clear(self) -> list:
        """Drop the HEAT overlay and RESTORE each HEAT-marked cell to its exact pre-HEAT base
        state from the snapshot (locks, ratchet, send, macro) — not just the currently-active
        ones, so no transform can leave a trace. Hand-placed (Rec+pad) living steps are never
        HEAT-marked, so they're left untouched. Idempotent. Returns EVERY (track,cell) that was
        HEAT-marked, so the caller resets exactly those in the engine."""
        touched = []
        snap = self._heat_snap
        for t, tr in enumerate(self.tracks):
            for c in range(N_STEPS):
                if not tr.step_heat[c]:
                    continue
                touched.append((t, c))
                tr.step_heat[c] = False
                tr.step_living[c] = False
                tr.step_period[c] = 4
                tr.step_cyc[c] = 0
                tr.step_active[c] = False
                tr.step_lbase[c] = None
                if snap is not None:                    # restore the exact base for this cell
                    n, v, pa, ra, se, xm = snap[t][c]
                    tr.step_note[c] = n; tr.step_vel[c] = v; tr.step_pan[c] = pa
                    tr.step_ratchet[c] = ra; tr.step_send[c] = se
                    tr.step_xmacro[c] = list(xm) if xm else None
                else:                                   # no snapshot -> plain defaults
                    self._revert_living_cell(t, c)
        return touched

    def heat_apply(self, pct: float) -> None:
        """HEAT: mark ~pct of the SEQUENCED steps (pattern hits) of every non-empty track as
        living, with per-step periods spread over 2..6 (varied within each track) and STAGGERED
        cycle phases so they don't all transform on the same bar. It's a TEMPORARY OVERLAY:
        marks are flagged step_heat (never saved), it skips steps that are already living (so
        hand-placed marks are preserved), and the caller clears the overlay first (heat_clear)
        so re-applies never stack."""
        pct = max(0.0, min(1.0, float(pct)))
        if pct <= 0.0:
            return
        for t, tr in enumerate(self.tracks):
            if tr.type == "EMPTY":
                continue
            # HEAT follows SHUFFLE: engine track t plays `src`'s rhythm, so mark the cells that
            # ACTUALLY fire on t (src's hits) and time the period to src's loop, while the
            # transform itself still uses t's own SOUND (reroll_living reads tr.type).
            src = self.tracks[self.shuffle_perm.get(t, t)]
            cands = [c for c in range(min(src.length, N_STEPS))
                     if src.pattern[c] and not tr.step_living[c]]   # skip hand-placed living steps
            if not cands:
                continue
            random.shuffle(cands)
            k = max(1, int(round(len(cands) * pct)))    # heat every playing track at least a little
            chosen = cands[:k]
            loop_bars = max(1, math.ceil(src.length / (16.0 * max(src.rate, 0.0625))))
            for cell, per in zip(chosen, self._heat_periods(len(chosen))):
                tr.step_living[cell] = True
                tr.step_heat[cell] = True               # HEAT-owned: cleared on toggle-off, never saved
                tr.step_period[cell] = per
                tr.step_active[cell] = False
                # keep whatever the step already had; HEAT should not erase hand-set or
                # generated locks while it holds the cell
                tr.step_lbase[cell] = (tr.step_note[cell], tr.step_vel[cell], tr.step_pan[cell])
                self._revert_living_cell(t, cell)       # start plain; fires when its period elapses
                tr.step_cyc[cell] = random.randrange(per * loop_bars)   # stagger the first fire

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
        self.chaos_invalidate()

    # -- engine palette ---------------------------------------------------- #
    def palette_voice(self, idx: int) -> dict | None:
        return self.palette[idx] if 0 <= idx < len(self.palette) else None

    def palette_regen(self, idx: int) -> dict | None:
        """Generate a fresh candidate sound for engine pad `idx`. A DRUM pad locked to a
        type (see set_drum_mode) keeps rolling variations of THAT drum."""
        if 0 <= idx < len(self.palette):
            engine = kits.PALETTE_ENGINES[idx]
            dm = self.drum_mode if (engine == "DRUM" and self.drum_mode >= 0) else None
            self.palette[idx] = kits.gen_palette_voice(engine, drum_mode=dm)
            return self.palette[idx]
        return None

    def drum_type_example(self, mode: int) -> dict | None:
        """A STABLE, representative DRUM voice for one type — deterministic, so tapping a
        type pad auditions *that type* (the same reference sound every press) instead of a
        fresh random variation each time. Pure preview: changes no state."""
        if not (0 <= mode <= 6):
            return None
        return kits.gen_palette_voice("DRUM", random.Random(9000 + mode), drum_mode=mode)

    def set_drum_mode(self, mode: int) -> dict | None:
        """Lock the DRUM palette pad to one drum type (0..6; anything else = unlocked) and
        re-roll that pad as the chosen type — so the picked type IS the engine's sound the
        moment you lift your hand (ready to assign), and every later generate stays on it.
        Returns the fresh voice so the caller can audition it."""
        self.drum_mode = mode if 0 <= mode <= 6 else -1
        if "DRUM" not in kits.PALETTE_ENGINES:
            return None
        return self.palette_regen(kits.PALETTE_ENGINES.index("DRUM"))

    def palette_assign(self, idx: int, track: int) -> bool:
        """Assign engine pad `idx`'s current sound to `track` (keeps pattern/locks)."""
        if 0 <= idx < len(self.palette) and 0 <= track < N_TRACKS:
            self.tracks[track].load_voice(self.palette[idx])
            self.reroll_voice_macro(track)
            self.chaos_invalidate()
            return True
        return False

    # -- edits ------------------------------------------------------------- #
    def toggle_step(self, track: int, cell: int) -> int:
        tr = self.tracks[track]
        tr.pattern[cell] ^= 1
        if tr.pattern[cell] == 0:
            self.clear_step(track, cell)     # a deleted step leaves nothing behind
        return tr.pattern[cell]

    def clear_step(self, track: int, cell: int) -> None:
        """Reset one step slot to the track's defaults — EVERYTHING it held.

        Deleting a step used to remove only the hit, leaving its pitch, velocity, pan,
        macro, FX mask, cycle divider, filter, sample window, ratchet, send and living
        mark sitting in the slot. Drawing a new step there inherited all of it, which is
        both surprising and impossible to undo by hand.

        The field list is derived from the dataclass defaults rather than written out, so
        a per-step parameter added later is cleared here automatically instead of quietly
        becoming the next instance of this bug.
        """
        tr = self.tracks[track]
        for name in _STEP_FIELDS_ALL:
            getattr(tr, name)[cell] = _STEP_DEFAULTS[name]

    def toggle_mute(self, track: int) -> bool:
        self.tracks[track].muted = not self.tracks[track].muted
        return self.tracks[track].muted

    # -- step / row clipboard ---------------------------------------------- #
    # Everything that makes a step what it is: whether it fires, its parameter locks, and
    # its living-step settings. Copy carries ALL of it — a step pasted elsewhere sounds
    # exactly like the one it came from.
    _STEP_FIELDS = ("pattern", "step_note", "step_vel", "step_pan", "step_macro",
                    "step_living", "step_period", "step_ratchet", "step_send", "step_fx",
                    "step_cycle", "step_start", "step_end", "step_filt")

    def copy_step(self, track: int, cell: int) -> dict | None:
        """Snapshot one step (and every lock on it). None if the cell is out of range."""
        if not (0 <= track < N_TRACKS and 0 <= cell < N_STEPS):
            return None
        tr = self.tracks[track]
        return {f: getattr(tr, f)[cell] for f in self._STEP_FIELDS}

    def paste_step(self, track: int, cell: int, clip: dict) -> bool:
        """Write a snapshot onto a step, replacing whatever was there."""
        if not (0 <= track < N_TRACKS and 0 <= cell < N_STEPS) or not clip:
            return False
        tr = self.tracks[track]
        for f in self._STEP_FIELDS:
            if f in clip:
                getattr(tr, f)[cell] = clip[f]
        return True

    def copy_row(self, track: int, row: int, per_row: int = 8) -> list | None:
        """Snapshot a whole row of steps (row 0 = steps 1-8, row 1 = steps 9-16)."""
        if not (0 <= track < N_TRACKS) or row < 0:
            return None
        base = row * per_row
        if base + per_row > N_STEPS:
            return None
        return [self.copy_step(track, base + i) for i in range(per_row)]

    def paste_row(self, track: int, row: int, clip: list, per_row: int = 8) -> list[int]:
        """Write a row snapshot onto a row. Returns the cells actually written."""
        if not (0 <= track < N_TRACKS) or row < 0 or not clip:
            return []
        base = row * per_row
        if base + len(clip) > N_STEPS:
            return []
        written = []
        for i, step in enumerate(clip):
            if step and self.paste_step(track, base + i, step):
                written.append(base + i)
        return written

    # -- the project's scale ------------------------------------------------ #
    # There is no key selector, and there should not be one: the first track to carry
    # pitched material decides what the piece is in, and generated tracks answer to it.
    def set_scale(self, root: int, name: str) -> tuple:
        self.scale_root = int(root)
        self.scale_name = str(name)
        return (self.scale_root, self.scale_name)

    def ensure_scale(self, notes=None) -> tuple:
        """Establish the scale from what has been played, if it isn't established yet."""
        if self.scale_name is not None:
            return (self.scale_root, self.scale_name)
        from . import scales
        pool = list(notes or [])
        if not pool:
            ctx = scales.context(self)
            pool = ctx["notes"]
        root, name = scales.detect(pool)
        return self.set_scale(root, name)

    def clear_pattern(self, track: int) -> None:
        # Same story as clear_step, one slot at a time: the hand-written list here missed
        # the living marks, the macro locks, ratchets, sends and transform overrides, so a
        # cleared pattern was not actually empty.
        tr = self.tracks[track]
        tr.pattern = [0] * N_STEPS
        for cell in range(N_STEPS):
            self.clear_step(track, cell)

    def eff_start(self, track: int, cell: int) -> float:
        tr = self.tracks[track]
        v = tr.step_start[cell]
        return float(v) if v is not None else float(tr.params.get("sample.start", 0.0))

    def eff_end(self, track: int, cell: int) -> float:
        tr = self.tracks[track]
        v = tr.step_end[cell]
        return float(v) if v is not None else float(tr.params.get("sample.end", 1.0))

    def set_step_window(self, track: int, cell: int, which: str, value: float) -> tuple:
        """Lock this step's slice of the sample. Start and end clamp against each other so
        the window can never invert."""
        tr = self.tracks[track]
        v = max(0.0, min(1.0, float(value)))
        if which == "start":
            tr.step_start[cell] = min(v, self.eff_end(track, cell) - 0.01)
        else:
            tr.step_end[cell] = max(v, self.eff_start(track, cell) + 0.01)
        return (self.eff_start(track, cell), self.eff_end(track, cell))

    def eff_filter(self, track: int, cell: int) -> tuple:
        """The filter this step will play through: its own lock, else the track's."""
        tr = self.tracks[track]
        v = tr.step_filt[cell]
        if v is None:
            return (tr.filt_cutoff, tr.filt_res, tr.filt_type)
        return (float(v[0]), float(v[1]), int(v[2]))

    def set_step_filter(self, track: int, cell: int, cutoff=None, res=None, ftype=None) -> tuple:
        """Lock the filter for ONE step. The first touch seeds the lock from the track, so
        turning a knob nudges what you are already hearing rather than jumping."""
        cut, rs, ty = self.eff_filter(track, cell)
        if cutoff is not None:
            cut = max(20.0, min(19000.0, float(cutoff)))
        if res is not None:
            rs = max(0.0, min(1.0, float(res)))
        if ftype is not None:
            ty = 1 if int(ftype) else 0
        self.tracks[track].step_filt[cell] = [cut, rs, ty]
        return (cut, rs, ty)

    def set_filter(self, track: int, cutoff: float | None = None,
                   res: float | None = None, ftype: int | None = None) -> tuple:
        tr = self.tracks[track]
        if cutoff is not None:
            tr.filt_cutoff = max(20.0, min(19000.0, float(cutoff)))
        if res is not None:
            tr.filt_res = max(0.0, min(1.0, float(res)))
        if ftype is not None:
            tr.filt_type = 1 if int(ftype) else 0
        return (tr.filt_cutoff, tr.filt_res, tr.filt_type)

    def set_step_cycle(self, track: int, cell: int, every: int) -> int:
        """How often this step may fire, in pattern repetitions (1 = every cycle, 8 = max)."""
        n = max(1, min(8, int(every)))
        self.tracks[track].step_cycle[cell] = n
        return n

    def set_length(self, track: int, length: int) -> int:
        self.tracks[track].length = max(1, min(MAX_STEPS, int(length)))
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
