"""PoundHard pattern-variation generator.

The flagship generative feature: from the pattern the user is on, produce up to 8
new patterns that are **structurally and musically related** but clearly distinct —
recognizable as parts of the same piece. It first *analyses* the existing patterns
(active tracks, rhythmic density & onsets, the piece's pitch material, roles), then
applies bounded, musical transformations that ramp from subtle (variation 1) to bold
(variation 8).

Crucial architecture constraint: pattern LOAD is groove-only (see Project._GROOVE_KEYS
— pattern / muted / length / rate / step_note / step_vel / step_pan / step_macro).
`note` is a *sound* field and is NOT applied on a live switch. So every variation
expresses melody as **per-step pitch locks** and rhythm as the on/off pattern — all
groove keys — which keeps the kit sounds identical (that's the family resemblance)
and works with live switching. The only thing that touches the kit is *adding* a
complementary instrument: its sound is written into the shared live state (an empty
track), silent in the base pattern and played in some variations.
"""
from __future__ import annotations

import random

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
def _decide_additions(project, analysis: dict, rng) -> list[int]:
    """Add 0–2 complementary instruments to EMPTY tracks when there's a clear gap.
    Returns the track indices added (their sound goes into the shared live kit)."""
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
        project.tracks[t].load_voice(voice)
        project.reroll_voice_macro(t)
        added.append(t)
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
def _make_variation(base: dict, analysis: dict, added: list[int], engine_of: dict,
                    intensity: float, rng) -> dict:
    snap = {k: (list(v) if isinstance(v, list) else v) for k, v in base.items()}
    src_tracks = base["tracks"]
    new_tracks = []
    active = set(analysis["active"])
    anchor = analysis["anchor"]
    pcs = analysis["pcs"]

    # how many non-anchor active tracks to transform this variation (>=1, grows w/ intensity)
    variable = [i for i in analysis["active"] if i != anchor]
    n_change = max(1, min(len(variable), round((0.4 + 0.5 * intensity) * len(variable)))) if variable else 0
    to_change = set(rng.sample(variable, n_change)) if variable else set()

    for i, td in enumerate(src_tracks):
        tr = Track.from_dict(td)
        if i in added:                         # a freshly-added instrument
            if rng.random() < 0.35 + 0.5 * intensity:
                L = max(1, int(td.get("length", N_STEPS)))
                _added_groove(tr, engine_of[i], L, intensity, rng)
            new_tracks.append(tr.to_dict())
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
    added = _decide_additions(st, analysis, rng)
    engine_of = {i: st.tracks[i].type for i in added}
    if added:
        st.commit_current()                    # base slot now carries the (silent) new tracks
        base = st.snapshot()
        analysis = analyze(base, st.patterns)

    slots = empty_slots[:count]
    for v, slot in enumerate(slots):
        intensity = 0.25 + 0.65 * (v / max(1, count - 1))
        st.patterns[slot] = _make_variation(base, analysis, added, engine_of, intensity, rng)
    return (added, slots)
