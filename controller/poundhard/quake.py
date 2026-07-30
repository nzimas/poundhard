"""QUAKE — a temporary rhythmic transformation of the whole rig.

The third toggle on the bottom row, beside HEAT and SHUFFLE, and like them it is an
ENGINE-ONLY overlay: nothing here touches the pattern. Toggling off pushes every track's
own length and rate back and the rig plays exactly as programmed.

It combines the two things that make rhythm complex without making it arbitrary:

  POLYMETER  — tracks are given DIFFERENT LENGTHS. A 15-step track against a 16-step one
               shifts by a step every bar and comes back into phase after 16; a 12-step
               track against 16 realigns after 4. Mixing lengths that share a factor with
               16 against lengths coprime with it gives both short cycles you can hear
               resolve and long ones that keep moving underneath them.

  POLYRHYTHM — tracks are given RATIO CLOCK RATES. The engine's clock is a float
               accumulator (`~acc[t] += ~rate[t]`), so 3:2 and 7:5 are as native as x2 —
               there is no grid to fight. The ladder in the UI only exposes powers of two;
               this reaches the ratios between them.

WHAT MAKES IT MUSICAL RATHER THAN RANDOM

  * An ANCHOR is never touched. The densest drum-like track keeps its own length and rate,
    so the pulse survives and the result stays recognisably the same piece. Without this
    the whole rig drifts at once and you just hear a mess.
  * DENSITY decides how hard a track is hit. A busy track gets a small length change OR a
    mild ratio — never both, because a dense part under a 7:4 clock is mush. A sparse track
    can take the wild end, where it reads as a counter-rhythm rather than a smear.
  * Not everything moves. Roughly half to two thirds of the eligible tracks are
    transformed; the rest hold the frame the others move against.
  * Ratios are applied as MULTIPLIERS on the track's existing rate, so a track already
    running at x2 stays fast and keeps its role in the arrangement.
"""
from __future__ import annotations

import random

# Lengths worth landing on, split by how they behave against a 16-step frame.
#   FAST realign: share a factor with 16, so they resolve within a few bars — audible as a
#   deliberate turnaround rather than as drift.
_LEN_FAST = (12, 14, 20, 24)
#   SLOW realign: coprime with 16, so they walk all the way round before coming back. This
#   is where the "phasing forever" character comes from.
_LEN_SLOW = (13, 15, 17, 19, 11)

# Ratio clock rates, as multipliers on the track's current rate. Ordered by how far they
# pull away from the pulse: the gentle end is safe on anything, the wild end needs space.
_RATIO_GENTLE = (9 / 8, 8 / 9, 5 / 4, 4 / 5)
_RATIO_MID = (3 / 2, 2 / 3, 4 / 3, 3 / 4)
_RATIO_WILD = (7 / 4, 4 / 7, 7 / 5, 5 / 7, 5 / 3, 3 / 5)

_DRUMISH = {"DRUM", "MEMBRANE", "SHAKER"}


def _density(tr) -> float:
    n = max(1, min(len(tr.pattern), int(tr.length)))
    return sum(1 for c in range(n) if tr.pattern[c]) / n


def plan(project, rng: random.Random | None = None) -> dict:
    """Work out a Quake configuration. Returns {track: (length, rate)} for the tracks that
    should change — every other track is left exactly as programmed.

    Pure: it reads the project and decides, but changes nothing. The caller pushes the
    result to the engine and keeps the original values to put back.
    """
    rng = rng or random.Random()
    tracks = project.tracks
    live = [t for t in range(len(tracks))
            if tracks[t].type != "EMPTY" and any(tracks[t].pattern)]
    if len(live) < 2:
        return {}

    # THE ANCHOR: the busiest drum-like track, else simply the busiest. It keeps its own
    # length and rate so there is still a pulse to hear everything else against.
    drums = [t for t in live if tracks[t].type in _DRUMISH]
    pool = drums or live
    anchor = max(pool, key=lambda t: _density(tracks[t]))

    movable = [t for t in live if t != anchor]
    rng.shuffle(movable)
    # Most of the rig moves. Exempting the anchor AND half the rest left every drum in
    # place on a typical kit, so only the quiet melodic tracks shifted and the pulse barely
    # changed — subtle where this is supposed to reshape the landscape.
    k = max(1, round(len(movable) * rng.uniform(0.65, 0.9)))
    chosen = movable[:k]
    # The rhythm section IS the landscape. If there is another drum-like track besides the
    # anchor, make sure at least one of them moves — otherwise the transformation happens
    # entirely underneath the part the ear is actually tracking.
    others = [t for t in movable if t in drums]
    if others and not any(t in chosen for t in others):
        chosen = chosen[:-1] + [rng.choice(others)] if chosen else [rng.choice(others)]

    out: dict[int, tuple[int, float]] = {}
    slow_used = 0
    for t in chosen:
        tr = tracks[t]
        dens = _density(tr)
        length, rate = int(tr.length), float(tr.rate)

        # A dense track gets ONE transformation, and a gentle one. A sparse track can take
        # a length change and a ratio together, and from the wilder end.
        busy = dens > 0.45
        if busy:
            mode = rng.choice(("length", "rate"))
        else:
            mode = rng.choice(("length", "rate", "both", "both"))

        if mode in ("length", "both"):
            # keep a couple of tracks on the slow-realigning lengths — all of them coprime
            # at once never resolves, and none of them never drifts
            if slow_used < 2 and rng.random() < 0.6:
                length = rng.choice(_LEN_SLOW)
                slow_used += 1
            else:
                length = rng.choice(_LEN_FAST)
            # a dense part loses its shape if it is chopped hard; keep it near its own size
            if busy:
                length = min(_LEN_FAST + _LEN_SLOW,
                             key=lambda L: abs(L - int(tr.length)))

        if mode in ("rate", "both"):
            bank = _RATIO_GENTLE if busy else (
                _RATIO_MID + _RATIO_WILD if rng.random() < 0.55 else _RATIO_MID)
            rate = float(tr.rate) * rng.choice(bank)
            # stay inside the engine's usable band, and never so slow a track drops out of
            # earshot for bars at a time
            rate = max(0.125, min(8.0, rate))

        # Two tracks handed the SAME length and the same ratio move together instead of
        # against each other, which is the one thing this is for. Nudge a collision onto a
        # neighbouring length rather than dropping the track from the plan.
        cand = (int(length), round(rate, 5))
        if cand in out.values():
            alts = [L for L in (_LEN_SLOW + _LEN_FAST) if (L, cand[1]) not in out.values()]
            if alts:
                cand = (rng.choice(alts), cand[1])
        if cand != (int(tr.length), float(tr.rate)):
            out[t] = cand
    return out


def describe(project, cfg: dict) -> str:
    """One line for the log/screen: what Quake actually did."""
    if not cfg:
        return "quake: nothing to move"
    bits = []
    for t in sorted(cfg):
        L, r = cfg[t]
        tr = project.tracks[t]
        part = "T%d" % (t + 1)
        if L != int(tr.length):
            part += " %d" % L
        if abs(r - float(tr.rate)) > 1e-6:
            part += " x%.3g" % (r / max(float(tr.rate), 1e-9))
        bits.append(part)
    return "quake: " + "  ".join(bits)
