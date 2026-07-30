"""CHURN — the CDP end of the ornamentation modifier.

Churn records short fragments of the master, has CDP transform them, and drops the results
back into the performance where there is room. This module owns the middle step: building a
transform chain and running it. Capture, placement and scheduling live in the controller.

WHY CDP AND NOT MORE DSP. PoundHard already has twenty engines and eight inserts; another
reverb would add nothing. CDP's value here is that it is a *different kind* of
transformation — offline, non-realtime processes (spectral blurs, waveset mangles, brassage,
time warps) that cannot run in an audio callback at all. Churn is the only way that class of
sound gets into a live performance.

SPEED. Measured on the device with a pattern playing: a full spectral chain (pvoc anal →
blur → pvoc synth) on a 1.2 s fragment takes 0.28 s; waveset and varispeed stages are
0.02-0.03 s. A two-stage chain therefore lands well inside a bar, which is what makes a
continuous capture → transform → schedule pipeline possible at all.

THE FAMILIES. Structured after wildrider's CDP runner: recipes are grouped by the KIND of
transformation, and a chain draws its stages from DIFFERENT families, so results span the
space instead of clustering on lookalike smears. Every stage is guarded — CDP programs are
finicky and a failed one must not take the ornament with it.
"""
from __future__ import annotations

import os
import random
import subprocess
from pathlib import Path

CDP_BIN = Path(os.environ.get("PH_CDP_BIN", "/data/UserData/poundhard/cdp/bin"))
_TIMEOUT = 12.0          # per program; a 1-2 s fragment is quick, a hung one must not stall
# A "valid" output is not the same as a usable one. Some transforms (a 2.4x varispeed on a
# short fragment, a hard waveset thin) shrink the audio to a few tens of milliseconds — the
# file is well-formed and CDP is happy, but what comes back is a click, not an ornament.
# 13 KB at 44.1k/16-bit is ~0.15 s, the point where a fragment starts being material.
_MIN_BYTES = 13000


def available() -> bool:
    return (CDP_BIN / "pvoc").exists()


class _Job:
    """One fragment's scratch: a guarded runner and a temp-file mint, swept when done."""

    def __init__(self, work: Path, rng: random.Random, tag: str):
        self.work, self.rng, self.tag, self._n = work, rng, tag, 0
        # CDP writes scratch to $TMPDIR. On the Move that defaults to the ROOT partition,
        # which runs ~96% full — pvoc analyses are megabytes and fail there, silently. Pin
        # it to the work directory on /data.
        self._env = dict(os.environ, TMPDIR=str(work))

    def tmp(self, ext: str = "wav") -> Path:
        self._n += 1
        return self.work / f"_{self.tag}_{self._n}.{ext}"

    def run(self, prog: str, *args, out=None) -> bool:
        """Run one CDP program. `out` names the file it is about to create.

        CDP REFUSES TO OVERWRITE an existing output file — it exits non-zero and writes
        nothing. Reusing a destination path therefore works exactly once and then fails
        silently forever, which on a continuous loop looks like the feature switching itself
        off. The output is cleared first, and ONLY the output: an earlier version of this
        swept every .wav argument, which deleted the input.
        """
        exe = CDP_BIN / prog
        if not exe.exists():
            return False
        if out is not None:
            try:
                Path(out).unlink()
            except OSError:
                pass
        try:
            r = subprocess.run([str(exe), *map(str, args)], cwd=str(self.work),
                               capture_output=True, env=self._env, timeout=_TIMEOUT)
            return r.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def sweep(self) -> None:
        for f in self.work.glob(f"_{self.tag}_*"):
            try:
                f.unlink()
            except OSError:
                pass


def _ok(p: Path) -> bool:
    try:
        return p.stat().st_size >= _MIN_BYTES
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# stages, by family. Each takes (job, src, out) and returns True if `out` is real.
# --------------------------------------------------------------------------- #
def _anal(j: _Job, src: Path):
    ana = j.tmp("ana")
    return ana if j.run("pvoc", "anal", "1", src, ana, out=ana) and _ok(ana) else None


def _synth(j: _Job, ana: Path, out: Path) -> bool:
    return j.run("pvoc", "synth", ana, out, out=out) and _ok(out)


# SPECTRAL — blur, average, scatter. The smeared, electroacoustic end.
def _s_blur(j, src, out):
    a = _anal(j, src)
    if not a:
        return False
    b = j.tmp("ana")
    return j.run("blur", "blur", a, b, j.rng.randint(4, 40), out=b) and _synth(j, b, out)


def _s_scatter(j, src, out):
    a = _anal(j, src)
    if not a:
        return False
    b = j.tmp("ana")
    return j.run("blur", "scatter", a, b, j.rng.randint(2, 12), out=b) and _synth(j, b, out)


def _s_avrg(j, src, out):
    a = _anal(j, src)
    if not a:
        return False
    b = j.tmp("ana")
    # spectral averaging flattens the fragment toward its own mean spectrum — the ornament
    # keeps the source's colour but loses its attack, so it sits under the music
    return j.run("blur", "avrg", a, b, j.rng.randint(2, 20), out=b) and _synth(j, b, out)


def _s_stretch(j, src, out):
    a = _anal(j, src)
    if not a:
        return False
    b = j.tmp("ana")
    return j.run("stretch", "time", "1", a, b, round(j.rng.uniform(0.35, 3.0), 3), out=b) \
        and _synth(j, b, out)


# WAVESET — CDP's signature destructive mangles. The rhythmic-noise end.
def _w_repeat(j, src, out):
    return j.run("distort", "repeat", src, out, j.rng.randint(2, 8), out=out) and _ok(out)


def _w_multiply(j, src, out):
    return j.run("distort", "multiply", src, out, j.rng.randint(2, 6), out=out) and _ok(out)


def _w_reverse(j, src, out):
    return j.run("distort", "reverse", src, out, j.rng.randint(1, 6), out=out) and _ok(out)


def _w_average(j, src, out):
    return j.run("distort", "average", src, out, j.rng.randint(2, 12), out=out) and _ok(out)


# TIME / PITCH — varispeed and brassage. Keeps a recognisable relation to the source.
def _t_speed(j, src, out):
    # away from 1.0 in either direction, but never so far the fragment stops being material
    # The downward end is deliberately shallower than the upward one. Slowing a fragment
    # that contains a kick drags an already low, already loud transient lower and longer,
    # which is the farting blob rather than an ornament.
    r = j.rng.choice([j.rng.uniform(0.65, 0.88), j.rng.uniform(1.25, 2.4)])
    return j.run("modify", "speed", "1", src, out, round(r, 4), out=out) and _ok(out)


def _t_brassage(j, src, out):
    return j.run("modify", "brassage", "1", src, out, j.rng.randint(-8, 8), out=out) and _ok(out)


# GRANULAR / RHYTHM — restructures the fragment in time.
def _r_bounce(j, src, out):
    #        count            startgap        shorten         endlevel  ewarp
    return j.run("bounce", "bounce", src, out,
                 j.rng.randint(2, 7),
                 round(j.rng.uniform(0.05, 0.3), 3),
                 round(j.rng.uniform(0.55, 0.95), 3),
                 round(j.rng.uniform(0.05, 0.4), 3),
                 round(j.rng.uniform(0.7, 1.6), 3), out=out) and _ok(out)


FAMILIES: dict[str, list] = {
    "spectral": [_s_blur, _s_scatter, _s_avrg, _s_stretch],
    "waveset":  [_w_repeat, _w_multiply, _w_reverse, _w_average],
    "timepitch": [_t_speed, _t_brassage],
    "granular": [_r_bounce],
}


def transform(src: Path, dst: Path, work: Path, rng: random.Random | None = None) -> str | None:
    """Run a fresh chain over `src`, writing `dst`. Returns a short description, or None.

    One or two stages, the second always from a DIFFERENT family — a blur on a blur is
    still just a blur, whereas a waveset mangle on a spectral smear is a new sound. Each
    stage is tried a few times across its family before the chain is abandoned, because an
    individual CDP program refusing a particular fragment is routine and is not a reason to
    lose the ornament.
    """
    rng = rng or random.Random()
    if not available() or not _ok(Path(src)):
        return None
    work.mkdir(parents=True, exist_ok=True)
    dst = Path(dst)
    if dst.exists():          # see _Job.run: CDP will not write over a file that is there
        try:
            dst.unlink()
        except OSError:
            return None
    j = _Job(work, rng, "ch%d" % rng.randrange(1 << 20))
    try:
        fams = list(FAMILIES)
        rng.shuffle(fams)
        cur = Path(src)
        used: list[str] = []
        stages = 1 if rng.random() < 0.4 else 2
        for i in range(stages):
            fam = fams[i % len(fams)]
            out = j.tmp() if i < stages - 1 else Path(dst)
            recipes = FAMILIES[fam][:]
            rng.shuffle(recipes)
            for fn in recipes:
                if fn(j, cur, out):
                    used.append("%s:%s" % (fam, fn.__name__.lstrip("_")))
                    cur = out
                    break
            else:
                # nothing in this family took; if we already have a stage, keep it
                if i == 0:
                    return None
                break
        if cur != dst:
            # the last stage failed but an earlier one produced audio — keep that
            try:
                dst.write_bytes(cur.read_bytes())
            except OSError:
                return None
        return " -> ".join(used) if _ok(dst) else None
    finally:
        j.sweep()


# --------------------------------------------------------------------------- #
# placement — where an ornament can go without fighting the music
# --------------------------------------------------------------------------- #
def peak(path) -> float:
    """Peak amplitude of a 16-bit mono WAV, 0-1. Cheap enough to run on every ornament.

    CDP output level is not predictable: a spectral average comes back tens of dB quieter
    than a waveset multiply of the same fragment. Playing them all at the same nominal amp
    therefore gives an ornament stream where half are inaudible under the mix and the rest
    jump out. The peak is measured once, when the ornament is made, so playback can be
    level-matched instead of guessed.
    """
    import struct
    import wave
    try:
        w = wave.open(str(path))
        n = min(w.getnframes(), 44100 * 4)
        d = w.readframes(n)
        w.close()
        if not d:
            return 0.0
        xs = struct.unpack("<%dh" % (len(d) // 2), d[:len(d) // 2 * 2])
        return max(abs(v) for v in xs) / 32768.0
    except Exception:
        return 0.0


def clipped(path, frac: float = 0.0008) -> bool:
    """Is this file clipped? True if more than `frac` of its samples sit at full scale.

    A CDP transform can be a big gain: waveset multiply, bounce and the spectral resynths
    routinely come back louder than they went in, and the output is written as int16, so the
    excess is not headroom lost — it is hard clipping baked into the file. On low-frequency
    material, which on any normal pattern means the kick, that reads as a farting buzz.
    Nothing downstream can undo it, so a clipped ornament is thrown away rather than played.
    """
    import struct
    import wave
    try:
        w = wave.open(str(path))
        n = min(w.getnframes(), 44100 * 4)
        d = w.readframes(n)
        w.close()
        if not d:
            return False
        xs = struct.unpack("<%dh" % (len(d) // 2), d[:len(d) // 2 * 2])
        hot = sum(1 for v in xs if v >= 32700 or v <= -32700)
        return hot > max(8, len(xs) * frac)
    except Exception:
        return False


def gaps(project, rng: random.Random | None = None) -> list[int]:
    """Step positions with the LEAST going on, ranked best first.

    Churn is meant to fill space, not compete, so placement is driven by how many tracks
    hit each step. A step where four tracks land is the worst place to put an ornament; a
    step nothing touches is the best. Downbeats are penalised even when they are empty —
    an ornament on beat one reads as a mistake rather than as decoration.
    """
    rng = rng or random.Random()
    n = 16
    load = [0] * n
    for tr in project.tracks:
        if tr.type == "EMPTY":
            continue
        ln = max(1, min(n, int(tr.length)))
        for c in range(ln):
            if tr.pattern[c]:
                load[c] += 1
                # the step after a hit is still busy: the tail is sounding
                load[(c + 1) % n] += 0.5
    scored = []
    for c in range(n):
        s = load[c]
        if c % 4 == 0:
            s += 1.5            # keep off the beats
        if c % 8 == 0:
            s += 1.0            # and further off the bar line
        scored.append((s + rng.uniform(0, 0.4), c))
    scored.sort()
    return [c for _, c in scored]
