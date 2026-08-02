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

# Rate modulation depth. The first pass sat at 0.06..0.22 and was too polite to hear over a
# busy pattern — the modifier was doing exactly what it claimed and nobody could tell. This
# is the level where a track audibly drags and pushes against the grid while the pattern is
# still recognisably the pattern.
RATE_DEPTH = (0.16, 0.42)
# Filter movement, in octaves around the programmed cutoff. Three octaves is a sweep you
# hear as an event rather than as drift.
CUT_OCTAVES = (1.0, 3.0)
# How hard the slow/surge gestures pull. These multiply ON TOP of the breathing, so the
# combined swing is checked in the tests rather than assumed.
G_SLOW, G_SURGE = -0.46, 0.58

# NO BURST. Ratchets and rapid repetitions belong to another modifier; Whim adds no note
# events at all. It expresses itself by reshaping the flow of time, not by filling it.
GESTURES = ("slow", "surge", "stop", "colour")


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


def _wobble(seed: int, ph: float) -> float:
    """A smooth, wandering curve that is EXACTLY zero-mean over its cycle.

    Genuine random-smooth interpolation is the obvious choice for "smooth random", and it is
    wrong here: its mean over any given cycle is not zero, so a track modulated by it gains
    or loses a little phase every cycle and walks away from the grid for good. Adding two
    quiet harmonics to the fundamental gives the same wandering, never-quite-repeating
    character — no two cycles feel alike because the harmonics sit at their own phases — while
    every component completes a whole number of cycles per period and therefore integrates to
    zero. Smoothness and elasticity without the drift.
    """
    r = random.Random(seed)
    p2, p3 = r.random(), r.random()
    return (0.62 * math.sin(2.0 * math.pi * ph)
            + 0.26 * math.sin(2.0 * math.pi * (2.0 * ph + p2))
            + 0.12 * math.sin(2.0 * math.pi * (3.0 * ph + p3)))


def wave(shape: str, seed: int, ph: float) -> float:
    if shape == "sine":
        return math.sin(2.0 * math.pi * ph)
    if shape == "tri":
        return _tri(ph)
    if shape == "smooth":
        return _smooth(seed, ph)
    if shape == "wobble":
        return _wobble(seed, ph)
    return _sh(seed, ph)


class TrackWhim:
    """One track's continuous modulation, plus whatever gesture it is currently running."""

    __slots__ = ("track", "rate_shape", "rate_div", "rate_depth", "rate_seed", "rate_phase",
                 "cut_shape", "cut_div", "cut_oct", "cut_seed", "res_add",
                 "gesture", "g_until", "g_from", "muted", "burst_cells")

    def __init__(self, track: int, rng: random.Random, gentle: bool):
        self.track = track
        # TIME gets zero-mean shapes only, so a track always comes back to the grid.
        # `wobble` is the smooth-random one — see _wobble for why it is not actual noise.
        self.rate_shape = rng.choice(("sine", "tri", "wobble", "wobble"))
        self.rate_div = rng.choice(_SLOW)[1]
        # ITS OWN PHASE. Without this every modulated track reaches its fastest point at the
        # same instant and the whole pattern surges together, which reads as one sloppy
        # tempo rather than several parts pulling against each other.
        self.rate_phase = rng.random()
        lo, hi = RATE_DEPTH
        self.rate_depth = rng.uniform(lo, hi * (0.7 if gentle else 1.0))
        self.rate_seed = rng.randrange(1 << 20)
        # TIMBRE may step and lurch — that is the mischief.
        self.cut_shape = rng.choice(("sine", "tri", "smooth", "smooth", "sh"))
        self.cut_div = rng.choice(DIVISIONS)[1]
        clo, chi = CUT_OCTAVES
        self.cut_oct = rng.uniform(clo, chi * (0.7 if gentle else 1.0))
        self.cut_seed = rng.randrange(1 << 20)
        self.res_add = rng.uniform(0.0, 0.30 if not gentle else 0.16)
        self.gesture = None
        self.g_until = 0.0
        self.g_from = 0.0
        self.muted = False
        self.burst_cells: list[int] = []

    def reroll_rate(self, rng: random.Random, gentle: bool) -> None:
        """New shape, division, phase and depth — called whenever this track is (re)selected
        for tempo modulation, so being picked twice does not mean the same wobble twice."""
        self.rate_shape = rng.choice(("sine", "tri", "wobble", "wobble"))
        self.rate_div = rng.choice(_SLOW)[1]
        self.rate_phase = rng.random()
        lo, hi = RATE_DEPTH
        self.rate_depth = rng.uniform(lo, hi * (0.7 if gentle else 1.0))
        self.rate_seed = rng.randrange(1 << 20)

    # -- continuous ------------------------------------------------------- #
    def rate_mul(self, bars: float) -> float:
        """Multiplier on the track's programmed rate. Averages to 1.0 over a cycle."""
        w = wave(self.rate_shape, self.rate_seed, bars * self.rate_div + self.rate_phase)
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
            m *= 1.0 + (G_SLOW if self.gesture == "slow" else G_SURGE) * env
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
        # WHICH TRACKS ARE BEING TEMPO-MODULATED. A subset, not everything: if every track
        # wobbles, nothing is wobbling AGAINST anything and the result reads as one unsteady
        # tempo. Holding some parts firm is what makes the modulated ones audible as elastic.
        self.rate_on: set[int] = set()
        self._reselect_at = 0

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
        # floor raised from 0.15: at the old floor Whim effectively switched itself off on a
        # dense pattern with other modifiers up, which is precisely when you had turned it on.
        self.intensity = max(0.35, 1.0 - 0.30 * crowd - 0.15 * busy_mods)
        gentle = self.intensity < 0.45

        for t in live:
            if t not in self.state:
                self.state[t] = TrackWhim(t, rng, gentle or t == pulse)
        for t in list(self.state):
            if t not in live:
                del self.state[t]

        # RE-SELECT the tempo-modulated subset every few bars, so the relationship between
        # what bends and what holds keeps changing over a long performance.
        if live and self.bars >= self._reselect_at:
            self._reselect_at = self.bars + rng.randint(4, 12)
            want = max(1, min(len(live), round(len(live) * rng.uniform(0.35, 0.7))))
            # the pulse is eligible but unlikely — bending the beat itself now and then is a
            # lovely effect, bending it constantly just sounds like a bad clock
            pool = [t for t in live for _ in range(1 if t == pulse else 3)]
            picked: set[int] = set()
            while pool and len(picked) < want:
                c = rng.choice(pool)
                picked.add(c)
                pool = [x for x in pool if x != c]
            self.rate_on = picked
            for t in picked:                      # a fresh curve each time it is selected
                self.state[t].reroll_rate(rng, gentle or t == pulse)
        self.rate_on &= set(live)

        # expire finished gestures
        for w in self.state.values():
            if w.gesture and self.bars >= w.g_until:
                w.gesture = None
                w.burst_cells = []

        # GESTURE BUDGET: at most two disruptive things at once, fewer when it is already
        # busy. A pattern where every track is doing something is not mischief, it is mud.
        running = sum(1 for w in self.state.values() if w.gesture)
        budget = max(0, (3 if self.intensity > 0.5 else 2) - running)
        # a good phrase boundary is where a bigger gesture belongs
        chance = 0.45 + 0.45 * seam * self.intensity
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
            # slow and surge are weighted highest: they ARE the tempo modulation, taken to
            # gesture scale, and Whim's defining feature is temporal rather than timbral.
            g = rng.choices(GESTURES, weights=(
                5, 5, 1.5 if t != pulse else 0.4, 3))[0]
            w = self.state[t]
            w.gesture = g
            w.g_from = float(self.bars)
            w.g_until = float(self.bars) + (1 if g in ("stop", "burst") else rng.choice([1, 2]))
            picks.append((t, g))
            budget -= 1

        self.last_log = ("whim: intensity %.2f  wobble on %d/%d  %d gesturing  %s"
                         % (self.intensity, len(self.rate_on), len(live),
                            sum(1 for w in self.state.values() if w.gesture),
                            ", ".join("T%d:%s" % (t + 1, g) for t, g in picks) or "-"))
        return {t: g for t, g in picks}

    # -- continuous -------------------------------------------------------- #
    def rates(self, bars: float) -> dict[int, float]:
        """Only the SELECTED tracks are tempo-modulated. A track running a slow/surge gesture
        is included regardless — the gesture is a temporal one and has to be heard."""
        return {t: w.rate_mul(bars) for t, w in self.state.items()
                if t in self.rate_on or w.gesture in ("slow", "surge")}

    def cutoffs(self, bars: float) -> dict[int, tuple[float, float]]:
        return {t: (w.cutoff_mul(bars), w.res_add) for t, w in self.state.items()}
