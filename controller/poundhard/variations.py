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
_MELODIC = {"FMTONE", "MOLLY", "RINGS", "ICARUS"}
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
_MAX_ONSETS = 72                           # total density budget across the pattern


def _role_pool() -> dict:
    pool = {r.name: r for r in kits.ROLES}
    pool["ICARUS"] = kits.PALETTE_ROLES["ICARUS"]     # pad engine that isn't in ROLES
    _CAT["ICARUS"] = "pad"
    return pool


# Layout order for a generated pattern: engines in palette order, and within an engine
# the roles keep their musical order from kits.ROLES (kick before snare before hats…).
# The step buttons are coloured by engine, so grouping this way makes the generated rig
# read as contiguous colour blocks instead of a scatter.
_ROLE_ORDER = {r.name: i for i, r in enumerate(kits.ROLES)}


def _layout_key(name: str, pool: dict) -> tuple[int, int]:
    t = pool[name].type
    engine = kits.PALETTE_ENGINES.index(t) if t in kits.PALETTE_ENGINES else len(kits.PALETTE_ENGINES)
    return (engine, _ROLE_ORDER.get(name, 99))


def _part_for(name: str, cat: str, L: int, rng) -> list[int]:
    """An idiomatic part for a role, on the in-length grid."""
    pat = [0] * N_STEPS
    def put(row):
        for i, v in enumerate(row[:L]):
            pat[i] = v
    if cat == "kick":
        put(_euclid(rng.choice([3, 4, 4, 5, 6]), L))      # euclid always lands a hit on 0
    elif name in ("SNARE", "CLAP"):
        if rng.random() < 0.6:                            # backbeat
            for i in range(L):
                if i % 8 == 4:
                    pat[i] = 1
        else:
            put(_rotate(_euclid(rng.choice([2, 3]), L), L, rng.choice([2, 4])))
    elif name == "CL HAT":
        put(_euclid(rng.choice([6, 8, 10, 12]), L))
    elif name == "OP HAT":
        put(_rotate(_euclid(rng.choice([2, 3, 4]), L), L, rng.choice([1, 2, 3])))
    elif name == "PERC":
        put(_rotate(_euclid(rng.choice([3, 5, 7]), L), L, rng.randrange(L)))
    elif cat == "bass":
        put(_euclid(rng.choice([3, 4, 5, 6]), L))
    elif cat == "tonal":
        put(_rotate(_euclid(rng.choice([3, 4, 5, 6, 7]), L), L, rng.choice([0, 0, 1, 2])))
    elif cat == "texture":
        if name == "BEN":                                  # it self-patterns; retrigger rarely
            put(_euclid(rng.choice([1, 2, 3]), L))
        else:                                              # rhythmic noise
            put(_rotate(_euclid(rng.choice([3, 4, 5, 6, 8]), L), L, rng.randrange(L)))
    else:                                                  # pad / drone
        pat[0] = 1
        if rng.random() < 0.4:
            pat[L // 2] = 1
    return pat


def _pick_ensemble(rng) -> list[str]:
    """4–10 roles that actually work together: a kick, some percussion, and a
    balanced spread of bass / tonal / texture / pad."""
    n = rng.randint(4, 10)
    chosen = ["KICK", rng.choice(["SNARE", "CLAP", "CL HAT", "PERC"])]
    buckets = {
        "perc": [r for r in ("SNARE", "CL HAT", "OP HAT", "CLAP", "PERC")],
        "bass": ["BASS"],
        "tonal": ["RING M", "RING P", "ORNMNT", "M LEAD"],
        "texture": ["NOIZOP", "NOISE", "BEN"],
        "pad": ["M PAD", "DRONE", "ICARUS"],
    }
    # aim for a sensible shape before filling at random
    order = ["bass", "tonal", "perc", "texture", "pad", "tonal", "texture", "perc"]
    caps = {"perc": 3, "bass": 1, "tonal": 3, "texture": 2, "pad": 1}
    used = {"perc": 1, "bass": 0, "tonal": 0, "texture": 0, "pad": 0}
    for cat in order:
        if len(chosen) >= n:
            break
        if used[cat] >= caps[cat]:
            continue
        opts = [r for r in buckets[cat] if r not in chosen]
        if not opts:
            continue
        chosen.append(rng.choice(opts))
        used[cat] += 1
    return chosen[:n]


def random_pattern(project, rng: random.Random | None = None) -> list[str]:
    """Fully randomise the CURRENT pattern in place (no new slots). Returns the role
    names used. The algorithm also picks the global tempo to suit what it built."""
    rng = rng or random.Random()
    st = project
    st.chaos_invalidate()                      # a new pattern -> a new chaos-macro safe zone
    pool = _role_pool()
    names = _pick_ensemble(rng)
    # group by engine type (palette order) so the used tracks form contiguous,
    # colour-coded blocks on the step buttons — readable at a glance
    names.sort(key=lambda n: _layout_key(n, pool))

    # wipe the machine, then place the ensemble on CONTIGUOUS tracks from track 1
    st.tracks = [Track() for _ in range(N_TRACKS)]
    st.track_fx = [[] for _ in range(N_TRACKS)]
    st.fx_bypass = [False] * N_TRACKS
    st.solo = -1
    slots = list(range(len(names)))

    base_len = rng.choice([16, 16, 16, 32])
    total = 0
    placed = []
    for idx, (t, name) in enumerate(zip(slots, names)):
        role = pool[name]
        cat = _CAT[name]
        voice = kits.gen_voice(role, rng)
        # level + stereo placement keep the mix readable (kick/bass centred)
        lo, hi = _LEVEL[cat]
        pfx = voice["type"].lower()
        voice["params"][pfx + ".amp"] = round(rng.uniform(lo, hi), 3)
        voice["params"][pfx + ".pan"] = 0.0 if cat in ("kick", "bass") else round(rng.uniform(-0.7, 0.7), 3)
        tr = st.tracks[t]
        tr.load_voice(voice)
        # mostly the shared length; the odd voice runs polymetric against it
        L = base_len if rng.random() < 0.75 else rng.choice([12, 20, 24, 32])
        tr.length = min(N_STEPS, L)
        tr.rate = 1.0 if rng.random() < 0.85 else rng.choice([0.5, 2.0])
        tr.pattern = _part_for(name, cat, tr.length, rng)
        # melodic voices get a per-step line drawn from the role's own scale material
        if voice["type"] in _MELODIC and cat in ("tonal", "bass") and rng.random() < 0.7:
            pcs = {(kits._ROOT + s) % 12 for s in kits._SCALE}
            for i in _onsets(tr.pattern, tr.length):
                if rng.random() < 0.6:
                    tr.step_note[i] = max(24, min(96, _snap(tr.note + rng.choice(
                        [-12, -5, -3, 0, 0, 0, 2, 3, 5, 7, 12]), pcs)))
        st.reroll_voice_macro(t)
        total += len(_onsets(tr.pattern, tr.length))
        placed.append((t, name, cat))

    # density budget: if it's too busy, thin the fullest non-kick voices until it breathes
    while total > _MAX_ONSETS:
        cands = [(len(_onsets(st.tracks[t].pattern, st.tracks[t].length)), t)
                 for t, nm, c in placed if c != "kick"]
        if not cands:
            break
        _n, t = max(cands)
        tr = st.tracks[t]
        before = len(_onsets(tr.pattern, tr.length))
        tr.pattern = _thin(tr.pattern, tr.length, 0.4, rng, {0})
        after = len(_onsets(tr.pattern, tr.length))
        if after == before:
            break
        total -= (before - after)

    # a little FX: 0-3 inserts at moderate wet. Reverb favours pads/tonal, drive the noise.
    for t, name, cat in placed:
        if rng.random() < {"pad": 0.7, "tonal": 0.45, "texture": 0.4}.get(cat, 0.15):
            fx = 7 if cat in ("pad", "tonal") else rng.choice([0, 2, 6])   # VERB / OD / CRSH / DLY
            if sum(1 for s in st.track_fx if s) < 3:
                st.track_fx[t] = [fx]
                st.fx_macro[fx] = round(rng.uniform(0.3, 0.7), 3)
                st.fx_wet[fx] = round(rng.uniform(0.15, 0.5), 3)
    st.kit_name = "RND-%04d" % rng.randrange(10000)

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


def generate(project, count: int = 8, rng: random.Random | None = None) -> tuple[list[int], list[int]]:
    """Generate up to `count` variation patterns into empty slots. May add 0–2
    complementary instruments to the shared kit. Returns (added_track_indices,
    filled_slot_indices)."""
    rng = rng or random.Random()
    st = project
    st.commit_current()
    base = st.snapshot()

    active = [i for i, td in enumerate(base["tracks"])
              if td.get("type", "EMPTY") != "EMPTY" and any(td.get("pattern", []))]
    if not active:
        return ([], [])                        # nothing to vary

    empty_slots = [s for s in range(N_PATTERNS) if st.patterns[s] is None]
    # make sure the seed pattern lives in a slot (so the set is a coherent group)
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
    added = _decide_additions(analysis, rng)   # pure — the seed pattern is left alone

    slots = empty_slots[:count]
    for v, slot in enumerate(slots):
        intensity = 0.25 + 0.65 * (v / max(1, count - 1))
        st.patterns[slot] = _make_variation(base, analysis, added, intensity, rng)
    return ([t for t, _v in added], slots)
