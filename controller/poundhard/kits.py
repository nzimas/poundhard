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
  Tracks 13-14 FMTONE     — bass, metallic ornament
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
    # ---- tracks 13-14: FMTONE (bass / ornament) ----
    Role("BASS", "FMTONE", note_choices=(0, 3, 5), octave=0,
         bands={"fmtone.ratio": (0.5, 3.0), "fmtone.fmAmt": (0.2, 0.7),
                "fmtone.feedback": (0.0, 1.2), "fmtone.decay": (0.15, 0.8),
                "fmtone.cutoff": (400, 5000), "fmtone.drive": (1.0, 2.6)}),
    Role("ORNMNT", "FMTONE", note_choices=(7, 10, 12, 15), octave=24,
         bands={"fmtone.ratio": (2.0, 11.0), "fmtone.fmAmt": (0.2, 0.8),
                "fmtone.feedback": (0.0, 1.0), "fmtone.decay": (0.1, 0.7),
                "fmtone.cutoff": (2000, 15000), "fmtone.fold": (0.0, 0.4)}),
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
PALETTE_ENGINES = ["DRUM", "FMTONE", "BUCHLOID", "MOLLY", "RINGS", "BEN", "NOIZEOP", "ICARUS"]

# a canonical note per drum mode, so an auditioned/assigned drum sits in register
# (mode order matches catalog DRUM enum: kick snare hihat metal clap tom noise)
_DRUM_MODE_NOTE = [33, 49, 72, 64, 60, 45, 67]

PALETTE_ROLES: dict[str, Role] = {
    # DRUM — roll every mode; the note is fixed up per mode in gen_palette_voice.
    "DRUM": Role("DRUM", "DRUM", note=45, jitter=0.9),
    "FMTONE": Role("FMTONE", "FMTONE", note_choices=tuple(_SCALE), octave=0, jitter=0.85),
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


def gen_palette_voice(engine: str, rng: random.Random | None = None) -> dict:
    """Generate one fresh sound for an engine's palette pad (audition / assign)."""
    rng = rng or random.Random()
    voice = gen_voice(PALETTE_ROLES[engine], rng)
    if engine == "DRUM":                       # put the drum in register for its mode
        mode = int(round(voice["params"].get("drum.mode", 0)))
        voice["note"] = _DRUM_MODE_NOTE[max(0, min(6, mode))]
    return voice


ROLE_NAMES = [r.name for r in ROLES]
ROLE_TYPES = [r.type for r in ROLES]
