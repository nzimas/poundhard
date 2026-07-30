"""BREAK — automatic, musically-placed breakdowns.

The fifth bottom-row toggle. Every N pattern cycles Break takes over for one cycle,
transforms what the rig is playing, and hands it straight back. Like the other modifiers it
is an ENGINE-ONLY overlay: the pattern data is never touched, and everything it changes is
pushed back from the controller's own (untouched) state when the break ends.

WHY IT IS NOT A TEMPLATE LIBRARY. A fixed set of canned breakdowns gives itself away in
about four repetitions. What makes a break sound programmed rather than triggered is that it
responds to what is actually playing: which tracks carry the pulse, which are ornament, how
dense the bar is, and how much room there is to take something away. So the *type* is chosen
from what the pattern can support, and the parameters inside each type are then rolled.

THE VOCABULARY. Every type below is built from four primitives the engine already has, none
of which edits a sequence:

  mute        drop a track for the break            (dropouts, kick-only, percussion-only)
  pattern     push a DIFFERENT step list temporarily (stutters, displacement, pauses, fills)
  rate        change a track's clock                (double-time stutters, half-time drags)
  filter      move the per-track filter             (filtered breakdowns, build-ups)

`pattern` is the interesting one: pushing a modified step list to the engine leaves
`state.tracks[t].pattern` completely alone, so restoring is just re-pushing the real thing.
"""
from __future__ import annotations

import random

N_STEPS = 16

# Engines that read as rhythm section rather than melody. A break needs to know what the
# pulse IS before it can decide what to take away.
_DRUMISH = {"DRUM", "MEMBRANE", "SHAKER"}


def _density(tr) -> float:
    n = max(1, min(len(tr.pattern), int(tr.length)))
    return sum(1 for c in range(n) if tr.pattern[c]) / n


def _hits(tr, n=N_STEPS) -> list[int]:
    ln = max(1, min(n, int(tr.length)))
    return [c for c in range(ln) if tr.pattern[c]]


def analyse(project) -> dict:
    """What is this pattern made of? Everything the type chooser needs."""
    live, drums, melodic = [], [], []
    for t, tr in enumerate(project.tracks):
        if tr.type == "EMPTY" or not any(tr.pattern):
            continue
        live.append(t)
        (drums if tr.type in _DRUMISH else melodic).append(t)
    # the KICK-alike: the drum whose hits sit most on the beat, which is what a
    # "kick only" break has to keep to stay recognisable
    def beatiness(t):
        h = _hits(project.tracks[t])
        return sum(1 for c in h if c % 4 == 0) / max(1, len(h))
    anchor = max(drums, key=beatiness) if drums else (live[0] if live else None)
    total = sum(len(_hits(project.tracks[t])) for t in live)
    return {
        "live": live, "drums": drums, "melodic": melodic, "anchor": anchor,
        "density": total / max(1, len(live) * N_STEPS),
        "busy": total,
    }


# --------------------------------------------------------------------------- #
# break types. Each returns a plan: {"mute": [...], "pattern": {t: steps},
#                                    "rate": {t: r}, "filter": {t: (cut,res,type)}}
# --------------------------------------------------------------------------- #
def _plan() -> dict:
    return {"mute": [], "pattern": {}, "rate": {}, "filter": {}, "name": ""}


def _b_dropout(p, a, rng):
    """Everything but the rhythm section goes. The classic, and it works because what is
    left is the part the ear was using to keep time."""
    pl = _plan(); pl["name"] = "dropout"
    pl["mute"] = list(a["melodic"])
    if len(a["drums"]) > 2 and rng.random() < 0.5:
        pl["mute"] += rng.sample(a["drums"], 1)
    return pl


def _b_kick_only(p, a, rng):
    """Strip to the pulse. Keeps only the most on-the-beat drum."""
    pl = _plan(); pl["name"] = "kick only"
    pl["mute"] = [t for t in a["live"] if t != a["anchor"]]
    return pl


def _b_perc_only(p, a, rng):
    """The inverse: the melodic material goes and the kit is left exposed."""
    pl = _plan(); pl["name"] = "percussion only"
    pl["mute"] = list(a["melodic"])
    if a["anchor"] is not None and len(a["drums"]) > 1 and rng.random() < 0.6:
        pl["mute"].append(a["anchor"])          # even the kick — the most exposed version
    return pl


def _b_stutter(p, a, rng):
    """Take a SHORT cell from the front of the bar and repeat it across the whole bar.

    This is the one that most reads as 'programmed': it is not a mute, it is the pattern
    itself being folded down to a 2, 3 or 4 step loop, so the material is unmistakably the
    same but the phrase is gone.
    """
    pl = _plan(); pl["name"] = "stutter"
    cell = rng.choice((2, 3, 4, 4))
    for t in a["live"]:
        tr = p.tracks[t]
        src = list(tr.pattern[:N_STEPS])
        out = [0] * len(tr.pattern)
        for c in range(N_STEPS):
            out[c] = src[c % cell]
        pl["pattern"][t] = out
    # a stutter that also speeds up is a fill rather than a loop
    if rng.random() < 0.4:
        for t in a["drums"]:
            pl["rate"][t] = min(8.0, float(p.tracks[t].rate) * 2)
    return pl


def _b_displace(p, a, rng):
    """Rotate some tracks against the others. Nothing is removed — the bar simply lands in
    the wrong place, which is a break you feel rather than hear as a gap."""
    pl = _plan(); pl["name"] = "displacement"
    movers = [t for t in a["live"] if t != a["anchor"]]
    if not movers:
        return None
    rng.shuffle(movers)
    for t in movers[:max(1, len(movers) // 2)]:
        tr = p.tracks[t]
        ln = max(1, min(N_STEPS, int(tr.length)))
        k = rng.choice((-3, -2, -1, 1, 2, 3))
        src = list(tr.pattern[:ln])
        rot = src[-k % ln:] + src[:-k % ln]
        pl["pattern"][t] = rot + list(tr.pattern[ln:])
    return pl


def _b_pause(p, a, rng):
    """A hole. Everything stops for the last beat or two of the bar — the break that makes
    the downbeat that follows land hardest."""
    pl = _plan(); pl["name"] = "pause"
    keep = rng.choice((8, 12, 12, 14))         # silence from this step to the end
    for t in a["live"]:
        tr = p.tracks[t]
        out = list(tr.pattern)
        for c in range(keep, N_STEPS):
            out[c] = 0
        pl["pattern"][t] = out
    return pl


def _b_filtered(p, a, rng):
    """A filtered breakdown: the rig stays but loses its top, so the return is a lift
    rather than an entrance."""
    pl = _plan(); pl["name"] = "filtered"
    cut = rng.uniform(220, 900)
    for t in a["live"]:
        pl["filter"][t] = (cut * rng.uniform(0.8, 1.3), rng.uniform(0.15, 0.5), 0)
    if rng.random() < 0.4:
        pl["mute"] = rng.sample(a["melodic"], min(1, len(a["melodic"]))) if a["melodic"] else []
    return pl


def _b_halftime(p, a, rng):
    """Drag the rhythm section to half speed — the bar becomes twice as long and the
    pattern has to wait, which is the most physical break of the set."""
    pl = _plan(); pl["name"] = "half time"
    for t in a["drums"] or a["live"]:
        pl["rate"][t] = max(0.125, float(p.tracks[t].rate) * 0.5)
    return pl


def _b_buildup(p, a, rng):
    """A build: thin at the start of the bar, everything by the end, so the break leads
    back INTO the pattern instead of just stopping."""
    pl = _plan(); pl["name"] = "build-up"
    for t in a["live"]:
        tr = p.tracks[t]
        out = list(tr.pattern)
        for c in range(N_STEPS):
            # progressively more likely to survive as the bar goes on
            if out[c] and rng.random() > (0.15 + 0.85 * (c / N_STEPS)):
                out[c] = 0
        pl["pattern"][t] = out
    if a["drums"] and rng.random() < 0.5:
        t = rng.choice(a["drums"])
        pl["rate"][t] = min(8.0, float(p.tracks[t].rate) * 2)
    return pl


# Weighted by how often each is worth hearing. The mutes are the backbone; the ones that
# rewrite the bar are the surprises and are rarer on purpose.
_TYPES = [
    (_b_dropout, 3), (_b_kick_only, 2), (_b_perc_only, 2), (_b_stutter, 3),
    (_b_displace, 2), (_b_pause, 2), (_b_filtered, 2), (_b_halftime, 2), (_b_buildup, 3),
]


def plan(project, rng: random.Random | None = None, avoid: str = "") -> dict | None:
    """Choose and build one break for the current pattern.

    `avoid` is the previous break's name — the same break twice running is the fastest way
    to make this sound like a preset, so it is skipped unless nothing else fits.
    """
    rng = rng or random.Random()
    a = analyse(project)
    if not a["live"]:
        return None

    fns, wts = [], []
    for fn, w in _TYPES:
        # a break that removes the melodic material needs some to remove; one that strips to
        # the kit needs a kit
        if fn in (_b_dropout, _b_perc_only) and not a["melodic"]:
            continue
        if fn in (_b_kick_only, _b_halftime) and not a["drums"]:
            continue
        if len(a["live"]) < 2 and fn in (_b_dropout, _b_kick_only, _b_perc_only, _b_displace):
            continue
        fns.append(fn)
        wts.append(w * (0.25 if fn.__name__.endswith(avoid.replace(" ", "_")) else 1))
    if not fns:
        return None
    for _ in range(4):
        fn = rng.choices(fns, weights=wts)[0]
        pl = fn(project, a, rng)
        if pl and (pl["mute"] or pl["pattern"] or pl["rate"] or pl["filter"]):
            # never mute EVERYTHING for a whole cycle — that is a dropout, not a break
            if pl["mute"] and len(set(pl["mute"])) >= len(a["live"]) and not pl["pattern"]:
                continue
            return pl
    return None


def describe(pl: dict) -> str:
    if not pl:
        return "break: nothing to do"
    bits = [pl["name"]]
    if pl["mute"]:
        bits.append("mute %s" % ",".join("T%d" % (t + 1) for t in sorted(set(pl["mute"]))))
    if pl["pattern"]:
        bits.append("re-step %d" % len(pl["pattern"]))
    if pl["rate"]:
        bits.append("rate %d" % len(pl["rate"]))
    if pl["filter"]:
        bits.append("filter %d" % len(pl["filter"]))
    return "break: " + "  ".join(bits)
