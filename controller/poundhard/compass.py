"""COMPASS — the norns script's command sequencer, driving a live tape loop.

After Olivier Creurer's script, and this time on the thing the original actually
manipulates: a **softcut buffer**. The master is recorded continuously into 40 seconds of
tape while two heads play it back, and a sequence of terse commands moves those heads —
rate, direction, position, loop length, pan, record. That is where the tape-loop character
lives, and no amount of step-sequencer manipulation reproduces it: a step sequencer can
reorder notes, but it cannot play the last four seconds of the performance backwards at
2/3 speed inside a shrinking loop.

THE SELF-MODIFYING CLOCK is the other half. `<` `>` `[` `]` change how fast the command
stream itself runs, so it accelerates, stalls and lurches under its own influence instead
of ticking evenly.

The commands are the original's, one for one:

    F R      rate forward / reverse (a NEGATIVE softcut rate — real reverse playback)
    + - !    rate increment / decrement / random, from the original's rate table
    1 P      jump to loop start / a random position inside the loop
    L        random loop length
    ( )      random pan, left head and right head
    ::       toggle recording — freezes the tape, so the heads keep playing what is on it
    [ ] < >  the command clock
    ?        jump the command sequencer to a random position

NON-DESTRUCTIVE by construction: it records the master and plays into the master. No track,
pattern or parameter is touched, so switching off is freeing the synth and wiping the tape.
"""
from __future__ import annotations

import random

SEQ_LEN = 12
# the original's rate table — musical ratios, both directions
RATES = (-2.0, -1.0, -0.5, 0.5, 1.0, 2.0)
BUF_SECONDS = 40.0


class Head:
    """One softcut head's live parameters."""

    def __init__(self, pan):
        self.rate = 1.0
        self.start = 0.0
        self.end = 4.0
        self.pan = pan
        self.rec = 1.0
        self.pre = 0.75

    def as_args(self, i):
        n = str(i)
        return {"rate" + n: self.rate, "start" + n: self.start, "end" + n: self.end,
                "pan" + n: self.pan, "rec" + n: self.rec, "pre" + n: self.pre}


# --------------------------------------------------------------------------- #
# commands. Each takes (cp, rng) and mutates the sequencer or both heads.
# --------------------------------------------------------------------------- #
def c_metro_bottom(cp, rng):  cp.division = 8
def c_metro_top(cp, rng):     cp.division = 1
def c_metro_dec(cp, rng):     cp.division = max(1, cp.division // 2)
def c_metro_inc(cp, rng):     cp.division = min(8, cp.division * 2)
def c_step_rnd(cp, rng):      cp.pos = rng.randrange(SEQ_LEN)


def c_rate_fwd(cp, rng):
    """F — 1x forward, both heads."""
    cp.rate_pos = 4
    for h in cp.heads:
        h.rate = RATES[4]


def c_rate_rev(cp, rng):
    """R — -1x. Reverse playback of recorded audio, which is the whole point."""
    cp.rate_pos = 1
    for h in cp.heads:
        h.rate = RATES[1]


def c_rate_inc(cp, rng):
    cp.rate_pos = min(len(RATES) - 1, cp.rate_pos + 1)
    for h in cp.heads:
        h.rate = RATES[cp.rate_pos]


def c_rate_dec(cp, rng):
    cp.rate_pos = max(0, cp.rate_pos - 1)
    for h in cp.heads:
        h.rate = RATES[cp.rate_pos]


def c_rate_rnd(cp, rng):
    cp.rate_pos = rng.randrange(len(RATES))
    for h in cp.heads:
        h.rate = RATES[cp.rate_pos]


def c_pos_start(cp, rng):
    """1 — both heads to the top of the loop."""
    for i, h in enumerate(cp.heads):
        cp.cut[i] = h.start


def c_pos_rnd(cp, rng):
    """P — both heads somewhere else inside the loop."""
    for i, h in enumerate(cp.heads):
        cp.cut[i] = rng.uniform(h.start, max(h.start + 0.05, h.end))


def c_loop_rnd(cp, rng):
    """L — a new loop window inside the tape. Short windows are where it starts to stutter
    rather than loop, so the low end is deliberately reachable."""
    a = rng.uniform(0.0, BUF_SECONDS - 1.0)
    # Weighted SHORT. A four-second window is a delay; an eighth-second window is the tape
    # stuttering on one grain, and that is the sound the script is known for. Long windows
    # are still reachable, they are just no longer the common case.
    span = rng.choice((0.06, 0.08, 0.12, 0.15, 0.25, 0.4, 0.6, 1.0, 2.0, 4.0))
    b = min(BUF_SECONDS, a + span)
    for h in cp.heads:
        h.start, h.end = round(a, 4), round(b, 4)


def c_pan_l(cp, rng):
    cp.heads[0].pan = round(rng.uniform(0, 8) / -10.0, 3)


def c_pan_r(cp, rng):
    cp.heads[1].pan = round(rng.uniform(0, 8) / 10.0, 3)


def c_toggle_rec(cp, rng):
    """:: — the original's record toggle, and the single most characterful command in the
    set. With recording off the tape stops being overwritten, so the heads keep chewing on
    a frozen few seconds; turn it back on and the performance bleeds in again."""
    cp.rec_on = not cp.rec_on
    for h in cp.heads:
        h.rec = 1.0 if cp.rec_on else 0.0


COMMANDS = [
    (c_metro_bottom, "["), (c_metro_top, "]"), (c_metro_dec, "<"), (c_metro_inc, ">"),
    (c_step_rnd, "?"), (c_rate_fwd, "F"), (c_rate_rev, "R"), (c_rate_inc, "+"),
    (c_rate_dec, "-"), (c_rate_rnd, "!"), (c_pos_start, "1"), (c_pos_rnd, "P"),
    (c_loop_rnd, "L"), (c_pan_l, "("), (c_pan_r, ")"), (c_toggle_rec, "::"),
]
# The gestures that MOVE THE TAPE are what you hear; the clock commands only shape the
# stream. Measured on the device, an even weighting left the heads parked on a plain
# four-second forward loop for most of a run — an echo, not a tape loop. So the loop,
# position, rate and freeze commands carry most of the weight, and `?` (which reorders the
# sequence without touching the audio) carries almost none.
_WEIGHTS = {"[": 1, "]": 2, "<": 2, ">": 2, "?": 1, "F": 2, "R": 5, "+": 3, "-": 3,
            "!": 4, "1": 3, "P": 5, "L": 7, "(": 2, ")": 2, "::": 4}


class Compass:
    """The command sequencer: a list of commands, a position, a self-modifying divider."""

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        # every cycle by default: the clock commands are there to slow it DOWN from this,
        # and starting at 2 meant half the run went by before the tape did anything.
        self.division = 1
        self.pos = 0
        self.counter = 0
        self.rate_pos = 4
        self.rec_on = True
        self.heads = [Head(-0.3), Head(0.3)]
        self.cut = [-1.0, -1.0]
        self.seq: list = []
        self.reseed()

    def reseed(self) -> None:
        fns = [c for c, _ in COMMANDS]
        wts = [_WEIGHTS[g] for _, g in COMMANDS]
        self.seq = self.rng.choices(fns, weights=wts, k=SEQ_LEN)
        self.pos = 0

    def glyph(self, fn) -> str:
        return next(g for c, g in COMMANDS if c is fn)

    def tick(self):
        """One pattern cycle. Returns (log line, {synth arg: value}) when a command fired."""
        self.counter += 1
        if self.counter < max(1, self.division):
            return None, None
        self.counter = 0
        if self.rng.random() < 0.06:
            self.reseed()
        self.cut = [-1.0, -1.0]                 # cut is a trigger; clear it each command
        fn = self.seq[self.pos % len(self.seq)]
        self.pos = (self.pos + 1) % len(self.seq)
        fn(self, self.rng)

        args = {}
        for i, h in enumerate(self.heads, start=1):
            args.update(h.as_args(i))
        for i, c in enumerate(self.cut, start=1):
            if c >= 0:
                args["cut" + str(i)] = c
        return ("compass: %-2s  rate %+.2g  loop %.2f-%.2f  rec %s  (every %d)"
                % (self.glyph(fn), self.heads[0].rate, self.heads[0].start,
                   self.heads[0].end, "on" if self.rec_on else "FROZEN", self.division)), args
