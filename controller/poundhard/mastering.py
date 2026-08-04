"""MASTERING — eight chains on one continuum, from restrained to destroyed.

WHY A PROFILE IS A SET OF NUMBERS AND NOT A DIFFERENT GRAPH. The obvious design is eight
synthdefs and a crossfade between them. It is also the design that clicks: swapping graphs
means building and freeing nodes under the audio thread, and the moment of overlap is where
gain jumps and dropouts live. Instead the engine runs ONE chain with every stage present,
and a profile is a set of amounts for those stages. Every amount is lagged in the synth, so
changing profile is a 120 ms glide along the same signal path. Nothing is created, freed or
reordered, so there is nothing that CAN click.

The cost of that choice is that the stage ORDER is fixed. It is the order that behaves —
tone before dynamics, dynamics before saturation, saturation before clipping, limiter last —
and the profiles get their distinct identities from which stages they lean on rather than
from rearranging them.

THE PROGRESSION IS THE FEATURE. These are not eight presets that happen to sit next to each
other; each parameter moves monotonically (or close to it) across the eight, so moving right
always means more control, more density and more pressure. The test asserts that.

WHAT MAKES THEM SOUND DIFFERENT rather than just louder: saturation is gain-compensated, so
drive adds harmonics without adding level, and the profiles differ in WHERE the density comes
from — compression on 3, multiband on 4-5, saturation on 5-6, clipping on 7-8.
"""
from __future__ import annotations

# Every parameter of the chain, with the range a knob sweeps it over.
#   name: (lo, hi, label)
PARAMS = {
    "eqTilt":   (-1.0, 1.0, "TILT"),      # -1 weight, +1 air
    "eqLow":    (-0.6, 1.0, "LOW"),
    "eqHigh":   (-0.6, 1.0, "HIGH"),
    "cThresh":  (0.05, 1.0, "THRESH"),
    "cRatio":   (1.0, 12.0, "RATIO"),
    "cAtk":     (0.0008, 0.06, "ATTACK"),
    "cRel":     (0.03, 0.8, "RELEASE"),
    "cMakeup":  (1.0, 3.0, "MAKEUP"),
    "mbAmt":    (0.0, 1.0, "MBAND"),
    "mbThresh": (0.05, 0.9, "MB THR"),
    "satAmt":   (0.0, 1.0, "SATURATE"),
    "clipAmt":  (0.0, 1.0, "SOFTCLIP"),
    "clipHard": (0.0, 1.0, "HARDCLIP"),
    "ceiling":  (0.5, 0.99, "CEILING"),
    "outGain":  (0.4, 2.2, "OUT"),
    "width":    (0.0, 1.8, "WIDTH"),
    "mix":      (0.0, 1.0, "MIX"),
}

# --------------------------------------------------------------------------- #
# THE EIGHT. Left to right: more dynamic control, more density, more pressure.
#
# `knobs` is which eight parameters the top row exposes for that profile — only the ones
# that actually do something there. A knob that moves a parameter the profile does not use
# is worse than no knob at all.
# --------------------------------------------------------------------------- #
PROFILES = [
    {"name": "GLASS", "blurb": "barely there — level and a ceiling",
     "set": {"eqTilt": 0.0, "eqLow": 0.0, "eqHigh": 0.05,
             "cThresh": 0.85, "cRatio": 1.6, "cAtk": 0.03, "cRel": 0.35, "cMakeup": 1.05,
             "mbAmt": 0.0, "mbThresh": 0.6, "satAmt": 0.0, "clipAmt": 0.0, "clipHard": 0.0,
             "ceiling": 0.95, "outGain": 1.0, "width": 1.0, "mix": 1.0},
     "knobs": ["outGain", "eqTilt", "cThresh", "cRatio", "cRel", "width", "ceiling", "mix"]},

    {"name": "FIRM", "blurb": "gentle glue, a little lift",
     "set": {"eqTilt": 0.05, "eqLow": 0.1, "eqHigh": 0.12,
             "cThresh": 0.62, "cRatio": 2.4, "cAtk": 0.02, "cRel": 0.28, "cMakeup": 1.2,
             "mbAmt": 0.15, "mbThresh": 0.55, "satAmt": 0.06, "clipAmt": 0.0, "clipHard": 0.0,
             "ceiling": 0.94, "outGain": 1.08, "width": 1.05, "mix": 1.0},
     "knobs": ["outGain", "cThresh", "cRatio", "cRel", "eqTilt", "satAmt", "width", "ceiling"]},

    {"name": "GRIP", "blurb": "the compressor is doing real work now",
     "set": {"eqTilt": 0.0, "eqLow": 0.18, "eqHigh": 0.15,
             "cThresh": 0.42, "cRatio": 3.6, "cAtk": 0.012, "cRel": 0.2, "cMakeup": 1.45,
             "mbAmt": 0.3, "mbThresh": 0.5, "satAmt": 0.12, "clipAmt": 0.05, "clipHard": 0.0,
             "ceiling": 0.95, "outGain": 1.15, "width": 1.08, "mix": 1.0},
     "knobs": ["cThresh", "cRatio", "cAtk", "cRel", "cMakeup", "satAmt", "outGain", "eqTilt"]},

    {"name": "BAND", "blurb": "multiband takes over — the kick stops ducking everything",
     "set": {"eqTilt": -0.05, "eqLow": 0.25, "eqHigh": 0.2,
             "cThresh": 0.4, "cRatio": 4.0, "cAtk": 0.008, "cRel": 0.16, "cMakeup": 1.55,
             "mbAmt": 0.62, "mbThresh": 0.4, "satAmt": 0.2, "clipAmt": 0.1, "clipHard": 0.0,
             "ceiling": 0.94, "outGain": 1.22, "width": 1.12, "mix": 1.0},
     "knobs": ["mbAmt", "mbThresh", "cThresh", "cRatio", "satAmt", "eqLow", "outGain", "width"]},

    {"name": "IRON", "blurb": "dense and forward, saturation carrying the weight",
     "set": {"eqTilt": -0.1, "eqLow": 0.3, "eqHigh": 0.25,
             "cThresh": 0.32, "cRatio": 5.0, "cAtk": 0.005, "cRel": 0.13, "cMakeup": 1.7,
             "mbAmt": 0.75, "mbThresh": 0.34, "satAmt": 0.36, "clipAmt": 0.2, "clipHard": 0.05,
             "ceiling": 0.94, "outGain": 1.34, "width": 1.15, "mix": 1.0},
     "knobs": ["satAmt", "cThresh", "cRatio", "mbAmt", "clipAmt", "eqLow", "outGain", "width"]},

    {"name": "FORGE", "blurb": "overdriven — harmonics are the point",
     "set": {"eqTilt": -0.12, "eqLow": 0.35, "eqHigh": 0.3,
             "cThresh": 0.26, "cRatio": 6.5, "cAtk": 0.003, "cRel": 0.1, "cMakeup": 1.85,
             "mbAmt": 0.8, "mbThresh": 0.28, "satAmt": 0.55, "clipAmt": 0.35, "clipHard": 0.15,
             "ceiling": 0.94, "outGain": 1.48, "width": 1.18, "mix": 1.0},
     "knobs": ["satAmt", "clipAmt", "cThresh", "cRatio", "mbAmt", "outGain", "eqTilt", "ceiling"]},

    {"name": "ANVIL", "blurb": "clipped, compact, physically forceful",
     "set": {"eqTilt": -0.15, "eqLow": 0.42, "eqHigh": 0.34,
             "cThresh": 0.2, "cRatio": 8.5, "cAtk": 0.0018, "cRel": 0.075, "cMakeup": 2.0,
             "mbAmt": 0.85, "mbThresh": 0.22, "satAmt": 0.7, "clipAmt": 0.55, "clipHard": 0.4,
             "ceiling": 0.94, "outGain": 1.62, "width": 1.2, "mix": 1.0},
     "knobs": ["clipHard", "clipAmt", "satAmt", "cThresh", "cRatio", "mbAmt", "outGain", "eqLow"]},

    {"name": "RUIN", "blurb": "the loudest thing this box will do on purpose",
     "set": {"eqTilt": -0.18, "eqLow": 0.5, "eqHigh": 0.4,
             "cThresh": 0.14, "cRatio": 11.0, "cAtk": 0.001, "cRel": 0.05, "cMakeup": 2.3,
             "mbAmt": 0.9, "mbThresh": 0.16, "satAmt": 0.88, "clipAmt": 0.78, "clipHard": 0.72,
             "ceiling": 0.94, "outGain": 1.95, "width": 1.22, "mix": 1.0},
     "knobs": ["clipHard", "clipAmt", "satAmt", "cThresh", "cMakeup", "mbAmt", "outGain", "ceiling"]},
]

N_PROFILES = len(PROFILES)

# Profile -1 means BYPASS: the chain still runs (it always runs) but every stage sits at
# unity and the limiter alone protects the output. Pressing the lit pad returns here, so
# there is always a way back to "no mastering" without hunting for one.
BYPASS = {
    "eqTilt": 0.0, "eqLow": 0.0, "eqHigh": 0.0,
    "cThresh": 1.0, "cRatio": 1.0, "cAtk": 0.01, "cRel": 0.2, "cMakeup": 1.0,
    "mbAmt": 0.0, "mbThresh": 0.5, "satAmt": 0.0, "clipAmt": 0.0, "clipHard": 0.0,
    "ceiling": 0.95, "outGain": 1.0, "width": 1.0, "mix": 1.0,
}


def profile_values(idx: int) -> dict:
    """The full parameter set for a profile (or bypass), as a fresh dict."""
    if not (0 <= idx < N_PROFILES):
        return dict(BYPASS)
    return dict(PROFILES[idx]["set"])


def knob_params(idx: int) -> list:
    return list(PROFILES[idx]["knobs"]) if 0 <= idx < N_PROFILES else []


def norm(param: str, value: float) -> float:
    """A parameter's value as 0..1, for the knob and the readout."""
    lo, hi = PARAMS[param][0], PARAMS[param][1]
    return 0.0 if hi <= lo else max(0.0, min(1.0, (float(value) - lo) / (hi - lo)))


def denorm(param: str, pos: float) -> float:
    lo, hi = PARAMS[param][0], PARAMS[param][1]
    return lo + max(0.0, min(1.0, float(pos))) * (hi - lo)


def label(param: str) -> str:
    return PARAMS[param][2]
