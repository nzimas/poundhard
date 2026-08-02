"""RECIPES — pattern-level composition.

WHAT WAS WRONG WITH THE OLD ARCHETYPES. There were six, and each one set four numbers: a
track count, a category mix, one density scalar and one interlock scalar. Everything else in
the pattern was uniform randomness applied per track — lengths were 16 eighty percent of the
time, clock rates were 1.0 eighty-eight percent of the time, velocity was whatever the voice
came with, pan was uniform in +-0.7 regardless of what else was panned there, and nothing at
all set living steps, per-step FX, step-cycle conditions or register. So the archetype chose
the *cast* and then sixteen tracks were improvised independently. That is why the good ones
were accidents: when the dice happened to agree, it sounded arranged.

A recipe here is a COMPOSITIONAL BRIEF, and it decides across the pattern rather than within
a track. Every dimension below is stated by the recipe, and the parts are generated against
each other:

  roles       which track carries the pulse, which counters it, which is texture, which is
              sustain. Not the same thing as the engine category — a bass can be the pulse.
  density     per ROLE, not one number for the pattern
  algos       which rhythm generators that role may use (stepgen has six; the old code only
              ever called euclid)
  lengths     a length POLICY: uniform, polymetric with deliberate ratios, or prime-ish
  rates       clock divisions, again as a policy
  register    an octave band per role, so low/mid/high are occupied on purpose
  accent      how velocity is shaped — downbeat, backbeat, rolling crescendo, flat, eroded
  pan         a spread STRATEGY over the whole pattern, so two textures do not stack
  pitch       static, motif, walk, arpeggio or drone
  living      how much of the pattern rewrites itself over time
  stepfx      per-step effects, and how often they fire
  cycles      step-cycle conditions, so a pattern is longer than its bar
  avoid       which roles must not sound on the same step

THEN IT IS JUDGED. `score` marks a finished candidate against the ways these patterns go
wrong — everything on at once, no rhythmic contrast, dead tracks, two tracks doing the same
job, all the energy in one octave, no variation over time, one effect everywhere. `compose`
builds several candidates and returns the best, and repairs the weakest track of a candidate
before scoring it. That is the difference between "sometimes good" and "usually good".
"""
from __future__ import annotations

import random

from .tracks import N_STEPS, MAX_STEPS

# --------------------------------------------------------------------------- #
# ROLES — the job a track does in the pattern, which is NOT its engine category.
# A BASS can be the pulse; a perc can be texture. Parts are generated per role.
# --------------------------------------------------------------------------- #
PULSE = "pulse"        # the primary recurring impulse — need not be a kick, or on the beat
COUNTER = "counter"    # syncopation against the pulse
FILL = "fill"          # busy subdivision, hats and rattle
TEXTURE = "texture"    # noise, atmosphere, non-rhythmic content
SUSTAIN = "sustain"    # drone, pad, held material
LEAD = "lead"          # the quasi-melodic voice
ACCENT = "accent"      # sparse, loud, punctuating

ROLE_KINDS = (PULSE, COUNTER, FILL, TEXTURE, SUSTAIN, LEAD, ACCENT)

# Register bands as semitone offsets from the voice's own note. Occupying distinct bands is
# what stops six voices piling into the same octave and turning to mud.
BAND_LOW, BAND_MID, BAND_HIGH = -12, 0, 12


def _clampi(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


# --------------------------------------------------------------------------- #
# THE RECIPES. Each has a compositional identity that a listener could name, and the
# fields are what MAKES that identity rather than a label on top of the same generator.
#
# `roles` is the shape of the ensemble in JOBS. `dens` is per role. `algos` restricts the
# rhythm generators so a recipe's parts share a rhythmic dialect. Fields left out fall back
# to _DEFAULTS, so a recipe only states what it actually cares about.
# --------------------------------------------------------------------------- #
_DEFAULTS = {
    "dens": {PULSE: 0.45, COUNTER: 0.4, FILL: 0.7, TEXTURE: 0.35, SUSTAIN: 0.12,
             LEAD: 0.4, ACCENT: 0.15},
    "algos": {PULSE: ["euclid"], COUNTER: ["euclid", "asymmetric"], FILL: ["euclid"],
              TEXTURE: ["sieve", "fracture"], SUSTAIN: ["euclid"], LEAD: ["euclid"],
              ACCENT: ["sieve"]},
    "lengths": "uniform", "rates": "straight", "accent": "downbeat", "pan": "spread",
    "pitch": "static", "living": 0.15, "stepfx": 0.03, "cycles": "none",
    "interlock": 0.7, "avoid": [], "contrast": 0.0, "ratchet": 0.015,
    "tempo": None, "register": {},
}

RECIPES = [
    {"name": "GRID", "blurb": "one relentless pulse, everything else locked to it",
     "n": (4, 6), "roles": {PULSE: 1, FILL: 1, COUNTER: 1, TEXTURE: 1},
     "dens": {PULSE: 0.6, FILL: 0.85, COUNTER: 0.35, TEXTURE: 0.25},
     "algos": {FILL: ["euclid", "euclid pair"], COUNTER: ["euclid"]},
     "accent": "downbeat", "interlock": 0.55, "living": 0.08,
     "register": {PULSE: BAND_LOW, TEXTURE: BAND_HIGH}, "tempo": (128, 160)},

    {"name": "BROKEN", "blurb": "the pulse is displaced and never lands where expected",
     "n": (5, 7), "roles": {PULSE: 1, COUNTER: 2, FILL: 1, TEXTURE: 1},
     "dens": {PULSE: 0.35, COUNTER: 0.5, FILL: 0.6},
     "algos": {PULSE: ["asymmetric", "euclid"], COUNTER: ["asymmetric", "fracture"],
               FILL: ["euclid pair", "burst"]},
     "accent": "eroded", "interlock": 0.9, "living": 0.2, "cycles": "sparse",
     "lengths": "asym", "tempo": (96, 132)},

    {"name": "POLYMETER", "blurb": "tracks of different lengths drifting against each other",
     "n": (4, 6), "roles": {PULSE: 1, COUNTER: 2, FILL: 1, SUSTAIN: 1},
     "dens": {PULSE: 0.4, COUNTER: 0.45, FILL: 0.5},
     "lengths": "polymeter", "rates": "straight", "interlock": 0.25,
     "accent": "downbeat", "living": 0.12,
     "register": {PULSE: BAND_LOW, COUNTER: BAND_MID, SUSTAIN: BAND_LOW},
     "tempo": (108, 140)},

    {"name": "POLYRHYTHM", "blurb": "one bar, several clock divisions running through it",
     "n": (4, 6), "roles": {PULSE: 1, COUNTER: 2, FILL: 1, TEXTURE: 1},
     "dens": {PULSE: 0.4, COUNTER: 0.4},
     "rates": "divided", "interlock": 0.3, "accent": "rolling", "living": 0.15,
     "algos": {COUNTER: ["euclid"], FILL: ["euclid"]}, "tempo": (100, 138)},

    {"name": "SPARSE", "blurb": "mostly silence, and every event has to earn its place",
     "n": (3, 5), "roles": {PULSE: 1, ACCENT: 1, TEXTURE: 1, SUSTAIN: 1},
     "dens": {PULSE: 0.18, ACCENT: 0.1, TEXTURE: 0.12, SUSTAIN: 0.08},
     "algos": {PULSE: ["euclid"], ACCENT: ["sieve"], TEXTURE: ["sieve"]},
     "accent": "flat", "pan": "wide", "living": 0.3, "cycles": "wide",
     "interlock": 0.9, "lengths": "asym", "tempo": (76, 108)},

    {"name": "WALL", "blurb": "power noise: dense, interlocking, no air left in it",
     "n": (5, 8), "roles": {PULSE: 1, FILL: 2, COUNTER: 1, TEXTURE: 2},
     "dens": {PULSE: 0.75, FILL: 0.9, COUNTER: 0.7, TEXTURE: 0.8},
     "algos": {FILL: ["euclid pair", "burst"], TEXTURE: ["fracture", "burst"]},
     "accent": "rolling", "interlock": 0.35, "living": 0.05, "stepfx": 0.18,
     "pan": "narrow", "tempo": (132, 172)},

    {"name": "DRONEBED", "blurb": "a held bed with sparse events over it",
     "n": (4, 6), "roles": {SUSTAIN: 2, TEXTURE: 1, ACCENT: 1, PULSE: 1},
     "dens": {SUSTAIN: 0.06, TEXTURE: 0.2, ACCENT: 0.12, PULSE: 0.2},
     "pitch": "drone", "accent": "flat", "pan": "wide", "living": 0.35,
     "cycles": "wide", "interlock": 0.5,
     "register": {SUSTAIN: BAND_LOW, TEXTURE: BAND_HIGH}, "tempo": (72, 104)},

    {"name": "CALL", "blurb": "two voices answering each other across the bar",
     "n": (4, 6), "roles": {PULSE: 1, LEAD: 2, TEXTURE: 1},
     "dens": {PULSE: 0.35, LEAD: 0.4},
     "pitch": "motif", "accent": "downbeat", "interlock": 0.6,
     "avoid": [(LEAD, LEAD)], "living": 0.18,
     "register": {LEAD: BAND_MID}, "tempo": (104, 136)},

    {"name": "MUTATION", "blurb": "a short figure that rewrites itself as it repeats",
     "n": (4, 6), "roles": {PULSE: 1, COUNTER: 1, FILL: 1, LEAD: 1},
     "dens": {PULSE: 0.45, COUNTER: 0.4, FILL: 0.6},
     "lengths": "short", "living": 0.55, "cycles": "dense", "accent": "eroded",
     "interlock": 0.7, "stepfx": 0.2, "tempo": (112, 148)},

    {"name": "TEXTURAL", "blurb": "no groove — spectral movement is the content",
     "n": (4, 6), "roles": {TEXTURE: 3, SUSTAIN: 1, ACCENT: 1},
     "dens": {TEXTURE: 0.3, SUSTAIN: 0.08, ACCENT: 0.1},
     "algos": {TEXTURE: ["sieve", "fracture"]},
     "accent": "flat", "pan": "wide", "pitch": "drone", "living": 0.4,
     "cycles": "wide", "interlock": 0.2, "stepfx": 0.22,
     "register": {TEXTURE: BAND_HIGH, SUSTAIN: BAND_LOW}, "tempo": (68, 100)},

    {"name": "MACHINE", "blurb": "industrial, mechanical, hard on the grid",
     "n": (5, 7), "roles": {PULSE: 1, FILL: 2, ACCENT: 1, TEXTURE: 1},
     "dens": {PULSE: 0.55, FILL: 0.75, ACCENT: 0.2, TEXTURE: 0.3},
     "algos": {PULSE: ["euclid"], FILL: ["euclid", "euclid pair"]},
     "accent": "backbeat", "pan": "narrow", "interlock": 0.5, "living": 0.1,
     "ratchet": 0.18, "register": {PULSE: BAND_LOW}, "tempo": (120, 150)},

    {"name": "STAGGER", "blurb": "asymmetric bars that never quite resolve",
     "n": (4, 6), "roles": {PULSE: 1, COUNTER: 2, FILL: 1},
     "dens": {PULSE: 0.4, COUNTER: 0.45, FILL: 0.55},
     "algos": {PULSE: ["asymmetric"], COUNTER: ["asymmetric", "sieve"]},
     "lengths": "asym", "accent": "eroded", "interlock": 0.75, "living": 0.2,
     "tempo": (100, 134)},

    {"name": "SWARM", "blurb": "many sparse voices adding up to one moving mass",
     "n": (6, 8), "roles": {TEXTURE: 3, FILL: 2, PULSE: 1, SUSTAIN: 1},
     "dens": {TEXTURE: 0.2, FILL: 0.3, PULSE: 0.25, SUSTAIN: 0.08},
     "pan": "wide", "accent": "flat", "interlock": 0.2, "living": 0.3,
     "lengths": "polymeter", "tempo": (96, 128)},

    {"name": "CONTRAST", "blurb": "half the bar crowded, half of it empty",
     "n": (5, 7), "roles": {PULSE: 1, FILL: 2, COUNTER: 1, TEXTURE: 1},
     "dens": {PULSE: 0.5, FILL: 0.8, COUNTER: 0.5, TEXTURE: 0.4},
     "contrast": 0.75, "accent": "rolling", "interlock": 0.6, "living": 0.15,
     "tempo": (112, 152)},

    {"name": "SUBBASS", "blurb": "built from the bottom up, the low end is the subject",
     "n": (4, 6), "roles": {PULSE: 2, SUSTAIN: 1, FILL: 1, TEXTURE: 1},
     "dens": {PULSE: 0.5, SUSTAIN: 0.1, FILL: 0.55},
     "register": {PULSE: BAND_LOW, SUSTAIN: BAND_LOW, TEXTURE: BAND_HIGH},
     "pitch": "walk", "accent": "downbeat", "interlock": 0.65, "living": 0.12,
     "tempo": (88, 124)},

    {"name": "GLITCH", "blurb": "fractured, stuttering, deliberately unstable",
     "n": (4, 6), "roles": {PULSE: 1, COUNTER: 1, FILL: 2, TEXTURE: 1},
     "dens": {PULSE: 0.35, COUNTER: 0.5, FILL: 0.75, TEXTURE: 0.4},
     "algos": {FILL: ["burst", "fracture"], COUNTER: ["fracture"], TEXTURE: ["fracture"]},
     "accent": "eroded", "ratchet": 0.3, "stepfx": 0.25, "living": 0.3,
     "cycles": "dense", "lengths": "short", "interlock": 0.6, "tempo": (124, 168)},

    {"name": "PROCESSION", "blurb": "slow, heavy, ceremonial",
     "n": (4, 6), "roles": {PULSE: 1, ACCENT: 1, SUSTAIN: 2, TEXTURE: 1},
     "dens": {PULSE: 0.25, ACCENT: 0.12, SUSTAIN: 0.08, TEXTURE: 0.2},
     "accent": "downbeat", "pitch": "drone", "pan": "wide", "living": 0.25,
     "cycles": "wide", "interlock": 0.7,
     "register": {SUSTAIN: BAND_LOW, TEXTURE: BAND_HIGH}, "tempo": (64, 92)},

    {"name": "INTERLOCK", "blurb": "parts that only make sense together",
     "n": (5, 7), "roles": {PULSE: 1, COUNTER: 2, FILL: 1, LEAD: 1},
     "dens": {PULSE: 0.4, COUNTER: 0.45, FILL: 0.55, LEAD: 0.35},
     "accent": "rolling", "interlock": 0.95,
     "avoid": [(PULSE, COUNTER), (COUNTER, COUNTER)],
     "pitch": "motif", "living": 0.15, "tempo": (110, 144)},
]


def get(recipe: dict, key: str):
    """A recipe states only what it cares about; the rest comes from _DEFAULTS."""
    if key in recipe:
        v = recipe[key]
        if key in ("dens", "algos", "register") and isinstance(v, dict):
            merged = dict(_DEFAULTS[key])
            merged.update(v)
            return merged
        return v
    return _DEFAULTS[key]


def pick(rng: random.Random) -> dict:
    return rng.choice(RECIPES)


# --------------------------------------------------------------------------- #
# LENGTHS AND RATES — policies, not per-track dice.
#
# The old generator drew a length per track with an 80% chance of 16 and a rate per track
# with an 88% chance of 1.0, which means "polymetric" happened by accident about twice in a
# hundred patterns and, when it did, the lengths were unrelated. A polymetric recipe has to
# produce lengths that MEAN something against each other.
# --------------------------------------------------------------------------- #
# MAX_STEPS is 16, so every relationship here has to LIVE inside 16. Sets containing 32, 24
# or 20 were silently clamped to 16, which destroys the very ratio that makes them
# polymetric: (32, 24, 16, 12) arrived as (16, 16, 16, 12), i.e. three tracks in lockstep.
# Each set below keeps a 16 spine with lengths that take a real number of bars to come back
# round against it — 16 against 12 realigns every 4 bars, against 14 every 8, against 11
# every 11.
_POLY_SETS = [(16, 12, 16, 14), (16, 12, 14, 16), (16, 14, 16, 10), (16, 9, 16, 12),
              (16, 15, 16, 13), (12, 16, 10, 16), (16, 11, 16, 13), (16, 6, 16, 12)]
_ASYM = (7, 9, 10, 11, 13, 14, 15)
_RATES = (0.5, 0.75, 1.0, 1.0, 1.5, 2.0)


def lengths_for(recipe: dict, n: int, rng: random.Random) -> list[int]:
    pol = get(recipe, "lengths")
    if pol == "polymeter":
        base = list(rng.choice(_POLY_SETS))
        out = [base[i % len(base)] for i in range(n)]
        rng.shuffle(out)
        return [_clampi(v, 2, MAX_STEPS) for v in out]
    if pol == "asym":
        # one common length so the pattern has a spine, the rest odd against it
        spine = rng.choice([16, 16, 12])
        return [spine if i == 0 or rng.random() < 0.35 else rng.choice(_ASYM)
                for i in range(n)]
    if pol == "short":
        return [rng.choice([6, 7, 8, 8, 10, 12]) for _ in range(n)]
    base = rng.choice([16, 16, 16, 12])
    return [base] * n


def rates_for(recipe: dict, kinds: list[str], rng: random.Random) -> list[float]:
    pol = get(recipe, "rates")
    if pol != "divided":
        # even a "straight" recipe lets a texture or sustain run at half speed — that is a
        # colour, not a polyrhythm, and it stops every track ticking in lockstep
        return [rng.choice([0.5, 1.0]) if k in (TEXTURE, SUSTAIN) and rng.random() < 0.3
                else 1.0 for k in kinds]
    out = []
    for k in kinds:
        # The pulse defines the reference clock. If it drifts too, there is nothing for the
        # other divisions to be a division OF, and the result is just four unrelated tracks.
        out.append(1.0 if k == PULSE else rng.choice(_RATES))
    return out


# --------------------------------------------------------------------------- #
# ACCENT — velocity as STRUCTURE. The old generator never wrote step velocities at all, so
# every hit in a track was identical and the pattern had no internal dynamics whatsoever.
# --------------------------------------------------------------------------- #
def accents_for(recipe: dict, pat: list[int], L: int, rng: random.Random) -> dict[int, float]:
    mode = get(recipe, "accent")
    out: dict[int, float] = {}
    hits = [i for i in range(L) if pat[i]]
    if not hits:
        return out
    for i in hits:
        if mode == "downbeat":
            v = 1.0 if i % max(1, L // 4) == 0 else rng.uniform(0.55, 0.8)
        elif mode == "backbeat":
            v = 1.0 if (i % max(1, L // 2)) == max(1, L // 4) else rng.uniform(0.5, 0.78)
        elif mode == "rolling":
            v = 0.5 + 0.5 * (i / max(1, L - 1))           # a crescendo across the bar
        elif mode == "eroded":
            v = rng.uniform(0.35, 1.0)                    # deliberately uneven
        else:                                             # flat — but never mechanical
            v = rng.uniform(0.7, 0.9)
        out[i] = round(_clampf(v * rng.uniform(0.94, 1.06), 0.15, 1.6), 3)
    # A pattern with no loud step has no shape: guarantee one peak.
    peak = max(out, key=lambda k: out[k])
    out[peak] = round(min(1.6, out[peak] * 1.25), 3)
    return out


def _clampf(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


# --------------------------------------------------------------------------- #
# PAN — allocated across the PATTERN, not drawn per track. Two textures both landing at
# -0.6 is the commonest way a generated pattern turns to mush in the middle.
# --------------------------------------------------------------------------- #
def pan_plan(recipe: dict, kinds: list[str], rng: random.Random) -> list[float]:
    mode = get(recipe, "pan")
    width = {"narrow": 0.3, "spread": 0.65, "wide": 0.95}.get(mode, 0.65)
    out: list[float] = []
    # positions are dealt alternately outward from the centre, so voices are spaced rather
    # than clustered wherever the dice fell
    slots = [0.0]
    k = 1
    while len(slots) < max(1, len(kinds)):
        slots.append(round(width * k / max(1, len(kinds) // 2 + 1), 3))
        slots.append(round(-width * k / max(1, len(kinds) // 2 + 1), 3))
        k += 1
    si = 0
    for kind in kinds:
        if kind in (PULSE, SUSTAIN):
            out.append(0.0)                       # low content stays centred or it wanders
        else:
            out.append(_clampf(slots[si % len(slots)] + rng.uniform(-0.08, 0.08), -1.0, 1.0))
            si += 1
    return out


# --------------------------------------------------------------------------- #
# PITCH — relationships, not independent random notes.
# --------------------------------------------------------------------------- #
_MOTIF_SHAPES = [(0, 3, 7, 3), (0, -2, 3, 5), (0, 7, 5, 12), (0, 5, 3, -2),
                 (0, 2, 3, 7), (0, -5, -3, 2), (0, 12, 7, 5)]


def pitch_plan(recipe: dict, pat: list[int], L: int, base: int, pcs: set[int],
               rng: random.Random) -> dict[int, int]:
    """Per-step notes for one voice, related to each other rather than drawn independently."""
    mode = get(recipe, "pitch")
    hits = [i for i in range(L) if pat[i]]
    out: dict[int, int] = {}
    if not hits or mode == "static":
        return out
    if mode == "drone":
        # one pitch, occasionally an octave or fifth — the point is that it does NOT move
        for n, i in enumerate(hits):
            out[i] = base if n == 0 or rng.random() < 0.75 else base + rng.choice([-12, 7, 12])
        return out
    if mode == "motif":
        shape = list(rng.choice(_MOTIF_SHAPES))
        if rng.random() < 0.4:
            shape = [-s for s in shape]                  # inversion
        for n, i in enumerate(hits):
            out[i] = _snap_pc(base + shape[n % len(shape)], pcs)
        return out
    if mode == "arpeggio":
        chord = rng.choice([[0, 3, 7], [0, 4, 7], [0, 3, 7, 10], [0, 5, 7], [0, 2, 7]])
        for n, i in enumerate(hits):
            oct_ = 12 * (n // len(chord) % 2)
            out[i] = _snap_pc(base + chord[n % len(chord)] + oct_, pcs)
        return out
    # walk: a bounded random walk, so consecutive notes are RELATED
    cur = base
    for i in hits:
        cur += rng.choice([-5, -3, -2, 0, 2, 3, 5])
        cur = _clampi(cur, base - 12, base + 12)
        out[i] = _snap_pc(cur, pcs)
    return out


def _snap_pc(note: int, pcs: set[int]) -> int:
    if not pcs:
        return _clampi(note, 24, 96)
    for d in (0, 1, -1, 2, -2, 3, -3):
        if (note + d) % 12 in pcs:
            return _clampi(note + d, 24, 96)
    return _clampi(note, 24, 96)


# --------------------------------------------------------------------------- #
# TIME-VARYING MATERIAL — living steps, step cycles, ratchets, per-step FX.
# None of this was generated at all before, so every pattern was frozen the moment it was
# made: it looped identically forever and the only variation was whatever the user added.
# --------------------------------------------------------------------------- #
_CYCLE_CHOICES = {"none": [1], "sparse": [1, 1, 1, 2, 3], "wide": [1, 2, 3, 4, 6, 8],
                  "dense": [1, 1, 2, 2, 3, 4]}


def time_plan(recipe: dict, pat: list[int], L: int, kind: str, rng: random.Random) -> dict:
    """Living steps, step-cycle conditions, ratchets and per-step FX for one voice."""
    hits = [i for i in range(L) if pat[i]]
    plan = {"living": {}, "cycle": {}, "ratchet": {}, "fx": {}, "fxcycle": {}}
    if not hits:
        return plan

    # LIVING — never the downbeat (the ear's anchor) and never more than a quarter of the
    # hits, or the rhythm stops being legible. Periods are made distinct so marked steps
    # transform on different bars instead of lurching together.
    frac = get(recipe, "living")
    want = min(4, int(round(len(hits) * frac)))
    cands = [i for i in hits if i != 0] or hits[1:]
    rng.shuffle(cands)
    used_p: set[int] = set()
    for i in cands[:want]:
        p = rng.choice([2, 3, 4, 5, 6, 8])
        for _ in range(6):
            if p not in used_p:
                break
            p = rng.choice([2, 3, 4, 5, 6, 8])
        used_p.add(p)
        plan["living"][i] = p

    # STEP CYCLES — a step that only fires every Nth pass makes the pattern longer than its
    # bar without adding a single note to it.
    ch = _CYCLE_CHOICES[get(recipe, "cycles")]
    if len(ch) > 1:
        for i in hits:
            if i == 0:
                continue                                  # keep the downbeat dependable
            c = rng.choice(ch)
            if c > 1:
                plan["cycle"][i] = c

    # RATCHETS — retriggers. Machine and glitch recipes lean on these; others barely.
    rp = get(recipe, "ratchet")
    for i in hits:
        if rng.random() < rp:
            plan["ratchet"][i] = rng.choice([2, 2, 3, 4])

    # PER-STEP FX — occasional, and never on every hit of a track.
    # step_fx is a BITMASK of inserts, not an index — a step can carry more than one.
    fp = get(recipe, "stepfx")
    if fp > 0:
        allowed = [0, 2, 3, 5, 6] if kind in (TEXTURE, FILL) else [0, 2, 5]
        for i in hits:
            if rng.random() < fp:
                bits = rng.sample(allowed, 1 if rng.random() < 0.75 else 2)
                mask = 0
                for b in bits:
                    mask |= (1 << b)
                plan["fx"][i] = mask
                plan["fxcycle"][i] = rng.choice([1, 1, 2, 3, 4])
    return plan


# --------------------------------------------------------------------------- #
# COORDINATION — the parts have to be generated against each other.
# --------------------------------------------------------------------------- #
def fit_density(row: list[int], L: int, target: float, rng: random.Random) -> list[int]:
    """Bring a generated row to the density the recipe actually asked for.

    stepgen's algorithms take a density, but they compress it hard — euclid maps it through
    `0.2 + density * 0.45`, so a request for 0.08 comes back at 0.2 and a request for 0.9
    comes back at 0.6. Every recipe's intent was being squeezed into that one band: measured
    across 25 patterns each, SPARSE landed at 0.26 and WALL at 0.47, and their ranges
    OVERLAPPED — a sparse pattern could be denser than a wall of noise, which is exactly the
    failure a recipe exists to prevent.

    The algorithm still chooses WHERE the hits go — that is the rhythmic dialect, and it is
    left alone. This only corrects HOW MANY. Removals prefer off-beats and additions prefer
    on-beats, so thinning opens the bar out rather than shredding it.
    """
    want = _clampi(int(round(L * target)), 1, L)
    out = list(row)
    hits = [i for i in range(L) if out[i]]
    if len(hits) > want:
        # drop off-beats first: they carry least of the algorithm's character
        order = sorted((i for i in hits if i != 0),
                       key=lambda i: (0 if i % 4 else 1, rng.random()))
        for i in order[:len(hits) - want]:
            out[i] = 0
    elif len(hits) < want:
        free = sorted((i for i in range(L) if not out[i]),
                      key=lambda i: (0 if i % 2 == 0 else 1, rng.random()))
        for i in free[:want - len(hits)]:
            out[i] = 1
    if not any(out[:L]):
        out[0] = 1
    return out


def interlock(pat: list[int], L: int, ref: list[int], rng: random.Random,
              avoid: float) -> list[int]:
    """Push a part off the reference part so the two interlock rather than double up."""
    out = list(pat)
    for i in range(L):
        if out[i] and i < len(ref) and ref[i] and rng.random() < avoid:
            out[i] = 0
            for j in (i + 1, i - 1, i + 2, i - 2):
                j %= L
                if not out[j] and not (j < len(ref) and ref[j]):
                    out[j] = 1
                    break
    if not any(out[:L]):
        out[rng.randrange(L)] = 1
    return out


def call_response(a: list[int], b: list[int], L: int) -> list[int]:
    """Give `b` the half of the bar `a` does not use, so they answer rather than overlap."""
    half = max(1, L // 2)
    first = sum(a[:half])
    out = list(b)
    lo, hi = (half, L) if first >= sum(a[half:L]) else (0, half)
    for i in range(L):
        if out[i] and not (lo <= i < hi):
            out[i] = 0
    if not any(out[:L]):
        out[lo + (hi - lo) // 2] = 1
    return out


def apply_contrast(pat: list[int], L: int, amount: float, rng: random.Random) -> list[int]:
    """Empty out a contiguous region so the bar has a hole in it."""
    if amount <= 0 or L < 8:
        return pat
    out = list(pat)
    span = max(2, int(L * rng.uniform(0.25, 0.45)))
    start = rng.randrange(L)
    for k in range(span):
        i = (start + k) % L
        if i != 0 and rng.random() < amount:
            out[i] = 0
    if not any(out[:L]):
        out[0] = 1
    return out


# --------------------------------------------------------------------------- #
# SCORING — judge a finished candidate before the user ever hears it.
#
# Each check is one of the ways these patterns actually go wrong. The score is a penalty
# (lower is better) and the notes say WHY, which is what makes a bad result diagnosable
# instead of merely unlucky.
# --------------------------------------------------------------------------- #
def score(voices: list[dict], recipe: dict) -> tuple[float, list[str]]:
    notes: list[str] = []
    if not voices:
        return 1e6, ["empty"]
    pen = 0.0
    L = max(v["length"] for v in voices)

    # --- simultaneity: everything landing on the same steps is the commonest failure
    hits_at = [0] * L
    for v in voices:
        for i in range(v["length"]):
            if v["pattern"][i]:
                hits_at[i % L] += 1
    crowd = sum(1 for c in hits_at if c >= max(3, len(voices) - 1))
    if crowd > L * 0.35:
        pen += (crowd - L * 0.35) * 1.4
        notes.append("too much simultaneous activity")

    # --- dead tracks
    dead = [v for v in voices if sum(v["pattern"][:v["length"]]) < 2]
    if dead:
        pen += len(dead) * 3.0
        notes.append("%d near-empty track(s)" % len(dead))

    # --- rhythmic contrast: two tracks with the same onset set are one track
    for i in range(len(voices)):
        for j in range(i + 1, len(voices)):
            a, b = voices[i], voices[j]
            n = min(a["length"], b["length"])
            if n < 4:
                continue
            same = sum(1 for k in range(n) if a["pattern"][k] == b["pattern"][k] == 1)
            tot = max(1, sum(a["pattern"][:n]) + sum(b["pattern"][:n]) - same)
            if same / tot > 0.8:
                pen += 2.5
                notes.append("%s and %s play the same rhythm" % (a["name"], b["name"]))

    # --- redundant roles
    kinds = [v["kind"] for v in voices]
    for k in set(kinds):
        if kinds.count(k) > 3:
            pen += (kinds.count(k) - 3) * 1.5
            notes.append("too many %s tracks" % k)

    # --- frequency distribution: everything in one octave is mud
    regs = [v.get("register", 0) for v in voices]
    if len(voices) >= 4 and len(set(regs)) == 1:
        pen += 2.5
        notes.append("all voices in one register")

    # --- accent structure: a pattern where nothing is louder than anything else is flat
    flat = sum(1 for v in voices if len(set(round(x, 1) for x in v["accents"].values())) <= 1
               and len(v["accents"]) > 3)
    if flat > len(voices) * 0.6:
        pen += 1.8
        notes.append("no accent variation")

    # --- variation over cycles: a pattern that never changes is a loop, not a piece
    varying = sum(1 for v in voices if v["time"]["living"] or v["time"]["cycle"])
    if varying == 0 and len(voices) >= 3:
        pen += 2.2
        notes.append("nothing varies over repeats")

    # --- effect overuse
    allfx = [f for v in voices for f in v["time"]["fx"].values()]
    if allfx and len(set(allfx)) == 1 and len(allfx) > 4:
        pen += 1.2
        notes.append("one effect used everywhere")

    # --- the recipe's own intent must survive the randomness
    dens = sum(sum(v["pattern"][:v["length"]]) for v in voices) / max(
        1, sum(v["length"] for v in voices))
    want = sum(get(recipe, "dens").get(v["kind"], 0.4) for v in voices) / len(voices)
    if abs(dens - want) > 0.28:
        pen += abs(dens - want) * 4.0
        notes.append("density %.2f drifted from the recipe's %.2f" % (dens, want))
    return pen, notes


def weakest(voices: list[dict], recipe: dict) -> int:
    """Index of the track contributing most to the penalty — the one worth regenerating."""
    if len(voices) < 2:
        return -1
    base, _ = score(voices, recipe)
    worst_i, worst_gain = -1, 0.0
    for i in range(len(voices)):
        without = voices[:i] + voices[i + 1:]
        s, _ = score(without, recipe)
        gain = base - s
        if gain > worst_gain:
            worst_gain, worst_i = gain, i
    return worst_i if worst_gain > 1.0 else -1


# --------------------------------------------------------------------------- #
# ROLE ASSIGNMENT — which ENGINE does which JOB.
#
# The engine categories (kick/perc/bass/tonal/texture/pad) say what a voice sounds like; the
# role says what it does in the pattern. Keeping them separate is what lets a recipe put the
# pulse on a bass or make a perc voice into texture, instead of every pattern being a drum
# kit with decoration.
# --------------------------------------------------------------------------- #
# how well an engine category suits each job (0 = never)
_FIT = {
    PULSE:   {"kick": 1.0, "perc": 0.5, "bass": 0.8, "tonal": 0.15, "texture": 0.2, "pad": 0.0},
    COUNTER: {"kick": 0.2, "perc": 1.0, "bass": 0.6, "tonal": 0.6, "texture": 0.5, "pad": 0.0},
    FILL:    {"kick": 0.0, "perc": 1.0, "bass": 0.1, "tonal": 0.4, "texture": 0.6, "pad": 0.0},
    TEXTURE: {"kick": 0.0, "perc": 0.3, "bass": 0.1, "tonal": 0.3, "texture": 1.0, "pad": 0.5},
    SUSTAIN: {"kick": 0.0, "perc": 0.0, "bass": 0.3, "tonal": 0.4, "texture": 0.4, "pad": 1.0},
    LEAD:    {"kick": 0.0, "perc": 0.1, "bass": 0.3, "tonal": 1.0, "texture": 0.2, "pad": 0.3},
    ACCENT:  {"kick": 0.4, "perc": 1.0, "bass": 0.3, "tonal": 0.4, "texture": 0.6, "pad": 0.0},
}


def assign_roles(recipe: dict, rng: random.Random) -> list[str]:
    """The list of JOBS this pattern needs, in the recipe's proportions."""
    n = rng.randint(*recipe["n"])
    jobs: list[str] = []
    for kind, cnt in recipe["roles"].items():
        jobs += [kind] * cnt
    rng.shuffle(jobs)
    # Always keep whatever the recipe leads with; trim or pad to the drawn size.
    while len(jobs) < n:
        jobs.append(rng.choice(list(recipe["roles"].keys())))
    return jobs[:n]


def fit_score(kind: str, cat: str) -> float:
    return _FIT.get(kind, {}).get(cat, 0.2)
