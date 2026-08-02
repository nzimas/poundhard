"""MODULATION — a bank of 32 tempo-synced LFOs, assigned automatically.

WHY IT CAN BE NON-DESTRUCTIVE. `/ph/param` writes the engine's `~pstore[t][sym]` (the default
for future strikes) AND sets the value on any currently-ringing voice. It does not touch the
controller's Project at all. So an LFO can drive a parameter continuously without any of it
being stored: nothing is written to `tr.params`, nothing is saved, and switching the LFO off
re-sends the programmed value once and the parameter is exactly as it was. That is the whole
reason the modulation lives here rather than in the engine.

TEMPO SYNC BY CONSTRUCTION. An LFO's rate is a number of cycles per BAR, drawn from musical
divisions, and its phase is computed from the sequencer's bar position rather than from wall
clock. Change the tempo and every LFO follows, because there is no free-running oscillator
anywhere in it — `phase = bars * cycles_per_bar`, and that is the only clock.

PITCH IS EXCLUDED, deliberately and by name. Sweeping engine pitch continuously produces the
laser-gun effect that has nothing to do with this instrument; pitch belongs to the sequencer
and the scale. Filter cutoff, resonator brightness and vibrato RATE are not pitch and are
allowed — the exclusion is of parameters that transpose the voice, not of everything with a
frequency in it.
"""
from __future__ import annotations

import math
import random

from . import catalog

N_LFO = 32
N_SH = 16                    # pads 1-16: sample-and-hold; 17-32: sine

# --------------------------------------------------------------------------- #
# TEMPO DIVISIONS — cycles per BAR. Everything is a musical relationship to the bar, so
# there is no free-running rate anywhere and a tempo change carries the whole bank with it.
# --------------------------------------------------------------------------- #
DIVISIONS = [
    ("8 bars", 0.125), ("4 bars", 0.25), ("2 bars", 0.5), ("bar", 1.0),
    ("1/2", 2.0), ("1/2.", 1.5), ("1/2T", 3.0),
    ("1/4", 4.0), ("1/4.", 3.0), ("1/4T", 6.0),
    ("1/8", 8.0), ("1/8.", 6.0), ("1/8T", 12.0),
    ("1/16", 16.0),
]
# Slow movement is what "evolving" means; the fast divisions are the seasoning. Sine LFOs
# lean slower still, since a fast sine on a timbral parameter is a tremolo, not a movement.
_SLOW = [d for d in DIVISIONS if d[1] <= 2.0]
_FAST = [d for d in DIVISIONS if d[1] > 2.0]

# --------------------------------------------------------------------------- #
# PITCH EXCLUSION. Matched on the parameter's SUFFIX, so it holds for every engine at once.
# These transpose the voice; a continuous sweep of any of them is the laser gun.
# NOT excluded, and deliberately: cutoff / filtFreq / ffreqNN (filter, not pitch), lfoRate /
# modRate / pwmfreq / vibratofreq (rates, not pitch), ratio / fmNRatio (FM ratio is the
# timbre of an FM voice — sweeping it is inharmonic movement, which is the house style),
# pitchDecay (a drum's pitch-envelope TIME, which is a percussion timbre control).
# --------------------------------------------------------------------------- #
_PITCH = {"detune", "detuning", "subpitch", "suboct", "transpose2", "portamento",
          "pitchMod", "freq01", "freq02", "freq03", "freq04", "freq2"}

# Parameters worth modulating, in rough order of how much they repay it. Anything not listed
# is still eligible, just ranked below these — the list is a preference, not a whitelist.
_PRIZE = {
    "cutoff": 10, "filtFreq": 10, "res": 8, "resonance": 8, "q": 7,
    "timbre": 10, "morph": 10, "harm": 9, "harmonics": 9, "struct": 9,
    "index": 9, "fmAmt": 9, "fmDepth": 9, "fold": 9, "waveFolds": 9,
    "drive": 8, "crush": 8, "grit": 8, "destruction": 8, "downsample": 8,
    "tone": 8, "bright": 8, "damp": 7, "tension": 7, "pos": 8, "pos1": 7, "pos2": 7,
    "feedback": 8, "fb": 8, "chaosA": 8, "chaosB": 8, "rungler1": 7, "rungler2": 7,
    "noiseAmt": 6, "noiseLevel": 6, "sublevel": 6, "subLevel": 6, "oscmix": 7,
    "balance": 6, "tilt": 7, "energy": 7, "pressure": 7, "excite": 7,
    "decay": 5, "release": 5, "dec": 5, "sustain": 4,
    "pan": 6, "amp": 3,               # useful, but shallow — see _DEPTH
}
# How far an LFO is allowed to swing a parameter, as a fraction of its musical range.
# Amp and pan are held down hard: a deep amp LFO is a gate, not a modulation, and a deep pan
# LFO makes the whole mix seasick.
_DEPTH = {"amp": (0.10, 0.22), "pan": (0.15, 0.40)}
_DEPTH_DEFAULT = (0.22, 0.60)

FX_NAMES = ["OD", "AMP", "CRSH", "RING", "CLDS", "RESO", "GREY", "VERB"]


class Target:
    """One modulation destination: what to move, its range, and its programmed value."""

    __slots__ = ("kind", "track", "pid", "label", "lo", "hi", "base", "prize")

    def __init__(self, kind, track, pid, label, lo, hi, base, prize):
        self.kind = kind          # "voice" | "fxmacro" | "fxwet" | "filter"
        self.track = track
        self.pid = pid
        self.label = label
        self.lo, self.hi = float(lo), float(hi)
        self.base = float(base)
        self.prize = prize

    def key(self):
        return (self.kind, self.track, self.pid)


def _suffix(pid: str) -> str:
    return pid.split(".", 1)[1] if "." in pid else pid


def discover(project) -> list[Target]:
    """Every parameter in the CURRENT project that is worth and safe to modulate.

    This is the "analyse before generating" step: only live tracks contribute, only
    parameters the catalog marks modulatable are considered, pitch is removed by name, and
    each target carries the value the project has programmed for it so the LFO can swing
    AROUND that rather than replacing it.
    """
    out: list[Target] = []
    for t, tr in enumerate(project.tracks):
        if tr.type == "EMPTY":
            continue
        # A muted track or one with no hits is not "the current musical context" — modulating
        # it moves something nobody can hear and wastes one of the 32 pads.
        if getattr(tr, "muted", False):
            continue
        if not any(tr.pattern[:max(1, tr.length)]):
            continue
        spec = catalog.VOICES.get(tr.type)
        if spec is None:
            continue
        for p in spec.params:
            if not p.modulatable:
                continue
            suf = _suffix(p.id)
            if suf in _PITCH:
                continue
            lo, hi = (p.musical if getattr(p, "musical", None) else (p.rmin, p.rmax))
            if hi <= lo:
                continue
            base = float(tr.params.get(p.id, getattr(p, "default", (lo + hi) / 2)))
            out.append(Target("voice", t, p.id, "T%d %s" % (t + 1, suf[:8]),
                              lo, hi, base, _PRIZE.get(suf, 4)))
        # the per-track filter is a mixer-side control, not an engine parameter
        out.append(Target("filter", t, "cutoff", "T%d fcut" % (t + 1),
                          200.0, 16000.0, float(getattr(tr, "filt_cutoff", 18000.0)), 10))
        out.append(Target("filter", t, "res", "T%d fres" % (t + 1),
                          0.0, 0.9, float(getattr(tr, "filt_res", 0.0)), 7))

    # effects: only the ones actually assigned to a track, or they modulate nothing
    live_fx = sorted({f for row in getattr(project, "track_fx", []) for f in row})
    for f in live_fx:
        nm = FX_NAMES[f] if f < len(FX_NAMES) else str(f)
        out.append(Target("fxmacro", -1, f, "%s mac" % nm, 0.0, 1.0,
                          float(project.fx_macro[f]), 9))
        out.append(Target("fxwet", -1, f, "%s wet" % nm, 0.0, 1.0,
                          float(project.fx_wet[f]), 8))
    return out


class Lfo:
    """One assigned LFO. Off until the pad is pressed; never writes to the project."""

    __slots__ = ("slot", "shape", "target", "div", "div_name", "depth", "phase",
                 "offset", "on", "_last", "_seed")

    def __init__(self, slot, shape, target, div, div_name, depth, phase, offset, seed):
        self.slot = slot
        self.shape = shape                 # "sh" | "sine"
        self.target = target
        self.div = div
        self.div_name = div_name
        self.depth = depth
        self.phase = phase
        self.offset = offset
        self.on = False
        self._last = None
        self._seed = seed

    # -- the waveform ------------------------------------------------------ #
    def wave(self, bars: float) -> float:
        """-1..1 at this bar position. Nothing here free-runs: `bars` IS the clock."""
        ph = bars * self.div + self.phase
        if self.shape == "sine":
            return math.sin(2.0 * math.pi * ph)
        # SAMPLE AND HOLD: one new random level per division step, held until the next.
        # Derived from the step INDEX rather than drawn as we go, so the same bar always
        # gives the same value — the modulation is repeatable, and a stopped-and-restarted
        # sequencer does not resynthesise a different performance.
        step = math.floor(ph)
        r = random.Random((self._seed << 20) ^ (step & 0xFFFFF))
        return r.uniform(-1.0, 1.0)

    def value(self, bars: float) -> float:
        tg = self.target
        span = (tg.hi - tg.lo) * self.depth * 0.5
        v = tg.base + self.offset * span + self.wave(bars) * span
        return max(tg.lo, min(tg.hi, v))

    def label(self) -> str:
        return "%s %s %s" % ("S/H" if self.shape == "sh" else "SIN",
                             self.target.label, self.div_name)


def _depth_for(pid: str, rng: random.Random) -> float:
    lo, hi = _DEPTH.get(_suffix(pid), _DEPTH_DEFAULT)
    return round(rng.uniform(lo, hi), 3)


def assign(project, rng: random.Random | None = None) -> list[Lfo | None]:
    """Generate the whole bank against the current project.

    UNIQUENESS IS STRUCTURAL: targets are popped from a pool, so no two LFOs can ever share a
    destination. If the project offers fewer than 32 usable targets the remaining slots stay
    None and their pads stay dark — duplicating an assignment to fill the grid would mean two
    LFOs fighting over one parameter, which is worse than an empty pad.
    """
    rng = rng or random.Random()
    pool = discover(project)
    if not pool:
        return [None] * N_LFO

    # Rank by how much a parameter repays modulation, then SPREAD ACROSS TRACKS: taking the
    # top 32 outright would put six LFOs on whichever track happens to have the most knobs.
    rng.shuffle(pool)
    pool.sort(key=lambda t: -t.prize)
    by_track: dict[int, list[Target]] = {}
    for t in pool:
        by_track.setdefault(t.track, []).append(t)
    ordered: list[Target] = []
    while any(by_track.values()):
        for k in sorted(by_track):
            if by_track[k]:
                ordered.append(by_track[k].pop(0))

    bank: list[Lfo | None] = []
    for slot in range(N_LFO):
        if not ordered:
            bank.append(None)
            continue
        tg = ordered.pop(0)
        shape = "sh" if slot < N_SH else "sine"
        # Sample-and-hold wants steps you can hear as events; a sine wants to be a slow
        # swell. Weighting the pools differently is most of what makes the two halves of
        # the grid feel like different instruments rather than two shapes of the same one.
        if shape == "sh":
            div_name, div = rng.choice(_SLOW + _FAST)
        else:
            div_name, div = rng.choice(_SLOW + _SLOW + _FAST)
        bank.append(Lfo(slot, shape, tg, div, div_name,
                        _depth_for(tg.pid if isinstance(tg.pid, str) else "amp", rng),
                        round(rng.random(), 3),
                        round(rng.uniform(-0.35, 0.35), 3),
                        rng.randrange(1 << 20)))
    return bank


class Bank:
    """The live bank: assignment, toggling, and the per-tick output."""

    # Only send when the value has actually moved: a slow sine on a filter cutoff changes by
    # a fraction of a hertz between ticks, and sending that is pure traffic. The deadband is
    # a fraction of each target's own range, so it means the same thing for a 0..1 morph and
    # a 200..16000 cutoff.
    DEADBAND = 0.004

    def __init__(self):
        self.bank: list[Lfo | None] = [None] * N_LFO
        self.bars = 0.0
        self.dirty = False

    def regenerate(self, project, rng=None) -> int:
        keep = {i: l.on for i, l in enumerate(self.bank) if l is not None}
        self.bank = assign(project, rng)
        # A regeneration should not silently switch things on: everything comes up off, and
        # the pads the user had lit stay lit only if that slot still has a target.
        for i, on in keep.items():
            if self.bank[i] is not None:
                self.bank[i].on = on
        self.dirty = True
        return sum(1 for l in self.bank if l is not None)

    def toggle(self, slot: int, project, bridge) -> bool:
        if not (0 <= slot < N_LFO) or self.bank[slot] is None:
            return False
        l = self.bank[slot]
        l.on = not l.on
        if not l.on:
            self._restore(l, project, bridge)
        self.dirty = True
        return l.on

    def all_off(self, project, bridge) -> None:
        for l in self.bank:
            if l is not None and l.on:
                l.on = False
                self._restore(l, project, bridge)
        self.dirty = True

    def active(self) -> int:
        return sum(1 for l in self.bank if l is not None and l.on)

    # -- output ------------------------------------------------------------ #
    def tick(self, bars: float, project, bridge) -> int:
        """Advance to bar position `bars` and push whatever moved. Returns messages sent."""
        self.bars = bars
        sent = 0
        for l in self.bank:
            if l is None or not l.on:
                continue
            v = l.value(bars)
            span = max(1e-9, l.target.hi - l.target.lo)
            if l._last is not None and abs(v - l._last) < span * self.DEADBAND:
                continue
            l._last = v
            self._emit(l.target, v, project, bridge)
            sent += 1
        return sent

    def _emit(self, tg: Target, v: float, project, bridge) -> None:
        """Send the modulated value WITHOUT storing it anywhere."""
        if tg.kind == "voice":
            bridge.param(tg.track, tg.pid, v)
        elif tg.kind == "filter":
            tr = project.tracks[tg.track]
            if tg.pid == "cutoff":
                bridge.filter(tg.track, v, tr.filt_res, tr.filt_type)
            else:
                bridge.filter(tg.track, tr.filt_cutoff, v, tr.filt_type)
        elif tg.kind == "fxmacro":
            # computed through the project's own mapping at an OVERRIDDEN position, so the
            # stored fx_macro is untouched
            for arg, val in project.macro_values(tg.pid, pos=v):
                bridge.fxset(tg.pid, arg, val)
        elif tg.kind == "fxwet":
            bridge.fxset(tg.pid, "wet", v)

    def _restore(self, l: Lfo, project, bridge) -> None:
        """Put the parameter back exactly as the project has it programmed."""
        l._last = None
        self._emit(l.target, l.target.base, project, bridge)

    def rebase(self, project) -> None:
        """Re-read the programmed values (after a pattern change, kit regen or edit), so an
        LFO swings around what the project NOW says rather than a stale centre."""
        for l in self.bank:
            if l is None:
                continue
            tg = l.target
            if tg.kind == "voice" and 0 <= tg.track < len(project.tracks):
                tr = project.tracks[tg.track]
                if tg.pid in tr.params:
                    tg.base = float(tr.params[tg.pid])
            elif tg.kind == "filter" and 0 <= tg.track < len(project.tracks):
                tr = project.tracks[tg.track]
                tg.base = float(tr.filt_cutoff if tg.pid == "cutoff" else tr.filt_res)
            elif tg.kind == "fxmacro":
                tg.base = float(project.fx_macro[tg.pid])
            elif tg.kind == "fxwet":
                tg.base = float(project.fx_wet[tg.pid])

    def status(self) -> list[int]:
        """Per-pad state for the UI: 0 = no target, 1 = assigned, 2 = active."""
        return [0 if l is None else (2 if l.on else 1) for l in self.bank]

    def labels(self) -> list[str]:
        return ["" if l is None else l.label() for l in self.bank]
