"""Algorithmic step-sequence generation for ONE track.

Shift + touch the volume knob + Track 1 in the edit view: the open track gets a new
16-step sequence, complete with its per-step locks. The aesthetic target is the same as
the rest of the instrument — IDM, rhythmic noise, abstract and textural electronica —
so the rhythm palette is deliberately wider than "Euclidean and its rotations":

  euclid          even distribution of k over n; the reliable spine
  euclid pair     two Euclids combined (AND / XOR / OR) — polyrhythm inside one bar
  asymmetric      additive grouping (3+3+2, 3+2+3, 5+3…), accents on group heads
  burst           dense clusters separated by gaps; the rhythmic-noise shape
  sieve           a grid thinned by a residue rule (every 3rd, offset 1) — irregular
                  but not arbitrary, and it repeats coherently
  fracture        a Euclid whose hits are displaced by one step at random points

Every generator returns hits ONLY; the character comes from what is then written into
each hit: velocity contour, pan movement, pitch (scale-aware — see `scales`), and cycle
dividers so some hits sit out most repetitions. A generated bar should not sound like
a random bar: accents fall in groups, pans move rather than jitter, and the pitch
material belongs to the piece.
"""

from __future__ import annotations

import math
import random

from . import scales
from .catalog import VOICES
from .tracks import N_STEPS, MAX_STEPS

# engines whose pitch is musically meaningful (a note lock changes the note you hear,
# not just the timbre). DRUM/noise engines take pitch as colour, so they get a much
# narrower treatment.
_PITCHED = {"FM7", "BUCHLOID", "MOLLY", "RINGS", "PLAITS", "MALLET", "BOWED", "PLUCK",
            "TUBE", "MEMBRANE", "ICARUS", "WTABLE"}
# engines that are texture rather than line: they get sparse, wide, slow material
_TEXTURE = {"NOIZEOP", "CHAOS", "BEN", "BYTEBEAT", "ICARUS", "BUCHLOID"}


# --------------------------------------------------------------------------- #
# rhythm
# --------------------------------------------------------------------------- #
def _euclid(k: int, n: int, rotate: int = 0) -> list[int]:
    """Even distribution of k pulses over n steps, optionally rotated."""
    if n <= 0:
        return []
    k = max(0, min(k, n))
    if k == 0:
        return [0] * n
    out, bucket = [], 0
    for _ in range(n):
        bucket += k
        if bucket >= n:
            bucket -= n
            out.append(1)
        else:
            out.append(0)
    first = out.index(1) if 1 in out else 0
    out = out[first:] + out[:first]
    if rotate:
        rotate %= n
        out = out[-rotate:] + out[:-rotate]
    return out


def _asymmetric(n: int, rng: random.Random) -> list[int]:
    """Additive grouping: 3+3+2, 3+2+3, 5+3, 2+3+3… — the head of each group is a hit."""
    groups = {16: [(3, 3, 2, 3, 3, 2), (3, 3, 3, 3, 2, 2), (5, 3, 5, 3), (3, 5, 3, 5),
                   (2, 3, 3, 2, 3, 3), (7, 5, 4), (4, 3, 4, 5)]}.get(n)
    if not groups:
        groups = [(3, 3, 2)]
    g = list(rng.choice(groups))
    rng.random() < 0.4 and g.reverse()
    out, i = [0] * n, 0
    for size in g:
        if i >= n:
            break
        out[i] = 1
        i += size
    return out


def _burst(n: int, rng: random.Random, density: float) -> list[int]:
    """Clusters of consecutive hits separated by silence — rhythmic-noise phrasing."""
    out = [0] * n
    i = 0
    while i < n:
        if rng.random() < 0.45 + (density * 0.3):
            run = rng.choice((2, 2, 3, 3, 4, 5))
            for j in range(run):
                if i + j < n:
                    out[i + j] = 1
            i += run + rng.choice((1, 2, 2, 3, 4))
        else:
            i += rng.choice((1, 2, 3))
    return out


def _sieve(n: int, rng: random.Random) -> list[int]:
    """Residue sieve: hits where (step % m) == r, for one or two (m, r) pairs.

    Irregular against a 16-grid but perfectly periodic, which is what keeps it musical
    rather than merely uneven.
    """
    out = [0] * n
    pairs = [(rng.choice((3, 5, 6, 7)), rng.randrange(0, 3))]
    if rng.random() < 0.5:
        pairs.append((rng.choice((4, 5, 7)), rng.randrange(0, 4)))
    for m, r in pairs:
        for i in range(n):
            if i % m == r:
                out[i] = 1
    return out


def _fracture(n: int, rng: random.Random, density: float) -> list[int]:
    """A Euclid whose hits are nudged off the grid — displaced, not randomised."""
    k = max(2, min(n - 1, round(n * (0.25 + density * 0.35))))
    base = _euclid(k, n, rotate=rng.randrange(0, n))
    out = list(base)
    for i in range(n):
        if base[i] and rng.random() < 0.35:
            j = i + rng.choice((-1, 1))
            if 0 <= j < n and not out[j]:
                out[i], out[j] = 0, 1
    return out


def _euclid_pair(n: int, rng: random.Random, density: float) -> list[int]:
    """Two Euclidean layers combined — polyrhythm folded into one bar."""
    a = _euclid(rng.choice((3, 5, 7)), n, rotate=rng.randrange(0, n))
    b = _euclid(rng.choice((2, 3, 4, 6)), n, rotate=rng.randrange(0, n))
    op = rng.choice(("or", "or", "xor", "and"))
    out = []
    for x, y in zip(a, b):
        if op == "or":
            out.append(1 if (x or y) else 0)
        elif op == "xor":
            out.append(1 if (x != y) else 0)
        else:
            out.append(1 if (x and y) else 0)
    if sum(out) < 2:                      # AND can empty the bar; fall back to the spine
        out = a
    return out


_ALGOS = ("euclid", "euclid pair", "asymmetric", "burst", "sieve", "fracture")


def _rhythm(n: int, rng: random.Random, density: float, algo: str) -> list[int]:
    if algo == "euclid":
        k = max(1, min(n, round(n * (0.2 + density * 0.45))))
        return _euclid(k, n, rotate=rng.choice((0, 0, 0, 1, 2, 3)))
    if algo == "euclid pair":
        return _euclid_pair(n, rng, density)
    if algo == "asymmetric":
        return _asymmetric(n, rng)
    if algo == "burst":
        return _burst(n, rng, density)
    if algo == "sieve":
        return _sieve(n, rng)
    return _fracture(n, rng, density)


# --------------------------------------------------------------------------- #
# the generator
# --------------------------------------------------------------------------- #
def generate(project, track: int, rng: random.Random | None = None) -> dict:
    """Write a new sequence (and its per-step locks) into `track`. Returns a summary."""
    rng = rng or random.Random()
    tr = project.tracks[track]
    if tr.type == "EMPTY" or VOICES.get(tr.type) is None:
        return {"ok": False, "why": "no engine on this track"}

    n = min(MAX_STEPS, max(1, int(tr.length)))
    pitched = tr.type in _PITCHED
    texture = tr.type in _TEXTURE
    drum = tr.type == "DRUM"

    # density: textures stay sparse and slow, drums can carry the bar
    density = rng.uniform(0.15, 0.45) if texture else (
        rng.uniform(0.35, 0.8) if drum else rng.uniform(0.25, 0.6))
    algo = rng.choice(_ALGOS)
    hits = _rhythm(n, rng, density, algo)
    if sum(hits) == 0:
        hits[0] = 1

    # ---- scale: the FIRST pitched material in the project decides the key ----
    ctx = scales.context(project, skip=track)
    if project.scale_name is None and pitched:
        seed_notes = ctx["notes"] or [tr.note]
        root, name = scales.detect(seed_notes)
        project.set_scale(root, name)
    root = project.scale_root if project.scale_root is not None else scales.DEFAULT_ROOT
    name = project.scale_name or scales.DEFAULT_SCALE
    prefer = {pc for pc, _ in sorted(ctx["pcs"].items(), key=lambda kv: -kv[1])[:4]}

    # ---- clear this track's step state, then write the new bar ----
    tr.pattern = [0] * N_STEPS
    tr.step_note = [None] * N_STEPS
    tr.step_vel = [None] * N_STEPS
    tr.step_pan = [None] * N_STEPS
    tr.step_cycle = [1] * N_STEPS

    # a shared contour so accents/pan/pitch move together rather than each jittering
    phase = rng.uniform(0, math.tau)
    swing = rng.uniform(0.5, 1.5)
    pan_span = rng.uniform(0.15, 0.75) * (1.3 if texture else 1.0)
    centre = rng.uniform(-0.25, 0.25)
    # pitch: a low anchor plus a contour in scale degrees; textures roam wider
    degs = list(scales.SCALES.get(name, scales.SCALES[scales.DEFAULT_SCALE]))
    # REGISTER. Sit an octave-ish above the root by default, and if other tracks are
    # already playing, lean away from the register they occupy so lines don't pile up
    # in the same place. The window is then enforced on every note.
    base_oct = rng.choice((0, 12, 12, 24)) if pitched else 0
    if ctx["any"] and pitched:
        crowd = (ctx["low"] + ctx["high"]) / 2
        base_oct = 24 if (root + 12) < crowd - 6 else (0 if (root + 12) > crowd + 6 else base_oct)
    lo_note, hi_note = root - 5, root + 31
    walk = 0
    tension = 0.25 if texture else 0.12          # licence to leave the scale

    accents = 0
    for i in range(n):
        if not hits[i]:
            continue
        tr.pattern[i] = 1
        pos = i / max(1, n)
        wave = math.sin(phase + pos * math.tau * swing)

        # VELOCITY — grouped accents, not per-step noise: the head of each group and
        # the contour peak are loud, the rest sit back.
        head = (i % 4 == 0) or (i > 0 and not hits[i - 1])
        vel = 0.55 + (0.3 * wave) + (0.25 if head else 0.0)
        vel += rng.uniform(-0.08, 0.08)
        if rng.random() < 0.12:                  # occasional ghost
            vel *= 0.45
        tr.step_vel[i] = round(min(1.6, max(0.15, vel)), 3)
        accents += 1 if head else 0

        # PAN — movement across the bar (a slow sweep plus small steps), not scatter
        tr.step_pan[i] = round(max(-1.0, min(1.0,
            centre + (pan_span * math.sin(phase * 1.7 + pos * math.tau)) +
            rng.uniform(-0.08, 0.08))), 3)

        # PITCH — a walk through scale degrees, anchored low, related to the piece
        if pitched:
            walk += rng.choice((-2, -1, -1, 0, 1, 1, 2, 3))
            walk = max(-len(degs), min(2 * len(degs), walk))     # keep the line in reach
            deg = degs[walk % len(degs)]
            octv = base_oct + 12 * (walk // len(degs))
            if rng.random() < 0.18:              # leaps keep a line from trudging
                octv += rng.choice((-12, 12))
            cand = root + deg + octv
            note = scales.quantise(cand, root, name, prefer=prefer, rng=rng,
                                   tension=tension)
            # fold into the register window rather than clamping, so a leap that lands
            # outside comes back as the same pitch class an octave in
            while note < lo_note:
                note += 12
            while note > hi_note:
                note -= 12
            tr.step_note[i] = int(max(12, min(108, note)))
        elif drum and rng.random() < 0.3:
            tr.step_note[i] = int(max(12, min(90, tr.note + rng.choice((-7, -5, 5, 7, 12)))))

        # CYCLE FREQUENCY — some hits sit out most repetitions, which is what makes a
        # 16-step bar unfold over a much longer span. Kept off the downbeat.
        if i != 0 and rng.random() < (0.3 if texture else 0.18):
            tr.step_cycle[i] = rng.choice((2, 2, 3, 4, 4, 8))

    return {"ok": True, "algo": algo, "hits": sum(hits), "steps": n,
            "scale": f"{name}", "root": root, "pitched": pitched}
