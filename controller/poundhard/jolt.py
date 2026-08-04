"""JOLT — procedural breakbeat.

A break is a recording of a whole number of beats at a known tempo, and this library states
both in every filename (`amen_de0afe48_beats8_bpm170.flac`). The audio matches exactly — a
4-beat/160 bpm file measures 1.500 s, which is 4 * 60/160 to the millisecond. That single
fact is what makes the engine possible:

    TEMPO SYNC IS ARITHMETIC, NOT ANALYSIS. Play the break at patternBpm/breakBpm and it
    lands on the grid — a fast break in a slow bar plays SLOWER, not faster. Plain resampling, so there are no time-stretch artefacts, and every
    slice is TRIGGERED by the sequencer rather than free-running from a loop point, so
    nothing can drift however violently the pattern is rearranged.

WHAT A BREAK PROGRAM IS. Sixteen steps, each holding a slice index and how to play it —
rate, reverse, gate length, and how much glitch. Rearranging WHICH slice a step plays is the
whole of breakcore editing; everything else is seasoning on top.

THE EIGHT LEVELS are a real progression, not eight presets. Each named probability rises (or
its counterpart falls) monotonically across them, and the test asserts it. Level 1 is the
break nearly as recorded with the odd substitution; level 8 rearranges almost every step,
stutters, reverses, drops beats out and glitches what is left.

The per-break `.json` beside each file is the reference project's own analysis: one loudness
value per slice, in dB. Slices near -86 dB are silence and the loud ones are where the hits
are. It is used here to keep the downbeat honest — a rearrangement that never lands a strong
slice on beat one stops sounding like a break and starts sounding like a malfunction.
"""
from __future__ import annotations

import json
import os
import random
import re

BREAKS_DIR = os.environ.get(
    "PH_BREAKS_DIR", "/data/UserData/poundhard/breaks/amenbreak")

STEPS = 16                    # a Jolt program is one bar of sixteenths
_NAME = re.compile(r"beats(\d+)_bpm(\d+)")


class Break:
    """One break file: where it is, how long it is, and where its hits fall."""

    __slots__ = ("path", "name", "beats", "bpm", "slices", "energy")

    def __init__(self, path: str, beats: int, bpm: int, energy: list):
        self.path = path
        self.name = os.path.basename(path)
        self.beats = beats
        self.bpm = bpm
        # the library analyses two slices per beat; Jolt subdivides to sixteenths
        self.slices = max(1, beats * 4)
        self.energy = energy or []

    def strong(self) -> list:
        """Slice indices that actually carry a hit, loudest first.

        The analysis is per EIGHTH; a sixteenth-resolution program maps two of its slices
        onto each analysed value, so a strong eighth marks both of its halves as candidates.
        """
        if not self.energy:
            return list(range(0, self.slices, 4))
        pairs = sorted(range(len(self.energy)), key=lambda i: -self.energy[i])
        keep = [i for i in pairs if self.energy[i] > -40.0] or pairs[:4]
        out = []
        for i in keep:
            out += [i * 2, i * 2 + 1]
        return [s for s in out if s < self.slices]

    def stretch_for(self, tempo: float) -> float:
        """Playback rate that makes this break fit the pattern's tempo exactly.

        tempo/bpm, NOT bpm/tempo. A 170 bpm break dropped into a 90 bpm bar has to play
        SLOWER — rate 0.53 — because the bar it must fill is longer. Getting this the wrong
        way round inverts every break in the library and nothing lines up at any tempo except
        the one the break was recorded at.
        """
        return max(0.05, float(tempo)) / max(20.0, float(self.bpm))


def scan(directory: str | None = None) -> list:
    """Index the break library. Missing directory is not an error — it means the library
    has not been fetched yet (move/fetch-breaks.sh), and the engine reports that plainly
    rather than half-working."""
    d = directory or BREAKS_DIR
    out = []
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".flac") and not fn.endswith(".wav"):
            continue
        m = _NAME.search(fn)
        if not m:
            continue
        beats, bpm = int(m.group(1)), int(m.group(2))
        if beats < 2 or bpm < 40:
            continue
        energy = []
        try:
            with open(os.path.join(d, fn + ".json")) as f:
                v = json.load(f)
            if isinstance(v, list):
                energy = [float(x) for x in v]
        except (OSError, ValueError):
            pass
        out.append(Break(os.path.join(d, fn), beats, bpm, energy))
    return out


# --------------------------------------------------------------------------- #
# THE EIGHT LEVELS. Every field moves monotonically across them — that is what makes this a
# continuum the performer can navigate rather than eight unrelated buttons.
#
#   move     chance a step plays a slice other than its own (rearrangement)
#   stutter  chance a step repeats a slice from the step before it (rolls)
#   rev      chance a slice plays backwards
#   drop     chance a step is silent (the holes that make a break breathe)
#   halftime chance a step plays at half rate (the classic drop into slow motion)
#   glitch   how much bitcrush / decimation
#   gate     how short the slices are cut — lower is choppier
#   fills    chance the last quarter of the bar becomes a fill
# --------------------------------------------------------------------------- #
LEVELS = [
    {"name": "STRAIGHT", "move": 0.06, "stutter": 0.02, "rev": 0.0,  "drop": 0.03,
     "halftime": 0.0,  "glitch": 0.0,  "gate": 1.0,  "fills": 0.05},
    {"name": "NUDGE",    "move": 0.14, "stutter": 0.05, "rev": 0.01, "drop": 0.05,
     "halftime": 0.01, "glitch": 0.03, "gate": 0.98, "fills": 0.12},
    {"name": "CHOP",     "move": 0.26, "stutter": 0.10, "rev": 0.03, "drop": 0.08,
     "halftime": 0.03, "glitch": 0.06, "gate": 0.92, "fills": 0.22},
    {"name": "ROLL",     "move": 0.38, "stutter": 0.20, "rev": 0.06, "drop": 0.11,
     "halftime": 0.05, "glitch": 0.10, "gate": 0.85, "fills": 0.34},
    {"name": "FRACTURE", "move": 0.50, "stutter": 0.30, "rev": 0.10, "drop": 0.14,
     "halftime": 0.08, "glitch": 0.16, "gate": 0.76, "fills": 0.46},
    {"name": "MANGLE",   "move": 0.62, "stutter": 0.40, "rev": 0.15, "drop": 0.17,
     "halftime": 0.11, "glitch": 0.24, "gate": 0.66, "fills": 0.58},
    {"name": "SHRED",    "move": 0.74, "stutter": 0.52, "rev": 0.21, "drop": 0.20,
     "halftime": 0.14, "glitch": 0.34, "gate": 0.55, "fills": 0.70},
    {"name": "RUPTURE",  "move": 0.86, "stutter": 0.66, "rev": 0.28, "drop": 0.23,
     "halftime": 0.18, "glitch": 0.46, "gate": 0.44, "fills": 0.82},
]
N_LEVELS = len(LEVELS)


class Step:
    """One sixteenth of a break program."""

    __slots__ = ("slice", "rate", "rev", "gate", "crush", "decim", "vel", "on")

    def __init__(self, slice_=0, rate=1.0, rev=0, gate=1.0, crush=0.0, decim=0.0, vel=1.0,
                 on=True):
        self.slice = slice_
        self.rate = rate
        self.rev = rev
        self.gate = gate
        self.crush = crush
        self.decim = decim
        self.vel = vel
        self.on = on

    def as_dict(self) -> dict:
        return {"s": self.slice, "r": round(self.rate, 4), "v": int(self.rev),
                "g": round(self.gate, 3), "c": round(self.crush, 3),
                "d": round(self.decim, 3), "a": round(self.vel, 3), "on": bool(self.on)}

    @staticmethod
    def from_dict(d: dict) -> "Step":
        return Step(int(d.get("s", 0)), float(d.get("r", 1.0)), int(d.get("v", 0)),
                    float(d.get("g", 1.0)), float(d.get("c", 0.0)), float(d.get("d", 0.0)),
                    float(d.get("a", 1.0)), bool(d.get("on", True)))


def generate(brk: Break, level: int, rng: random.Random | None = None) -> list:
    """A break program: sixteen steps of slice-and-how-to-play-it."""
    rng = rng or random.Random()
    L = LEVELS[max(0, min(N_LEVELS - 1, level))]
    n = brk.slices
    strong = brk.strong() or [0]
    prog = []

    for i in range(STEPS):
        # the straight reading: step i plays the slice that lives at step i
        base = int(i * n / STEPS) % n
        st = Step(base)

        # REARRANGEMENT — the heart of it. A moved step prefers a slice that actually has a
        # hit on it, because moving to a silent slice just makes a hole, and holes are what
        # `drop` is for.
        if rng.random() < L["move"]:
            st.slice = rng.choice(strong) if rng.random() < 0.7 else rng.randrange(n)

        # STUTTER — repeat the previous step's slice. This is what makes rolls.
        if i > 0 and rng.random() < L["stutter"]:
            st.slice = prog[-1].slice
            if rng.random() < 0.5:
                st.rate = rng.choice([1.0, 1.0, 2.0, 0.5])

        if rng.random() < L["rev"]:
            st.rev = 1
        if rng.random() < L["halftime"]:
            st.rate *= 0.5
        if rng.random() < L["drop"]:
            st.on = False

        g = L["gate"]
        st.gate = round(max(0.12, rng.uniform(g * 0.7, g * 1.15)), 3)
        if L["glitch"] > 0 and rng.random() < L["glitch"] * 1.6:
            st.crush = round(rng.uniform(0.2, 1.0) * L["glitch"], 3)
            st.decim = round(rng.uniform(0.0, 1.0) * L["glitch"], 3)
        st.vel = round(rng.uniform(0.82, 1.0) + (0.14 if i % 4 == 0 else 0.0), 3)
        prog.append(st)

    # FILLS — the last quarter of the bar rewritten as a burst. A fill that lands anywhere
    # else is just noise; at the end of the bar it reads as a turnaround.
    if rng.random() < L["fills"]:
        for i in range(STEPS - 4, STEPS):
            s = prog[i]
            s.on = True
            s.slice = rng.choice(strong)
            s.rate = rng.choice([1.0, 1.0, 2.0, 2.0, 4.0])
            s.gate = round(max(0.1, L["gate"] * rng.uniform(0.35, 0.7)), 3)
            if rng.random() < 0.4:
                s.rev = 1

    # THE DOWNBEAT IS NOT NEGOTIABLE. A rearrangement that never lands a hit on beat one
    # stops sounding like a break and starts sounding like a fault, however clever the rest
    # of the bar is. Step 0 always plays, always forwards, always from a slice with a hit.
    prog[0].on = True
    prog[0].rev = 0
    prog[0].rate = 1.0
    if prog[0].slice not in strong:
        prog[0].slice = strong[0]
    prog[0].gate = max(prog[0].gate, 0.6)
    return prog


def program_to_list(prog: list) -> list:
    return [s.as_dict() for s in prog]


def program_from_list(v: list) -> list:
    return [Step.from_dict(d) for d in (v or [])][:STEPS]


# --------------------------------------------------------------------------- #
# AUTOMATIC RECONSTRUCTION — excursions around a HOME level, never a free walk.
#
# The pad selected on row 1 is the BASE: the main loop, and the thing the ear holds onto. The
# automation leaves it for one or two cycles at a time and then comes back. It never chains
# variation into variation, because that is how a break stops having an identity — after four
# unrelated bars there is nothing left to be a variation OF.
#
#   base for N cycles -> a different level for 1 or 2 -> base again -> ...
#
# THE BASE PROGRAM IS KEPT, NOT REGENERATED. Coming home replays the exact program that was
# playing before the excursion, so "the main loop" really is one loop rather than a fresh roll
# at the same intensity every time. Only the excursions are newly generated.
# --------------------------------------------------------------------------- #
RATES = (1, 2, 3, 4, 5, 6, 7)     # pattern cycles at the base between excursions — pads 2..8

# How appealing a given distance from the base is for a temporary variation. Adjacent is a
# little dull for a fill, and the far end of the range is a shock rather than a contrast, so
# the weight peaks in the middle.
_CONTRAST = {1: 0.8, 2: 1.0, 3: 1.0, 4: 0.8, 5: 0.6, 6: 0.45, 7: 0.3}


class Excursion:
    """Decides when to leave the base level, where to go, and when to come home."""

    def __init__(self, base: int = 2, every: int = 2, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.base = max(0, min(N_LEVELS - 1, base))
        self.every = max(1, int(every))
        self.at_base = True
        self.count = 0
        self.away_left = 0
        self.last_away = -1

    def set_base(self, level: int) -> None:
        """The performer picked a row-1 pad. That is home from now on."""
        self.base = max(0, min(N_LEVELS - 1, level))
        self.at_base = True
        self.count = 0
        self.away_left = 0

    def pick(self) -> int:
        """Where to go for this excursion.

        Extreme levels are held back UNLESS the base is already complex — dropping RUPTURE
        into a STRAIGHT loop every other bar is not contrast, it is a different piece of
        music. When the base is itself near the top, the whole range is fair game.
        """
        rng = self.rng
        cands, weights = [], []
        for c in range(N_LEVELS):
            if c == self.base:
                continue
            w = _CONTRAST.get(abs(c - self.base), 0.3)
            if c >= 6:
                w *= 0.35 + 0.65 * (self.base / (N_LEVELS - 1))
            if c == self.last_away:
                w *= 0.35            # don't reach for the same variation twice running
            cands.append(c)
            weights.append(max(0.01, w))
        pick = rng.choices(cands, weights=weights)[0]
        self.last_away = pick
        return pick

    def tick(self):
        """One completed pattern cycle.

        Returns the level that should be playing NOW if it just changed, else None. A second
        value says whether that is the base (so the caller can restore the kept program
        rather than generate a new one).
        """
        if self.at_base:
            self.count += 1
            if self.count < self.every:
                return None, False
            self.count = 0
            self.at_base = False
            # one cycle usually, two when the excursion should read as a section rather than
            # a stumble
            self.away_left = 1 if self.rng.random() < 0.7 else 2
            return self.pick(), False
        self.away_left -= 1
        if self.away_left > 0:
            return None, False
        self.at_base = True
        return self.base, True
