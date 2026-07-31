"""PHRASE — where a change belongs in time.

The rhythmic modifiers used to engage on the keypress. A pattern does not care when you
press a pad, so the change landed wherever your thumb did: two steps into a bar, halfway
through a fill, in the middle of a phrase that had four bars left to run. That reads as a
mistake even when the effect itself is good, because the ear hears the seam, not the effect.

This decides WHEN. A pad press ARMS a modifier; the monitor commits it at the next boundary
worth using, and the same on the way out.

THE PHRASE IS COMPUTED FROM THE PATTERN, not assumed to be a bar. Every track has its own
length and its own clock rate, so a track of 12 steps at rate 1 against one of 16 at rate 3/2
does not come back round for a while — and the moment they all realign is the one moment in
the piece where a change costs nothing. That is the LCM of the per-track cycles, in exact
rationals so a 3:2 rate is not rounded into something that never lines up.

SEAM QUALITY ranks the candidates: the phrase boundary is worth most, the half and quarter
less, a plain barline least. Onset density adjusts it — a change into a sparse bar, or out of
a busy one, is masked by the music either way, and the pattern's own gaps are where a
listener already expects something to happen.

THE THRESHOLD DECAYS, so an armed modifier cannot wait forever: it starts out holding out for
a phrase boundary and by one full phrase it will take any barline. The longest anything ever
waits is one phrase.
"""
from __future__ import annotations

from fractions import Fraction

BAR_STEPS = 16              # the engine's fixed bar grid (/ph/cycle fires on step 15)
MAX_PHRASE_BARS = 16        # past this it stops being a phrase and starts being a wait
# Phrase lengths that are worth snapping to. An exact LCM of 11 bars is arithmetically
# right and musically useless; 8 is what the piece is actually built out of.
MUSICAL = (1, 2, 3, 4, 6, 8, 12, 16)


class PhraseMonitor:
    """Tracks where we are in the phrase, and scores the upcoming boundary."""

    def __init__(self):
        self.phrase_bars = 4
        self.bar = 0                    # bars since the phrase was last recomputed
        self.density: list[int] = []    # onsets per bar across one phrase
        self._sig = None                # pattern fingerprint, to know when to re-analyse

    # ------------------------------------------------------------------ analysis
    def analyse(self, project) -> None:
        """Recompute the phrase from the tracks' lengths and rates."""
        live = []
        for t, tr in enumerate(project.tracks):
            if project.eff_muted(t):
                continue
            ln = max(1, min(32, int(tr.length)))
            if not any(tr.pattern[c] for c in range(min(ln, len(tr.pattern)))):
                continue
            live.append((t, tr, ln, Fraction(tr.rate).limit_denominator(16) or Fraction(1)))

        if not live:
            self.phrase_bars, self.density = 4, []
            return

        # A track of length L at rate r repeats every L/r GLOBAL steps. Exact rationals, so
        # a 3:2 rate stays 3:2 instead of being rounded into a cycle that never realigns.
        cycles = []
        for _, _, ln, rate in live:
            if rate <= 0:
                rate = Fraction(1)
            cycles.append(Fraction(ln) / rate)
        total = cycles[0]
        for c in cycles[1:]:
            total = _lcm_frac(total, c)
        total = _lcm_frac(total, Fraction(BAR_STEPS))     # always a whole number of bars

        bars = total / BAR_STEPS
        n = int(bars) if bars.denominator == 1 else int(bars) + 1
        self.phrase_bars = _snap(n)
        self.density = _density(live, self.phrase_bars)

    def maybe_analyse(self, project) -> None:
        """Re-analyse only when the pattern's rhythmic shape actually changed."""
        sig = tuple(
            (int(tr.length), round(float(tr.rate), 4), project.eff_muted(t),
             tuple(1 if tr.pattern[c] else 0 for c in range(min(32, len(tr.pattern)))))
            for t, tr in enumerate(project.tracks))
        if sig != self._sig:
            self._sig = sig
            self.analyse(project)
            self.bar = self.bar % max(1, self.phrase_bars)

    # ------------------------------------------------------------------ per bar
    def tick(self) -> None:
        self.bar = (self.bar + 1) % max(1, self.phrase_bars)

    @property
    def next_bar(self) -> int:
        """The bar the pattern is about to enter. /ph/cycle fires on the LAST step of a bar,
        so a decision taken now takes effect on the next downbeat — that is the seam."""
        return (self.bar + 1) % max(1, self.phrase_bars)

    def quality(self, bar: int | None = None) -> float:
        """How good a seam the upcoming boundary is, 0..1."""
        b = self.next_bar if bar is None else bar
        p = max(1, self.phrase_bars)
        if b == 0:
            q = 1.0                                   # the phrase comes round
        elif p >= 2 and b == p // 2:
            q = 0.7                                   # halfway
        elif p >= 4 and b % max(1, p // 4) == 0:
            q = 0.5                                   # a quarter of the way
        else:
            q = 0.22                                  # a plain barline
        # The music's own gaps are where a listener already expects something to happen: a
        # change INTO a sparse bar, or OUT of a busy one, is masked either way.
        if self.density:
            avg = sum(self.density) / len(self.density)
            if avg > 0:
                into = self.density[b % len(self.density)] / avg
                outof = self.density[self.bar % len(self.density)] / avg
                q += 0.18 * (1.0 - min(2.0, into))    # sparse ahead -> better
                q += 0.10 * (min(2.0, outof) - 1.0)   # busy behind -> better
        return max(0.0, min(1.0, q))

    def ready(self, waited_bars: int) -> bool:
        """Commit now? The bar it has waited relaxes what it will settle for, so nothing
        armed can hang: by one full phrase it accepts any barline."""
        p = max(1, self.phrase_bars)
        need = 1.0 - (0.85 * min(1.0, waited_bars / p))
        return self.quality() >= need


# --------------------------------------------------------------------------- #
def _lcm_frac(a: Fraction, b: Fraction) -> Fraction:
    """LCM over rationals: lcm(num)/gcd(den). Keeps 3:2 rates exact."""
    from math import gcd
    n = (a.numerator * b.numerator) // gcd(a.numerator, b.numerator)
    d = gcd(a.denominator, b.denominator)
    return Fraction(n, d)


def _snap(bars: int) -> int:
    """Nearest musical phrase length. An exact LCM of 11 bars is arithmetically right and
    musically useless; the piece is built out of 4s and 8s."""
    if bars <= 0:
        return 4
    if bars > MAX_PHRASE_BARS:
        return MAX_PHRASE_BARS
    return min(MUSICAL, key=lambda m: (abs(m - bars), m))


def _density(live, phrase_bars: int) -> list[int]:
    """Onsets per bar across one phrase, replaying each track's own clock.

    Polymeter means the bars of a phrase are NOT interchangeable — a track of 12 against the
    16-step grid puts its hits somewhere different in every bar, and this is what finds the
    thin one.
    """
    out = []
    for b in range(max(1, phrase_bars)):
        n = 0
        for _, tr, ln, rate in live:
            for s in range(BAR_STEPS):
                gstep = (b * BAR_STEPS) + s
                idx = int(Fraction(gstep) * rate) % ln
                if idx < len(tr.pattern) and tr.pattern[idx]:
                    n += 1
        out.append(n)
    return out
