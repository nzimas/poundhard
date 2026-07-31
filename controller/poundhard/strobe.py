"""STROBE — rhythmic gating and microlooping, redistributed every bar.

Two effects on the track buses, usable together or apart:

  GATE       rhythmic amplitude gating. `gDiv` gates per bar, `gDuty` of each one open,
             `gDepth` how far it shuts. Divisions are not restricted to powers of two —
             3, 5, 6 and 7 per bar are exactly as locked to the bar as 8 or 16, they just
             land somewhere more interesting.
  MICROLOOP  a slice of bar/`lDiv` seconds recirculated in the engine, so a fragment
             repeats. The slice length comes from the bar, so it is tempo-synced by
             construction rather than by being told a rate in seconds.

EVERYTHING IS A DIVISION OF THE BAR. The engine publishes one bar-phase signal and every
insert derives its own sub-phase from it, so a 3-per-bar gate on one track and a 1/16
microloop on another are locked to the bar and to each other, at audio rate, and follow a
tempo change without being rebuilt. Nothing here ever sends a rate in hertz.

WHAT MAKES IT AN ARRANGEMENT RATHER THAN A TREMOLO is that it is not applied uniformly:

  * TARGETING — a subset of tracks, re-chosen periodically. Sometimes everything, more
    often a handful. Tracks that carry the pattern get picked less often than the rest,
    because gating the kick every bar stops being an effect and starts being the beat.
  * DISTRIBUTION — each effect owns a WINDOW WITHIN THE BAR (`gFrom`/`gSpan`,
    `lFrom`/`lSpan`), so it can take the last quarter of the bar, or the middle eighth,
    rather than running end to end. Windows move independently per track, which is what
    stops sixteen gated tracks sounding like one gated mix.
  * DENSITY — how many tracks, how wide the windows, and how deep the effect all move
    together on a slow cycle, so it breathes instead of chattering at a constant rate.

NON-DESTRUCTIVE: the inserts live on the track buses and touch no pattern, parameter or
track state. Switching off frees them, and the tracks are exactly as they were.
"""
from __future__ import annotations

import random

# Gates or slices per bar. Deliberately not all powers of two: the odd divisions are what
# make it sound composed rather than switched on.
GATE_DIVS = (2, 3, 4, 5, 6, 8, 8, 12, 16, 16, 24, 32)
LOOP_DIVS = (2, 3, 4, 6, 8, 8, 12, 16, 16, 24, 32)

# Windows are quantised to sixteenths of a bar so an effect starts on a step boundary.
SIXTEENTH = 1.0 / 16.0


def _q(x: float) -> float:
    return round(x / SIXTEENTH) * SIXTEENTH


class TrackState:
    """What one track's insert is currently doing. Compared against, to avoid resending."""

    def __init__(self):
        self.args: dict[str, float] = {}

    def diff(self, new: dict) -> dict:
        out = {k: v for k, v in new.items() if self.args.get(k) != v}
        self.args.update(out)
        return out


class Strobe:
    """The performer. `bar()` is called once per pattern cycle and decides everything."""

    def __init__(self, n_tracks: int, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.n = n_tracks
        self.state = [TrackState() for _ in range(n_tracks)]
        self.targets: set[int] = set()
        self.bars = 0
        # the slow breathing cycle: density rises and falls over this many bars
        self.period = self.rng.randint(8, 24)
        self.density = 0.35
        self.mode = "both"
        self.last_log = ""

    # ------------------------------------------------------------------ targeting
    def _retarget(self, live: list[int], busy: set[int]) -> None:
        """Choose which tracks the effects sit on.

        Occasionally everything; usually a handful. `busy` are the tracks carrying the
        pattern — they are eligible but weighted down, because gating the kick every bar
        stops being an effect and becomes the beat.
        """
        if not live:
            self.targets = set()
            return
        r = self.rng.random()
        if r < 0.12:
            self.targets = set(live)                       # everything, occasionally
            return
        want = max(1, min(len(live), int(round(len(live) * self.density))))
        weights = [0.35 if t in busy else 1.0 for t in live]
        chosen: set[int] = set()
        pool = list(live)
        w = list(weights)
        while pool and len(chosen) < want:
            pick = self.rng.choices(range(len(pool)), weights=w, k=1)[0]
            chosen.add(pool.pop(pick))
            w.pop(pick)
        self.targets = chosen

    # ------------------------------------------------------------------ per-bar
    def bar(self, live: list[int], busy: set[int]) -> tuple[dict[int, dict], set[int], set[int]]:
        """One pattern cycle.

        Returns (per-track argument changes, tracks to switch on, tracks to switch off).
        """
        self.bars += 1
        # density breathes on a slow cycle rather than being redrawn every bar, so the
        # modifier has shape over time instead of a constant rate of incident
        phase = (self.bars % self.period) / self.period
        self.density = 0.15 + (0.55 * (1 - abs((phase * 2) - 1)))

        if self.bars % max(2, self.period // 3) == 1 or not self.targets:
            self._retarget(live, busy)
            self.mode = self.rng.choices(
                ("gate", "loop", "both"), weights=(4, 3, 3), k=1)[0]

        want = set(self.targets) & set(live)
        have = {t for t in range(self.n) if self.state[t].args}
        turn_on = want - have
        turn_off = have - want
        for t in turn_off:
            self.state[t].args.clear()

        changes: dict[int, dict] = {}
        for t in sorted(want):
            changes[t] = self.state[t].diff(self._voice(t))

        g = sum(1 for t in want if changes.get(t, self.state[t].args).get("gMix", 0) > 0)
        self.last_log = ("strobe: %-4s  %2d/%2d tracks  density %.2f  gating %d"
                         % (self.mode, len(want), len(live), self.density, g))
        return changes, turn_on, turn_off

    def _voice(self, track: int) -> dict:
        """One track's settings for this bar. Every value is a division of the bar."""
        rng = self.rng
        a: dict[str, float] = {}

        gate_on = self.mode in ("gate", "both") and rng.random() < 0.85
        loop_on = self.mode in ("loop", "both") and rng.random() < 0.55

        if gate_on:
            a["gDiv"] = float(rng.choice(GATE_DIVS))
            # duty and depth together decide whether this is a shimmer or a chop
            a["gDuty"] = round(rng.uniform(0.18, 0.72), 3)
            a["gDepth"] = round(rng.uniform(0.45, 1.0), 3)
            a["gMix"] = round(rng.uniform(0.5, 1.0), 3)
            # a skew offsets this track's gate against the others, so several gated tracks
            # interlock instead of pumping in unison
            a["gSkew"] = round(rng.uniform(0.0, 1.0), 3)
            a["gShape"] = round(rng.uniform(0.0015, 0.02), 4)
            frm, span = self._window(0.25)
            a["gFrom"], a["gSpan"] = frm, span
        else:
            a["gMix"] = 0.0

        if loop_on:
            a["lDiv"] = float(rng.choice(LOOP_DIVS))
            a["lMix"] = round(rng.uniform(0.6, 1.0), 3)
            a["lFeed"] = round(rng.uniform(0.9, 1.0), 3)
            # a microloop that runs all bar is a drone, so its window is deliberately
            # shorter than the gate's — it is an interruption, not a texture
            frm, span = self._window(0.12, lo=0.06, hi=0.5)
            a["lFrom"], a["lSpan"] = frm, span
        else:
            a["lMix"] = 0.0
            a["lSpan"] = 0.0
        return a

    def _window(self, min_span: float, lo: float = 0.12, hi: float = 1.0) -> tuple[float, float]:
        """A slice of the bar, quantised to sixteenths and never running past the barline."""
        rng = self.rng
        if rng.random() < 0.22 and hi >= 1.0:
            return 0.0, 1.0                                # occasionally the whole bar
        span = max(min_span, _q(rng.uniform(lo, hi)))
        frm = _q(rng.uniform(0.0, max(0.0, 1.0 - span)))
        return round(frm, 4), round(min(span, 1.0 - frm), 4)
