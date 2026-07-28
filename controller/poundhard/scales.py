"""Project scale: what the piece is IN, derived from what has been played.

PoundHard has no key selector, and it should not have one — the first track to carry
pitched material decides what the piece is in, and every track generated afterwards
answers to that. This module does three jobs:

  * `detect`   — given the notes that exist, find the root + scale that explains them
  * `quantise` — snap a candidate pitch into that scale, optionally preferring pitch
                 classes the piece already uses
  * `context`  — collect the pitch material of the tracks that already play

The scale set is deliberately dark and modal rather than a general music-theory
library: this is an instrument for IDM, rhythmic noise and abstract electronica, so the
palette runs from phrygian and locrian through octatonic and whole-tone, and includes
sets (pentatonic, chromatic clusters) that generate tension without being random.

Nothing here forces consonance. Generated tracks may still sit a semitone apart or
lean on tritones — the point is that the dissonance is CHOSEN from a shared set rather
than arrived at by accident.
"""

from __future__ import annotations

import random

# name -> pitch classes above the root. Ordered dark-to-bright-ish; ties in `detect`
# resolve toward the earlier (darker) entry, which suits the instrument.
SCALES: dict[str, tuple[int, ...]] = {
    "phrygian":       (0, 1, 3, 5, 7, 8, 10),
    "locrian":        (0, 1, 3, 5, 6, 8, 10),
    "aeolian":        (0, 2, 3, 5, 7, 8, 10),
    "dorian":         (0, 2, 3, 5, 7, 9, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11),
    "octatonic":      (0, 1, 3, 4, 6, 7, 9, 10),
    "whole tone":     (0, 2, 4, 6, 8, 10),
    "minor pent":     (0, 3, 5, 7, 10),
    "in sen":         (0, 1, 5, 7, 10),          # Japanese, very dark, wide leaps
    "chromatic":      tuple(range(12)),          # last resort: explains anything
}

# What a fresh project falls back to before anything pitched has been played. A1
# phrygian is the instrument's historical default (see kits.py) — dark and low.
DEFAULT_ROOT = 33
DEFAULT_SCALE = "phrygian"


def pitch_classes(root: int, name: str) -> set[int]:
    """The pitch classes of a scale, as absolute pc values (0-11)."""
    return {(root + i) % 12 for i in SCALES.get(name, SCALES[DEFAULT_SCALE])}


def in_scale(note: int, root: int, name: str) -> bool:
    return (note % 12) in pitch_classes(root, name)


def detect(notes, prefer_root: int | None = None) -> tuple[int, str]:
    """Find the (root, scale) that best explains `notes`.

    Scoring is deliberately simple and explainable: a candidate is rewarded for
    covering the notes actually played and penalised for being larger than it needs to
    be — so a set of notes that fits both `minor pent` and `chromatic` reads as the
    pentatonic. The most common note is a strong hint for the root, because in this
    music the repeated low note usually IS the tonic.
    """
    pcs = [n % 12 for n in notes if n is not None]
    if not pcs:
        return (DEFAULT_ROOT if prefer_root is None else prefer_root, DEFAULT_SCALE)
    weight: dict[int, int] = {}
    for pc in pcs:
        weight[pc] = weight.get(pc, 0) + 1
    used = set(weight)
    best = None
    for name, ivs in SCALES.items():
        for root in range(12):
            member = {(root + i) % 12 for i in ivs}
            covered = sum(w for pc, w in weight.items() if pc in member)
            missed = sum(w for pc, w in weight.items() if pc not in member)
            # coverage first, then tightness (fewer notes explaining the same material),
            # then a nudge for a root the piece actually leans on
            score = (covered * 10) - (missed * 25) - len(ivs)
            if root == max(weight, key=lambda p: weight[p]):
                score += 6
            if prefer_root is not None and root == prefer_root % 12:
                score += 3
            if best is None or score > best[0]:
                best = (score, root, name)
    _, root_pc, name = best
    # place the root in the instrument's low register, near where the material sits
    low = min(n for n in notes if n is not None)
    root = root_pc + 12 * max(0, round((low - root_pc) / 12))
    return (int(root), name)


def quantise(note: int, root: int, name: str, prefer: set[int] | None = None,
             rng: random.Random | None = None, tension: float = 0.0) -> int:
    """Snap `note` into the scale, keeping it as close to the candidate as possible.

    `prefer` is a set of pitch classes the piece already uses; when two scale tones are
    equally close, the one already in play wins, which is what makes a new track sound
    related to the others rather than merely legal.

    `tension` (0-1) is the licence to leave: at 0 the result is always in scale, and as
    it rises the note may land a semitone outside it. That is on purpose — this music
    wants grit, but chosen grit.
    """
    rng = rng or random
    if tension > 0 and rng.random() < tension * 0.35:
        return int(note + rng.choice((-1, 1)))
    member = pitch_classes(root, name)
    if (note % 12) in member:
        return int(note)
    best, best_key = None, None
    for delta in range(0, 7):
        for cand in (note - delta, note + delta):
            if (cand % 12) not in member:
                continue
            key = (delta, 0 if (prefer and (cand % 12) in prefer) else 1)
            if best is None or key < best_key:
                best, best_key = cand, key
    return int(best if best is not None else note)


def context(project, skip: int | None = None) -> dict:
    """What the rest of the piece is already playing.

    Returns the pitch classes in use (weighted by how often), the register other tracks
    occupy, and whether anything pitched exists at all. A generator uses this to sit
    WITH the piece: sharing pitch classes, and staying out of a register that is
    already crowded.
    """
    from .catalog import VOICES

    pcs: dict[int, int] = {}
    notes: list[int] = []
    for i, tr in enumerate(project.tracks):
        if i == skip or tr.type == "EMPTY":
            continue
        spec = VOICES.get(tr.type)
        if spec is None:
            continue
        # a track counts as pitched if it has a note and actually plays
        if not any(tr.pattern):
            continue
        stepnotes = [n for n in tr.step_note if n is not None]
        for n in (stepnotes or [tr.note]):
            notes.append(int(n))
            pcs[int(n) % 12] = pcs.get(int(n) % 12, 0) + 1
    return {
        "pcs": pcs,
        "notes": notes,
        "low": min(notes) if notes else None,
        "high": max(notes) if notes else None,
        "any": bool(notes),
    }
