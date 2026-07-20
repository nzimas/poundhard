"""PoundHard pattern-variation generator.

The flagship generative feature: from the pattern the user is on, produce up to 8
new patterns that are **structurally and musically related** but clearly distinct —
recognizable as parts of the same piece. It first *analyses* the existing patterns
(active tracks, rhythmic density & onsets, the piece's pitch material, roles), then
applies bounded, musical transformations that ramp from subtle (variation 1) to bold
(variation 8).

Patterns are **self-contained**: a load restores every engine's params, the
engine-to-track assignment, FX and the sequences. So each variation carries the base's
sounds verbatim (that's the family resemblance) and only its *groove* is transformed —
and a variation that introduces a complementary instrument can simply carry that
instrument's sound itself, leaving the seed pattern untouched.

Melody is expressed as **per-step pitch locks** rather than by moving a track's default
note: it keeps the voice's identity intact while giving the line real movement.
"""
from __future__ import annotations

import random

from . import catalog
from . import kits
from .tracks import Track, N_TRACKS, N_STEPS, N_PATTERNS

# engines whose pitch is genuinely melodic (worth per-step pitch locks). BEN /
# NOIZEOP / BUCHLOID track `note` but as texture, so they get rhythm-only variation.
_MELODIC = {"FM7", "MOLLY", "RINGS", "ICARUS"}
_DRUM_MODE = ["kick", "snare", "hihat", "metal", "clap", "tom", "noise"]


# --------------------------------------------------------------------------- #
# small rhythm helpers (operate on the in-length [0..L) slice of a 32-step row)
# --------------------------------------------------------------------------- #
def _euclid(k: int, n: int) -> list[int]:
    """Even (Euclidean) distribution of k pulses over n steps, first pulse on 0."""
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
    # rotate so a hit lands on step 0 (downbeat anchor)
    first = out.index(1) if 1 in out else 0
    return out[first:] + out[:first]


def _onsets(row: list[int], L: int) -> list[int]:
    return [i for i in range(min(L, len(row))) if row[i]]


def _rotate(row: list[int], L: int, by: int) -> list[int]:
    out = [0] * len(row)
    on = _onsets(row, L)
    for i in on:
        out[(i + by) % L] = 1
    return out


def _thin(row: list[int], L: int, amt: float, rng, protect: set[int]) -> list[int]:
    out = list(row)
    for i in _onsets(row, L):
        if i not in protect and rng.random() < amt:
            out[i] = 0
    return out


def _thicken(row: list[int], L: int, amt: float, rng) -> list[int]:
    out = list(row)
    empties = [i for i in range(L) if not out[i]]
    # prefer off-beats (odd 16th positions) for added hits — syncopation, not clutter
    rng.shuffle(empties)
    empties.sort(key=lambda i: 0 if (i % 2 == 1) else 1)
    for i in empties:
        if rng.random() < amt:
            out[i] = 1
    return out


def _fill(row: list[int], L: int, rng) -> list[int]:
    """A short burst over the last 2–4 steps (end-of-phrase fill)."""
    out = list(row)
    span = rng.choice([2, 3, 4])
    for i in range(max(0, L - span), L):
        out[i] = 1
    return out


# --------------------------------------------------------------------------- #
# pitch helpers
# --------------------------------------------------------------------------- #
def _snap(note: int, pcs: set[int]) -> int:
    """Nearest note whose pitch-class is in the scale set (stays in key)."""
    if not pcs:
        return note
    for d in range(0, 12):
        for cand in (note - d, note + d):
            if cand % 12 in pcs:
                return cand
    return note


# --------------------------------------------------------------------------- #
# analysis
# --------------------------------------------------------------------------- #
def _role(td: dict) -> str:
    t = td.get("type", "EMPTY")
    if t == "DRUM":
        return "drum:" + _DRUM_MODE[int(round(td.get("params", {}).get("drum.mode", 0))) % 7]
    if t in ("ICARUS", "BUCHLOID"):
        return "pad"
    if t == "NOIZEOP":
        return "noise"
    if t in _MELODIC:
        return "tonal"
    return "other"


def analyze(base: dict, all_patterns: list) -> dict:
    """Understand the piece before transforming it: which tracks play, how densely,
    what the pitch material is, and where the rhythmic anchor sits."""
    tracks = base.get("tracks", [])
    active, densities = [], {}
    for i, td in enumerate(tracks):
        L = max(1, int(td.get("length", N_STEPS)))
        on = _onsets(td.get("pattern", []), L)
        if td.get("type", "EMPTY") != "EMPTY" and on:
            active.append(i)
            densities[i] = len(on) / L

    # pitch material: every note actually sounded across ALL patterns (default note +
    # step-note locks on melodic tracks) -> the piece's key.
    pcs: set[int] = set()
    pats = [p for p in ([base] + list(all_patterns)) if p]
    for snap in pats:
        for td in snap.get("tracks", []):
            if td.get("type") in _MELODIC:
                L = max(1, int(td.get("length", N_STEPS)))
                for i in _onsets(td.get("pattern", []), L):
                    locks = td.get("step_note", [])
                    n = locks[i] if i < len(locks) and locks[i] is not None else td.get("note")
                    if n is not None:
                        pcs.add(int(n) % 12)
    if len(pcs) < 3:                       # too little to infer -> fall back to the kit scale
        pcs = {(kits._ROOT + s) % 12 for s in kits._SCALE}

    # anchor = the kick if present, else densest drum, else the lowest-index active track
    anchor = -1
    drums = [i for i in active if tracks[i].get("type") == "DRUM"]
    kicks = [i for i in drums if _role(tracks[i]) == "drum:kick"]
    if kicks:
        anchor = kicks[0]
    elif drums:
        anchor = max(drums, key=lambda i: densities[i])
    elif active:
        anchor = active[0]

    engines = {td.get("type") for td in tracks if td.get("type", "EMPTY") != "EMPTY"}
    roles = {i: _role(tracks[i]) for i in active}
    return {"active": active, "densities": densities, "pcs": pcs, "anchor": anchor,
            "engines": engines, "roles": roles,
            "empty_tracks": [i for i, td in enumerate(tracks) if td.get("type", "EMPTY") == "EMPTY"]}


# --------------------------------------------------------------------------- #
# per-track transforms (all groove-only)
# --------------------------------------------------------------------------- #
def _vary_rhythm(tr: Track, role: str, intensity: float, rng, is_anchor: bool) -> None:
    L = max(1, tr.length)
    on = _onsets(tr.pattern, L)
    k = len(on)
    if k == 0:
        return
    if is_anchor:
        # the anchor holds the piece together — only a tiny nudge at high intensity
        if intensity > 0.6 and rng.random() < 0.3:
            tr.pattern = _rotate(tr.pattern, L, rng.choice([-1, 1]))
        return
    protect = {0} if (0 in on) else set()        # keep the downbeat if it had one
    r = rng.random()
    if role.startswith("drum:hihat") or role == "noise":
        nk = max(1, min(L, k + rng.choice([-2, -1, 1, 2, 3])))
        tr.pattern = _euclid(nk, L) + [0] * (N_STEPS - L)
    elif r < 0.20 + 0.25 * intensity:
        tr.pattern = _rotate(tr.pattern, L, rng.choice([-3, -2, -1, 1, 2, 3]))
    elif r < 0.50:
        nk = max(1, min(L, k + rng.choice([-1, 0, 1])))
        tr.pattern = _euclid(nk, L) + [0] * (N_STEPS - L)
    elif r < 0.70:
        tr.pattern = _thin(tr.pattern, L, 0.20 + 0.30 * intensity, rng, protect)
    elif r < 0.90:
        tr.pattern = _thicken(tr.pattern, L, 0.20 + 0.30 * intensity, rng)
    else:
        tr.pattern = _fill(tr.pattern, L, rng)
    # never let a track go fully silent from a transform (keeps the arrangement full)
    if not any(tr.pattern[:L]):
        tr.pattern[on[0]] = 1


def _vary_melody(tr: Track, pcs: set[int], intensity: float, rng) -> None:
    """Melody = per-step pitch locks (groove). Transpose the line by a consonant
    interval and/or add stepwise contour, snapping everything back into key."""
    L = max(1, tr.length)
    on = _onsets(tr.pattern, L)
    if not on:
        return
    delta = 0
    if rng.random() < 0.25 + 0.55 * intensity:
        delta = rng.choice([-12, -7, -5, -3, 3, 5, 7, 12])
    contour = rng.random() < 0.5 * intensity
    if delta == 0 and not contour:
        return
    for i in on:
        base = tr.step_note[i] if tr.step_note[i] is not None else tr.note
        n = int(base) + delta
        if contour:
            n += rng.choice([-2, -1, 0, 0, 1, 2])
        tr.step_note[i] = max(24, min(96, _snap(n, pcs)))


def _vary_dynamics(tr: Track, intensity: float, rng) -> None:
    """Light accents: emphasise the downbeat, duck a few off-beats. Adds feel without
    changing the notes."""
    if rng.random() > 0.4 * intensity:
        return
    L = max(1, tr.length)
    for i in _onsets(tr.pattern, L):
        base = tr.step_vel[i] if tr.step_vel[i] is not None else tr.vel
        accent = 1.0
        if i % 4 == 0:
            accent = 1.0 + 0.15 * intensity
        elif rng.random() < 0.3:
            accent = 1.0 - 0.25 * intensity
        tr.step_vel[i] = round(max(0.1, min(2.0, base * accent)), 3)


# --------------------------------------------------------------------------- #
# adding a complementary instrument (sparingly)
# --------------------------------------------------------------------------- #
def _decide_additions(analysis: dict, rng) -> list[tuple[int, dict]]:
    """Pick 0–2 complementary instruments for EMPTY tracks when there's a clear gap.
    PURE: returns [(track_idx, voice)] — the sound is installed into the variations that
    use it, so the seed pattern is never touched."""
    empty = list(analysis["empty_tracks"])
    engines = analysis["engines"]
    if not empty:
        return []
    wants: list[str] = []
    # a sustaining pad/drone under the groove
    if not (engines & {"ICARUS", "BUCHLOID"}):
        wants.append("ICARUS")
    # a high percussion / noise shimmer
    drum_roles = {analysis["roles"][i] for i in analysis["active"] if analysis["roles"][i].startswith("drum")}
    if "drum:hihat" not in drum_roles and "NOIZEOP" not in engines:
        wants.append(rng.choice(["NOIZEOP", "DRUM"]))
    rng.shuffle(wants)
    added = []
    for engine in wants[:2]:
        if not empty:
            break
        t = empty.pop(rng.randrange(len(empty)))
        voice = kits.gen_palette_voice(engine, rng)
        if engine == "DRUM":                   # force a hi-hat so it complements, not doubles the kick
            voice["params"]["drum.mode"] = 2
            voice["note"] = 72
        added.append((t, voice))
    return added


def _added_groove(tr: Track, engine: str, L: int, intensity: float, rng) -> None:
    """Give a newly-added instrument a sparse, related part for THIS variation."""
    tr.length = L
    if engine in ("ICARUS", "BUCHLOID"):       # pad: a hit at the top of the phrase (+ maybe mid)
        pat = [0] * N_STEPS
        pat[0] = 1
        if rng.random() < 0.5:
            pat[L // 2] = 1
        tr.pattern = pat
    else:                                      # perc / noise: a euclidean shimmer
        k = rng.choice([3, 4, 5, 6, 8])
        tr.pattern = _euclid(min(k, L), L) + [0] * (N_STEPS - L)


# --------------------------------------------------------------------------- #
# variation assembly
# --------------------------------------------------------------------------- #
def _make_variation(base: dict, analysis: dict, added: list[tuple[int, dict]],
                    intensity: float, rng) -> dict:
    snap = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
    snap["voice_dir"] = [dict(d) for d in base.get("voice_dir", [])]
    src_tracks = base["tracks"]
    new_tracks = []
    active = set(analysis["active"])
    anchor = analysis["anchor"]
    pcs = analysis["pcs"]
    add_map = dict(added)

    # how many non-anchor active tracks to transform this variation (>=1, grows w/ intensity)
    variable = [i for i in analysis["active"] if i != anchor]
    n_change = max(1, min(len(variable), round((0.4 + 0.5 * intensity) * len(variable)))) if variable else 0
    to_change = set(rng.sample(variable, n_change)) if variable else set()

    for i, td in enumerate(src_tracks):
        tr = Track.from_dict(td)
        if i in add_map:                       # a complementary instrument for THIS variation
            if rng.random() < 0.35 + 0.5 * intensity:
                voice = add_map[i]
                tr.load_voice(voice)           # the variation carries the sound itself
                _added_groove(tr, voice["type"], 16, intensity, rng)
                snap["voice_dir"][i] = {arg: (1 if rng.random() < 0.5 else -1)
                                        for (_pid, arg, _lo, _hi) in catalog.macro_specs(voice["type"])}
            new_tracks.append(tr.to_dict())    # otherwise the track stays EMPTY here
            continue
        if i not in active:
            new_tracks.append(td)
            continue
        role = analysis["roles"].get(i, "other")
        if i == anchor:
            _vary_rhythm(tr, role, intensity, rng, is_anchor=True)
        elif i in to_change:
            _vary_rhythm(tr, role, intensity, rng, is_anchor=False)
            if td.get("type") in _MELODIC:
                _vary_melody(tr, pcs, intensity, rng)
            _vary_dynamics(tr, intensity, rng)
            # occasional structural contrast: drop a non-anchor track, or shift its meter
            if rng.random() < 0.15 * intensity:
                tr.muted = not tr.muted
            if role == "tonal" and rng.random() < 0.2 * intensity:
                tr.length = rng.choice([12, 16, 20, 24, 32])
        new_tracks.append(tr.to_dict())

    snap["tracks"] = new_tracks
    return snap


# --------------------------------------------------------------------------- #
# FULL PATTERN RANDOMISER (Shift + volume touch + Track 3)
#
# Builds a whole self-contained pattern from nothing: picks an ensemble of 4–10
# tracks, assigns engines, generates their sounds, writes idiomatic parts, and sets
# a little FX. Aesthetic target: between IDM and rhythmic noise — and NOT cacophonic,
# which is what most of the rules below are actually for:
#   * every voice comes from a curated role in kits.ROLES, so notes are all drawn
#     from the same low phrygian scale over the same root -> it's always in key
#   * roles fix the register (sub / bass / mid / ornament), so voices don't mask
#   * per-category level + pan placement keeps the mix readable
#   * a density budget thins the busiest voices when the whole thing gets too full
#   * only 0–3 FX, at moderate wet — no wall of mud
# --------------------------------------------------------------------------- #
_CAT = {                                   # role name -> ensemble category
    "KICK": "kick",
    "SNARE": "perc", "CL HAT": "perc", "OP HAT": "perc", "CLAP": "perc", "PERC": "perc",
    "BASS": "bass",
    "RING M": "tonal", "RING P": "tonal", "ORNMNT": "tonal", "M LEAD": "tonal",
    "NOIZOP": "texture", "NOISE": "texture", "BEN": "texture",
    "M PAD": "pad", "DRONE": "pad",
}
# category -> (level band, pan spread). Textures and pads sit back; drums lead.
_LEVEL = {"kick": (0.85, 1.0), "perc": (0.6, 0.9), "bass": (0.75, 0.95),
          "tonal": (0.45, 0.7), "texture": (0.3, 0.55), "pad": (0.35, 0.6)}
_MAX_ONSETS = 56                           # musical restraint: total onsets across the pattern

# ---- CPU budget -----------------------------------------------------------
# MEASURED on the device (scsynth /status, one track at density 0.5, maxPoly 3,
# 120bpm), as %CPU above a 4.9% idle baseline. These are why generated patterns
# could XRun: ten expensive tracks is >130% CPU before a single effect.
_ENGINE_COST = {"DRUM": 5.3, "FM7": 8.5, "BUCHLOID": 6.0, "RINGS": 9.6,
                "BEN": 9.7, "MOLLY": 11.7, "NOIZEOP": 12.0, "ICARUS": 13.2,
                # PLAITS measured 5.1% mean / 6.9% worst across its models (it's one
                # well-optimised macro-oscillator) — the conservative figure is used.
                # FM7 is a real 6-operator matrix — provisional 8.5 pending device measure.
                # SHAKER (STK) / MEMBRANE (2D waveguide) provisional pending device measure.
                "PLAITS": 6.9, "SHAKER": 7.0, "MEMBRANE": 9.0}
# Measured per FX INSTANCE (they're per-track inserts, not sends!). Reverb costs as
# much as a whole ICARUS voice, so a pattern gets at most one. CLDS = MiClouds
# (granular) and GREY = Greyhole are provisional pending device measure.
_FX_COST = [2.5, 1.7, 0.8, 1.0, 1.1, 6.0, 4.5, 10.0]   # OD AMP CRSH RING FLNG CLDS GREY VRB
_CPU_BUDGET = 52.0                         # leaves ~45% headroom for peaks/jitter on the ARM
_MAX_TRACKS = 8


def _voice_cost(engine: str, onsets: int, length: int) -> float:
    """Estimated %CPU for a voice, scaled by how many voices are alive at once.
    _ENGINE_COST was measured at density 0.5, so that's the 1.0 calibration point; a
    denser part overlaps more voices (up to the maxPoly=3 cap), so it costs MORE — the
    factor keeps rising past 0.5 instead of flattening there (a flat cap under-budgeted
    the busiest patterns, which is what let them XRun). A sparse part still rings once,
    hence the 0.5 floor."""
    d = onsets / max(1, length)
    return _ENGINE_COST.get(engine, 6.0) * min(1.8, max(0.5, 0.5 + d))


# ---- archetypes -----------------------------------------------------------
# A pattern is built to ONE of these, not from uniform randomness. That's what makes a
# generated pattern feel intentional (it has a clear identity) while the set stays
# diverse (a different identity each time). Cheap ensembles may run wider; expensive,
# textural ones stay small — which happens to align with the CPU budget.
_ARCHETYPES = [
    {"name": "MINIMAL",   "n": (4, 5), "want": {"perc": 1, "bass": 1, "tonal": 1, "pad": 1},
     "dens": 0.55, "interlock": 0.7},
    {"name": "BROKEN",    "n": (5, 7), "want": {"perc": 2, "bass": 1, "tonal": 1, "texture": 1},
     "dens": 0.9, "interlock": 0.85},
    {"name": "NOISE",     "n": (4, 6), "want": {"perc": 1, "bass": 1, "texture": 2},
     "dens": 1.0, "interlock": 0.5},
    {"name": "HYPNOTIC",  "n": (5, 7), "want": {"perc": 2, "bass": 1, "tonal": 1, "pad": 1},
     "dens": 0.8, "interlock": 0.4},
    {"name": "TEXTURAL",  "n": (4, 6), "want": {"perc": 1, "tonal": 1, "texture": 1, "pad": 1},
     "dens": 0.45, "interlock": 0.6},
    {"name": "PERCUSSIVE", "n": (6, 8), "want": {"perc": 4, "bass": 1, "tonal": 1},
     "dens": 1.0, "interlock": 0.8},
]


def _role_pool() -> dict:
    pool = {r.name: r for r in kits.ROLES}
    pool["ICARUS"] = kits.PALETTE_ROLES["ICARUS"]     # pad engine that isn't in ROLES
    _CAT["ICARUS"] = "pad"
    pool.update(kits.PLAITS_ROLES)                    # one targeted role per Plaits model
    _CAT.update(kits.PLAITS_CAT)
    pool.update(kits.SHAKER_ROLES)                    # STK shakers — percussion
    pool.update(kits.MEMBRANE_ROLES)                  # struck membranes — percussion
    for n in kits.SHAKER_ROLES:
        _CAT[n] = "perc"
    for n in kits.MEMBRANE_ROLES:
        _CAT[n] = "perc"
    return pool


# Layout order for a generated pattern: engines in palette order, and within an engine
# the roles keep their musical order from kits.ROLES (kick before snare before hats…).
# The step buttons are coloured by engine, so grouping this way makes the generated rig
# read as contiguous colour blocks instead of a scatter.
_ROLE_ORDER = {r.name: i for i, r in enumerate(kits.ROLES)}
# Plaits' models order themselves by model index inside the PLAITS block
_ROLE_ORDER.update({s[1]: 100 + s[0] for s in kits._PLAITS_SPEC})
# SHAKER then MEMBRANE blocks sort after PLAITS (palette order 9, 10)
_ROLE_ORDER.update({s[1]: 200 + i for i, s in enumerate(kits._SHAKER_SPEC)})
_ROLE_ORDER.update({s[0]: 300 + i for i, s in enumerate(kits._MEMBRANE_SPEC)})


def _layout_key(name: str, pool: dict) -> tuple[int, int]:
    t = pool[name].type
    engine = kits.PALETTE_ENGINES.index(t) if t in kits.PALETTE_ENGINES else len(kits.PALETTE_ENGINES)
    return (engine, _ROLE_ORDER.get(name, 99))


def _used_fx(voices: list[dict]) -> list[int]:
    return [k for v in voices for k in v["fx"]]


def _has_verb(voices: list[dict]) -> bool:
    return 7 in _used_fx(voices)


def _scale_k(choices: list[int], dens: float, L: int, rng) -> int:
    """Pick a pulse count and scale it by the archetype's density."""
    return max(1, min(L, round(rng.choice(choices) * dens)))


def _part_for(name: str, cat: str, L: int, dens: float, rng) -> list[int]:
    """An idiomatic part for a role, on the in-length grid."""
    pat = [0] * N_STEPS
    def put(row):
        for i, v in enumerate(row[:L]):
            pat[i] = v
    if cat == "kick":
        put(_euclid(_scale_k([3, 4, 4, 5, 6], dens, L, rng), L))   # euclid lands a hit on 0
    elif name in ("SNARE", "CLAP", "PL SD"):
        if rng.random() < 0.6:                            # backbeat
            for i in range(L):
                if i % 8 == 4:
                    pat[i] = 1
        else:
            put(_rotate(_euclid(_scale_k([2, 3], dens, L, rng), L), L, rng.choice([2, 4])))
    elif name in ("CL HAT", "PL HH"):
        put(_euclid(_scale_k([6, 8, 10, 12], dens, L, rng), L))
    elif name == "OP HAT":
        put(_rotate(_euclid(_scale_k([2, 3, 4], dens, L, rng), L), L, rng.choice([1, 2, 3])))
    elif cat == "perc":                                   # PERC and any other percussion
        put(_rotate(_euclid(_scale_k([3, 5, 7], dens, L, rng), L), L, rng.randrange(L)))
    elif cat == "bass":
        put(_euclid(_scale_k([3, 4, 5, 6], dens, L, rng), L))
    elif cat == "tonal":
        put(_rotate(_euclid(_scale_k([3, 4, 5, 6, 7], dens, L, rng), L), L, rng.choice([0, 0, 1, 2])))
    elif cat == "texture":
        if name == "BEN":                                  # it self-patterns; retrigger rarely
            put(_euclid(_scale_k([1, 2, 3], dens, L, rng), L))
        else:                                              # rhythmic noise
            put(_rotate(_euclid(_scale_k([3, 4, 5, 6, 8], dens, L, rng), L), L, rng.randrange(L)))
    else:                                                  # pad / drone: one long hit, maybe two
        pat[0] = 1
        if rng.random() < 0.35 * dens:
            pat[L // 2] = 1
    return pat


def _interlock(pat: list[int], L: int, kick: list[int], rng, avoid: float) -> list[int]:
    """Push a part OFF the kick so the two interlock instead of doubling up. This is most
    of what makes a generated groove sound arranged rather than merely layered."""
    out = list(pat)
    for i in range(L):
        if out[i] and kick[i] and rng.random() < avoid:
            out[i] = 0
            for j in (i + 1, i - 1, i + 2):               # nudge to a free, kick-less step
                j %= L
                if not out[j] and not kick[j]:
                    out[j] = 1
                    break
    if not any(out[:L]):                                   # never silence a voice entirely
        out[rng.randrange(L)] = 1
    return out


# Plaits contributes 16 roles to buckets that hold ~5 each, so an unweighted pick would
# make it ~45% of every kit and drown the other eight engines. Weight its roles down so
# it reads as one versatile peer (~20-25% of voices), not the house sound.
_PLAITS_ROLE_W = 0.3


def _weighted_role(opts: list[str], rng) -> str:
    w = [_PLAITS_ROLE_W if o.startswith("PL ") else 1.0 for o in opts]
    return rng.choices(opts, weights=w)[0]


def _pick_ensemble(arch: dict, rng) -> list[str]:
    """Roles that fit the archetype: always a kick, then its wanted categories."""
    n = min(_MAX_TRACKS, rng.randint(*arch["n"]))
    # Plaits' models sit in these buckets by the job each one actually does, so the
    # randomiser reaches for (say) its speech model when it wants a texture — not at random.
    buckets = {
        "perc": ["SNARE", "CL HAT", "OP HAT", "CLAP", "PERC", "PL SD", "PL HH"],
        "bass": ["BASS", "PL VA", "PL FM"],
        "tonal": ["RING M", "RING P", "ORNMNT", "M LEAD",
                  "PL MODL", "PL STRG", "PL WSHP", "PL WTBL"],
        "texture": ["NOIZOP", "NOISE", "BEN", "PL SPCH", "PL PART", "PL NOIS", "PL FORM"],
        "pad": ["M PAD", "DRONE", "ICARUS", "PL CHRD", "PL HARM", "PL CLOUD"],
    }
    chosen = ["KICK" if rng.random() < 0.8 else "PL BD"]     # either kick engine
    # take the archetype's wants in a shuffled order so the same shape isn't always filled
    wants: list[str] = []
    for cat, cnt in arch["want"].items():
        wants += [cat] * cnt
    rng.shuffle(wants)
    for cat in wants:
        if len(chosen) >= n:
            break
        opts = [r for r in buckets[cat] if r not in chosen]
        if opts:
            chosen.append(_weighted_role(opts, rng))
    return chosen[:n]


def random_pattern(project, rng: random.Random | None = None) -> list[str]:
    """Fully randomise the CURRENT pattern in place (no new slots). Returns the role
    names used. The algorithm also picks the global tempo to suit what it built."""
    rng = rng or random.Random()
    st = project
    st.chaos_invalidate()                      # a new pattern -> a new chaos-macro safe zone
    pool = _role_pool()
    arch = rng.choice(_ARCHETYPES)             # ONE identity per pattern -> intentional
    dens = arch["dens"]
    names = _pick_ensemble(arch, rng)

    # --- build the voices first (unplaced), so the budget can trim before layout ---
    base_len = rng.choice([16, 16, 16, 32])
    voices = []                                # [{name, cat, voice, pattern, length, rate, locks}]
    kick_row: list[int] = [0] * N_STEPS
    for name in names:
        role = pool[name]
        cat = _CAT[name]
        voice = kits.gen_voice(role, rng)
        lo, hi = _LEVEL[cat]
        pfx = voice["type"].lower()
        voice["params"][pfx + ".amp"] = round(rng.uniform(lo, hi), 3)
        voice["params"][pfx + ".pan"] = 0.0 if cat in ("kick", "bass") else round(rng.uniform(-0.7, 0.7), 3)
        L = min(N_STEPS, base_len if rng.random() < 0.8 else rng.choice([12, 20, 24, 32]))
        rate = 1.0 if rng.random() < 0.88 else rng.choice([0.5, 2.0])
        pat = _part_for(name, cat, L, dens, rng)
        if cat == "kick":
            kick_row = list(pat)
        elif cat in ("perc", "bass", "tonal"):
            # interlock with the kick: the single biggest thing that makes it sound arranged
            # rather than merely layered. The bass leans on the kick more than it dodges it.
            avoid = arch["interlock"] * (0.5 if cat == "bass" else 1.0)
            pat = _interlock(pat, L, kick_row, rng, avoid)
        locks: dict[int, int] = {}
        if voice["type"] in _MELODIC and cat in ("tonal", "bass") and rng.random() < 0.7:
            pcs = {(kits._ROOT + s) % 12 for s in kits._SCALE}
            for i in _onsets(pat, L):
                if rng.random() < 0.6:
                    locks[i] = max(24, min(96, _snap(voice["note"] + rng.choice(
                        [-12, -5, -3, 0, 0, 0, 2, 3, 5, 7, 12]), pcs)))
        voices.append({"name": name, "cat": cat, "voice": voice, "pattern": pat,
                       "length": L, "rate": rate, "locks": locks, "fx": []})

    # --- FX: at most 2 inserts, and at most ONE reverb (measured at 10% CPU each) ---
    fx_budget = 0.0
    for v in voices:
        if len(_used_fx(voices)) >= 2:
            break
        p = {"pad": 0.6, "tonal": 0.35, "texture": 0.35}.get(v["cat"], 0.12)
        if rng.random() >= p:
            continue
        want_verb = v["cat"] in ("pad", "tonal") and not _has_verb(voices)
        fx = 7 if want_verb else rng.choice([0, 2, 6])          # VERB / OD, CRSH, DLY
        if fx_budget + _FX_COST[fx] > 12.0:                     # keep FX off the voices' budget
            continue
        v["fx"] = [fx]
        fx_budget += _FX_COST[fx]

    # --- CPU BUDGET (measured costs): thin the priciest voices, then drop them ---
    def est() -> float:
        c = sum(_voice_cost(v["voice"]["type"], len(_onsets(v["pattern"], v["length"])), v["length"])
                for v in voices)
        return c + sum(_FX_COST[k] for v in voices for k in v["fx"])
    guard = 0
    while est() > _CPU_BUDGET and len(voices) > 3 and guard < 64:
        guard += 1
        cands = [v for v in voices if v["cat"] != "kick"]
        if not cands:
            break
        worst = max(cands, key=lambda v: _voice_cost(
            v["voice"]["type"], len(_onsets(v["pattern"], v["length"])), v["length"]))
        before = len(_onsets(worst["pattern"], worst["length"]))
        if before > 2:                                          # thin it first — keep the voice
            worst["pattern"] = _thin(worst["pattern"], worst["length"], 0.4, rng, {0})
            if len(_onsets(worst["pattern"], worst["length"])) < before:
                continue
        voices.remove(worst)                                    # already sparse -> it has to go
    # musical restraint on top of the CPU rule
    guard = 0
    while sum(len(_onsets(v["pattern"], v["length"])) for v in voices) > _MAX_ONSETS and guard < 64:
        guard += 1
        cands = [v for v in voices if v["cat"] != "kick"]
        if not cands:
            break
        busiest = max(cands, key=lambda v: len(_onsets(v["pattern"], v["length"])))
        before = len(_onsets(busiest["pattern"], busiest["length"]))
        busiest["pattern"] = _thin(busiest["pattern"], busiest["length"], 0.4, rng, {0})
        if len(_onsets(busiest["pattern"], busiest["length"])) == before:
            break

    # --- lay out: grouped by engine, contiguous from track 1 ---
    voices.sort(key=lambda v: _layout_key(v["name"], pool))
    st.tracks = [Track() for _ in range(N_TRACKS)]
    st.track_fx = [[] for _ in range(N_TRACKS)]
    st.fx_bypass = [False] * N_TRACKS
    st.solo = -1
    total = 0
    placed = []
    for t, v in enumerate(voices):
        tr = st.tracks[t]
        tr.load_voice(v["voice"])
        tr.length = v["length"]
        tr.rate = v["rate"]
        tr.pattern = v["pattern"]
        for i, n in v["locks"].items():
            if i < N_STEPS and tr.pattern[i]:
                tr.step_note[i] = n
        st.reroll_voice_macro(t)
        if v["fx"]:
            fx = v["fx"][0]
            st.track_fx[t] = [fx]
            st.fx_macro[fx] = round(rng.uniform(0.3, 0.7), 3)
            st.fx_wet[fx] = round(rng.uniform(0.15, 0.45), 3)
        total += len(_onsets(tr.pattern, tr.length))
        placed.append((t, v["name"], v["cat"]))
    names = [v["name"] for v in voices]
    st.kit_name = "%s-%03d" % (arch["name"][:4], rng.randrange(1000))

    # TEMPO is the algorithm's call, judged against what it just built. IDM / rhythmic
    # noise spans roughly 85-175: a busy, texture-heavy pattern needs room to stay
    # legible, while a sparse one can run fast without turning to mush.
    span = max(1, sum(st.tracks[t].length for t, _n, _c in placed))
    density = total / span
    if density > 0.30:
        band = (86, 122)                       # dense -> slower, heavier
    elif density > 0.18:
        band = (112, 148)
    else:
        band = (130, 174)                      # sparse -> can run fast
    tempo = rng.uniform(*band)
    if rng.random() < 0.12:                    # the occasional outlier for character
        tempo = rng.uniform(80, 96) if rng.random() < 0.5 else rng.uniform(168, 180)
    st.tempo = float(round(max(80.0, min(180.0, tempo))))

    # the randomised pattern IS the current pattern (no extra slots created)
    if st.pattern_cur < 0:
        free = next((s for s in range(N_PATTERNS) if st.patterns[s] is None), -1)
        if free >= 0:
            st.pattern_cur = free
    if st.pattern_cur >= 0:
        st.patterns[st.pattern_cur] = st.snapshot()
    return names


# --------------------------------------------------------------------------- #
# SCORING — picking the ONE variation to keep.
#
# Shift+Track3 returns a single variation, so it can't lean on "one of eight will
# land". Instead we generate a pool of candidates and keep the best-scoring one.
# The score encodes what a good variation actually is: clearly a different part of
# the piece, unmistakably the same piece, musically arranged, and affordable.
# --------------------------------------------------------------------------- #
_DISTINCT_TARGET = 0.38        # ~this fraction of the groove changed reads as "a new part"
_CANDIDATES = 14


def _groove_distance(base: dict, cand: dict) -> float:
    """Fraction of in-length steps whose on/off state differs. Only tracks that carry
    material in EITHER version count — the ~11 idle tracks of a 5-voice pattern are
    identical by definition and would otherwise swamp the measurement."""
    diff = tot = 0
    for bt, ct in zip(base["tracks"], cand["tracks"]):
        b_on = bt.get("type", "EMPTY") != "EMPTY"
        c_on = ct.get("type", "EMPTY") != "EMPTY"
        if not (b_on or c_on):
            continue
        L = max(1, int((ct if c_on else bt).get("length", N_STEPS)))
        bp, cp = bt.get("pattern", []), ct.get("pattern", [])
        for i in range(L):
            tot += 1
            if (bp[i] if i < len(bp) else 0) != (cp[i] if i < len(cp) else 0):
                diff += 1
    return (diff / tot) if tot else 0.0


def _melody_moved(base: dict, cand: dict) -> bool:
    for bt, ct in zip(base["tracks"], cand["tracks"]):
        if bt.get("step_note") != ct.get("step_note"):
            return True
    return False


def _kick_row_of(snap: dict, anchor: int) -> tuple[list[int], int]:
    if anchor < 0:
        return ([], 0)
    td = snap["tracks"][anchor]
    L = max(1, int(td.get("length", N_STEPS)))
    return (list(td.get("pattern", [])), L)


def _score(base: dict, cand: dict, analysis: dict) -> float:
    """Higher is better. Rejects (-inf) are hard musical/CPU failures."""
    anchor = analysis["anchor"]
    active = analysis["active"]

    # --- hard rejects ---
    cost = 0.0
    for td in cand["tracks"]:
        t = td.get("type", "EMPTY")
        if t == "EMPTY":
            continue
        L = max(1, int(td.get("length", N_STEPS)))
        cost += _voice_cost(t, len(_onsets(td.get("pattern", []), L)), L)
    for stack in cand.get("track_fx", []):
        for k in stack:
            cost += _FX_COST[k]
    if cost > _CPU_BUDGET:
        return float("-inf")                   # would risk XRuns — never return this
    for i in active:                           # a voice that went silent isn't a variation
        td = cand["tracks"][i]
        if not any(td.get("pattern", [])[:max(1, int(td.get("length", N_STEPS)))]):
            return float("-inf")

    s = 0.0
    # --- distinctness: recognisably a different part, not a different piece ---
    d = _groove_distance(base, cand)
    s += 40.0 * max(0.0, 1.0 - abs(d - _DISTINCT_TARGET) / _DISTINCT_TARGET)
    if d < 0.10:
        s -= 60.0                              # barely changed — pointless
    if d > 0.70:
        s -= 40.0                              # unrecognisable — not the same piece

    # --- arrangement: do the parts interlock with the anchor rather than double it? ---
    kick, KL = _kick_row_of(cand, anchor)
    if kick:
        on_kick = tot = 0
        for i, td in enumerate(cand["tracks"]):
            if i == anchor or td.get("type", "EMPTY") == "EMPTY":
                continue
            L = max(1, int(td.get("length", N_STEPS)))
            if L != KL:
                continue
            for j in _onsets(td.get("pattern", []), L):
                tot += 1
                if j < len(kick) and kick[j]:
                    on_kick += 1
        if tot:
            s += 20.0 * (1.0 - (on_kick / tot))   # fewer collisions = better groove

    # --- density: musical, and it keeps the CPU honest ---
    onsets = sum(len(_onsets(td.get("pattern", []), max(1, int(td.get("length", N_STEPS)))))
                 for td in cand["tracks"] if td.get("type", "EMPTY") != "EMPTY")
    if onsets > _MAX_ONSETS:
        s -= 25.0
    if onsets < 6:
        s -= 25.0                              # too empty to be a part of anything

    # --- reward it for actually saying something new ---
    if _melody_moved(base, cand):
        s += 8.0
    new_voices = sum(1 for bt, ct in zip(base["tracks"], cand["tracks"])
                     if bt.get("type") == "EMPTY" and ct.get("type", "EMPTY") != "EMPTY")
    s += 10.0 * min(1, new_voices)             # introduced a complementary instrument
    s += 6.0 * (1.0 - cost / _CPU_BUDGET)      # gentle nudge toward the cheaper option
    return s


def generate(project, count: int = 1, rng: random.Random | None = None) -> tuple[list[int], list[int]]:
    """Generate ONE variation of the reference (currently selected) pattern into the next
    empty slot — the best of an internally-scored pool of candidates. Returns
    (added_track_indices, filled_slot_indices)."""
    rng = rng or random.Random()
    st = project
    st.commit_current()
    base = st.snapshot()

    active = [i for i, td in enumerate(base["tracks"])
              if td.get("type", "EMPTY") != "EMPTY" and any(td.get("pattern", []))]
    if not active:
        return ([], [])                        # nothing to vary

    empty_slots = [s for s in range(N_PATTERNS) if st.patterns[s] is None]
    # make sure the reference pattern lives in a slot (so the pair is a coherent group)
    if st.pattern_cur < 0:
        if not empty_slots:
            return ([], [])
        seed = empty_slots.pop(0)
        st.patterns[seed] = base
        st.pattern_cur = seed
    count = min(count, len(empty_slots))
    if count <= 0:
        return ([], [])

    analysis = analyze(base, st.patterns)

    slots = empty_slots[:count]
    out_added: list[int] = []
    for slot in slots:
        best, best_s, best_added = None, float("-inf"), []
        for _ in range(_CANDIDATES):
            # each candidate gets its own additions + intensity, so the pool really varies
            added = _decide_additions(analysis, rng)
            intensity = rng.uniform(0.30, 0.85)
            cand = _make_variation(base, analysis, added, intensity, rng)
            sc = _score(base, cand, analysis)
            if sc > best_s:
                best, best_s, best_added = cand, sc, added
        if best is None:                       # every candidate was rejected — try once, safely
            best = _make_variation(base, analysis, [], 0.45, rng)
            best_added = []
        st.patterns[slot] = best
        out_added += [t for t, _v in best_added
                      if best["tracks"][t].get("type", "EMPTY") != "EMPTY"]
    return (out_added, slots)
