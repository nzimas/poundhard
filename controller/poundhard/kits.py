"""PoundHard kit generation.

A *kit* is the 16 track voices (type + note + parameter values) — the sound set.
It does NOT touch step patterns or mutes (those are the performance).

The allocation is FIXED and curated for PoundHard's scope (edgy IDM, rhythmic
noise, percussion-centric experimental electronica):

  Tracks 1-6   DRUM       — kick, snare, closed hat, open hat, clap, glitch perc
  Tracks 7-8   RINGS      — mallet/bell, sympathetic pluck (Mutable Rings)
  Track  9     BEN        — Benjolin (rungler) chaotic generative machine
  Tracks 10-11 BUCHLOID   — drone, noise texture
  Track  12    NOIZEOP    — deeg's 4-sine / 6-algorithm glitch-noise machine
  Tracks 13-14 FM7        — FM bass, metallic ornament (6-op FM)
  Tracks 15-16 MOLLY      — gritty lead/stab, corroded pad

Each role fixes the essentials (voice type, drum mode, register) and randomizes
the rest within role-appropriate bands, so every generated kit is different but
always idiomatic. Notes for the tonal voices are drawn from a dark scale.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import catalog
from .catalog import VOICES, VoiceSpec

# Dark, IDM-friendly scale (phrygian-ish) over a low root; tonal roles pick from it.
_ROOT = 33                                   # A1
_SCALE = [0, 1, 3, 5, 7, 8, 10, 12, 13, 15]  # phrygian degrees + octave


@dataclass
class Role:
    name: str
    type: str
    # exact param overrides (value space) — the role's fingerprint
    fixed: dict[str, float] = field(default_factory=dict)
    # per-param uniform bands (value space) that override the catalog `musical` band
    bands: dict[str, tuple[float, float]] = field(default_factory=dict)
    note: int | None = None                  # fixed MIDI note (drums); None = pick from choices
    note_choices: tuple[int, ...] = ()       # tonal: semitone offsets from _ROOT (scale tones)
    octave: int = 0                          # semitone offset applied to the picked note
    vel: tuple[float, float] = (0.85, 1.05)  # velocity band
    jitter: float = 0.85                     # randomize amount for un-pinned params


# --- the 16 fixed roles ----------------------------------------------------- #
ROLES: list[Role] = [
    # ---------------- 6 DRUM tracks (1-6) ----------------
    Role("KICK", "DRUM", note=33,
         fixed={"drum.mode": 0, "drum.filterType": 0, "drum.pan": 0.0},
         bands={"drum.transient": (0.55, 1.0), "drum.pitchMod": (0.5, 1.0),
                "drum.pitchDecay": (0.03, 0.09), "drum.ampDecay": (0.14, 0.42),
                "drum.cutoff": (600, 6000), "drum.noiseAmt": (0.0, 0.2),
                "drum.drive": (0.8, 2.4)}),
    Role("SNARE", "DRUM", note=49,
         fixed={"drum.mode": 1},
         bands={"drum.noiseAmt": (0.4, 0.85), "drum.noiseTone": (0.35, 0.8),
                "drum.snap": (0.45, 0.95), "drum.ampDecay": (0.1, 0.35),
                "drum.noiseDecay": (0.08, 0.3)}),
    Role("CL HAT", "DRUM", note=72,
         fixed={"drum.mode": 2, "drum.filterType": 2},
         bands={"drum.noiseDecay": (0.015, 0.06), "drum.noiseTone": (0.6, 0.95),
                "drum.noiseAmt": (0.3, 0.7), "drum.ampDecay": (0.015, 0.06)}),
    Role("OP HAT", "DRUM", note=74,
         fixed={"drum.mode": 2, "drum.filterType": 2},
         bands={"drum.noiseDecay": (0.18, 0.55), "drum.noiseTone": (0.55, 0.9),
                "drum.noiseAmt": (0.35, 0.75), "drum.ampDecay": (0.15, 0.5)}),
    Role("CLAP", "DRUM", note=60,
         fixed={"drum.mode": 4},
         bands={"drum.noiseTone": (0.3, 0.75), "drum.snap": (0.4, 0.9),
                "drum.noiseDecay": (0.06, 0.25), "drum.res": (0.1, 0.5)}),
    Role("PERC", "DRUM", note=64,        # metallic / glitch percussion (tracks 1-6 = drums)
         fixed={"drum.mode": 3},
         bands={"drum.ratio": (1.4, 9.0), "drum.fmAmt": (0.1, 0.6),
                "drum.harmonics": (0.2, 0.8), "drum.ampDecay": (0.05, 0.35),
                "drum.res": (0.15, 0.6), "drum.crush": (0.0, 0.45),
                "drum.downsample": (0.0, 0.45)}),
    # ---- 10 tonal / texture tracks, GROUPED by generator (contiguous step buttons) ----
    # ---- tracks 7-8: RINGS (mallet / sympathetic) ----
    Role("RING M", "RINGS", note_choices=(0, 3, 7, 12), octave=12,   # mallet / bell (low register)
         fixed={"rings.model": 0},
         bands={"rings.struct": (0.2, 0.7), "rings.bright": (0.6, 0.95),
                "rings.damp": (0.6, 0.9), "rings.pos": (0.1, 0.6),
                "rings.decay": (0.8, 2.5)}, vel=(0.75, 1.0)),
    Role("RING P", "RINGS", note_choices=(0, 5, 7, 10), octave=0,    # sympathetic pluck (low register)
         fixed={"rings.model": 1},
         bands={"rings.struct": (0.3, 0.75), "rings.bright": (0.45, 0.85),
                "rings.damp": (0.75, 0.95), "rings.pos": (0.15, 0.7),
                "rings.decay": (1.5, 4.5)}, vel=(0.75, 1.0)),
    # ---- track 9: BEN — Benjolin chaotic generative machine ----
    # osc2 stays LOW (it clocks the shift register): a few Hz gives the slow, stepped,
    # self-patterning sequences; the rungler amounts decide how far it runs away.
    Role("BEN", "BEN", note_choices=(0, 5, 7, 12), octave=0,
         bands={"ben.freq2": (0.8, 60), "ben.scale": (0.25, 1.0),
                "ben.rungler1": (0.05, 0.55), "ben.rungler2": (0.0, 0.35),
                "ben.runglerFilt": (2.0, 16.0), "ben.filtFreq": (30, 900),
                "ben.q": (0.45, 0.95), "ben.gain": (1.0, 5.0),
                "ben.decay": (0.25, 2.2)}, vel=(0.70, 1.0)),
    # ---- tracks 10-11: BUCHLOID (drone / noise texture) ----
    Role("DRONE", "BUCHLOID", note_choices=(0, 7), octave=12,
         bands={"buchloid.fm1Amount": (0.05, 0.4), "buchloid.fm2Amount": (0.0, 0.35),
                "buchloid.timbre": (0.1, 0.6), "buchloid.waveFolds": (0.2, 1.6),
                "buchloid.attack": (0.15, 0.9), "buchloid.decay": (1.2, 3.5),
                "buchloid.peak": (500, 4000)}, vel=(0.7, 0.95)),
    Role("NOISE", "BUCHLOID", note_choices=(0, 5), octave=12,
         bands={"buchloid.fm1Amount": (0.3, 0.8), "buchloid.fm2Amount": (0.3, 0.8),
                "buchloid.waveFolds": (1.0, 3.0), "buchloid.timbre": (0.4, 1.0),
                "buchloid.pressure": (0.2, 0.7), "buchloid.decay": (0.1, 0.8),
                "buchloid.peak": (800, 9000), "buchloid.res": (0.2, 0.7)}, vel=(0.7, 1.0)),
    # ---- track 12: NOIZEOP — deeg's 4-sine / 6-algorithm glitch-noise machine ----
    # The four oscillator RATIOS are spread apart so the algorithms (products,
    # ratios, trunc) beat against each other; low root keeps the cluster audible.
    Role("NOIZOP", "NOIZEOP", note_choices=(0, 5, 7), octave=0,
         bands={"noizeop.freq01": (0.5, 2.0), "noizeop.freq02": (0.75, 3.5),
                "noizeop.freq03": (1.0, 5.0), "noizeop.freq04": (1.5, 8.0),
                "noizeop.a_mod_01": (0.4, 3.0), "noizeop.a_mod_02": (0.4, 3.0),
                "noizeop.a_mod_03": (0.008, 0.15), "noizeop.a_mod_04": (0.5, 3.0),
                "noizeop.a_mod_05": (0.2, 1.6), "noizeop.a_mod_06": (0.2, 1.6),
                "noizeop.a_vol_01": (0.0, 1.0), "noizeop.a_vol_02": (0.0, 1.0),
                "noizeop.a_vol_03": (0.0, 1.0), "noizeop.a_vol_04": (0.0, 0.8),
                "noizeop.a_vol_05": (0.0, 0.7), "noizeop.a_vol_06": (0.0, 0.7),
                "noizeop.ffreq01": (30, 800), "noizeop.ffreq02": (1500, 14000),
                "noizeop.ffreq03": (200, 5000), "noizeop.q03": (0.06, 0.6),
                "noizeop.gain": (0.7, 4.0), "noizeop.decay": (0.15, 1.6)}, vel=(0.7, 1.0)),
    # ---- tracks 13-14: FM7 (FM bass / metallic ornament) ----
    Role("BASS", "FM7", note_choices=(0, 3, 5), octave=0,
         fixed={"fm7.algo": 3},                          # fmbass topology
         bands={"fm7.r1": (0.99, 1.01), "fm7.r2": (1.0, 2.5), "fm7.r3": (0.5, 1.01),
                "fm7.r4": (1.0, 3.0), "fm7.index": (1.0, 3.5), "fm7.fb": (0.1, 0.5),
                "fm7.decay": (0.15, 0.7), "fm7.mDecay": (0.25, 0.7), "fm7.bright": (0.4, 1.5)}),
    Role("ORNMNT", "FM7", note_choices=(7, 10, 12, 15), octave=24,
         fixed={"fm7.algo": 1},                          # clang (6-op chain) topology
         bands={"fm7.r1": (0.99, 1.01), "fm7.r2": (1.4, 6.0), "fm7.r3": (1.4, 6.0),
                "fm7.r4": (1.4, 7.0), "fm7.r5": (1.4, 6.0), "fm7.r6": (1.4, 6.0),
                "fm7.index": (2.0, 5.0), "fm7.fb": (0.1, 0.5), "fm7.decay": (0.1, 0.6),
                "fm7.mDecay": (0.3, 0.8), "fm7.bright": (0.7, 2.2)}),
    # ---- tracks 15-16: MOLLY (lead / pad) ----
    Role("M LEAD", "MOLLY", note_choices=(0, 7, 12), octave=24,      # gritty lead / stab
         bands={"molly.oscShape": (0.4, 1.0), "molly.cutoff": (900, 7000),
                "molly.resonance": (0.3, 0.78), "molly.filterEnvAmt": (0.2, 0.9),
                "molly.hold": (0.08, 0.5), "molly.aRel": (0.05, 0.6),
                "molly.drive": (0.35, 0.85), "molly.detune": (4, 28),
                "molly.ringMod": (0.0, 0.35), "molly.fmAmt": (0.10, 0.45),
                "molly.fold": (0.25, 0.80), "molly.crush": (0.15, 0.70),
                "molly.downsample": (0.0, 0.50), "molly.grit": (0.10, 0.50)}, vel=(0.75, 1.0)),
    Role("M PAD", "MOLLY", note_choices=(0, 3, 7, 10), octave=12,     # corroded pad / keys
         bands={"molly.oscShape": (0.0, 0.7), "molly.cutoff": (400, 3200),
                "molly.resonance": (0.15, 0.55), "molly.subLevel": (0.1, 0.5),
                "molly.hold": (0.4, 1.5), "molly.aSus": (0.6, 1.0), "molly.aRel": (0.4, 2.5),
                "molly.chorus": (0.15, 0.6), "molly.detune": (6, 30),
                "molly.drive": (0.20, 0.60), "molly.fmAmt": (0.0, 0.30),
                "molly.fold": (0.15, 0.60), "molly.crush": (0.10, 0.55),
                "molly.downsample": (0.05, 0.45), "molly.grit": (0.05, 0.35)}, vel=(0.65, 0.95)),
]


def _pick_note(role: Role, rng: random.Random) -> int:
    if role.note is not None:
        return role.note
    off = rng.choice(role.note_choices) if role.note_choices else 0
    return int(_ROOT + off + role.octave)


def gen_voice(role: Role, rng: random.Random) -> dict:
    """Generate one track's voice: {type, note, vel, sample, params:{pid:val}}."""
    spec: VoiceSpec = VOICES[role.type]
    params: dict[str, float] = {}
    sample = -1
    for meta in spec.params:
        pid = meta.id
        if pid == "sampler.sample":
            sample = rng.randrange(catalog.SAMPLE_COUNT) if catalog.SAMPLE_COUNT > 0 else -1
            continue
        if pid in role.fixed:
            val = float(role.fixed[pid])
        elif pid in role.bands:
            lo, hi = role.bands[pid]
            val = rng.uniform(lo, hi)
        else:
            val = meta.randomize(rng, meta.default, role.jitter, expert=False)
        # ENUM / discrete params must land on an integer whatever produced them — the
        # default randomizer returns floats, which would feed e.g. Select.ar a fractional
        # index (a filter type of "1.7").
        if meta.curve.name == "ENUM" or meta.rate.name == "DISCRETE":
            val = round(val)
        params[pid] = round(meta.clamp(val), 5)
    return {
        "type": role.type,
        "note": _pick_note(role, rng),
        "vel": round(rng.uniform(*role.vel), 3),
        "sample": sample,
        "params": params,
    }


def gen_kit(seed: int | None = None) -> dict:
    """Generate a full 16-track kit. Returns {name, seed, tracks:[16 voices]}."""
    rng = random.Random(seed)
    tracks = [gen_voice(role, rng) for role in ROLES]
    name = "KIT-%04d" % (rng.randrange(10000) if seed is None else (seed % 10000))
    return {"name": name, "seed": seed, "tracks": tracks}


# --------------------------------------------------------------------------- #
# ENGINE PALETTE — one generic role per assignable engine. These drive the
# top-row "engine pads": the user auditions a generated sound, re-rolls it
# (Shift+pad), and holds the pad + taps a track to assign it. Unlike the fixed
# 16-track roles above, an engine can land on any track. Each role generalizes
# its engine (wider note choices; drums roll every mode) while still pinning the
# essentials that keep a voice idiomatic.
# --------------------------------------------------------------------------- #
PALETTE_ENGINES = ["DRUM", "FM7", "BUCHLOID", "MOLLY", "RINGS", "BEN", "NOIZEOP",
                   "ICARUS", "PLAITS", "SHAKER", "MEMBRANE", "MALLET", "BOWED",
                   "PLUCK", "TUBE"]

# a canonical note per drum mode, so an auditioned/assigned drum sits in register
# (mode order matches catalog DRUM enum: kick snare hihat metal clap tom noise)
_DRUM_MODE_NOTE = [33, 49, 72, 64, 60, 45, 67]

PALETTE_ROLES: dict[str, Role] = {
    # DRUM — roll every mode; the note is fixed up per mode in gen_palette_voice.
    "DRUM": Role("DRUM", "DRUM", note=45, jitter=0.9),
    # FM7 — the algorithm (and its targeted role) is chosen per generation in
    # gen_palette_voice, like PLAITS; this is just the default entry.
    "BUCHLOID": Role("BUCHLOID", "BUCHLOID", note_choices=tuple(_SCALE), octave=12, jitter=0.85),
    "MOLLY": Role("MOLLY", "MOLLY", note_choices=tuple(_SCALE), octave=12, jitter=0.85,
                  bands={"molly.fold": (0.2, 0.7), "molly.grit": (0.1, 0.5)}),
    "RINGS": Role("RINGS", "RINGS", note_choices=tuple(_SCALE), octave=0, jitter=0.85),
    # BEN — keep osc2 LOW so it clocks the shift register (stepped sequences).
    "BEN": Role("BEN", "BEN", note_choices=(0, 5, 7, 12), octave=0, jitter=0.85,
                bands={"ben.freq2": (0.8, 60), "ben.rungler1": (0.05, 0.5),
                       "ben.runglerFilt": (2.0, 16.0), "ben.filtFreq": (30, 900)}),
    # NOIZEOP — spread the four oscillator ratios so the algorithms beat.
    "NOIZEOP": Role("NOIZOP", "NOIZEOP", note_choices=(0, 5, 7), octave=0, jitter=0.85,
                    bands={"noizeop.freq01": (0.5, 2.0), "noizeop.freq02": (0.75, 3.5),
                           "noizeop.freq03": (1.0, 5.0), "noizeop.freq04": (1.5, 8.0),
                           "noizeop.a_mod_03": (0.008, 0.15)}),
    # ICARUS — drones / pads: long-ish envelopes, moderate feedback.
    "ICARUS": Role("ICARUS", "ICARUS", note_choices=tuple(_SCALE), octave=0, jitter=0.85,
                   bands={"icarus.attack": (0.05, 1.5), "icarus.decay": (0.6, 3.5),
                          "icarus.release": (0.8, 4.0), "icarus.feedback": (0.2, 0.7),
                          "icarus.lpf": (600, 8000)}),
}


# --------------------------------------------------------------------------- #
# PLAITS — per-model targeting.
#
# Plaits' `model` doesn't just change the timbre, it redefines what its three macro
# knobs DO. `harm` is oscillator detune in the VA model, chord type in the chord
# model, grain density in the cloud, and punch in the bass drum. Randomising the
# three knobs blindly would waste 16 engines; so every model gets its own role: the
# job it does in a PoundHard kit, the register it wants, and bands that suit what
# those knobs actually control in THAT model.
#
# Fields: (model, name, category, note, harm, timbre, morph, decay)
# `note` is either an int (drums: fixed register) or (choices, octave) for pitched.
# --------------------------------------------------------------------------- #
_TONAL = (tuple(_SCALE), 12)
_LOW = ((0, 3, 5, 7), 0)

_PLAITS_SPEC = [
    # --- pitched / bass -----------------------------------------------------
    # VA: harm=detune between the two waveforms, timbre=pulse width, morph=waveform.
    (0, "PL VA", "bass", _LOW, (0.0, 0.35), (0.2, 0.8), (0.0, 1.0), (0.15, 0.45)),
    # Waveshaping: harm=waveshaper index, timbre=fold amount, morph=asymmetry. Nasty.
    (1, "PL WSHP", "tonal", _TONAL, (0.3, 0.9), (0.3, 0.95), (0.2, 0.9), (0.10, 0.40)),
    # 2-op FM: harm=ratio, timbre=modulation index, morph=feedback (kept moderate —
    # full feedback is noise, and we have NOIZEOP/BEN for that).
    (2, "PL FM", "bass", _LOW, (0.1, 0.8), (0.2, 0.85), (0.0, 0.5), (0.10, 0.45)),
    # Granular formant: vocal-ish buzz. harm=formant ratio, timbre=formant freq.
    (3, "PL FORM", "texture", _TONAL, (0.2, 0.9), (0.2, 0.9), (0.1, 0.9), (0.10, 0.40)),
    # Harmonic (additive): harm=number of spectral bumps, timbre=peak position. Organ-like.
    (4, "PL HARM", "pad", ((0, 7), 0), (0.2, 0.9), (0.1, 0.8), (0.0, 0.8), (0.50, 0.90)),
    # Wavetable: harm=bank, timbre=x, morph=y. Digital and evolving.
    (5, "PL WTBL", "tonal", _TONAL, (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.20, 0.60)),
    # Chord: harm=chord type, timbre=inversion, morph=waveform. The pad engine.
    (6, "PL CHRD", "pad", ((0, 5, 7), 0), (0.0, 1.0), (0.1, 0.8), (0.0, 1.0), (0.50, 0.90)),
    # Speech: harm=bank, timbre=formant shift, morph=phoneme. Unmistakably IDM.
    (7, "PL SPCH", "texture", _TONAL, (0.0, 1.0), (0.1, 0.9), (0.0, 1.0), (0.15, 0.50)),
    # Granular cloud: harm=density, timbre=grain duration, morph=pitch randomisation.
    (8, "PL CLOUD", "pad", ((0, 7), 0), (0.2, 0.9), (0.2, 0.9), (0.1, 0.8), (0.40, 0.90)),
    # Filtered noise: timbre=filter freq, morph=resonance. Pitched by the filter.
    (9, "PL NOIS", "texture", ((0, 5, 7), 12), (0.1, 0.9), (0.2, 0.9), (0.3, 0.95), (0.10, 0.50)),
    # Particle noise: dust/glitch. harm=density, timbre=freq, morph=Q. Rhythmic noise.
    (10, "PL PART", "texture", _TONAL, (0.2, 0.9), (0.2, 0.9), (0.3, 0.95), (0.10, 0.40)),
    # Inharmonic string: harm=inharmonicity (low keeps it a musical pluck),
    # timbre=excitation brightness, morph=decay.
    (11, "PL STRG", "tonal", ((0, 3, 5, 7, 10), 0), (0.05, 0.6), (0.2, 0.8), (0.3, 0.8), (0.30, 0.70)),
    # Modal resonator: mallets and bells — Plaits' answer to RINGS.
    (12, "PL MODL", "tonal", _TONAL, (0.05, 0.7), (0.2, 0.85), (0.3, 0.85), (0.30, 0.70)),
    # --- drums: pitched in their own register, short LPG ---------------------
    # Analog bass drum: harm=punch/attack, timbre=tone, morph=decay.
    (13, "PL BD", "kick", 36, (0.2, 0.8), (0.2, 0.7), (0.2, 0.6), (0.10, 0.35)),
    # Analog snare: harm=tone/noise balance, timbre=tone, morph=snap.
    (14, "PL SD", "perc", 52, (0.2, 0.8), (0.2, 0.8), (0.2, 0.6), (0.10, 0.35)),
    # Analog hi-hat: morph kept short so it stays a hat, not a cymbal wash.
    (15, "PL HH", "perc", 76, (0.2, 0.8), (0.3, 0.9), (0.1, 0.4), (0.05, 0.25)),
]


def _plaits_role(spec) -> Role:
    model, name, _cat, note, harm, timbre, morph, decay = spec
    kw = {}
    if isinstance(note, int):
        kw["note"] = note
    else:
        kw["note_choices"], kw["octave"] = note[0], note[1]
    return Role(name, "PLAITS",
                fixed={"plaits.model": float(model)},
                bands={"plaits.harm": harm, "plaits.timbre": timbre,
                       "plaits.morph": morph, "plaits.decay": decay,
                       "plaits.lpgColour": (0.15, 0.85), "plaits.aux": (0.0, 0.5)},
                vel=(0.8, 1.05), **kw)


PLAITS_ROLES: dict[str, Role] = {s[1]: _plaits_role(s) for s in _PLAITS_SPEC}
PLAITS_CAT: dict[str, str] = {s[1]: s[2] for s in _PLAITS_SPEC}
# so PLAITS is a generatable engine everywhere (palette pad, per-track re-roll); the
# model is chosen per generation in gen_palette_voice, not pinned here.
PALETTE_ROLES["PLAITS"] = PLAITS_ROLES["PL VA"]
# The palette pad leans toward the models that most define PoundHard's territory
# (speech, particles, waveshaping, modal, chords) without ever excluding the rest.
_PLAITS_WEIGHTS = {"PL SPCH": 3, "PL PART": 3, "PL WSHP": 3, "PL MODL": 3, "PL CHRD": 2,
                   "PL NOIS": 2, "PL STRG": 2, "PL WTBL": 2, "PL FORM": 2, "PL CLOUD": 2,
                   "PL VA": 2, "PL FM": 2, "PL HARM": 2, "PL BD": 1, "PL SD": 1, "PL HH": 1}


# --------------------------------------------------------------------------- #
# FM7 — per-algorithm targeting.
#
# FM7's `algo` selects a modulation topology, and each topology wants its own
# operator ratios to sound like the thing it's good at. Rolling 6 ratios + index
# blindly would mostly make noise; so each algorithm gets a role that pins the
# ratios that make it a bell / e-piano / clang / FM bass / metal / stab, in the
# register that suits it.  The six operators are ordered [op0..op5]; which are
# carriers vs modulators depends on the algorithm (see \phFm7 in synthdefs.scd).
#
# Fields: (algo, name, category, note, rbands[6], index, fb, decay, mDecay, bright)
# --------------------------------------------------------------------------- #
_ONE = (0.99, 1.01)
_FM7_SPEC = [
    # 0 EPIANO — three parallel 2-op stacks: carriers op0/op2/op4 near unison, integer mods.
    (0, "FM EP", "tonal", (tuple(_SCALE), 12),
     [_ONE, (1.0, 3.0), _ONE, (1.0, 4.0), (0.99, 2.01), (1.0, 3.0)],
     (0.5, 2.2), (0.0, 0.3), (0.25, 1.1), (0.35, 0.9), (0.6, 1.8)),
    # 1 CLANG — 6-op chain, carrier op0, inharmonic modulators. Metallic, percussive.
    (1, "FM CLANG", "texture", (tuple(_SCALE), 0),
     [_ONE, (1.4, 6.5), (1.4, 6.5), (1.4, 7.5), (1.4, 6.5), (1.4, 6.5)],
     (2.0, 6.0), (0.2, 0.6), (0.08, 0.5), (0.3, 0.8), (0.8, 2.4)),
    # 2 ORGAN — additive: carriers op0..op3 as a harmonic series, two soft modulators.
    (2, "FM ORGAN", "pad", ((0, 7), 0),
     [_ONE, (1.99, 2.01), (2.99, 3.01), (3.99, 4.01), (1.0, 4.0), (1.0, 5.0)],
     (0.3, 2.0), (0.0, 0.25), (0.5, 2.2), (0.5, 1.2), (0.5, 1.6)),
    # 3 FMBASS — carrier+modulator with feedback, plus a sub carrier. Low register.
    (3, "FM BASS", "bass", ((0, 3, 5, 7), 0),
     [_ONE, (1.0, 2.5), (0.5, 1.01), (1.0, 3.0), _ONE, _ONE],
     (1.0, 4.0), (0.1, 0.5), (0.12, 0.6), (0.25, 0.7), (0.4, 1.5)),
    # 4 BELL — one carrier hit by three inharmonic modulators + a body carrier. Long.
    (4, "FM BELL", "tonal", (tuple(_SCALE), 12),
     [_ONE, (1.41, 3.5), (2.0, 5.0), (3.0, 7.0), (2.0, 6.0), (0.5, 1.01)],
     (1.5, 5.0), (0.1, 0.5), (0.6, 2.5), (0.5, 1.2), (0.6, 2.2)),
    # 5 STAB — two stacked 3-op branches, feedback. Brassy near-integer ratios.
    (5, "FM STAB", "tonal", ((0, 5, 7), 12),
     [_ONE, (1.0, 2.5), (1.0, 3.0), (0.99, 2.01), (1.0, 3.0), (1.0, 4.0)],
     (1.5, 4.5), (0.1, 0.4), (0.12, 0.8), (0.4, 1.0), (0.7, 2.2)),
]


def _fm7_role(spec) -> Role:
    algo, name, _cat, note, rb, idx, fbb, dec, mdec, brt = spec
    kw = {}
    if isinstance(note, int):
        kw["note"] = note
    else:
        kw["note_choices"], kw["octave"] = note[0], note[1]
    bands = {"fm7.r%d" % (i + 1): rb[i] for i in range(6)}
    bands.update({"fm7.index": idx, "fm7.fb": fbb, "fm7.decay": dec,
                  "fm7.mDecay": mdec, "fm7.bright": brt})
    return Role(name, "FM7", fixed={"fm7.algo": float(algo)}, bands=bands,
                vel=(0.82, 1.05), **kw)


FM7_ROLES: dict[str, Role] = {s[1]: _fm7_role(s) for s in _FM7_SPEC}
FM7_CAT: dict[str, str] = {s[1]: s[2] for s in _FM7_SPEC}
PALETTE_ROLES["FM7"] = FM7_ROLES["FM EP"]
# lean toward the algorithms that most define PoundHard's edge (clang, bass, bell)
_FM7_WEIGHTS = {"FM CLANG": 3, "FM BASS": 3, "FM BELL": 3, "FM STAB": 2, "FM EP": 2, "FM ORGAN": 1}


# --------------------------------------------------------------------------- #
# SHAKER (STK Shakers) — per-instrument targeting. `instr` picks one of 23 stochastic
# shaker/scraper models; each wants its own energy / decay / object-count / resonance
# to sound like that instrument. Fields: (instr, name, note, energy, decay, objects,
# resfreq, dec).
# --------------------------------------------------------------------------- #
_SHAKER_SPEC = [
    (0,  "SHK MARACA",  60, (75, 120), (35, 80),  (12, 40),  (55, 110), (0.05, 0.22)),
    (1,  "SHK CABASA",  62, (70, 115), (40, 90),  (18, 55),  (60, 115), (0.05, 0.20)),
    (2,  "SHK SEKERE",  58, (70, 118), (40, 95),  (25, 70),  (40, 95),  (0.06, 0.28)),
    (3,  "SHK GUIRO",   57, (60, 110), (55, 110), (8, 30),   (35, 90),  (0.10, 0.45)),
    (5,  "SHK BAMBOO",  67, (55, 100), (60, 118), (30, 80),  (55, 110), (0.20, 0.9)),
    (6,  "SHK TAMB",    64, (70, 120), (45, 95),  (20, 60),  (50, 105), (0.08, 0.35)),
    (7,  "SHK SLEIGH",  69, (65, 115), (55, 110), (25, 75),  (60, 115), (0.15, 0.6)),
    (11, "SHK SAND",    55, (55, 100), (40, 90),  (4, 20),   (30, 85),  (0.08, 0.4)),
    (20, "SHK ROCKS",   48, (70, 120), (30, 75),  (4, 16),   (20, 70),  (0.05, 0.25)),
    (22, "SHK ANKLUNG", 65, (60, 110), (55, 115), (12, 40),  (55, 110), (0.15, 0.7)),
]


def _shaker_role(spec) -> Role:
    instr, name, note, en, dc, ob, rf, dec = spec
    return Role(name, "SHAKER", fixed={"shaker.instr": float(instr)}, note=note,
                bands={"shaker.energy": en, "shaker.decay": dc, "shaker.objects": ob,
                       "shaker.resfreq": rf, "shaker.dec": dec}, vel=(0.8, 1.05))


SHAKER_ROLES: dict[str, Role] = {s[1]: _shaker_role(s) for s in _SHAKER_SPEC}
PALETTE_ROLES["SHAKER"] = SHAKER_ROLES["SHK MARACA"]
_SHAKER_WEIGHTS = {"SHK MARACA": 3, "SHK CABASA": 2, "SHK SEKERE": 2, "SHK GUIRO": 2,
                   "SHK TAMB": 2, "SHK SAND": 2, "SHK ROCKS": 2, "SHK BAMBOO": 1,
                   "SHK SLEIGH": 1, "SHK ANKLUNG": 1}


# --------------------------------------------------------------------------- #
# MEMBRANE (MembraneCircle) — struck-membrane roles: tom / frame drum / gong. Note
# shifts tension (pitch); `loss` sets the ring time. (tension, loss, tone, note).
# --------------------------------------------------------------------------- #
_MEMBRANE_SPEC = [
    ("MEM TOM",   (0.04, 0.1),    (0.997, 0.9995),   (0.3, 0.7),  ((0, 3, 5, 7), 0)),
    ("MEM FRAME", (0.02, 0.06),   (0.994, 0.999),    (0.4, 0.85), ((0, 5, 7), 12)),
    ("MEM GONG",  (0.008, 0.03),  (0.9996, 0.99996), (0.2, 0.6),  ((0, 7), -12)),
]


def _membrane_role(spec) -> Role:
    name, tns, loss, tone, note = spec
    return Role(name, "MEMBRANE", note_choices=note[0], octave=note[1],
                bands={"membrane.tension": tns, "membrane.loss": loss,
                       "membrane.tone": tone, "membrane.strike": (0.1, 0.8)}, vel=(0.8, 1.05))


MEMBRANE_ROLES: dict[str, Role] = {s[0]: _membrane_role(s) for s in _MEMBRANE_SPEC}
PALETTE_ROLES["MEMBRANE"] = MEMBRANE_ROLES["MEM TOM"]
_MEMBRANE_WEIGHTS = {"MEM TOM": 3, "MEM FRAME": 2, "MEM GONG": 1}


# --------------------------------------------------------------------------- #
# MALLET (STK ModalBar) — per-instrument targeting. `instrument` selects a struck
# modal bar; note tunes it. Fields: (instr, name, note, hardness, position, vibGain,
# vibFreq, mix, decay).
# --------------------------------------------------------------------------- #
_MALLET_SPEC = [
    (0, "ML MARIMBA", (tuple(_SCALE), 12), (55, 110), (10, 60), (0, 10),  (10, 40), (20, 70), (0.2, 0.9)),
    (1, "ML VIBES",   (tuple(_SCALE), 12), (30, 80),  (10, 60), (10, 45), (15, 55), (20, 70), (0.8, 3.0)),
    (2, "ML AGOGO",   (tuple(_SCALE), 12), (70, 128), (20, 80), (0, 8),   (10, 40), (30, 90), (0.15, 0.7)),
    (3, "ML WOOD",    (tuple(_SCALE), 12), (80, 128), (5, 50),  (0, 5),   (10, 30), (20, 60), (0.1, 0.5)),
    (4, "ML RESO",    (tuple(_SCALE), 0),  (40, 100), (15, 70), (5, 30),  (12, 50), (25, 80), (0.5, 2.2)),
    (6, "ML BELLS",   (tuple(_SCALE), 12), (45, 100), (20, 80), (8, 40),  (14, 60), (25, 85), (0.6, 2.6)),
]


def _mallet_role(spec) -> Role:
    instr, name, note, hard, pos, vg, vf, mix, dec = spec
    return Role(name, "MALLET", fixed={"mallet.instrument": float(instr)},
                note_choices=note[0], octave=note[1],
                bands={"mallet.stickhardness": hard, "mallet.stickposition": pos,
                       "mallet.vibratogain": vg, "mallet.vibratofreq": vf,
                       "mallet.directmix": mix, "mallet.decay": dec}, vel=(0.8, 1.05))


MALLET_ROLES: dict[str, Role] = {s[1]: _mallet_role(s) for s in _MALLET_SPEC}
PALETTE_ROLES["MALLET"] = MALLET_ROLES["ML MARIMBA"]
_MALLET_WEIGHTS = {"ML MARIMBA": 3, "ML VIBES": 3, "ML BELLS": 2, "ML AGOGO": 2,
                   "ML WOOD": 2, "ML RESO": 1}


# --------------------------------------------------------------------------- #
# BOWED (STK BandedWG) — per-instrument targeting: uniform/tuned bar, glass, bowl.
# Fields: (instr, name, note, striking, bowpressure, bowmotion, resonance, velocity, decay).
# --------------------------------------------------------------------------- #
_BOWED_SPEC = [
    (0, "BW UBAR",  (tuple(_SCALE), 0),  1, (40, 110), (0, 60),  (60, 120), (30, 110), (0.3, 2.0)),
    (1, "BW TBAR",  (tuple(_SCALE), 12), 1, (40, 110), (0, 60),  (60, 120), (30, 110), (0.4, 2.2)),
    (2, "BW GLASS", (tuple(_SCALE), 12), 0, (50, 120), (10, 80), (70, 128), (40, 120), (0.8, 4.0)),
    (3, "BW BOWL",  ((0, 5, 7), 0),      0, (40, 110), (0, 70),  (75, 128), (30, 110), (1.5, 4.0)),
]


def _bowed_role(spec) -> Role:
    instr, name, note, strike, bp, bm, mr, bv, dec = spec
    return Role(name, "BOWED", fixed={"bowed.instr": float(instr), "bowed.striking": float(strike)},
                note_choices=note[0], octave=note[1],
                bands={"bowed.bowpressure": bp, "bowed.bowmotion": bm,
                       "bowed.modalresonance": mr, "bowed.bowvelocity": bv,
                       "bowed.decay": dec}, vel=(0.8, 1.05))


BOWED_ROLES: dict[str, Role] = {s[1]: _bowed_role(s) for s in _BOWED_SPEC}
PALETTE_ROLES["BOWED"] = BOWED_ROLES["BW TBAR"]
_BOWED_WEIGHTS = {"BW TBAR": 3, "BW GLASS": 2, "BW BOWL": 2, "BW UBAR": 2}


# --------------------------------------------------------------------------- #
# PLUCK (DWG plucked stiff string) — flavour roles. (name, note, pos, decay, damp, bright)
# --------------------------------------------------------------------------- #
_PLUCK_SPEC = [
    ("PK KOTO",  (tuple(_SCALE), 12), (0.1, 0.3),  (0.5, 2.0), (5, 25),  (0.5, 0.9)),
    ("PK CLAV",  (tuple(_SCALE), 0),  (0.05, 0.2), (0.15, 0.6),(20, 60), (0.4, 0.8)),
    ("PK HARP",  (tuple(_SCALE), 12), (0.2, 0.42), (1.5, 4.0), (3, 15),  (0.3, 0.7)),
    ("PK MUTED", (tuple(_SCALE), 0),  (0.08, 0.25),(0.2, 0.7), (25, 70), (0.2, 0.6)),
]


def _pluck_role(spec) -> Role:
    name, note, pos, dec, damp, brt = spec
    return Role(name, "PLUCK", note_choices=note[0], octave=note[1],
                bands={"pluck.pos": pos, "pluck.decay": dec, "pluck.damp": damp,
                       "pluck.bright": brt}, vel=(0.8, 1.05))


PLUCK_ROLES: dict[str, Role] = {s[0]: _pluck_role(s) for s in _PLUCK_SPEC}
PALETTE_ROLES["PLUCK"] = PLUCK_ROLES["PK KOTO"]
_PLUCK_WEIGHTS = {"PK KOTO": 3, "PK CLAV": 2, "PK HARP": 2, "PK MUTED": 2}


# --------------------------------------------------------------------------- #
# TUBE (TwoTube waveguide) — flavour roles. (name, note, k, loss, balance, decay)
# --------------------------------------------------------------------------- #
_TUBE_SPEC = [
    ("TB HOLLOW", (tuple(_SCALE), 12), (0.005, 0.05), (0.98, 0.999), (0.3, 0.7), (0.4, 2.0)),
    ("TB REEDY",  (tuple(_SCALE), 0),  (0.02, 0.12),  (0.96, 0.99),  (0.2, 0.5), (0.2, 1.2)),
]


def _tube_role(spec) -> Role:
    name, note, k, loss, bal, dec = spec
    return Role(name, "TUBE", note_choices=note[0], octave=note[1],
                bands={"tube.k": k, "tube.loss": loss, "tube.balance": bal,
                       "tube.decay": dec}, vel=(0.8, 1.05))


TUBE_ROLES: dict[str, Role] = {s[0]: _tube_role(s) for s in _TUBE_SPEC}
PALETTE_ROLES["TUBE"] = TUBE_ROLES["TB HOLLOW"]
_TUBE_WEIGHTS = {"TB HOLLOW": 3, "TB REEDY": 2}


def gen_palette_voice(engine: str, rng: random.Random | None = None) -> dict:
    """Generate one fresh sound for an engine's palette pad (audition / assign)."""
    rng = rng or random.Random()
    if engine == "PLAITS":
        # pick a MODEL first, then generate through that model's own targeted role —
        # the three macro knobs mean something different in each.
        names = list(_PLAITS_WEIGHTS)
        name = rng.choices(names, weights=[_PLAITS_WEIGHTS[n] for n in names])[0]
        return gen_voice(PLAITS_ROLES[name], rng)
    if engine == "FM7":
        # pick an ALGORITHM first, then generate through its targeted role — the six
        # operator ratios mean something different under each topology.
        names = list(_FM7_WEIGHTS)
        name = rng.choices(names, weights=[_FM7_WEIGHTS[n] for n in names])[0]
        return gen_voice(FM7_ROLES[name], rng)
    if engine == "SHAKER":
        # pick an INSTRUMENT model first, then its targeted role.
        names = list(_SHAKER_WEIGHTS)
        name = rng.choices(names, weights=[_SHAKER_WEIGHTS[n] for n in names])[0]
        return gen_voice(SHAKER_ROLES[name], rng)
    if engine == "MEMBRANE":
        names = list(_MEMBRANE_WEIGHTS)
        name = rng.choices(names, weights=[_MEMBRANE_WEIGHTS[n] for n in names])[0]
        return gen_voice(MEMBRANE_ROLES[name], rng)
    if engine == "MALLET":
        names = list(_MALLET_WEIGHTS)
        name = rng.choices(names, weights=[_MALLET_WEIGHTS[n] for n in names])[0]
        return gen_voice(MALLET_ROLES[name], rng)
    if engine == "BOWED":
        names = list(_BOWED_WEIGHTS)
        name = rng.choices(names, weights=[_BOWED_WEIGHTS[n] for n in names])[0]
        return gen_voice(BOWED_ROLES[name], rng)
    if engine == "PLUCK":
        names = list(_PLUCK_WEIGHTS)
        name = rng.choices(names, weights=[_PLUCK_WEIGHTS[n] for n in names])[0]
        return gen_voice(PLUCK_ROLES[name], rng)
    if engine == "TUBE":
        names = list(_TUBE_WEIGHTS)
        name = rng.choices(names, weights=[_TUBE_WEIGHTS[n] for n in names])[0]
        return gen_voice(TUBE_ROLES[name], rng)
    voice = gen_voice(PALETTE_ROLES[engine], rng)
    if engine == "DRUM":                       # put the drum in register for its mode
        mode = int(round(voice["params"].get("drum.mode", 0)))
        voice["note"] = _DRUM_MODE_NOTE[max(0, min(6, mode))]
    return voice


ROLE_NAMES = [r.name for r in ROLES]
ROLE_TYPES = [r.type for r in ROLES]
