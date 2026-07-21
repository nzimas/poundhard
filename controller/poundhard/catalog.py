"""PoundHard voice catalog — parameter metadata for the four track voices.

Every param `id` is `module.arg`; the engine arg name is the suffix after the dot
(``engine_arg("drum.cutoff") == "cutoff"``), which matches the SynthDef argument
in ``supercollider/synthdefs.scd``. The metadata (ranges, `musical` bands, curves,
enums, randomize policies) drives kit generation in ``kits.py``.

`note`, `vel`, and the `t_trig` gate are NOT catalog params — they are per-track /
per-step and travel over dedicated OSC (`/ph/note`, `/ph/vel`, the step clock).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from .params import Curve, DangerClass, ParamMetadata, RandomizePolicy, Rate


def sampler_dir() -> str:
    """The SAMPLER library directory. First existing of: $SAMPLER_DIR,
    /data/samples (engine default), $PH_DATA/samples (dev fallback)."""
    candidates = [os.environ.get("SAMPLER_DIR"), "/data/samples",
                  os.path.join(os.environ.get("PH_DATA", "./data"), "samples")]
    for d in candidates:
        if d and os.path.isdir(d):
            return d
    return candidates[-1]


def _sample_count() -> int:
    try:
        return sum(1 for f in os.listdir(sampler_dir()) if f.lower().endswith(".wav"))
    except OSError:
        return 0


SAMPLE_COUNT = _sample_count()


def engine_arg(pid: str) -> str:
    """SynthDef arg name for a catalog param id (`"drum.cutoff"` -> `"cutoff"`)."""
    return pid.rsplit(".", 1)[-1]


def P(
    pid: str,
    label: str,
    *,
    unit: str = "none",
    rmin: float = 0.0,
    rmax: float = 1.0,
    default: float = 0.0,
    curve: Curve = Curve.LINEAR,
    rate: Rate = Rate.CONTROL,
    smoothing_ms: float = 50.0,
    musical: tuple[float, float] | None = None,
    modulatable: bool = True,
    macro: bool = True,
    midi: bool = True,
    randomize: RandomizePolicy = RandomizePolicy.SAFE,
    danger: DangerClass = DangerClass.NONE,
    formatter: str = "float2",
    enum: list[str] | None = None,
) -> ParamMetadata:
    return ParamMetadata(
        id=pid,
        label=label,
        unit=unit,
        rmin=rmin,
        rmax=rmax,
        musical_min=musical[0] if musical else None,
        musical_max=musical[1] if musical else None,
        default=default,
        curve=curve if enum is None else Curve.ENUM,
        rate=rate,
        smoothing_ms=smoothing_ms,
        modulatable=modulatable,
        macro_eligible=macro,
        midi_learnable=midi,
        randomize_policy=randomize,
        danger_class=danger,
        formatter=formatter,
        enum_values=enum,
    )


@dataclass
class VoiceSpec:
    type: str
    role: str
    synthdef: str          # /ph/track type index resolves via TYPE_INDEX below
    params: list[ParamMetadata] = field(default_factory=list)

    def param(self, pid: str) -> ParamMetadata | None:
        return next((p for p in self.params if p.id == pid or p.id.endswith("." + pid)), None)


# Engine `/ph/track` type indices (must match ~typeDefs in engine.scd).
# EMPTY = -1: an unassigned track (no engine, never spawns). Assignable engines 0..7.
TYPE_INDEX = {"EMPTY": -1, "DRUM": 0, "FM7": 1, "BUCHLOID": 2, "MOLLY": 3,
              "RINGS": 4, "BEN": 5, "NOIZEOP": 6, "ICARUS": 7, "PLAITS": 8,
              "SHAKER": 9, "MEMBRANE": 10, "MALLET": 11, "BOWED": 12,
              "PLUCK": 13, "TUBE": 14, "CHAOS": 15, "WTABLE": 16}


def _wt_sprite_count() -> int:
    """Number of Ableton Wavetable sprites the engine will enumerate. Must mirror
    ~wtScan in engine.scd (same directory, same sort). Falls back to a large count so
    the wt1/wt2 selector range stays usable when the sprite dir isn't on this host."""
    for d in ("/opt/move/Dsp/Vector/Sprites",
              os.path.join(os.environ.get("PH_DATA", "./data"), "wtsprites")):
        try:
            n = sum(1 for f in os.listdir(d) if f.lower().endswith(".wav"))
            if n > 0:
                return n
        except OSError:
            continue
    return 194


WT_SPRITE_COUNT = _wt_sprite_count()


def _wt_sprite_names() -> list[str]:
    """The sorted sprite filenames the engine will enumerate (same dir + sort as
    ~wtScan). Empty when the sprite dir isn't on this host (e.g. a dev box)."""
    for d in ("/opt/move/Dsp/Vector/Sprites",
              os.path.join(os.environ.get("PH_DATA", "./data"), "wtsprites")):
        try:
            names = sorted(f for f in os.listdir(d) if f.lower().endswith(".wav"))
            if names:
                return names
        except OSError:
            continue
    return []


WT_SPRITE_NAMES = _wt_sprite_names()
# Sprite indices the generator is allowed to pick. Two categories are excluded because
# the oscillator has no band-limiting: "Noise" sprites ARE noise, and "Distortion"
# sprites are so harmonically dense they alias into hash. Both stay reachable by hand
# via the wt1/wt2 range. Falls back to the whole range when names are unavailable.
_WT_SKIP_CATEGORIES = ("Noise", "Distortion")
WT_MUSICAL_INDICES = [i for i, n in enumerate(WT_SPRITE_NAMES)
                      if not any(c in n for c in _WT_SKIP_CATEGORIES)] \
                     or list(range(WT_SPRITE_COUNT))

_COMMON_TAIL = lambda pfx, ampd=0.8, ampmus=(0.5, 1.1): [
    P(f"{pfx}.amp", "Amp", unit="dB", rmin=0.0, rmax=2.0, default=ampd, curve=Curve.DB,
      formatter="dB1", danger=DangerClass.LOUDNESS, musical=ampmus),
    P(f"{pfx}.pan", "Spatial Pos", rmin=-1.0, rmax=1.0, default=0.0, curve=Curve.BIPOLAR),
]

# --------------------------------------------------------------------------- #
# DRUM — full digital drum voice (ported from wildrider-mele). One hit per step.
# --------------------------------------------------------------------------- #
DRUM = VoiceSpec(
    type="DRUM",
    role="Digital drum voice: kick / snare / hihat / metal / clap / tom / noise.",
    synthdef="phDrum",
    params=[
        P("drum.mode", "Mode", curve=Curve.ENUM,
          enum=["kick", "snare", "hihat", "metal", "clap", "tom", "noise"],
          default=0, randomize=RandomizePolicy.WIDE),
        # transient / click
        P("drum.transient", "Transient", default=0.6, musical=(0.3, 1.0)),
        P("drum.transTone", "Transient Tone", default=0.5, musical=(0.2, 0.9)),
        P("drum.transDecay", "Transient Decay", unit="s", rmin=0.0005, rmax=0.03, default=0.004,
          curve=Curve.EXP, formatter="float3", musical=(0.001, 0.012)),
        # pitch / body
        P("drum.pitchMod", "Pitch Drop", default=0.6, musical=(0.2, 1.0)),
        P("drum.pitchDecay", "Pitch Decay", unit="s", rmin=0.002, rmax=0.6, default=0.05,
          curve=Curve.EXP, formatter="float3", musical=(0.01, 0.15)),
        P("drum.ampDecay", "Amp Decay", unit="s", rmin=0.004, rmax=4.0, default=0.25,
          curve=Curve.EXP, formatter="float2", musical=(0.03, 0.9)),
        P("drum.ampCurve", "Amp Curve", rmin=-8.0, rmax=-1.0, default=-4.0,
          formatter="float1", musical=(-6.0, -2.0)),
        # noise layer
        P("drum.noiseAmt", "Noise Amount", default=0.3, musical=(0.0, 0.8)),
        P("drum.noiseTone", "Noise Tone", default=0.5, musical=(0.2, 0.9)),
        P("drum.noiseDecay", "Noise Decay", unit="s", rmin=0.004, rmax=3.0, default=0.12,
          curve=Curve.EXP, formatter="float2", musical=(0.02, 0.6)),
        P("drum.snap", "Snap", default=0.5, musical=(0.2, 0.9)),
        # metal / FM
        P("drum.ratio", "FM Ratio", rmin=0.2, rmax=12.0, default=1.5, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 7.0)),
        P("drum.fmAmt", "FM Amount", default=0.0, musical=(0.0, 0.5)),
        P("drum.harmonics", "Harmonics", default=0.5, musical=(0.0, 0.8)),
        # filter
        P("drum.cutoff", "Cutoff", unit="Hz", rmin=20.0, rmax=18000.0, default=9000.0,
          curve=Curve.EXP, formatter="Hz", musical=(400.0, 16000.0)),
        P("drum.res", "Resonance", default=0.2, musical=(0.0, 0.6), danger=DangerClass.FEEDBACK),
        P("drum.filterType", "Filter Type", curve=Curve.ENUM, enum=["lp", "bp", "hp"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("drum.filterEnv", "Filter Env", default=0.3, musical=(0.0, 0.8)),
        # grit
        P("drum.fold", "Wavefold", default=0.0, musical=(0.0, 0.5)),
        P("drum.drive", "Drive", rmin=0.0, rmax=6.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.3, 2.5)),
        P("drum.crush", "Bit Crush", default=0.0, musical=(0.0, 0.5)),
        P("drum.downsample", "Rate Crush", default=0.0, musical=(0.0, 0.5)),
        *_COMMON_TAIL("drum"),
    ],
)

# --------------------------------------------------------------------------- #
# FM7 — real 6-operator FM (sc3-plugins). `algo` picks one of 6 modulation
# topologies; the six operator ratios + FM index + feedback shape the tone. The
# generator targets each algorithm to a role (bell / e-piano / clang / FM bass /
# metal / stab) — see kits._FM7_SPEC.
# --------------------------------------------------------------------------- #
FM7 = VoiceSpec(
    type="FM7",
    role="6-operator FM: 6 algorithms, per-operator ratios, FM index + feedback.",
    synthdef="phFm7",
    params=[
        P("fm7.algo", "Algorithm", curve=Curve.ENUM,
          enum=["epiano", "clang", "organ", "fmbass", "bell", "stab"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("fm7.r1", "Ratio 1", rmin=0.01, rmax=24.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 8.0)),
        P("fm7.r2", "Ratio 2", rmin=0.01, rmax=24.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 8.0)),
        P("fm7.r3", "Ratio 3", rmin=0.01, rmax=24.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 8.0)),
        P("fm7.r4", "Ratio 4", rmin=0.01, rmax=24.0, default=2.0, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 11.0)),
        P("fm7.r5", "Ratio 5", rmin=0.01, rmax=24.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 8.0)),
        P("fm7.r6", "Ratio 6", rmin=0.01, rmax=24.0, default=3.5, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 11.0)),
        P("fm7.index", "FM Index", rmin=0.0, rmax=12.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.3, 6.0)),
        P("fm7.fb", "Feedback", rmin=0.0, rmax=1.0, default=0.1, musical=(0.0, 0.7),
          danger=DangerClass.FEEDBACK),
        P("fm7.bright", "Brightness", rmin=0.1, rmax=4.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.4, 2.5)),
        P("fm7.attack", "Attack", unit="s", rmin=0.0005, rmax=2.0, default=0.004,
          curve=Curve.EXP, formatter="float3", musical=(0.001, 0.05)),
        P("fm7.decay", "Decay", unit="s", rmin=0.01, rmax=8.0, default=0.6,
          curve=Curve.EXP, formatter="float2", musical=(0.08, 2.5)),
        P("fm7.ampCurve", "Amp Curve", rmin=-8.0, rmax=-1.0, default=-4.0,
          formatter="float1", musical=(-6.0, -2.0)),
        P("fm7.mDecay", "Index Decay", rmin=0.05, rmax=1.5, default=0.6,
          formatter="float2", musical=(0.2, 1.2)),
        P("fm7.cutoff", "Cutoff", unit="Hz", rmin=60.0, rmax=19000.0, default=16000.0,
          curve=Curve.EXP, formatter="Hz", musical=(800.0, 18000.0)),
        *_COMMON_TAIL("fm7", ampd=0.55, ampmus=(0.35, 0.9)),
    ],
)

# --------------------------------------------------------------------------- #
# BUCHLOID — west-coast complex osc (FM + wavefold + LPG), gate-triggered.
# --------------------------------------------------------------------------- #
BUCHLOID = VoiceSpec(
    type="BUCHLOID",
    role="Complex oscillator: two FM mods, wavefolder, resonant lowpass-gate.",
    synthdef="phBuchloid",
    params=[
        P("buchloid.fm1Ratio", "FM1 Ratio", rmin=0.1, rmax=12.0, default=0.66, curve=Curve.EXP,
          formatter="float2", musical=(0.5, 4.0)),
        P("buchloid.fm1Amount", "FM1 Amt", default=0.0, musical=(0.0, 0.6)),
        P("buchloid.fm2Ratio", "FM2 Ratio", rmin=0.1, rmax=24.0, default=3.3, curve=Curve.EXP,
          formatter="float2", musical=(1.0, 9.0)),
        P("buchloid.fm2Amount", "FM2 Amt", default=0.0, musical=(0.0, 0.6)),
        P("buchloid.waveShape", "Wave Shape", default=0.0, musical=(0.0, 1.0)),
        P("buchloid.waveFolds", "Wave Folds", rmin=0.0, rmax=3.0, default=0.0, musical=(0.0, 2.0)),
        P("buchloid.timbre", "Timbre", default=0.0, musical=(0.0, 1.0)),
        P("buchloid.attack", "Attack", unit="s", rmin=0.001, rmax=4.0, default=0.02,
          curve=Curve.EXP, formatter="float3", musical=(0.003, 0.6)),
        P("buchloid.decay", "Decay", unit="s", rmin=0.01, rmax=8.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.1, 3.0)),
        P("buchloid.peak", "Filter Peak", unit="Hz", rmin=100.0, rmax=12000.0, default=8000.0,
          curve=Curve.EXP, formatter="Hz", musical=(500.0, 9000.0)),
        P("buchloid.res", "Resonance", default=0.2, musical=(0.0, 0.7), danger=DangerClass.FEEDBACK),
        P("buchloid.pressure", "Pressure", default=0.0, musical=(0.0, 0.7)),
        P("buchloid.drive", "Drive", rmin=0.1, rmax=4.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.3, 1.8)),
        *_COMMON_TAIL("buchloid", ampd=0.5, ampmus=(0.3, 0.9)),
    ],
)

# --------------------------------------------------------------------------- #
# SAMPLER — single-file loop slice (buffer from /data/samples), gate-triggered.
# --------------------------------------------------------------------------- #
SAMPLER = VoiceSpec(
    type="SAMPLER",
    role="Sample slice player: pitch, scrub, reverse, loop window, crush + filter.",
    synthdef="phSampler",
    params=[
        # `sample` is a buffer selector (0..SAMPLE_COUNT-1), sent via /ph/samp, not /ph/param.
        P("sampler.sample", "Sample", rmin=0.0, rmax=float(max(0, SAMPLE_COUNT - 1)), default=0.0,
          rate=Rate.DISCRETE, formatter="int", randomize=RandomizePolicy.WIDE,
          musical=(0.0, float(max(0, SAMPLE_COUNT - 1))), modulatable=False),
        P("sampler.pitch", "Pitch", unit="st", rmin=-36.0, rmax=36.0, default=0.0,
          curve=Curve.BIPOLAR, formatter="float1", musical=(-12.0, 12.0)),
        P("sampler.direction", "Direction", curve=Curve.ENUM, enum=["forward", "reverse"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("sampler.posStart", "Start", default=0.0, musical=(0.0, 0.85)),
        P("sampler.posWindow", "Window", default=0.5, musical=(0.04, 0.7)),
        P("sampler.scrub", "Scrub", rmin=0.0, rmax=2.0, default=1.0, formatter="float2",
          musical=(0.05, 1.2)),
        P("sampler.attack", "Attack", unit="s", rmin=0.0005, rmax=2.0, default=0.001,
          curve=Curve.EXP, formatter="float3", musical=(0.001, 0.05)),
        P("sampler.decay", "Decay", unit="s", rmin=0.005, rmax=6.0, default=0.8,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 2.0)),
        P("sampler.cutoff", "Cutoff", unit="Hz", rmin=20.0, rmax=18000.0, default=14000.0,
          curve=Curve.EXP, formatter="Hz", musical=(500.0, 16000.0)),
        P("sampler.res", "Resonance", default=0.15, musical=(0.0, 0.5), danger=DangerClass.FEEDBACK),
        P("sampler.crush", "Bit Crush", default=0.0, musical=(0.0, 0.5)),
        P("sampler.downsample", "Rate Crush", default=0.0, musical=(0.0, 0.5)),
        P("sampler.drive", "Drive", rmin=0.1, rmax=4.0, default=1.0, curve=Curve.EXP,
          formatter="float2", musical=(0.4, 1.8)),
        *_COMMON_TAIL("sampler", ampd=0.6, ampmus=(0.35, 0.95)),
    ],
)

# --------------------------------------------------------------------------- #
# MOLLY — Molly-the-Poly analogue-voiced polysynth (lead / pad / stab), gated.
# --------------------------------------------------------------------------- #
MOLLY = VoiceSpec(
    type="MOLLY",
    role="Molly the Poly: characterful analogue polysynth — leads, pads, bass, stabs.",
    synthdef="phMolly",
    params=[
        P("molly.detune", "Detune", unit="cent", rmin=0.0, rmax=50.0, default=7.0,
          formatter="float1", musical=(0.0, 20.0)),
        P("molly.oscShape", "Osc Shape", default=0.5, musical=(0.0, 1.0)),
        P("molly.pulseWidth", "Pulse Width", rmin=0.05, rmax=0.95, default=0.5, musical=(0.2, 0.8)),
        P("molly.subLevel", "Sub", default=0.0, musical=(0.0, 0.5)),
        P("molly.noiseLevel", "Noise", default=0.0, musical=(0.0, 0.3)),
        P("molly.cutoff", "Cutoff", unit="Hz", rmin=20.0, rmax=18000.0, default=1200.0,
          curve=Curve.EXP, formatter="Hz", musical=(300.0, 6000.0)),
        P("molly.resonance", "Resonance", default=0.2, musical=(0.1, 0.7), danger=DangerClass.FEEDBACK),
        P("molly.lpType", "Filter", curve=Curve.ENUM, enum=["12dB", "24dB"], default=1,
          randomize=RandomizePolicy.WIDE),
        P("molly.filterEnvAmt", "Filter Env", rmin=-1.0, rmax=1.0, default=0.3,
          curve=Curve.BIPOLAR, musical=(0.0, 0.8)),
        P("molly.fDec", "F.Decay", unit="s", rmin=0.001, rmax=5.0, default=0.3,
          curve=Curve.EXP, formatter="float3", musical=(0.03, 1.5)),
        P("molly.fSus", "F.Sustain", default=0.6, musical=(0.0, 0.9)),
        P("molly.aDec", "A.Decay", unit="s", rmin=0.001, rmax=5.0, default=0.3,
          curve=Curve.EXP, formatter="float3", musical=(0.05, 1.5)),
        P("molly.aSus", "A.Sustain", default=0.8, musical=(0.0, 1.0)),
        P("molly.aRel", "A.Release", unit="s", rmin=0.001, rmax=8.0, default=0.5,
          curve=Curve.EXP, formatter="float3", musical=(0.05, 3.0)),
        P("molly.hold", "Note Length", unit="s", rmin=0.02, rmax=4.0, default=0.3,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 1.5)),
        P("molly.lfoRate", "LFO Rate", unit="Hz", rmin=0.01, rmax=12.0, default=4.0,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 2.5)),
        P("molly.lfoToCutoff", "LFO->Cutoff", default=0.0, musical=(0.0, 0.16)),
        P("molly.ringMod", "Ring Mod", default=0.0, musical=(0.0, 0.4)),
        P("molly.drive", "Drive", default=0.0, musical=(0.0, 0.6)),
        P("molly.chorus", "Chorus", default=0.0, musical=(0.0, 0.7)),
        # --- GRIT: what turns MOLLY from a polite Moog into an IDM / rhythmic-noise voice
        P("molly.fmAmt", "Cross FM", default=0.0, musical=(0.0, 0.5)),
        P("molly.fold", "Wavefold", default=0.0, musical=(0.0, 0.85)),
        P("molly.crush", "Bit Crush", default=0.0, musical=(0.0, 0.8)),
        P("molly.downsample", "Downsample", default=0.0, musical=(0.0, 0.7)),
        P("molly.grit", "Grit / Crackle", default=0.0, musical=(0.0, 0.6)),
        *_COMMON_TAIL("molly", ampd=0.35, ampmus=(0.25, 0.55)),
    ],
)

# --------------------------------------------------------------------------- #
# RINGS — Mutable Instruments modal/string resonator (MiRings), gate-triggered.
# --------------------------------------------------------------------------- #
RINGS = VoiceSpec(
    type="RINGS",
    role="Modal / sympathetic-string resonator (Mutable Instruments Rings) — plucks & bells.",
    synthdef="phRings",
    params=[
        P("rings.struct", "Structure", default=0.25, musical=(0.1, 0.8)),
        P("rings.bright", "Brightness", default=0.5, musical=(0.3, 0.9)),
        P("rings.damp", "Damping", default=0.7, musical=(0.4, 0.95)),
        P("rings.pos", "Position", default=0.25, musical=(0.1, 0.8)),
        P("rings.model", "Model", curve=Curve.ENUM,
          enum=["modal", "sympathetic", "inharmonic", "fm", "chords", "strreverb"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("rings.decay", "Decay", unit="s", rmin=0.05, rmax=8.0, default=1.2,
          curve=Curve.EXP, formatter="float2", musical=(0.2, 3.0)),
        *_COMMON_TAIL("rings", ampd=0.9, ampmus=(0.5, 1.05)),
    ],
)

# SAMPLER retired from the fleet (buffer streaming caused audio-thread stalls);
# MOLLY replaces it. The SAMPLER spec/synthdef remain defined but unused.
# --------------------------------------------------------------------------- #
# BEN — Benjolin (Rob Hordijk): two oscillators cross-modulated by a "rungler"
# shift register. Chaotic and self-patterning — a generative machine, not a
# note-player. The rungler amounts and `chaos` decide how far it runs away.
# --------------------------------------------------------------------------- #
BEN = VoiceSpec(
    type="BEN",
    role="Benjolin (Rob Hordijk) — rungler-driven chaotic generative machine.",
    synthdef="phBen",
    params=[
        # osc2 is often SUB-AUDIO: it clocks the shift register, so a few Hz gives the
        # slow stepped patterns the Benjolin is known for; push it up for grit/noise.
        P("ben.freq2", "Osc 2", unit="Hz", rmin=0.1, rmax=3000.0, default=4.0,
          curve=Curve.EXP, musical=(0.5, 400.0)),
        P("ben.scale", "Rungler Scale", default=1.0, musical=(0.15, 1.0)),
        P("ben.rungler1", "Rungler -> Osc1", default=0.16, musical=(0.0, 0.7)),
        P("ben.rungler2", "Rungler -> Osc2", default=0.0, musical=(0.0, 0.5)),
        P("ben.runglerFilt", "Rungler -> Filter", default=9.0, rmin=0.0, rmax=30.0,
          musical=(0.0, 18.0)),
        P("ben.filtFreq", "Cutoff", unit="Hz", rmin=20.0, rmax=8000.0, default=40.0,
          curve=Curve.EXP, musical=(30.0, 2000.0)),
        P("ben.q", "Q", default=0.82, musical=(0.3, 0.95), danger=DangerClass.FEEDBACK),
        P("ben.filterType", "Filter", curve=Curve.ENUM,
          enum=["LP", "HP", "SVF", "DFM1"], default=0, randomize=RandomizePolicy.WIDE),
        P("ben.outSignal", "Out Tap", curve=Curve.ENUM,
          enum=["tri1", "osc1", "tri2", "osc2", "pwm", "sh0", "filter"], default=6,
          randomize=RandomizePolicy.WIDE),
        P("ben.gain", "Drive", rmin=0.1, rmax=12.0, default=1.0, musical=(0.8, 6.0)),
        P("ben.decay", "Decay", unit="s", rmin=0.05, rmax=8.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.15, 2.5)),
        *_COMMON_TAIL("ben", ampd=0.35, ampmus=(0.25, 0.60)),
    ],
)

# --------------------------------------------------------------------------- #
# NOIZEOP — faithful port of deeg's NoizeOp Norns engine
# (github.com/deeg-deeg-deeg/noizeop). Four sine oscillators combined through six
# nonlinear algorithms (products / ratios / trunc / hypot / sum-of-squares),
# mixed by weight, then hipass -> lowpass -> resonz. Glitchy rhythmic noise. The
# four osc frequencies are note-relative ratios so the sequencer transposes the
# whole cluster; every algo/mul/mod/vol/filter arg is the engine's own.
# --------------------------------------------------------------------------- #
NOIZEOP = VoiceSpec(
    type="NOIZEOP",
    role="deeg's NoizeOp — 4 sines through 6 nonlinear algorithms; glitchy rhythmic noise.",
    synthdef="phNoizeop",
    params=[
        # osc frequency ratios vs the played note (1 = unison; detune for character)
        P("noizeop.freq01", "Ratio 1", rmin=0.125, rmax=16.0, default=1.0,
          curve=Curve.EXP, musical=(0.5, 4.0)),
        P("noizeop.freq02", "Ratio 2", rmin=0.125, rmax=16.0, default=1.5,
          curve=Curve.EXP, musical=(0.5, 6.0)),
        P("noizeop.freq03", "Ratio 3", rmin=0.125, rmax=16.0, default=2.0,
          curve=Curve.EXP, musical=(0.5, 8.0)),
        P("noizeop.freq04", "Ratio 4", rmin=0.125, rmax=16.0, default=3.0,
          curve=Curve.EXP, musical=(0.5, 12.0)),
        # per-oscillator amplitude
        P("noizeop.mul01", "Osc 1 Lvl", default=1.0, musical=(0.3, 1.0)),
        P("noizeop.mul02", "Osc 2 Lvl", default=1.0, musical=(0.3, 1.0)),
        P("noizeop.mul03", "Osc 3 Lvl", default=1.0, musical=(0.3, 1.0)),
        P("noizeop.mul04", "Osc 4 Lvl", default=1.0, musical=(0.3, 1.0)),
        # algorithm mod coefficients (a_mod_01/02/04 divide -> smaller = wilder;
        # a_mod_03 is the trunc/quantize step; a_mod_05/06 scale)
        P("noizeop.a_mod_01", "Mod 1", rmin=0.1, rmax=8.0, default=1.0,
          curve=Curve.EXP, musical=(0.4, 4.0)),
        P("noizeop.a_mod_02", "Mod 2", rmin=0.1, rmax=8.0, default=1.0,
          curve=Curve.EXP, musical=(0.4, 4.0)),
        P("noizeop.a_mod_03", "Trunc", rmin=0.001, rmax=0.5, default=0.02,
          curve=Curve.EXP, musical=(0.005, 0.2)),
        P("noizeop.a_mod_04", "Mod 4", rmin=0.1, rmax=8.0, default=1.0,
          curve=Curve.EXP, musical=(0.4, 4.0)),
        P("noizeop.a_mod_05", "Mod 5", rmin=0.05, rmax=4.0, default=1.0,
          curve=Curve.EXP, musical=(0.2, 2.0)),
        P("noizeop.a_mod_06", "Mod 6", rmin=0.05, rmax=4.0, default=1.0,
          curve=Curve.EXP, musical=(0.2, 2.0)),
        # algorithm mix weights (which of the six operators dominates the output)
        P("noizeop.a_vol_01", "Algo 1", default=0.5, musical=(0.0, 1.0)),
        P("noizeop.a_vol_02", "Algo 2", default=0.5, musical=(0.0, 1.0)),
        P("noizeop.a_vol_03", "Algo 3", default=0.5, musical=(0.0, 1.0)),
        P("noizeop.a_vol_04", "Algo 4", default=0.5, musical=(0.0, 1.0)),
        P("noizeop.a_vol_05", "Algo 5", default=0.5, musical=(0.0, 1.0)),
        P("noizeop.a_vol_06", "Algo 6", default=0.5, musical=(0.0, 1.0)),
        # filter bank: hipass -> lowpass -> resonz
        P("noizeop.ffreq01", "HP Freq", unit="Hz", rmin=20.0, rmax=8000.0, default=40.0,
          curve=Curve.EXP, musical=(30.0, 1200.0)),
        P("noizeop.ffreq02", "LP Freq", unit="Hz", rmin=200.0, rmax=18000.0, default=12000.0,
          curve=Curve.EXP, musical=(800.0, 14000.0)),
        P("noizeop.ffreq03", "Resonz", unit="Hz", rmin=60.0, rmax=12000.0, default=1200.0,
          curve=Curve.EXP, musical=(120.0, 6000.0)),
        P("noizeop.q01", "HP Q", rmin=0.05, rmax=2.0, default=1.0, musical=(0.3, 1.4)),
        P("noizeop.q02", "LP Q", rmin=0.05, rmax=2.0, default=1.0, musical=(0.3, 1.4)),
        P("noizeop.q03", "Resonz BW", rmin=0.02, rmax=1.5, default=1.0,
          curve=Curve.EXP, musical=(0.05, 0.8), danger=DangerClass.FEEDBACK),
        P("noizeop.gain", "Drive", rmin=0.1, rmax=12.0, default=1.0, musical=(0.5, 5.0)),
        P("noizeop.decay", "Decay", unit="s", rmin=0.05, rmax=8.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.12, 2.5)),
        *_COMMON_TAIL("noizeop", ampd=0.5, ampmus=(0.3, 0.7)),
    ],
)

# --------------------------------------------------------------------------- #
# ICARUS — faithful port of schollz's Icarus Norns engine
# (github.com/schollz/icarus). A "dreamcrusher" pad/drone: VarSaw main osc + Pulse
# sub, PWM + slow randomized detune, into a feedback delay network, a MoogLadder
# low-pass, and a Dust-gated "destruction" dropout. Excellent for drones and pads.
# --------------------------------------------------------------------------- #
ICARUS = VoiceSpec(
    type="ICARUS",
    role="schollz's Icarus 'dreamcrusher' — evolving drones & pads (VarSaw + FB delay + MoogLadder).",
    synthdef="phIcarus",
    params=[
        # sub-oscillator: octaves below the main VarSaw, and its level
        P("icarus.subpitch", "Sub Oct", rmin=0.0, rmax=3.0, default=1.0,
          curve=Curve.LINEAR, formatter="float1", musical=(1.0, 2.0)),
        P("icarus.sublevel", "Sub Lvl", default=0.3, musical=(0.0, 0.7)),
        # dreamcrusher detune / glide
        P("icarus.detuning", "Detune", default=0.1, musical=(0.0, 0.4)),
        P("icarus.portamento", "Glide", unit="s", rmin=0.0, rmax=2.0, default=0.1,
          curve=Curve.EXP, formatter="float2", musical=(0.02, 0.6)),
        # pulse-width modulation
        P("icarus.pwmcenter", "PWM Center", default=0.5, musical=(0.25, 0.75)),
        P("icarus.pwmwidth", "PWM Depth", default=0.05, musical=(0.0, 0.4)),
        P("icarus.pwmfreq", "PWM Rate", unit="Hz", rmin=0.05, rmax=40.0, default=10.0,
          curve=Curve.EXP, musical=(0.1, 12.0)),
        # filter
        P("icarus.lpf", "Cutoff", unit="Hz", rmin=80.0, rmax=18000.0, default=6000.0,
          curve=Curve.EXP, formatter="Hz", musical=(300.0, 12000.0)),
        P("icarus.resonance", "Resonance", default=0.2, musical=(0.0, 0.6),
          danger=DangerClass.FEEDBACK),
        # feedback delay network
        P("icarus.feedback", "FB Amount", default=0.5, musical=(0.0, 0.85),
          danger=DangerClass.FEEDBACK),
        P("icarus.delaytime", "Delay", unit="s", rmin=0.001, rmax=0.5, default=0.25,
          curve=Curve.EXP, formatter="float3", musical=(0.02, 0.45)),
        P("icarus.destruction", "Destruction", rmin=0.0, rmax=30.0, default=0.0,
          curve=Curve.EXP, musical=(0.0, 12.0)),
        # amplitude envelope (long values -> sustained drones / pads)
        P("icarus.attack", "Attack", unit="s", rmin=0.001, rmax=6.0, default=0.02,
          curve=Curve.EXP, formatter="float2", musical=(0.005, 2.0)),
        P("icarus.decay", "Decay", unit="s", rmin=0.02, rmax=8.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.3, 4.0)),
        P("icarus.sustain", "Sustain", default=0.8, musical=(0.4, 0.95)),
        P("icarus.release", "Release", unit="s", rmin=0.02, rmax=10.0, default=1.5,
          curve=Curve.EXP, formatter="float2", musical=(0.4, 5.0)),
        P("icarus.gain", "Drive", rmin=0.1, rmax=6.0, default=1.4, musical=(1.0, 3.0)),
        *_COMMON_TAIL("icarus", ampd=0.85, ampmus=(0.55, 0.95)),
    ],
)

# --------------------------------------------------------------------------- #
# PLAITS — Mutable Instruments Plaits, the REAL MiPlaits UGen (v7b1/mi-UGens),
# same plugin family as MiRings. A 16-model macro-oscillator: the `model` switch
# completely redefines what harm/timbre/morph do, which is why generation goes
# through the per-model targeting table in kits.py (PLAITS_MODELS) rather than
# randomising the three knobs blindly.
# --------------------------------------------------------------------------- #
PLAITS = VoiceSpec(
    type="PLAITS",
    role="Mutable Instruments Plaits (MiPlaits) — 16-model macro-oscillator, from drums to speech.",
    synthdef="phPlaits",
    params=[
        P("plaits.model", "Model", curve=Curve.ENUM,
          enum=["va", "waveshp", "fm", "formant", "harmonic", "wavetbl", "chord",
                "speech", "cloud", "noise", "particle", "string", "modal",
                "bassdrum", "snare", "hihat"],
          default=0, randomize=RandomizePolicy.WIDE),
        # harm/timbre/morph are Plaits' three macro knobs — their meaning is per-model
        P("plaits.harm", "Harmonics", default=0.5, musical=(0.05, 0.95)),
        P("plaits.timbre", "Timbre", default=0.5, musical=(0.05, 0.95)),
        P("plaits.morph", "Morph", default=0.5, musical=(0.05, 0.95)),
        # Plaits' own internal envelope + low-pass gate, fired by the per-step trigger
        P("plaits.decay", "Decay", default=0.4, musical=(0.05, 0.9)),
        P("plaits.lpgColour", "LPG Colour", default=0.5, musical=(0.0, 1.0)),
        # OUT vs AUX: two different signals per model, not a stereo pair
        P("plaits.aux", "Aux Blend", default=0.0, musical=(0.0, 1.0)),
        *_COMMON_TAIL("plaits", ampd=0.7, ampmus=(0.45, 0.9)),
    ],
)

# --------------------------------------------------------------------------- #
# SHAKER — STK Shakers (sc3-plugins): 23 stochastic shaker/scraper models.
# `instr` picks the model; the generator targets each to a role (see kits._SHAKER_SPEC).
# --------------------------------------------------------------------------- #
_SHAKER_INSTR = ["maraca", "cabasa", "sekere", "guiro", "waterdrop", "bambooChm",
                 "tambourin", "sleighBell", "sticks", "crunch", "wrench", "sandpaper",
                 "cokeCan", "nextMug", "pennyMug", "nickelMug", "dimeMug", "quartMug",
                 "francMug", "pesoMug", "bigRocks", "littleRock", "tunedBamboo"]
SHAKER = VoiceSpec(
    type="SHAKER",
    role="STK shaker/scraper models — maraca / cabasa / guiro / tambourine / chimes / sand.",
    synthdef="phShaker",
    params=[
        P("shaker.instr", "Instrument", curve=Curve.ENUM, enum=_SHAKER_INSTR,
          default=0, randomize=RandomizePolicy.WIDE),
        P("shaker.energy", "Energy", rmin=0.0, rmax=128.0, default=90.0,
          formatter="float1", musical=(50.0, 120.0)),
        P("shaker.decay", "System Decay", rmin=0.0, rmax=128.0, default=70.0,
          formatter="float1", musical=(30.0, 110.0)),
        P("shaker.objects", "Objects", rmin=0.0, rmax=128.0, default=40.0,
          formatter="float1", musical=(4.0, 90.0)),
        P("shaker.resfreq", "Resonance", rmin=0.0, rmax=128.0, default=64.0,
          formatter="float1", musical=(20.0, 110.0)),
        P("shaker.atk", "Attack", unit="s", rmin=0.0002, rmax=0.2, default=0.001,
          curve=Curve.EXP, formatter="float3", musical=(0.0005, 0.02)),
        P("shaker.dec", "Decay", unit="s", rmin=0.02, rmax=4.0, default=0.35,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 1.2)),
        *_COMMON_TAIL("shaker", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# MEMBRANE — 2D waveguide struck membrane (MembraneCircle, sc3-plugins).
# Struck drums / frame drums / gongs. Note shifts `tension` (pitch); `loss` = ring time.
# --------------------------------------------------------------------------- #
MEMBRANE = VoiceSpec(
    type="MEMBRANE",
    role="Struck 2D-waveguide membrane — tunable drums / frame drums / gongs.",
    synthdef="phMembrane",
    params=[
        P("membrane.tension", "Tension", rmin=0.004, rmax=0.22, default=0.05,
          curve=Curve.EXP, formatter="float3", musical=(0.01, 0.12)),
        P("membrane.loss", "Ring", rmin=0.9, rmax=0.99998, default=0.9995,
          formatter="float3", musical=(0.995, 0.99995)),
        P("membrane.tone", "Strike Tone", default=0.5, musical=(0.2, 0.9)),
        P("membrane.strike", "Strike Length", default=0.5, musical=(0.1, 0.8)),
        *_COMMON_TAIL("membrane", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# MALLET — STK ModalBar (sc3-plugins): struck tuned bars (marimba / vibraphone /
# agogo / wood / reso / beats). Pitched by the note; per-model targeting in kits.
# --------------------------------------------------------------------------- #
_MALLET_INSTR = ["marimba", "vibraphon", "agogo", "wood1", "reso", "wood2",
                 "beats", "twofixed", "clump"]
MALLET = VoiceSpec(
    type="MALLET",
    role="STK modal bars — marimba / vibraphone / agogo / wood / reso / bells.",
    synthdef="phMallet",
    params=[
        P("mallet.instrument", "Instrument", curve=Curve.ENUM, enum=_MALLET_INSTR,
          default=0, randomize=RandomizePolicy.WIDE),
        P("mallet.stickhardness", "Stick Hardness", rmin=0.0, rmax=128.0, default=64.0,
          formatter="float1", musical=(20.0, 120.0)),
        P("mallet.stickposition", "Stick Position", rmin=0.0, rmax=128.0, default=28.0,
          formatter="float1", musical=(5.0, 90.0)),
        P("mallet.vibratogain", "Vibrato Depth", rmin=0.0, rmax=128.0, default=8.0,
          formatter="float1", musical=(0.0, 40.0)),
        P("mallet.vibratofreq", "Vibrato Rate", rmin=0.0, rmax=128.0, default=20.0,
          formatter="float1", musical=(10.0, 80.0)),
        P("mallet.directmix", "Stick Mix", rmin=0.0, rmax=128.0, default=40.0,
          formatter="float1", musical=(10.0, 90.0)),
        P("mallet.decay", "Decay", unit="s", rmin=0.05, rmax=6.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.15, 3.0)),
        *_COMMON_TAIL("mallet", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# BOWED — STK BandedWG (sc3-plugins): banded-waveguide bars/glass/bowl, struck or
# bowed metal & glass. Pitched by the note; per-model targeting in kits.
# --------------------------------------------------------------------------- #
_BOWED_INSTR = ["unibar", "tunedbar", "glass", "bowl"]
BOWED = VoiceSpec(
    type="BOWED",
    role="STK banded waveguide — uniform/tuned bar, glass harmonica, Tibetan bowl.",
    synthdef="phBowed",
    params=[
        P("bowed.instr", "Instrument", curve=Curve.ENUM, enum=_BOWED_INSTR,
          default=0, randomize=RandomizePolicy.WIDE),
        P("bowed.striking", "Excite", curve=Curve.ENUM, enum=["bowed", "struck"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("bowed.bowpressure", "Bow Pressure", rmin=0.0, rmax=128.0, default=70.0,
          formatter="float1", musical=(30.0, 120.0)),
        P("bowed.bowmotion", "Bow Motion", rmin=0.0, rmax=128.0, default=30.0,
          formatter="float1", musical=(0.0, 90.0)),
        P("bowed.modalresonance", "Resonance", rmin=0.0, rmax=128.0, default=90.0,
          formatter="float1", musical=(40.0, 120.0)),
        P("bowed.bowvelocity", "Bow Velocity", rmin=0.0, rmax=128.0, default=80.0,
          formatter="float1", musical=(20.0, 120.0)),
        P("bowed.integration", "Integration", curve=Curve.ENUM, enum=["off", "on"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("bowed.decay", "Decay", unit="s", rmin=0.05, rmax=8.0, default=1.5,
          curve=Curve.EXP, formatter="float2", musical=(0.2, 4.0)),
        *_COMMON_TAIL("bowed", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# PLUCK — DWG plucked stiff string (sc3-plugins): inharmonic plucks (koto / clav /
# harp / muted string). Pitched by the note; a noise burst excites the string.
# --------------------------------------------------------------------------- #
PLUCK = VoiceSpec(
    type="PLUCK",
    role="Digital-waveguide plucked stiff string — koto / clav / harp / muted plucks.",
    synthdef="phPluck",
    params=[
        P("pluck.pos", "Pluck Position", rmin=0.02, rmax=0.5, default=0.14, musical=(0.05, 0.42)),
        P("pluck.decay", "Decay", unit="s", rmin=0.05, rmax=8.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.2, 4.0)),
        P("pluck.damp", "Damping", rmin=1.0, rmax=80.0, default=30.0, curve=Curve.EXP,
          formatter="float1", musical=(4.0, 60.0)),
        P("pluck.bright", "Brightness", default=0.5, musical=(0.1, 0.9)),
        P("pluck.excite", "Excite Length", unit="s", rmin=0.001, rmax=0.05, default=0.008,
          curve=Curve.EXP, formatter="float3", musical=(0.002, 0.03)),
        *_COMMON_TAIL("pluck", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# TUBE — TwoTube waveguide (sc3-plugins): hollow vocal-tract-ish plucks / reedy tones.
# Tube lengths (from the note) set the resonance; `balance` splits them.
# --------------------------------------------------------------------------- #
TUBE = VoiceSpec(
    type="TUBE",
    role="Two-tube waveguide — hollow formant plucks and reedy tones.",
    synthdef="phTube",
    params=[
        P("tube.k", "Junction", rmin=0.001, rmax=0.2, default=0.01, curve=Curve.EXP,
          formatter="float3", musical=(0.003, 0.12)),
        P("tube.loss", "Loss", rmin=0.9, rmax=1.0, default=0.99, formatter="float3",
          musical=(0.96, 0.999)),
        P("tube.balance", "Tube Balance", rmin=0.1, rmax=0.9, default=0.5, musical=(0.2, 0.8)),
        P("tube.excite", "Excite Length", unit="s", rmin=0.001, rmax=0.08, default=0.01,
          curve=Curve.EXP, formatter="float3", musical=(0.003, 0.05)),
        P("tube.decay", "Decay", unit="s", rmin=0.05, rmax=6.0, default=1.0,
          curve=Curve.EXP, formatter="float2", musical=(0.15, 3.0)),
        *_COMMON_TAIL("tube", ampd=0.9, ampmus=(0.5, 1.1)),
    ],
)

# --------------------------------------------------------------------------- #
# CHAOS — chaotic-map oscillator (core UGens): feedback sine + iterated maps.
# `type` selects the map; chaosA/chaosB steer it from tone to noise. Glitch/noise.
# --------------------------------------------------------------------------- #
CHAOS = VoiceSpec(
    type="CHAOS",
    role="Chaotic-map oscillator (FBSine / Latoocarfian / Henon / Standard / Cusp).",
    synthdef="phChaos",
    params=[
        P("chaos.type", "Map", curve=Curve.ENUM,
          enum=["fbsine", "latoocarf", "henon", "standard", "cusp"],
          default=0, randomize=RandomizePolicy.WIDE),
        P("chaos.chaosA", "Chaos A", rmin=0.0, rmax=4.0, default=1.1, musical=(0.3, 3.2)),
        P("chaos.chaosB", "Chaos B", rmin=0.0, rmax=3.0, default=0.5, musical=(0.1, 2.4)),
        P("chaos.fold", "Wavefold", default=0.0, musical=(0.0, 0.6)),
        P("chaos.cutoff", "Cutoff", unit="Hz", rmin=40.0, rmax=16000.0, default=6000.0,
          curve=Curve.EXP, formatter="Hz", musical=(300.0, 14000.0)),
        P("chaos.res", "Resonance", default=0.2, musical=(0.0, 0.7), danger=DangerClass.FEEDBACK),
        P("chaos.attack", "Attack", unit="s", rmin=0.0005, rmax=2.0, default=0.003,
          curve=Curve.EXP, formatter="float3", musical=(0.001, 0.05)),
        P("chaos.decay", "Decay", unit="s", rmin=0.01, rmax=8.0, default=0.5,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 2.0)),
        P("chaos.ampCurve", "Amp Curve", rmin=-8.0, rmax=-1.0, default=-4.0,
          formatter="float1", musical=(-6.0, -2.0)),
        *_COMMON_TAIL("chaos", ampd=0.55, ampmus=(0.35, 0.9)),
    ],
)

# --------------------------------------------------------------------------- #
# WTABLE — a full SuperCollider rebuild of Ableton's Wavetable, reading the Move's
# own factory sprites. Two morphing wavetable oscillators (position swept per-hit by
# an envelope + LFO — the movement that defines the timbre) + sub + noise -> a
# mode-morph filter with drive -> AR/sustain envelope. wt1/wt2 pick sprites (loaded
# engine-side, not synth args); everything else is a live synth control.
# --------------------------------------------------------------------------- #
_wt_hi = float(max(0, WT_SPRITE_COUNT - 1))
WTABLE = VoiceSpec(
    type="WTABLE",
    role="Wavetable synth (Ableton sprites): morphing dual-osc + sub + noise, mode-morph filter.",
    synthdef="phWtable",
    params=[
        # sprite selectors — buffer loads, not synth args (engine intercepts wt1/wt2).
        P("wtable.wt1", "Wavetable 1", rmin=0.0, rmax=_wt_hi, default=0.0,
          musical=(0.0, _wt_hi), modulatable=False, macro=False, randomize=RandomizePolicy.WIDE),
        P("wtable.wt2", "Wavetable 2", rmin=0.0, rmax=_wt_hi, default=0.0,
          musical=(0.0, _wt_hi), modulatable=False, macro=False, randomize=RandomizePolicy.WIDE),
        P("wtable.pos1", "Position 1", default=0.0, musical=(0.0, 0.85)),
        P("wtable.pos2", "Position 2", default=0.0, musical=(0.0, 0.85)),
        P("wtable.oscmix", "Osc Mix", default=0.5, musical=(0.2, 0.8)),
        P("wtable.detune", "Detune", unit="cents", rmin=-50.0, rmax=50.0, default=0.0,
          curve=Curve.BIPOLAR, formatter="float1", musical=(-24.0, 24.0)),
        P("wtable.transpose2", "Osc2 Transpose", unit="st", curve=Curve.ENUM,
          enum=[str(i) for i in range(-24, 25)], rmin=-24.0, rmax=24.0, default=0.0),
        P("wtable.suboct", "Sub Octave", curve=Curve.ENUM,
          enum=["0", "-1", "-2", "-3"], rmin=0.0, rmax=3.0, default=1.0),
        P("wtable.sublevel", "Sub Level", default=0.0, musical=(0.0, 0.6)),
        P("wtable.noiselevel", "Noise Level", default=0.0, musical=(0.0, 0.4)),
        P("wtable.cutoff", "Cutoff", unit="Hz", rmin=40.0, rmax=18000.0, default=8000.0,
          curve=Curve.EXP, formatter="Hz", musical=(400.0, 14000.0)),
        P("wtable.res", "Resonance", default=0.2, musical=(0.0, 0.75), danger=DangerClass.FEEDBACK),
        P("wtable.filttype", "Filter Mode", curve=Curve.ENUM,
          enum=["lowpass", "bandpass", "highpass"], rmin=0.0, rmax=2.0, default=0.0),
        P("wtable.drive", "Drive", rmin=0.1, rmax=6.0, default=1.0, musical=(0.3, 3.0)),
        P("wtable.filtenv", "Filter Env", default=0.3, musical=(0.0, 0.8)),
        P("wtable.posenv", "Position Env", default=0.35, musical=(0.0, 0.85)),
        P("wtable.poslfoRate", "Pos LFO Rate", unit="Hz", rmin=0.01, rmax=30.0, default=0.5,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 8.0)),
        P("wtable.poslfoAmt", "Pos LFO Amount", default=0.0, musical=(0.0, 0.6)),
        P("wtable.attack", "Attack", unit="s", rmin=0.001, rmax=4.0, default=0.01,
          curve=Curve.EXP, formatter="float3", musical=(0.002, 0.4)),
        P("wtable.decay", "Decay", unit="s", rmin=0.005, rmax=8.0, default=0.5,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 2.0)),
        P("wtable.sustain", "Sustain", default=0.7, musical=(0.2, 0.95)),
        P("wtable.release", "Release", unit="s", rmin=0.01, rmax=8.0, default=0.7,
          curve=Curve.EXP, formatter="float2", musical=(0.05, 3.0)),
        P("wtable.ampcurve", "Amp Curve", rmin=-8.0, rmax=-1.0, default=-4.0,
          formatter="float1", musical=(-6.0, -2.0)),
        *_COMMON_TAIL("wtable", ampd=0.5, ampmus=(0.35, 0.85)),
    ],
)

VOICES: dict[str, VoiceSpec] = {v.type: v for v in
                                (DRUM, FM7, BUCHLOID, MOLLY, RINGS, BEN, NOIZEOP, ICARUS,
                                 PLAITS, SHAKER, MEMBRANE, MALLET, BOWED, PLUCK, TUBE, CHAOS,
                                 WTABLE)}


def macro_specs(voice_type: str) -> list[tuple[str, str, float, float]]:
    """(full_pid, engine_arg, lo, hi) for every macro-sweepable param of a voice type.

    Drives the per-track voice-macro knob: one knob sweeps all of a voice's timbral
    params across their musical bands. Excludes amp/pan (dedicated knobs), enums
    (structural switches), and params flagged macro_eligible=False."""
    out: list[tuple[str, str, float, float]] = []
    if voice_type not in VOICES:          # EMPTY / unassigned track: no macro params
        return out
    for meta in VOICES[voice_type].params:
        if not meta.macro_eligible or meta.curve == Curve.ENUM:
            continue
        if meta.musical_min is None or meta.musical_max is None:
            continue
        arg = engine_arg(meta.id)
        if arg in ("amp", "pan"):
            continue
        out.append((meta.id, arg, float(meta.musical_min), float(meta.musical_max)))
    return out


def macro_specs_full(voice_type: str) -> list[tuple[str, str, float, float, float, float]]:
    """(pid, arg, rmin, rmax, musical_lo, musical_hi) for every macro-sweepable param.
    Like macro_specs but also carries the FULL parameter range — so a transform can push
    a param to an extreme (real fx/character), not just across its polite musical band."""
    out: list[tuple[str, str, float, float, float, float]] = []
    if voice_type not in VOICES:
        return out
    for meta in VOICES[voice_type].params:
        if not meta.macro_eligible or meta.curve == Curve.ENUM:
            continue
        arg = engine_arg(meta.id)
        if arg in ("amp", "pan"):
            continue
        mlo = meta.musical_min if meta.musical_min is not None else meta.rmin
        mhi = meta.musical_max if meta.musical_max is not None else meta.rmax
        out.append((meta.id, arg, float(meta.rmin), float(meta.rmax), float(mlo), float(mhi)))
    return out


# --------------------------------------------------------------------------- #
# FX chain — 8 insert effects in canonical signal-flow order (index == chain
# position == FX pad, left to right; VERB is last/rightmost). Must match
# ~fxDefs in engine.scd. Each entry: (engine_arg, musical_lo, musical_hi) — the
# band the randomized macro morphs the param across.
# --------------------------------------------------------------------------- #
@dataclass
class FxSpec:
    name: str
    short: str
    params: list           # [(arg, lo, hi), ...] morphed by the macro

FX_SPECS: list[FxSpec] = [
    FxSpec("OVERDRIVE", "OD", [("drive", 2.0, 32.0), ("tone", -0.6, 0.7), ("fold", 0.0, 0.9),
                               ("bias", 0.0, 0.55), ("grit", 0.0, 0.85), ("shape", 0.0, 0.8),
                               ("glitch", 0.0, 0.7)]),
    FxSpec("AMPSIM", "AMP", [("gain", 2.0, 20.0), ("bass", -8.0, 8.0), ("mid", -8.0, 8.0), ("treble", -8.0, 8.0)]),
    FxSpec("BITCRUSHER", "CRSH", [("bits", 3.0, 12.0), ("downsample", 1.0, 24.0)]),
    FxSpec("RINGMOD", "RING", [("freq", 20.0, 2000.0), ("drive", 0.5, 3.5)]),
    FxSpec("FLANGER", "FLNG", [("rate", 0.05, 2.0), ("depth", 0.3, 1.0), ("feedback", 0.0, 0.8)]),
    # Kept firmly in GRANULAR territory: density stays high (a cloud, not sparse echoes),
    # position near the write head (live, not a long delay tap), feedback low (no echo
    # tail), and NO global pitch shift (that + position was the "pitch-shifted delay"). The
    # texture comes from grain size/density/texture/spread + the internal reverb wash.
    FxSpec("CLOUDS", "CLDS", [("dens", 0.65, 0.98), ("size", 0.25, 0.7), ("tex", 0.3, 0.85),
                              ("pos", 0.0, 0.35), ("spread", 0.5, 1.0), ("rvb", 0.0, 0.4),
                              ("fb", 0.0, 0.2)]),
    # slot 6: RESO (Streson resonator) — replaces the reverb; slot 7: GREY moved to the end.
    FxSpec("STRESON", "RESO", [("freq", 60.0, 2000.0), ("res", 0.5, 0.96), ("damp", 0.1, 0.8)]),
    FxSpec("GREYHOLE", "GREY", [("dTime", 0.05, 1.2), ("feedback", 0.2, 0.85), ("size", 0.8, 4.0),
                                ("diff", 0.3, 1.0), ("damp", 0.1, 0.7), ("modDepth", 0.0, 0.5),
                                ("modFreq", 0.1, 6.0)]),
]
N_FX = len(FX_SPECS)
