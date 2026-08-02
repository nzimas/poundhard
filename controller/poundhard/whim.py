"""WHIM — the autonomous trickster.

The other modifiers each do ONE thing. Whim runs several small processes at once and lets
them interfere: tracks breathe in and out of time, hesitate, surge, drop out for a sixteenth,
fire off a burst, and change colour — then settle back. The point is not disorder. It is that
the pattern stops sounding mechanical while staying recognisably itself.

WHAT MAKES IT CONTROLLED RATHER THAN CHAOTIC:

  * RATE MODULATION IS ZERO-MEAN. Rate is scaled by a sine or triangle whose average over a
    cycle is exactly 1.0, so a track wanders ahead and behind the grid and comes back. A
    sample-and-hold rate would drift monotonically and never return — which is why S/H is
    used for TIMBRE here and never for time.
  * EVERY RATE IS A DIVISION OF THE BAR. Nothing free-runs; phase comes from the bar
    position, so a tempo change carries the whole modifier with it.
  * GESTURES ARE BUDGETED. At most a couple of tracks are doing something disruptive in any
    one bar, and the pulse track — whatever is carrying the beat — is protected: it is
    eligible far less often, and never for a stop and a burst at once.
  * IT READS THE ROOM. Density, phrase position, how many other modifiers are already
    running, and which track is the pulse all scale the intensity down.

NON-DESTRUCTIVE. Nothing here writes to the Project. Rate, filter and parameter changes go
straight to the engine, and every one is remembered so switching Whim off restores the
programmed value exactly — the same contract the LFO bank uses.
"""
from __future__ import annotations

import math
import random

# Cycles per BAR. Same vocabulary as the modulation bank: musical divisions only.
DIVISIONS = [("4 bars", 0.25), ("2 bars", 0.5), ("bar", 1.0), ("1/2", 2.0),
             ("1/2.", 1.5), ("1/2T", 3.0), ("1/4", 4.0), ("1/4.", 3.0), ("1/4T", 6.0),
             ("1/8", 8.0)]
_SLOW = [d for d in DIVISIONS if d[1] <= 2.0]

# Rate modulation depth. Deliberately moderate: past about a quarter the pattern stops being
# the pattern and becomes a tape-warp effect, which is a different modifier.
RATE_DEPTH = (0.06, 0.22)
# Filter movement, in octaves around the programmed cutoff.
CUT_OCTAVES = (0.4, 1.8)

GESTURES = ("slow", "surge", "stop", "burst", "colour")


def _tri(ph: float) -> float:
    """Triangle, -1..1. Zero mean, like the sine — safe for time."""
    x = (ph + 0.25) % 1.0
    return 4.0 * abs(x - 0.5) - 1.0


def _smooth(seed: int, ph: float) -> float:
    """Random-smooth: cosine-interpolated between per-step random levels. Zero mean only on
    average, so this is used for TIMBRE, never for rate."""
    i = math.floor(ph)
    f = ph - i
    a = random.Random((seed << 20) ^ (i & 0xFFFFF)).uniform(-1, 1)
    b = random.Random((seed << 20) ^ ((i + 1) & 0xFFFFF)).uniform(-1, 1)
    m = (1.0 - math.cos(f * math.pi)) * 0.5
    return a + (b - a) * m


def _sh(seed: int, ph: float) -> float:
    return random.Random((seed << 20) ^ (math.floor(ph) & 0xFFFFF)).uniform(-1, 1)


def wave(shape: str, seed: int, ph: float) -> float:
    if shape == "sine":
        return math.sin(2.0 * math.pi * ph)
    if shape == "tri":
        return _tri(ph)
    if shape == "smooth":
        return _smooth(seed, ph)
    return _sh(seed, ph)


class TrackWhim:
    """One track's continuous modulation, plus whatever gesture it is currently running."""

    __slots__ = ("track", "rate_shape", "rate_div", "rate_depth", "rate_seed",
                 "cut_shape", "cut_div", "cut_oct", "cut_seed", "res_add",
                 "gesture", "g_until", "g_from", "muted", "burst_cells")

    def __init__(self, track: int, rng: random.Random, gentle: bool):
        self.track = track
        # TIME gets zero-mean shapes only, so a track always comes back to the grid.
        self.rate_shape = rng.choice(("sine", "sine", "tri"))
        self.rate_div = rng.choice(_SLOW)[1]
        lo, hi = RATE_DEPTH
        self.rate_depth = rng.uniform(lo, hi * (0.5 if gentle else 1.0))
        self.rate_seed = rng.randrange(1 << 20)
        # TIMBRE may step and lurch — that is the mischief.
        self.cut_shape = rng.choice(("sine", "tri", "smooth", "smooth", "sh"))
        self.cut_div = rng.choice(DIVISIONS)[1]
        clo, chi = CUT_OCTAVES
        self.cut_oct = rng.uniform(clo, chi * (0.5 if gentle else 1.0))
        self.cut_seed = rng.randrange(1 << 20)
        self.res_add = rng.uniform(0.0, 0.22 if not gentle else 0.1)
        self.gesture = None
        self.g_until = 0.0
        self.g_from = 0.0
        self.muted = False
        self.burst_cells: list[int] = []

    # -- continuous ------------------------------------------------------- #
    def rate_mul(self, bars: float) -> float:
        """Multiplier on the track's programmed rate. Averages to 1.0 over a cycle."""
        w = wave(self.rate_shape, self.rate_seed, bars * self.rate_div)
        m = 1.0 + self.rate_depth * w
        if self.gesture in ("slow", "surge") and bars < self.g_until:
            # A FULL sine over the gesture, not a half one. A half-sine is always the same
            # sign, so a slowdown steals phase the track never gets back and it ends up
            # permanently behind the grid — after a few gestures it is nowhere near the
            # pattern. A full cycle integrates to zero: the track hesitates, then runs on by
            # exactly the amount it lost, and lands back where it belongs. That IS the
            # "settles back into synchronisation" behaviour, and it is arithmetic rather
            # than hope.
            span = max(1e-6, self.g_until - self.g_from)
            k = max(0.0, min(1.0, (bars - self.g_from) / span))
            env = math.sin(2.0 * math.pi * k)                     # 0 -> +1 -> 0 -> -1 -> 0
            m *= 1.0 + (-0.30 if self.gesture == "slow" else 0.38) * env
        return max(0.15, min(4.0, m))

    def cutoff_mul(self, bars: float) -> float:
        w = wave(self.cut_shape, self.cut_seed, bars * self.cut_div)
        return 2.0 ** (self.cut_oct * w)


class Whim:
    """The modifier. `bar()` decides gestures; `tick()` produces continuous values."""

    def __init__(self, n_tracks: int, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.n = n_tracks
        self.state: dict[int, TrackWhim] = {}
        self.bars = 0
        self.intensity = 0.6
        self.last_log = ""

    # -- per bar ----------------------------------------------------------- #
    def bar(self, live: list[int], pulse: int, density: float, busy_mods: int,
            seam: float) -> dict:
        """Decide this bar's gestures.

        `density` is onsets per step across the pattern, `busy_mods` is how many OTHER
        modifiers are running, `seam` is how good a phrase boundary this is (0..1). All three
        pull the intensity DOWN — the trickster gets quieter as the music gets busier, which
        is what stops Whim plus Quake plus Strobe turning into noise.
        """
        self.bars += 1
        rng = self.rng
        crowd = min(1.0, density / 0.45)
        self.intensity = max(0.15, 0.9 - 0.35 * crowd - 0.18 * busy_mods)
        gentle = self.intensity < 0.45

        for t in live:
            if t not in self.state:
                self.state[t] = TrackWhim(t, rng, gentle or t == pulse)
        for t in list(self.state):
            if t not in live:
                del self.state[t]

        # expire finished gestures
        for w in self.state.values():
            if w.gesture and self.bars >= w.g_until:
                w.gesture = None
                w.burst_cells = []

        # GESTURE BUDGET: at most two disruptive things at once, fewer when it is already
        # busy. A pattern where every track is doing something is not mischief, it is mud.
        running = sum(1 for w in self.state.values() if w.gesture)
        budget = max(0, (2 if self.intensity > 0.5 else 1) - running)
        # a good phrase boundary is where a bigger gesture belongs
        chance = 0.25 + 0.5 * seam * self.intensity
        picks = []
        cands = [t for t in live if self.state[t].gesture is None]
        rng.shuffle(cands)
        for t in cands:
            if budget <= 0 or rng.random() > chance:
                continue
            # THE PULSE IS PROTECTED. Stopping or bursting whatever carries the beat every
            # few bars stops being a surprise and becomes the arrangement.
            if t == pulse and rng.random() < 0.75:
                continue
            g = rng.choices(GESTURES, weights=(
                3, 3, 2 if t != pulse else 0.5, 2 if t != pulse else 0.5, 4))[0]
            w = self.state[t]
            w.gesture = g
            w.g_from = float(self.bars)
            w.g_until = float(self.bars) + (1 if g in ("stop", "burst") else rng.choice([1, 2]))
            picks.append((t, g))
            budget -= 1

        self.last_log = ("whim: intensity %.2f  %d/%d tracks moving  %s"
                         % (self.intensity, sum(1 for w in self.state.values() if w.gesture),
                            len(live), ", ".join("T%d:%s" % (t + 1, g) for t, g in picks) or "-"))
        return {t: g for t, g in picks}

    # -- continuous -------------------------------------------------------- #
    def rates(self, bars: float) -> dict[int, float]:
        return {t: w.rate_mul(bars) for t, w in self.state.items()}

    def cutoffs(self, bars: float) -> dict[int, tuple[float, float]]:
        return {t: (w.cutoff_mul(bars), w.res_add) for t, w in self.state.items()}
