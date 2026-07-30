"""Per-parameter step randomizers — live variation without rewriting the sequence.

Shift + touching a control in the edit view toggles a randomizer for whatever per-step
parameter that control edits. Each one is independent, and each has its own algorithm,
because "randomise" means something different for every parameter: a velocity that jumps
uniformly sounds broken, a pan that jumps uniformly sounds like a fault, and a pitch that
jumps uniformly is simply wrong notes.

NON-DESTRUCTIVE. Nothing here writes to the pattern. Every function takes the PROGRAMMED
values and returns a temporary set to push at the engine; the programmed values stay in the
controller untouched, so switching a randomizer off is just re-pushing them.

THE COMMON PRINCIPLE. Every algorithm varies around what is already there rather than
replacing it. That is what keeps the sequence recognisable: the accents stay where they
were put, the line keeps its shape, the filter keeps its character — they breathe rather
than churn. A randomizer that ignores the programmed value is a generator, not a variation.
"""
from __future__ import annotations

import math
import random

from . import scales

N_STEPS = 16


def _live(tr) -> list[int]:
    ln = max(1, min(N_STEPS, int(tr.length)))
    return [c for c in range(ln) if tr.pattern[c]]


# --------------------------------------------------------------------------- #
# one function per parameter. Each returns {cell: value} to push, or {}.
# --------------------------------------------------------------------------- #
def vel(tr, rng, depth=1.0) -> dict:
    """Velocity: keep the phrasing, move the dynamics.

    The accents a pattern was given are its phrasing — flattening them into noise is the
    one thing this must not do. Each hit moves by a bounded ratio around its OWN programmed
    value, so a step written loud stays the loud one; and a hit is occasionally ghosted,
    which is what a player does and a uniform distribution never will.
    """
    out = {}
    for c in _live(tr):
        base = tr.step_vel[c] if tr.step_vel[c] is not None else tr.vel
        v = base * rng.uniform(1 - 0.28 * depth, 1 + 0.28 * depth)
        if rng.random() < 0.08 * depth:
            v *= rng.uniform(0.35, 0.55)          # a ghost, not a gap
        out[c] = round(max(0.05, min(1.6, v)), 3)
    return out


def pan(tr, rng, depth=1.0) -> dict:
    """Pan: movement, not scatter.

    Independent random pans read as a fault in the signal path. A slow contour across the
    bar with a different phase and width each cycle reads as movement, so the values are
    drawn from one sweep rather than one at a time.
    """
    out = {}
    live = _live(tr)
    if not live:
        return out
    phase = rng.uniform(0, math.tau)
    width = rng.uniform(0.25, 0.85) * depth
    centre = rng.uniform(-0.2, 0.2)
    turns = rng.choice((0.5, 1.0, 1.0, 1.5, 2.0))
    ln = max(1, min(N_STEPS, int(tr.length)))
    for c in live:
        pos = c / ln
        p = centre + width * math.sin(phase + pos * math.tau * turns)
        out[c] = round(max(-1.0, min(1.0, p + rng.uniform(-0.05, 0.05))), 3)
    return out


def pitch(tr, rng, project, depth=1.0) -> dict:
    """Pitch: never a wrong note.

    Movement is in SCALE DEGREES around the step's own programmed note and then quantised
    to the project's scale, so the line keeps its shape and every result belongs to the
    piece. Small steps dominate; the occasional octave keeps it from trudging.
    """
    out = {}
    root = project.scale_root if project.scale_root is not None else scales.DEFAULT_ROOT
    name = project.scale_name or scales.DEFAULT_SCALE
    degs = scales.SCALES.get(name, scales.SCALES[scales.DEFAULT_SCALE])
    for c in _live(tr):
        base = tr.step_note[c] if tr.step_note[c] is not None else tr.note
        # move by degrees, not semitones: a semitone walk leaves the scale immediately
        step = rng.choice((-2, -1, -1, 0, 1, 1, 2)) * max(1, round(depth * 1.5))
        cand = base + (degs[abs(step) % len(degs)] * (1 if step >= 0 else -1))
        if rng.random() < 0.10 * depth:
            cand += rng.choice((-12, 12))
        n = scales.quantise(int(cand), root, name, rng=rng, tension=0.0)
        out[c] = int(max(12, min(108, n)))
    return out


def macro(tr, rng, depth=1.0) -> dict:
    """Voice macro: timbral drift around the programmed position."""
    out = {}
    for c in _live(tr):
        base = tr.step_macro[c]
        if base is None:
            base = 0.5
        v = base + rng.uniform(-0.3, 0.3) * depth
        out[c] = round(max(0.0, min(1.0, v)), 3)
    return out


def fcut(tr, rng, depth=1.0) -> dict:
    """Filter cutoff: multiplicative, and bounded.

    Cutoff is perceived logarithmically, so variation has to be a RATIO — a linear jitter is
    inaudible at the top and slams shut at the bottom. Bounded to a bit over an octave so a
    step never disappears behind a closed filter.
    """
    out = {}
    for c in _live(tr):
        fl = tr.step_filt[c]
        base = fl[0] if fl else tr.filt_cutoff
        res = fl[1] if fl else tr.filt_res
        ty = fl[2] if fl else tr.filt_type
        ratio = 2 ** rng.uniform(-1.1 * depth, 0.7 * depth)
        out[c] = (round(max(80.0, min(18000.0, base * ratio)), 1), res, ty)
    return out


def fres(tr, rng, depth=1.0) -> dict:
    """Resonance: small moves. Resonance is where a filter gets shrill, so the range is
    deliberately tighter than the others and never reaches the top of the control."""
    out = {}
    for c in _live(tr):
        fl = tr.step_filt[c]
        cut = fl[0] if fl else tr.filt_cutoff
        base = fl[1] if fl else tr.filt_res
        ty = fl[2] if fl else tr.filt_type
        v = base + rng.uniform(-0.18, 0.22) * depth
        out[c] = (cut, round(max(0.0, min(0.78, v)), 3), ty)
    return out


def window(tr, rng, which, depth=1.0) -> dict:
    """SAMPLE start / end: shift the slice, keep it a slice.

    The two are randomised together whatever was touched, because a start past its end is
    not a variation, it is silence.
    """
    out = {}
    for c in _live(tr):
        s = tr.step_start[c] if tr.step_start[c] is not None else 0.0
        e = tr.step_end[c] if tr.step_end[c] is not None else 1.0
        if which == "start":
            s = s + rng.uniform(-0.12, 0.28) * depth
        else:
            e = e + rng.uniform(-0.28, 0.12) * depth
        s = max(0.0, min(0.94, s))
        e = max(s + 0.06, min(1.0, e))
        out[c] = (round(s, 4), round(e, 4))
    return out


# What each control in the edit view randomises, and what to call it on screen.
# A control that edits no per-step data is deliberately absent — the gesture reports that
# rather than switching on something with no audible effect.
PARAMS = {
    "vel":   "VELOCITY",
    "pan":   "PAN",
    "pitch": "PITCH",
    "macro": "MACRO",
    "fcut":  "FILTER CUTOFF",
    "fres":  "RESONANCE",
    "start": "SAMPLE START",
    "end":   "SAMPLE END",
}


def generate(param: str, tr, project, rng: random.Random | None = None, depth: float = 1.0):
    """Fresh values for one parameter on one track. Returns {cell: value} or {}."""
    rng = rng or random.Random()
    if param == "vel":
        return vel(tr, rng, depth)
    if param == "pan":
        return pan(tr, rng, depth)
    if param == "pitch":
        return pitch(tr, rng, project, depth)
    if param == "macro":
        return macro(tr, rng, depth)
    if param == "fcut":
        return fcut(tr, rng, depth)
    if param == "fres":
        return fres(tr, rng, depth)
    if param in ("start", "end"):
        return window(tr, rng, param, depth)
    return {}
