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
    # TONAL POLES: explicit macro vectors this role should land ON, rather than a box to
    # draw inside. See the CSOUND table for why a box does not work.
    poles: tuple = ()
    spread: float = 0.1                      # how far a roll wanders off its chosen pole


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
    if role.type == "WTABLE":
        # wt1/wt2 are sprite selectors; the generic randomizer would pick across the
        # whole bank INCLUDING the Noise category (which reads as white noise). Draw two
        # DISTINCT musical sprites instead, so both oscillators carry timbre.
        pool = catalog.WT_MUSICAL_INDICES
        i1 = rng.choice(pool)
        i2 = rng.choice(pool) if len(pool) < 2 else rng.choice([x for x in pool if x != i1])
        params["wtable.wt1"] = float(i1)
        params["wtable.wt2"] = float(i2)
    if role.poles:
        # AIM AT A POLE, do not average into the middle. The eight macros are drawn as ONE
        # coherent vector — pick a pole, wander a little way off it, and occasionally push a
        # couple of macros the rest of the way to an extreme. Drawing them independently is
        # what made every Csound voice land near the centroid of its architecture and sound
        # like every other one.
        pole = rng.choice(role.poles)
        spread = role.spread
        extremes = rng.sample(range(len(pole)), k=rng.randint(0, 2))
        for i, target in enumerate(pole):
            v = target + rng.gauss(0.0, spread)
            if i in extremes:
                # a deliberate excursion: ride this macro to whichever end it is nearer
                v = (v * 0.35) if target < 0.5 else (1.0 - ((1.0 - v) * 0.35))
            pid = "csound.m%d" % (i + 1)
            meta = next((m for m in spec.params if m.id == pid), None)
            if meta is not None:
                params[pid] = round(meta.clamp(max(0.0, min(1.0, v))), 5)
    if role.type == "BYTEBEAT":
        # expr is a bank index (not a synth arg): land it on a clean integer expression.
        params["bytebeat.expr"] = float(rng.randrange(catalog.BB_EXPR_COUNT))
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
                   "PLUCK", "TUBE", "CHAOS", "WTABLE", "BYTEBEAT", "SAMPLE", "CSOUND"]
# "MIC" is absent: the engine is complete but the Move never switches its audio input on.
# See the MIC_ENABLED note in ui.js.

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
    # ICARUS — evolving pads: it must SPEAK in a groove, so attacks stay short-ish and
    # feedback moderate (high feedback washes the tone into a quiet drone); brighter filter,
    # some drive for presence. Long pads still come from long track notes, not a 2s attack.
    # OCTAVE 12, not 0. _ROOT is A1, so at octave 0 this ran 33..48 — the bottom of it
    # below C2, where a saw pad with a sub an octave under it is felt rather than heard and
    # disappears into the kick. Up one octave puts the whole range at A2..C4.
    "ICARUS": Role("ICARUS", "ICARUS", note_choices=tuple(_SCALE), octave=12, jitter=0.85,
                   bands={"icarus.attack": (0.005, 0.2), "icarus.decay": (0.4, 2.0),
                          "icarus.release": (0.4, 2.5), "icarus.sustain": (0.6, 0.92),
                          "icarus.feedback": (0.1, 0.45), "icarus.lpf": (1800, 10000),
                          "icarus.resonance": (0.05, 0.4), "icarus.gain": (2.4, 4.2),
                          "icarus.destruction": (0.0, 2.5), "icarus.sublevel": (0.25, 0.6),
                          "icarus.pwmwidth": (0.05, 0.3)}),
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


# HOW EACH MODEL SHOULD MOVE. Per model, because the macros mean different things in each
# one and so does moving them: sweeping `timbre` on the waveshaper is a fold opening, on the
# speech model it is a formant shift, and on the hi-hat it is the difference between a hat
# and a cymbal. Fields: sweep depths for harm/timbre/morph (signed — negative falls), drift
# depths for the same three, LFO rate in Hz, contour shape (negative = fast fall, positive =
# slow swell), vibrato, drive, tone tilt.
_PLAITS_MOD = {
    # VA — morph walks the waveform, drive thickens it. A bass that opens slightly.
    0:  dict(mE=(0.0, 0.1), tE=(0.1, 0.3), mrE=(-0.3, 0.3), tL=(0.02, 0.1),
             rate=(0.1, 0.7), curve=(-0.6, 0.1), drive=(0.15, 0.45), tilt=(-0.35, 0.0)),
    # Waveshaping — the fold is the sound, so timbre sweeps hard and fast.
    1:  dict(tE=(-0.6, 0.6), mrE=(-0.3, 0.4), tL=(0.05, 0.2), mrL=(0.05, 0.2),
             rate=(0.3, 2.5), curve=(-0.8, 0.2), drive=(0.1, 0.5), tilt=(0.0, 0.4)),
    # FM — index sweep IS an FM patch. Falling index = a struck bass.
    2:  dict(tE=(-0.7, 0.2), mE=(-0.15, 0.15), tL=(0.02, 0.12),
             rate=(0.1, 1.2), curve=(-0.9, -0.2), drive=(0.1, 0.4), tilt=(-0.3, 0.1)),
    # Formant — moving the formant is the whole point; vocal glide.
    3:  dict(tE=(-0.5, 0.5), mrE=(-0.4, 0.4), tL=(0.08, 0.3), mrL=(0.05, 0.25),
             rate=(0.4, 3.0), curve=(-0.5, 0.5), fm=(0.0, 0.08), drive=(0.0, 0.3)),
    # Harmonic — a drawbar organ opening: slow swell, no drive.
    4:  dict(hE=(0.1, 0.45), tE=(0.1, 0.4), hL=(0.03, 0.15), tL=(0.03, 0.15),
             rate=(0.05, 0.5), curve=(0.2, 0.9), tilt=(-0.2, 0.3)),
    # Wavetable — scanning the table is what it is for. Wide, slow, both axes.
    5:  dict(hE=(-0.4, 0.4), tE=(-0.5, 0.5), mrE=(-0.5, 0.5), tL=(0.1, 0.35),
             mrL=(0.1, 0.35), rate=(0.08, 1.5), curve=(-0.6, 0.6), tilt=(-0.3, 0.35)),
    # Chord — the chord itself must hold still or it arpeggiates; move the waveform only.
    6:  dict(mrE=(-0.35, 0.35), mrL=(0.05, 0.2), tL=(0.03, 0.12),
             rate=(0.03, 0.35), curve=(0.1, 0.8), tilt=(-0.3, 0.2)),
    # Speech — morph walks the phoneme. Fast and wide, or it is one vowel forever.
    7:  dict(tE=(-0.5, 0.5), mrE=(-0.7, 0.7), mrL=(0.1, 0.35), tL=(0.05, 0.25),
             rate=(0.5, 4.0), curve=(-0.7, 0.7), drive=(0.0, 0.35)),
    # Cloud — grain density and pitch spread drifting: a texture, not a note.
    8:  dict(hE=(-0.3, 0.35), tE=(-0.3, 0.35), hL=(0.1, 0.3), tL=(0.1, 0.3),
             mrL=(0.08, 0.3), rate=(0.05, 0.8), curve=(-0.3, 0.8), tilt=(-0.4, 0.2)),
    # Filtered noise — the filter sweep IS the gesture.
    9:  dict(tE=(-0.7, 0.7), mrE=(-0.3, 0.3), tL=(0.08, 0.3),
             rate=(0.2, 2.5), curve=(-0.8, 0.5), tilt=(-0.2, 0.4)),
    # Particle — density and Q moving makes it rhythmic instead of a hiss.
    10: dict(hE=(-0.4, 0.4), tE=(-0.4, 0.4), hL=(0.1, 0.3), mrL=(0.08, 0.3),
             rate=(0.3, 4.0), curve=(-0.6, 0.6), drive=(0.0, 0.3), tilt=(0.0, 0.4)),
    # String — brightness falls as a plucked string does. Inharmonicity stays put.
    11: dict(tE=(-0.6, -0.1), mrE=(-0.3, 0.2), hL=(0.01, 0.06),
             rate=(0.05, 0.6), curve=(-0.9, -0.3), fm=(0.0, 0.06), drive=(0.05, 0.3)),
    # Modal — a struck bar: excitation brightness collapses, body rings on.
    12: dict(tE=(-0.6, -0.1), mrE=(-0.25, 0.25), hL=(0.01, 0.08),
             rate=(0.05, 0.8), curve=(-0.9, -0.3), fm=(0.0, 0.05), tilt=(-0.2, 0.25)),
    # Drums: the sweep is the transient. Short, downward, drive for weight.
    13: dict(tE=(-0.4, -0.05), mrE=(-0.25, 0.0), rate=(0.05, 0.4),
             curve=(-1.0, -0.5), drive=(0.2, 0.55), tilt=(-0.4, -0.05)),
    14: dict(tE=(-0.45, -0.05), mrE=(-0.3, 0.1), rate=(0.05, 0.5),
             curve=(-1.0, -0.5), drive=(0.15, 0.5), tilt=(-0.1, 0.3)),
    15: dict(tE=(-0.35, 0.1), mrE=(-0.25, 0.05), rate=(0.1, 0.6),
             curve=(-1.0, -0.4), drive=(0.05, 0.35), tilt=(0.1, 0.5)),
}
_MOD_PARAM = {"hE": "harmEnv", "tE": "timbEnv", "mrE": "morphEnv",
              "hL": "harmLfo", "tL": "timbLfo", "mrL": "morphLfo",
              "rate": "modRate", "curve": "modCurve", "fm": "fmDepth",
              "drive": "drive", "tilt": "tilt"}
# `mE` was a typo-prone alias for harm sweep in a couple of rows; accept it too.
_MOD_PARAM["mE"] = "harmEnv"


def _plaits_role(spec) -> Role:
    model, name, _cat, note, harm, timbre, morph, decay = spec
    kw = {}
    if isinstance(note, int):
        kw["note"] = note
    else:
        kw["note_choices"], kw["octave"] = note[0], note[1]
    bands = {"plaits.harm": harm, "plaits.timbre": timbre,
             "plaits.morph": morph, "plaits.decay": decay,
             "plaits.lpgColour": (0.15, 0.85), "plaits.aux": (0.0, 0.5)}
    for key, band in _PLAITS_MOD.get(model, {}).items():
        bands["plaits." + _MOD_PARAM[key]] = band
    return Role(name, "PLAITS",
                fixed={"plaits.model": float(model)},
                bands=bands,
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


# --------------------------------------------------------------------------- #
# CHAOS (chaotic-map oscillator) — per-map targeting. (type, name, note, chaosA,
# chaosB, fold, cutoff, decay). A texture/noise voice in the BEN/NOIZEOP spirit.
# --------------------------------------------------------------------------- #
_CHAOS_SPEC = [
    (0, "CH FBSINE", (0, 5, 7), (0.5, 3.0), (0.2, 2.5), (0.0, 0.5), (400, 10000), (0.1, 1.0)),
    (1, "CH LATOO",  (0, 5, 7), (0.5, 3.5), (0.3, 2.0), (0.0, 0.5), (600, 12000), (0.15, 1.2)),
    (2, "CH HENON",  (0, 5, 7), (1.0, 3.0), (0.5, 2.0), (0.0, 0.4), (500, 9000),  (0.1, 0.8)),
    (3, "CH STD",    (0, 5, 7), (1.0, 3.0), (0.2, 1.5), (0.0, 0.4), (400, 8000),  (0.1, 0.9)),
    (4, "CH CUSP",   (0, 5, 7), (0.8, 2.5), (0.3, 2.0), (0.0, 0.5), (500, 10000), (0.1, 0.9)),
]


def _chaos_role(spec) -> Role:
    typ, name, note, ca, cb, fold, cut, dec = spec
    return Role(name, "CHAOS", fixed={"chaos.type": float(typ)},
                note_choices=note, octave=0,
                bands={"chaos.chaosA": ca, "chaos.chaosB": cb, "chaos.fold": fold,
                       "chaos.cutoff": cut, "chaos.decay": dec}, vel=(0.75, 1.0))


CHAOS_ROLES: dict[str, Role] = {s[1]: _chaos_role(s) for s in _CHAOS_SPEC}
PALETTE_ROLES["CHAOS"] = CHAOS_ROLES["CH FBSINE"]
_CHAOS_WEIGHTS = {"CH FBSINE": 3, "CH LATOO": 2, "CH HENON": 2, "CH STD": 2, "CH CUSP": 2}


# --------------------------------------------------------------------------- #
# WTABLE (Ableton-sprite wavetable synth) — character roles. The TIMBRE comes from
# WHERE each oscillator sits in its bank (pos1/pos2), like a real wavetable synth —
# NOT from sweeping the position on every hit. Position movement is therefore kept
# GENTLE (a fast per-hit sweep smears the pitch into a noise transient). Cutoffs stay
# moderate and lowpass: the raw single-cycle tables are not band-limited, so a bright
# table played high aliases into hash unless a lowpass tames the top. name,
# note(choices, octave), posenv, poslfoRate, poslfoAmt, cutoff, attack, decay,
# sustain, sub, filttype (0=LP 1=BP 2=HP).
# --------------------------------------------------------------------------- #
_WT_SPEC = [
    # slow-evolving pad: long env, barely-there position drift, dark-ish cutoff.
    ("WT PAD",   ((0, 3, 5, 7, 10), 0),  (0.0, 0.10), (0.05, 0.6), (0.0, 0.08),
     (1200, 6000),  (0.05, 0.4),  (0.6, 2.0),  (0.6, 0.9),  (0.0, 0.15), 0),
    # pluck: fast attack, short decay. A touch of position env for a bloom, not a sweep.
    ("WT PLUCK", ((0, 3, 5, 7, 12), 0),  (0.0, 0.12), (0.05, 0.5), (0.0, 0.05),
     (2000, 8000),  (0.002, 0.02), (0.15, 0.7), (0.0, 0.35), (0.0, 0.1), 0),
    # sub-heavy bass: low register, tight, sub osc up, darker.
    ("WT BASS",  ((0, 5, 7), -12),       (0.0, 0.08), (0.05, 0.4), (0.0, 0.05),
     (600, 3500),   (0.003, 0.03), (0.2, 0.9),  (0.3, 0.8),  (0.3, 0.6), 0),
    # lead: mid register, slow gentle position wobble. Lowpass (bandpass thinned it out
    # and stripped the fundamental).
    ("WT LEAD",  ((0, 3, 7, 10, 12), 0), (0.0, 0.10), (0.1, 2.0),  (0.0, 0.08),
     (2000, 8000),  (0.005, 0.06), (0.2, 1.0), (0.35, 0.85), (0.0, 0.2), 0),
]


def _wt_role(spec) -> Role:
    name, note, posenv, lfor, lfoamt, cut, atk, dec, sus, sub, ft = spec
    return Role(name, "WTABLE", note_choices=note[0], octave=note[1],
                fixed={"wtable.filttype": float(ft)},
                bands={"wtable.posenv": posenv, "wtable.poslfoRate": lfor,
                       "wtable.poslfoAmt": lfoamt, "wtable.cutoff": cut,
                       "wtable.attack": atk, "wtable.decay": dec,
                       "wtable.sustain": sus, "wtable.sublevel": sub,
                       # noise is a trace of air, never a wall — this engine is about
                       # the wavetables, not the noise source.
                       "wtable.noiselevel": (0.0, 0.03),
                       "wtable.drive": (0.5, 1.4),
                       # pos1/pos2 spread across the bank: THIS is where the timbral
                       # variety comes from (each voice sits at a different waveform).
                       "wtable.pos1": (0.0, 0.9), "wtable.pos2": (0.0, 0.9),
                       "wtable.oscmix": (0.3, 0.7),
                       # keep the filter envelope shallow — a big sweep re-introduces the
                       # bright-onset hash we're trying to kill.
                       "wtable.filtenv": (0.0, 0.3)},
                vel=(0.8, 1.05))


WTABLE_ROLES: dict[str, Role] = {s[0]: _wt_role(s) for s in _WT_SPEC}
PALETTE_ROLES["WTABLE"] = WTABLE_ROLES["WT PAD"]
_WT_WEIGHTS = {"WT PAD": 3, "WT PLUCK": 3, "WT BASS": 2, "WT LEAD": 2}


# --------------------------------------------------------------------------- #
# BYTEBEAT (ByteBeat UGen) — the expression (`expr`) carries the melody/rhythm and is
# chosen at random from the engine's bank; each role shapes the CLOCK (rate = pitch/
# speed/crunch), the register and the envelope. Glitch/texture, in the BEN/NOIZEOP/
# CHAOS family. name, note(choices, octave), rate, cutoff, attack, decay, sustain,
# release.
# --------------------------------------------------------------------------- #
_BB_SPEC = [
    # evolving drone: mid clock, long-ish env, darker filter.
    ("BB DRONE", ((0, 7), 0),        (3000, 10000),  (2000, 8000),  (0.02, 0.3),
     (0.6, 2.5),  (0.5, 0.9),  (0.3, 1.5)),
    # glitch stab: fast clock, high register, tight env.
    ("BB GLITCH", ((0, 5, 7, 12), 12), (8000, 30000), (4000, 15000), (0.001, 0.02),
     (0.1, 0.6),  (0.15, 0.5), (0.02, 0.3)),
    # bytebeat bass: low register, slow clock, dark.
    ("BB BASS", ((0, 5, 7), -12),    (1500, 6000),   (800, 3000),   (0.002, 0.03),
     (0.2, 1.0),  (0.3, 0.8),  (0.05, 0.5)),
    # chirpy lead: mid register, bright, medium clock.
    ("BB CHIRP", ((0, 3, 7, 10, 12), 0), (6000, 20000), (3000, 12000), (0.002, 0.04),
     (0.15, 0.8), (0.3, 0.7),  (0.05, 0.6)),
]


def _bb_role(spec) -> Role:
    name, note, rate, cut, atk, dec, sus, rel = spec
    return Role(name, "BYTEBEAT", note_choices=note[0], octave=note[1],
                bands={"bytebeat.rate": rate, "bytebeat.cutoff": cut,
                       "bytebeat.attack": atk, "bytebeat.decay": dec,
                       "bytebeat.sustain": sus, "bytebeat.release": rel,
                       "bytebeat.drive": (0.5, 2.0), "bytebeat.res": (0.0, 0.4)},
                vel=(0.8, 1.05))


BYTEBEAT_ROLES: dict[str, Role] = {s[0]: _bb_role(s) for s in _BB_SPEC}
PALETTE_ROLES["BYTEBEAT"] = BYTEBEAT_ROLES["BB GLITCH"]
_BB_WEIGHTS = {"BB DRONE": 2, "BB GLITCH": 3, "BB BASS": 2, "BB CHIRP": 3}


# CSOUND (engine 20) — one role per architecture. The architecture IS the instrument, so
# re-rolling a Csound track's sound means landing on a different one of the ten, with the
# eight macros banded to that architecture's musical range. name, arch, note(choices,
# octave), duration band, then the eight macro bands.
# --------------------------------------------------------------------------- #
# WHY POLES AND NOT BANDS. Every other engine draws each parameter independently and
# uniformly inside a band, which is fine for three or four parameters. Csound has EIGHT
# macros, and in eight dimensions a uniform draw lands near the middle of the box virtually
# every time: measured over 4000 rolls the mean per-macro distance from centre was 0.20 of a
# possible 0.40, and only 1.2% of rolls got even half their macros near an extreme. Ten
# architectures sampled at their centroids give you ten sounds, forever — which is exactly
# what this engine sounded like.
#
# So a recipe does not describe a box, it names POINTS. Each pole is a complete eight-macro
# vector that is known to be a distinct sound in that architecture, and a roll picks a pole
# and wanders a little way off it. The extremes are reachable because they are aimed at.
#
# Fields: name, arch, note choices, octave, duration band, spread, [pole, ...]
# --------------------------------------------------------------------------- #
_CS_SPEC = [
    # ---- 0: struck metal, inharmonic PM into resonators ---------------------
    ("CS BELL",   0, (0, 3, 7, 10), 12, (0.4, 1.8), 0.10,
     [(0.12, 0.70, 0.88, 0.30, 0.10, 0.25, 0.80, 0.22),
      (0.30, 0.40, 0.62, 0.55, 0.08, 0.55, 0.66, 0.40)]),
    ("CS ANVIL",  0, (0, 5, 7), 0, (0.12, 0.6), 0.09,
     [(0.55, 0.90, 0.35, 0.85, 0.60, 0.20, 0.90, 0.75),
      (0.75, 0.72, 0.20, 0.95, 0.40, 0.45, 0.72, 0.90)]),
    ("CS TINE",   0, (0, 3, 7, 10), 12, (0.25, 1.1), 0.08,
     [(0.08, 0.35, 0.95, 0.20, 0.05, 0.15, 0.45, 0.12),
      (0.18, 0.55, 0.80, 0.35, 0.12, 0.30, 0.30, 0.25)]),
    ("CS GONG",   0, (0, 7), -12, (1.2, 4.5), 0.11,
     [(0.85, 0.25, 0.55, 0.15, 0.75, 0.80, 0.95, 0.55),
      (0.65, 0.15, 0.40, 0.30, 0.90, 0.62, 0.85, 0.70)]),
    # ---- 1: granular clouds --------------------------------------------------
    ("CS CLOUD",  1, (0, 5, 7), 0, (1.0, 4.0), 0.10,
     [(0.70, 0.30, 0.80, 0.20, 0.35, 0.75, 0.55, 0.15),
      (0.45, 0.55, 0.62, 0.40, 0.55, 0.50, 0.70, 0.30)]),
    ("CS DUST",   1, (0, 7), 12, (0.3, 1.4), 0.09,
     [(0.15, 0.85, 0.25, 0.90, 0.20, 0.30, 0.15, 0.05),
      (0.25, 0.70, 0.40, 0.75, 0.10, 0.45, 0.30, 0.12)]),
    ("CS SWARM",  1, (0, 3, 5, 7), 0, (0.8, 3.0), 0.12,
     [(0.90, 0.65, 0.90, 0.55, 0.80, 0.85, 0.75, 0.45),
      (0.80, 0.80, 0.72, 0.70, 0.65, 0.70, 0.88, 0.35)]),
    ("CS HAZE",   1, (0, 5), -12, (2.0, 6.0), 0.09,
     [(0.55, 0.12, 0.88, 0.10, 0.25, 0.90, 0.40, 0.08),
      (0.40, 0.22, 0.95, 0.18, 0.15, 0.80, 0.30, 0.05)]),
    # ---- 2: noise-excited mode bank -----------------------------------------
    ("CS STRIKE", 2, (0, 3, 5, 7, 10), 0, (0.2, 1.2), 0.09,
     [(0.05, 0.75, 0.85, 0.30, 0.20, 0.15, 0.70, 0.55),
      (0.20, 0.60, 0.70, 0.50, 0.35, 0.30, 0.85, 0.40)]),
    ("CS PLATE",  2, (0, 7), -12, (0.9, 3.5), 0.10,
     [(0.35, 0.35, 0.95, 0.15, 0.60, 0.55, 0.92, 0.80),
      (0.25, 0.50, 0.88, 0.25, 0.75, 0.40, 0.80, 0.65)]),
    ("CS WOOD",   2, (0, 5, 7, 12), 0, (0.1, 0.5), 0.08,
     [(0.10, 0.85, 0.30, 0.70, 0.15, 0.10, 0.25, 0.20),
      (0.22, 0.72, 0.42, 0.55, 0.25, 0.20, 0.35, 0.32)]),
    ("CS GLASS",  2, (0, 3, 7, 10), 12, (0.5, 2.0), 0.08,
     [(0.02, 0.45, 0.98, 0.20, 0.08, 0.25, 0.95, 0.15),
      (0.12, 0.30, 0.90, 0.35, 0.05, 0.35, 0.88, 0.28)]),
    # ---- 3: feedback-FM chaos -----------------------------------------------
    ("CS CHAOS",  3, (0, 7), -12, (0.4, 2.5), 0.11,
     [(0.85, 0.25, 0.75, 0.35, 0.80, 0.90, 0.30, 0.15),
      (0.70, 0.45, 0.60, 0.55, 0.65, 0.75, 0.50, 0.30)]),
    ("CS SCREW",  3, (0, 1, 7), 0, (0.15, 0.9), 0.10,
     [(0.95, 0.70, 0.35, 0.85, 0.95, 0.55, 0.20, 0.55),
      (0.88, 0.55, 0.50, 0.72, 0.85, 0.68, 0.35, 0.42)]),
    ("CS RUST",   3, (0, 5), -12, (1.0, 4.0), 0.09,
     [(0.45, 0.15, 0.90, 0.15, 0.35, 0.95, 0.75, 0.10),
      (0.55, 0.28, 0.80, 0.25, 0.45, 0.85, 0.62, 0.20)]),
    ("CS TEAR",   3, (0, 3, 7), 0, (0.08, 0.45), 0.10,
     [(0.98, 0.90, 0.15, 0.95, 0.90, 0.35, 0.10, 0.85),
      (0.90, 0.80, 0.28, 0.85, 0.80, 0.48, 0.22, 0.70)]),
    # ---- 4: waveguides pushed hard ------------------------------------------
    ("CS WGUIDE", 4, (0, 5, 7, 12), 0, (0.3, 2.0), 0.10,
     [(0.30, 0.75, 0.25, 0.80, 0.20, 0.35, 0.15, 0.30),
      (0.50, 0.60, 0.40, 0.65, 0.35, 0.55, 0.30, 0.45)]),
    ("CS REED",   4, (0, 3, 7), 0, (0.5, 2.5), 0.09,
     [(0.75, 0.85, 0.15, 0.90, 0.55, 0.20, 0.45, 0.65),
      (0.62, 0.72, 0.30, 0.78, 0.45, 0.35, 0.55, 0.50)]),
    ("CS PIPE",   4, (0, 7, 12), 12, (0.8, 3.5), 0.08,
     [(0.15, 0.30, 0.85, 0.20, 0.10, 0.75, 0.20, 0.15),
      (0.28, 0.42, 0.72, 0.32, 0.22, 0.62, 0.35, 0.25)]),
    ("CS STRING", 4, (0, 5, 7, 10), 0, (0.6, 3.0), 0.09,
     [(0.20, 0.55, 0.60, 0.45, 0.85, 0.30, 0.90, 0.20),
      (0.35, 0.68, 0.48, 0.58, 0.72, 0.42, 0.78, 0.32)]),
    # ---- 5: analysis / resynthesis ------------------------------------------
    ("CS SPECTRL", 5, (0, 3, 7), 0, (1.0, 5.0), 0.10,
     [(0.30, 0.80, 0.25, 0.75, 0.30, 0.20, 0.85, 0.35),
      (0.55, 0.60, 0.45, 0.55, 0.55, 0.45, 0.65, 0.55)]),
    ("CS SMEAR",  5, (0, 5), -12, (2.0, 6.0), 0.09,
     [(0.85, 0.20, 0.90, 0.15, 0.80, 0.90, 0.40, 0.75),
      (0.72, 0.32, 0.82, 0.25, 0.70, 0.80, 0.52, 0.62)]),
    ("CS FREEZE", 5, (0, 7), 0, (2.5, 7.0), 0.07,
     [(0.10, 0.10, 0.95, 0.90, 0.15, 0.95, 0.20, 0.90),
      (0.20, 0.22, 0.88, 0.80, 0.25, 0.85, 0.32, 0.80)]),
    ("CS SHIFT",  5, (0, 1, 5, 7), 12, (0.4, 2.0), 0.10,
     [(0.95, 0.55, 0.15, 0.35, 0.95, 0.30, 0.75, 0.15),
      (0.82, 0.68, 0.28, 0.48, 0.85, 0.45, 0.62, 0.28)]),
    # ---- 6: phase distortion + quantisation ---------------------------------
    ("CS PHASE",  6, (0, 1, 5, 7), 0, (0.1, 0.9), 0.10,
     [(0.10, 0.85, 0.30, 0.75, 0.25, 0.20, 0.15, 0.20),
      (0.30, 0.65, 0.55, 0.55, 0.45, 0.40, 0.35, 0.40)]),
    ("CS CRUSH",  6, (0, 5), -12, (0.08, 0.5), 0.09,
     [(0.05, 0.95, 0.15, 0.95, 0.10, 0.10, 0.05, 0.95),
      (0.15, 0.85, 0.25, 0.85, 0.20, 0.25, 0.15, 0.82)]),
    ("CS FOLD",   6, (0, 3, 7), 0, (0.2, 1.2), 0.10,
     [(0.90, 0.40, 0.85, 0.20, 0.90, 0.75, 0.55, 0.25),
      (0.78, 0.52, 0.72, 0.35, 0.78, 0.62, 0.68, 0.38)]),
    ("CS ALIAS",  6, (0, 7, 12), 12, (0.06, 0.4), 0.08,
     [(0.50, 0.98, 0.10, 0.60, 0.98, 0.15, 0.90, 0.60),
      (0.62, 0.88, 0.22, 0.72, 0.88, 0.28, 0.78, 0.72)]),
    # ---- 7: rhythmic / correlated noise -------------------------------------
    ("CS NOISE",  7, (0, 5, 7), 0, (0.06, 0.6), 0.09,
     [(0.05, 0.75, 0.85, 0.20, 0.30, 0.35, 0.70, 0.25),
      (0.20, 0.60, 0.70, 0.40, 0.50, 0.55, 0.85, 0.40)]),
    ("CS HISS",   7, (0, 7), 12, (0.5, 2.5), 0.08,
     [(0.02, 0.20, 0.95, 0.05, 0.10, 0.90, 0.30, 0.10),
      (0.12, 0.32, 0.88, 0.15, 0.22, 0.80, 0.42, 0.20)]),
    ("CS GRIT",   7, (0, 3, 5), -12, (0.1, 0.8), 0.10,
     [(0.85, 0.90, 0.35, 0.85, 0.75, 0.20, 0.55, 0.85),
      (0.72, 0.78, 0.48, 0.72, 0.62, 0.35, 0.68, 0.72)]),
    ("CS CRACK",  7, (0, 5), 0, (0.03, 0.25), 0.07,
     [(0.30, 0.98, 0.20, 0.98, 0.40, 0.05, 0.95, 0.50),
      (0.42, 0.90, 0.32, 0.88, 0.52, 0.15, 0.85, 0.62)]),
    # ---- 8: inharmonic additive ---------------------------------------------
    ("CS ADD",    8, (0, 3, 7, 10), 0, (0.8, 4.0), 0.10,
     [(0.40, 0.30, 0.20, 0.75, 0.35, 0.30, 0.80, 0.35),
      (0.60, 0.50, 0.40, 0.55, 0.55, 0.50, 0.60, 0.55)]),
    ("CS DRONE",  8, (0, 7), -12, (3.0, 8.0), 0.07,
     [(0.90, 0.10, 0.10, 0.95, 0.15, 0.85, 0.95, 0.10),
      (0.80, 0.20, 0.22, 0.85, 0.28, 0.75, 0.85, 0.22)]),
    ("CS ORGAN",  8, (0, 5, 7, 12), 0, (0.6, 3.0), 0.08,
     [(0.20, 0.65, 0.15, 0.30, 0.85, 0.20, 0.35, 0.80),
      (0.32, 0.55, 0.28, 0.42, 0.72, 0.32, 0.48, 0.68)]),
    ("CS SHIMMER", 8, (0, 3, 7, 10), 12, (1.5, 5.5), 0.09,
     [(0.15, 0.85, 0.90, 0.20, 0.90, 0.60, 0.25, 0.90),
      (0.28, 0.75, 0.80, 0.32, 0.78, 0.70, 0.38, 0.78)]),
    # ---- 9: PADsynth wavetables ---------------------------------------------
    ("CS PAD",    9, (0, 5, 7, 12), -12, (1.5, 6.0), 0.10,
     [(0.45, 0.25, 0.30, 0.25, 0.55, 0.55, 0.60, 0.55),
      (0.65, 0.45, 0.50, 0.45, 0.75, 0.70, 0.40, 0.75)]),
    ("CS WASH",   9, (0, 7), -12, (3.0, 8.0), 0.08,
     [(0.95, 0.10, 0.85, 0.10, 0.90, 0.95, 0.20, 0.95),
      (0.85, 0.22, 0.75, 0.22, 0.80, 0.85, 0.32, 0.85)]),
    ("CS CHOIR",  9, (0, 3, 7), 0, (1.2, 4.5), 0.09,
     [(0.25, 0.70, 0.20, 0.85, 0.30, 0.35, 0.85, 0.30),
      (0.38, 0.60, 0.35, 0.72, 0.45, 0.48, 0.72, 0.45)]),
    ("CS GLACIER", 9, (0, 5), -12, (4.0, 8.0), 0.06,
     [(0.10, 0.05, 0.95, 0.05, 0.10, 0.98, 0.90, 0.05),
      (0.20, 0.15, 0.88, 0.15, 0.22, 0.90, 0.80, 0.15)]),
]


def _cs_role(spec) -> Role:
    name, arch, notes, octave, dur, spread, poles = spec
    return Role(name, "CSOUND", note_choices=notes, octave=octave,
                fixed={"csound.arch": float(arch)},
                bands={"csound.dur": dur},
                poles=tuple(poles), spread=spread, vel=(0.8, 1.05))


CSOUND_ROLES: dict[str, Role] = {s[0]: _cs_role(s) for s in _CS_SPEC}
PALETTE_ROLES["CSOUND"] = CSOUND_ROLES["CS METAL"] if "CS METAL" in CSOUND_ROLES \
    else CSOUND_ROLES["CS BELL"]
# Weighted toward the architectures that carry a track rather than ornament it. Anything
# absent gets weight 1, so adding a recipe above needs no edit here.
_CS_WEIGHTS = {"CS BELL": 3, "CS ANVIL": 3, "CS STRIKE": 3, "CS WOOD": 3, "CS CHAOS": 3,
               "CS SCREW": 2, "CS NOISE": 3, "CS GRIT": 3, "CS CRACK": 2, "CS PHASE": 3,
               "CS CRUSH": 2, "CS FOLD": 2, "CS CLOUD": 2, "CS DUST": 2, "CS PLATE": 2,
               "CS GLASS": 2, "CS WGUIDE": 2, "CS STRING": 2, "CS ADD": 2, "CS PAD": 2}


# SAMPLE plays back whatever was just captured + mangled, so its "sound" is playback
# shaping only — kept gentle so the mangled character comes through rather than being
# re-processed into mush.
# MIC plays back whatever the microphone just captured, so its "sound" is playback shaping
# only — and gentler than SAMPLE's, because a recording of a room is already the character
# and re-processing it into mush defeats the point of pointing a microphone at something.
PALETTE_ROLES["MIC"] = Role("MIC", "MIC", note_choices=(0, 5, 7, 12), octave=0,
                            bands={"mic.start": (0.0, 0.05), "mic.rate": (0.85, 1.2),
                                   "mic.cutoff": (3000, 17000), "mic.drive": (0.7, 1.6),
                                   "mic.decay": (0.4, 2.5), "mic.sustain": (0.7, 1.0),
                                   "mic.release": (0.08, 0.9)},
                            vel=(0.85, 1.05))

PALETTE_ROLES["SAMPLE"] = Role("SAMPLE", "SAMPLE", note_choices=(0, 5, 7, 12), octave=0,
                               bands={"sample.start": (0.0, 0.0), "sample.rate": (0.8, 1.25),
                                      "sample.cutoff": (2500, 17000), "sample.drive": (0.4, 1.6),
                                      "sample.decay": (0.3, 2.0), "sample.sustain": (0.6, 1.0),
                                      "sample.release": (0.05, 0.8)},
                               vel=(0.85, 1.05))


def gen_palette_voice(engine: str, rng: random.Random | None = None,
                      drum_mode: int | None = None) -> dict:
    """Generate one fresh sound for an engine's palette pad (audition / assign).

    `drum_mode` (0..6 = kick/snare/hihat/metal/clap/tom/noise) LOCKS the DRUM engine to
    one type, so the pad keeps rolling variations of that drum instead of a random one.
    None = roll the type freely (the default)."""
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
    if engine == "CHAOS":
        names = list(_CHAOS_WEIGHTS)
        name = rng.choices(names, weights=[_CHAOS_WEIGHTS[n] for n in names])[0]
        return gen_voice(CHAOS_ROLES[name], rng)
    if engine == "WTABLE":
        names = list(_WT_WEIGHTS)
        name = rng.choices(names, weights=[_WT_WEIGHTS[n] for n in names])[0]
        return gen_voice(WTABLE_ROLES[name], rng)   # gen_voice picks two musical sprites
    if engine == "BYTEBEAT":
        names = list(_BB_WEIGHTS)
        name = rng.choices(names, weights=[_BB_WEIGHTS[n] for n in names])[0]
        return gen_voice(BYTEBEAT_ROLES[name], rng)  # gen_voice picks a random expression
    if engine == "CSOUND":
        names = list(_CS_WEIGHTS)
        name = rng.choices(names, weights=[_CS_WEIGHTS[n] for n in names])[0]
        return gen_voice(CSOUND_ROLES[name], rng)    # the architecture is the sound
    voice = gen_voice(PALETTE_ROLES[engine], rng)
    if engine == "DRUM":                       # put the drum in register for its mode
        if drum_mode is not None and 0 <= int(drum_mode) <= 6:
            voice["params"]["drum.mode"] = float(int(drum_mode))   # type locked by the picker
        mode = int(round(voice["params"].get("drum.mode", 0)))
        voice["note"] = _DRUM_MODE_NOTE[max(0, min(6, mode))]
    return voice


ROLE_NAMES = [r.name for r in ROLES]
ROLE_TYPES = [r.type for r in ROLES]
