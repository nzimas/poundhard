"""COMPASS — a command sequencer that improvises on one or two tracks.

After Olivier Creurer's norns script, which is not a looper with effects on it but a
SEQUENCE OF COMMANDS stepped through at a rate the commands themselves keep changing. That
self-modifying clock is the whole character: `<` `>` `[` `]` alter how fast the command
stream runs, so it accelerates, stalls and lurches on its own rather than ticking evenly.

The original's commands drive softcut — rate forward/reverse, rate inc/dec/random, jump to
start, random position, random loop length, random pan, toggle record. PoundHard has no
softcut, but it has a direct equivalent for nearly all of them at the SEQUENCER level:

    softcut rate            ->  the track's clock rate
    reverse playback        ->  the step list, reversed
    jump / random position  ->  the step list, rotated
    random loop length      ->  the track's length (polymeter)
    random pan              ->  the track's pan
    (and, since PoundHard knows what key it is in, two the original could not have:
     transpose within the scale, and an octave jump)

SCOPE IS THE POINT. One or two tracks, never more. The original runs on a whole
performance; here the rest of the rig has to stay recognisable, so Compass is the
improviser sitting inside an arrangement rather than the arrangement itself.

NON-DESTRUCTIVE. Every command writes into a per-track overlay of (rate, length, pattern,
pan, transpose) which the caller pushes at the engine. The pattern data is never touched,
so switching off is re-pushing the controller's own state.
"""
from __future__ import annotations

import random

N_STEPS = 16
SEQ_LEN = 12            # commands in the sequence — long enough not to read as a loop


class State:
    """One track's live overlay. Starts as 'exactly what was programmed'."""

    def __init__(self, tr):
        self.rate_mult = 1.0
        self.length = int(tr.length)
        self.rotate = 0
        self.reverse = False
        self.pan = None                 # None = leave the track's own pan alone
        self.transpose = 0

    def dirty(self, tr) -> bool:
        return (abs(self.rate_mult - 1.0) > 1e-6 or self.length != int(tr.length)
                or self.rotate or self.reverse or self.pan is not None or self.transpose)


# --------------------------------------------------------------------------- #
# the commands. Each takes (compass, state, track, rng) and mutates the overlay
# or the sequencer itself. Named with the original's glyphs so the log reads like
# a Compass sequence.
# --------------------------------------------------------------------------- #
# The clock band is 1-8 pattern cycles, not the original's 1-16. At 16 a command fires
# about every 30 seconds, which is not an improviser, it is a timer — measured, the stream
# parked at the slow end for more than half its life.
def c_metro_bottom(cp, st, tr, rng):    cp.division = 8           # "[" slowest
def c_metro_top(cp, st, tr, rng):       cp.division = 1           # "]" fastest
def c_metro_dec(cp, st, tr, rng):       cp.division = max(1, cp.division // 2)      # "<"
def c_metro_inc(cp, st, tr, rng):       cp.division = min(8, cp.division * 2)       # ">"
def c_step_rnd(cp, st, tr, rng):        cp.pos = rng.randrange(SEQ_LEN)             # "?"


def c_rate_fwd(cp, st, tr, rng):
    """F — back to the programmed clock, forwards."""
    st.rate_mult = 1.0
    st.reverse = False


def c_rate_rev(cp, st, tr, rng):
    """R — the original's -1x. A step sequencer has no negative clock, so reverse is the
    step list read backwards, which is the same musical gesture at this level."""
    st.reverse = not st.reverse


def c_rate_inc(cp, st, tr, rng):
    """+ — faster, in musical ratios rather than a smooth sweep."""
    st.rate_mult = min(4.0, st.rate_mult * rng.choice((1.5, 2.0, 4 / 3)))


def c_rate_dec(cp, st, tr, rng):
    """- — slower."""
    st.rate_mult = max(0.25, st.rate_mult * rng.choice((2 / 3, 0.5, 0.75)))


def c_rate_rnd(cp, st, tr, rng):
    """! — anywhere in the usable band, ratios included."""
    st.rate_mult = rng.choice((0.25, 0.5, 2 / 3, 0.75, 1.0, 1.5, 2.0, 3.0))


def c_pos_start(cp, st, tr, rng):
    """1 — back to the top of the bar."""
    st.rotate = 0


def c_pos_rnd(cp, st, tr, rng):
    """P — land somewhere else in the bar. Displacement, not a different pattern."""
    st.rotate = rng.randrange(N_STEPS)


def c_loop_rnd(cp, st, tr, rng):
    """L — a different loop length, which against the other tracks is polymeter."""
    st.length = rng.choice((3, 5, 6, 7, 9, 11, 12, 13, 14, 15, 16))


def c_pan_rnd(cp, st, tr, rng):
    """( ) — the original had one command per side; one command that picks a side is the
    same result with half the sequence spent on it."""
    st.pan = round(rng.choice((-1, 1)) * rng.uniform(0.25, 0.9), 3)


def c_transpose(cp, st, tr, rng):
    """A command the original could not have: PoundHard knows what key it is in, so the
    improviser can move the line and stay in it. Scale-quantised by the caller."""
    st.transpose = rng.choice((-7, -5, -3, -2, 2, 3, 5, 7))


def c_octave(cp, st, tr, rng):
    st.transpose = rng.choice((-12, 12))


def c_reset(cp, st, tr, rng):
    """A rest in the command stream: this track back to exactly as programmed. Without it
    the overlay only ever accumulates and the track never comes home."""
    st.rate_mult = 1.0
    st.length = int(tr.length)
    st.rotate = 0
    st.reverse = False
    st.pan = None
    st.transpose = 0


COMMANDS = [
    (c_metro_bottom, "["), (c_metro_top, "]"), (c_metro_dec, "<"), (c_metro_inc, ">"),
    (c_step_rnd, "?"), (c_rate_fwd, "F"), (c_rate_rev, "R"), (c_rate_inc, "+"),
    (c_rate_dec, "-"), (c_rate_rnd, "!"), (c_pos_start, "1"), (c_pos_rnd, "P"),
    (c_loop_rnd, "L"), (c_pan_rnd, "("), (c_transpose, "T"), (c_octave, "8"),
    (c_reset, "."),
]
# The clock commands are what give the stream its shape, so they are common; reset is
# common too, because a track that never returns stops being a variation of anything.
_WEIGHTS = {"[": 1, "]": 2, "<": 4, ">": 2, "?": 2, "F": 2, "R": 2, "+": 3, "-": 3,
            "!": 2, "1": 2, "P": 3, "L": 3, "(": 2, "T": 3, "8": 1, ".": 4}


class Compass:
    """The sequencer: a command list, a position, and a self-modifying divider."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.division = 2          # pattern cycles between commands (commands change this)
        self.pos = 0
        self.counter = 0
        self.tracks: list[int] = []
        self.state: dict[int, State] = {}
        self.seq: list = []
        self.reseed()

    def reseed(self) -> None:
        fns = [c for c, _ in COMMANDS]
        wts = [_WEIGHTS[g] for _, g in COMMANDS]
        self.seq = self.rng.choices(fns, weights=wts, k=SEQ_LEN)
        self.pos = 0

    def pick_tracks(self, project) -> list[int]:
        """One or two tracks with sequence data — never an empty one, never more than two."""
        live = [t for t, tr in enumerate(project.tracks)
                if tr.type != "EMPTY" and any(tr.pattern)]
        if not live:
            return []
        if len(live) == 1:
            return live
        return self.rng.sample(live, self.rng.choice((1, 2, 2)))

    def glyph(self, fn) -> str:
        return next(g for c, g in COMMANDS if c is fn)

    def tick(self, project) -> str | None:
        """One pattern cycle. Returns a log line when a command actually fired.

        The divider is counted in pattern cycles, and the commands move it, so the stream
        speeds up and slows down under its own influence — which is the thing that makes
        the original feel like an improviser rather than an arpeggiator.
        """
        self.counter += 1
        if self.counter < max(1, self.division):
            return None
        self.counter = 0

        # occasionally hand the improviser different material and a fresh sequence
        if not self.tracks or self.rng.random() < 0.08:
            self.tracks = self.pick_tracks(project)
            self.state = {t: State(project.tracks[t]) for t in self.tracks}
            if self.rng.random() < 0.5:
                self.reseed()
        if not self.tracks:
            return None

        fn = self.seq[self.pos % len(self.seq)]
        self.pos = (self.pos + 1) % len(self.seq)
        fired = []
        for t in self.tracks:
            st = self.state.get(t)
            if st is None:
                continue
            fn(self, st, project.tracks[t], self.rng)
            fired.append("T%d" % (t + 1))
        return "compass: %s  %s  (every %d)" % (self.glyph(fn), ",".join(fired), self.division)


def steps_for(tr, st: State) -> list:
    """The step list this overlay implies — rotated and/or reversed, never edited."""
    ln = max(1, min(N_STEPS, int(tr.length)))
    src = list(tr.pattern[:ln])
    if st.reverse:
        src = src[::-1]
    if st.rotate:
        k = st.rotate % ln
        src = src[-k:] + src[:-k]
    return src + list(tr.pattern[ln:])
