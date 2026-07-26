"""Offline Csound mangling for the SAMPLE engine (19th engine).

A captured hit is rendered through a FRESHLY ASSEMBLED opcode graph — not a fixed signal
flow and not a preset menu. Each stage is a typed module (audio 'a' or spectral 'f'); the
builder wires a random chain and inserts the pvsanal/pvsynth bridges automatically when the
chain crosses into or out of the spectral domain.

The manual's core rule is enforced as a constraint: the most characteristic results come
from chaining UNLIKE domains, so two consecutive stages never share a domain.
Domains: spectral · granular · resonant · nonlinear · delay.

Csound 6.18 gotchas (from wildrider): the strict parser rejects bare constants where a
k-rate var is expected (so every control is assigned first); mincer's time pointer and
flanger's delay are AUDIO rate; gain staging stays conservative because resonators,
waveshapers and feedback nets can peak hugely even at low average level.
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile

PH = os.environ.get("PH_DIR", "/data/UserData/poundhard")
CS_DIR = os.environ.get("PH_CSOUND_DIR", os.path.join(PH, "csound"))
CS_BIN = os.path.join(CS_DIR, "bin", "csound")
MAX_DUR = 8.0


def csound_env() -> dict:
    env = dict(os.environ)
    env["OPCODE6DIR64"] = os.path.join(CS_DIR, "plugins")
    env["LD_LIBRARY_PATH"] = os.path.join(CS_DIR, "lib") + ":" + env.get("LD_LIBRARY_PATH", "")
    return env


def available() -> bool:
    return os.path.isfile(CS_BIN) and os.access(CS_BIN, os.X_OK)


def _f(x, nd=4):
    return f"{round(x, nd)}"


class Stage:
    def __init__(self, name, dom, itype, otype, emit):
        self.name, self.dom, self.itype, self.otype, self.emit = name, dom, itype, otype, emit


# ---- spectral (f -> f) -----------------------------------------------------
def _blur(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.05, 0.9))}", f"{o} pvsblur {i}, k{n}a, 1.0"]


def _freeze(r, i, o, n):                       # freeze one axis only, so it still evolves
    fa, ff = (1, 0) if r.random() < 0.5 else (0, 1)
    return [f"k{n}a = {fa}", f"k{n}b = {ff}", f"{o} pvsfreeze {i}, k{n}a, k{n}b"]


def _scale(r, i, o, n):                        # non-octave ratios break harmonicity
    return [f"k{n}a = {_f(r.choice([0.5, 0.63, 0.75, 1.33, 1.5, 1.87, 2.51]))}",
            f"{o} pvscale {i}, k{n}a"]


def _warp(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.4, 2.2))}", f"k{n}b = {_f(r.uniform(-0.3, 0.3))}",
            f"{o} pvswarp {i}, k{n}a, k{n}b"]


def _shift(r, i, o, n):                        # fixed-bin translation, not pitch shift
    return [f"k{n}a = {_f(r.uniform(-400, 700))}", f"k{n}b = 0",
            f"{o} pvshift {i}, k{n}a, k{n}b"]


def _trace(r, i, o, n):                        # reduce to a few moving spectral lines
    return [f"k{n}a = {r.randint(3, 60)}", f"{o} pvstrace {i}, k{n}a"]


def _smooth(r, i, o, n):                       # asymmetric: stable amps, sluggish freqs
    a, b = r.uniform(0.02, 0.4), r.uniform(0.6, 1.0)
    if r.random() < 0.5:
        a, b = b, a
    return [f"k{n}a = {_f(a)}", f"k{n}b = {_f(b)}", f"{o} pvsmooth {i}, k{n}a, k{n}b"]


# ---- granular (reads the source TABLE; defines the time base -> first only) -
def _syncgrain(r, i, o, n):
    return [f"k{n}a = 0.7", f"k{n}b = {_f(r.uniform(8, 90))}",
            f"k{n}c = {_f(r.choice([0.5, 0.75, 1.0, 1.5, 2.0]))}",
            f"k{n}d = {_f(r.uniform(0.02, 0.28))}", f"k{n}e = {_f(r.uniform(0.2, 1.4))}",
            f"{o} syncgrain k{n}a, k{n}b, k{n}c, k{n}d, k{n}e, giSrc, giWin, 32"]


def _sndwarp(r, i, o, n):                      # extreme stretch: geological-scale change
    return [f"k{n}a = 0.7", f"k{n}b = {_f(r.uniform(0.15, 3.0))}",
            f"k{n}c = {_f(r.choice([0.5, 1.0, 1.5, 2.0]))}",
            f"{o} sndwarp k{n}a, k{n}b, k{n}c, giSrc, 0, {_f(r.uniform(0.05, 0.2))}, "
            f"{_f(r.uniform(0.005, 0.06))}, {r.randint(3, 12)}, giWin, 1"]


def _mincer(r, i, o, n):                       # time pointer is AUDIO rate (gotcha)
    return [f"a{n}t line 0, p3, giLen * {_f(r.uniform(0.3, 1.0))}", f"k{n}a = 0.8",
            f"k{n}b = {_f(r.choice([0.5, 0.75, 1.0, 1.26, 2.0]))}", f"k{n}c = 0",
            f"{o} mincer a{n}t, k{n}a, k{n}b, giSrc, k{n}c"]


# ---- resonant (a -> a): implies an impossible body -------------------------
def _modebank(r, i, o, n):
    base = r.uniform(70, 420)
    parts, lines = [], []
    for j, ra in enumerate(r.sample([1.0, 1.41, 1.73, 2.09, 2.51, 3.13, 3.77, 5.19], 3)):
        lines += [f"k{n}f{j} = {_f(base * ra)}", f"k{n}q{j} = {_f(r.uniform(20, 320))}",
                  f"a{n}m{j} mode {i}, k{n}f{j}, k{n}q{j}"]
        parts.append(f"a{n}m{j}")
    lines.append(f"{o} = ({' + '.join(parts)}) * {_f(1.0 / len(parts))}")
    return lines


def _resonx(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(120, 3000))}", f"k{n}b = {_f(r.uniform(8, 260))}",
            f"{o} resonx {i}, k{n}a, k{n}b, {r.randint(2, 4)}, 1"]


def _streson(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(60, 700))}", f"k{n}b = {_f(r.uniform(0.75, 0.96))}",
            f"{o} streson {i}, k{n}a, k{n}b"]


def _wguide(r, i, o, n):                       # feedback near instability, clipped later
    return [f"k{n}a = {_f(r.uniform(60, 900))}", f"k{n}b = {_f(r.uniform(1200, 9000))}",
            f"k{n}c = {_f(r.uniform(0.6, 0.94))}", f"{o} wguide1 {i}, k{n}a, k{n}b, k{n}c"]


# ---- nonlinear (a -> a): generates NEW spectral content --------------------
def _powershape(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.3, 8.0))}", f"{o} powershape {i}, k{n}a"]


def _distort1(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(1.0, 12.0))}", f"k{n}b = {_f(r.uniform(0.2, 0.8))}",
            f"k{n}c = {_f(r.uniform(0.0, 0.9))}", f"k{n}d = {_f(r.uniform(0.0, 0.9))}",
            f"{o} distort1 {i}, k{n}a, k{n}b, k{n}c, k{n}d"]


def _cheby(r, i, o, n):                        # odd weights, often missing fundamental
    w = [0.0 if r.random() < 0.4 else round(r.uniform(-1, 1), 3) for _ in range(5)]
    return [f"{o} chebyshevpoly {i}, " + ", ".join(_f(x) for x in w)]


def _fold(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(1.0, 24.0))}", f"{o} fold {i}, k{n}a"]


def _clipstack(r, i, o, n):                    # repeated LOW-level clips + filter between
    lim = _f(r.uniform(0.3, 0.8))              # clip's method/limit are I-rate, not k-rate
    return [f"k{n}b = {_f(r.uniform(800, 6000))}",
            f"a{n}c clip {i} * {_f(r.uniform(1.5, 5.0))}, 0, {lim}",
            f"a{n}t tone a{n}c, k{n}b",
            f"{o} clip a{n}t * {_f(r.uniform(1.5, 4.0))}, 2, {lim}"]


# ---- delay / recursion (a -> a) -------------------------------------------
def _comb(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.2, 2.4))}", f"{o} comb {i}, k{n}a, {_f(r.uniform(0.004, 0.09))}"]


def _alpass(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.3, 2.0))}", f"{o} alpass {i}, k{n}a, {_f(r.uniform(0.002, 0.05))}"]


def _vcomb(r, i, o, n):
    return [f"k{n}a = {_f(r.uniform(0.3, 2.0))}",
            f"k{n}b oscili {_f(r.uniform(0.002, 0.02))}, {_f(r.uniform(0.05, 1.2))}, giWin",
            f"k{n}c = abs(k{n}b) + 0.002", f"{o} vcomb {i}, k{n}a, k{n}c, 0.1"]


def _multitap(r, i, o, n):                     # prime-ish taps = rhythmic geometry
    taps = sorted(r.uniform(0.003, 0.28) for _ in range(r.randint(3, 6)))
    return [f"{o} multitap {i}, " + ", ".join(f"{_f(t)}, {_f(r.uniform(0.2, 0.85))}" for t in taps)]


def _flanger(r, i, o, n):                      # delay arg is AUDIO rate (gotcha)
    return [f"a{n}d oscili {_f(r.uniform(0.0004, 0.006))}, {_f(r.uniform(0.05, 3.0))}, giWin",
            f"a{n}e = abs(a{n}d) + 0.0002", f"k{n}a = {_f(r.uniform(0.3, 0.88))}",
            f"{o} flanger {i}, a{n}e, k{n}a"]


STAGES = [
    Stage("pvsblur", "spectral", "f", "f", _blur),
    Stage("pvsfreeze", "spectral", "f", "f", _freeze),
    Stage("pvscale", "spectral", "f", "f", _scale),
    Stage("pvswarp", "spectral", "f", "f", _warp),
    Stage("pvshift", "spectral", "f", "f", _shift),
    Stage("pvstrace", "spectral", "f", "f", _trace),
    Stage("pvsmooth", "spectral", "f", "f", _smooth),
    Stage("syncgrain", "granular", "a", "a", _syncgrain),
    Stage("mincer", "granular", "a", "a", _mincer),
    Stage("modebank", "resonant", "a", "a", _modebank),
    Stage("resonx", "resonant", "a", "a", _resonx),
    Stage("streson", "resonant", "a", "a", _streson),
    Stage("powershape", "nonlinear", "a", "a", _powershape),
    Stage("distort1", "nonlinear", "a", "a", _distort1),
    Stage("chebyshevpoly", "nonlinear", "a", "a", _cheby),
    Stage("fold", "nonlinear", "a", "a", _fold),
    Stage("clipstack", "nonlinear", "a", "a", _clipstack),
    Stage("comb", "delay", "a", "a", _comb),
    Stage("alpass", "delay", "a", "a", _alpass),
    Stage("vcomb", "delay", "a", "a", _vcomb),
    Stage("multitap", "delay", "a", "a", _multitap),
    Stage("flanger", "delay", "a", "a", _flanger),
]
DOMAINS = sorted({s.dom for s in STAGES})


def build_chain(rng, n_stages=None):
    """Random chain, never two consecutive stages from the same domain. Granular stages
    read the source table and define the time base, so they only go first."""
    n, chain, last = n_stages or rng.randint(2, 4), [], None
    for k in range(n):
        pool = [s for s in STAGES if s.dom != last and (k == 0 or s.dom != "granular")]
        s = rng.choice(pool)
        chain.append(s)
        last = s.dom
    return chain


def _src_channels(path):
    """diskin2's output-arg count must MATCH the file's channels, so read it."""
    try:
        import wave
        with wave.open(path, "rb") as w:
            return max(1, min(2, w.getnchannels()))
    except Exception:
        return 1


def build_csd(rng, src, dst, dur, fmt="-s", nch=1):
    """Assemble one complete .csd. Returns (text, stage names)."""
    chain = build_chain(rng)
    fft = rng.choice([1024, 2048, 4096, 8192])        # offline: overspecify resolution
    hop = fft // rng.choice([4, 8])
    body, cur, ct, n = [], "asrc", "a", 0
    for st in chain:
        n += 1
        if st.itype == "f" and ct == "a":              # bridge into the spectral domain
            body.append(f"f{n}i pvsanal {cur}, {fft}, {hop}, {fft}, 1")
            cur, ct = f"f{n}i", "f"
        elif st.itype == "a" and ct == "f":            # ...and back out of it
            body.append(f"a{n}r pvsynth {cur}")
            cur, ct = f"a{n}r", "a"
        out = ("f" if st.otype == "f" else "a") + f"{n}o"
        body += st.emit(rng, cur, out, n)
        cur, ct = out, st.otype
    if ct == "f":                                      # always land back in time domain
        n += 1
        body.append(f"a{n}r pvsynth {cur}")
        cur = f"a{n}r"
    # mono source -> one output arg; stereo -> two, summed to mono for mangling
    read = ('  asrc diskin2 "%s", 1, 0, 1' % src) if nch == 1 else (
        '  aInL, aInR diskin2 "%s", 1, 0, 1\n  asrc = (aInL + aInR) * 0.5' % src)
    lines = chr(10).join("  " + ln for ln in body)
    csd = f"""<CsoundSynthesizer>
<CsOptions>
-o {dst} -W {fmt} -d
</CsOptions>
<CsInstruments>
sr = 44100
ksmps = 32
nchnls = 1
0dbfs = 1
giSrc ftgen 0, 0, 0, 1, "{src}", 0, 0, 1
giWin ftgen 0, 0, 8192, 10, 1
giLen = ftlen(giSrc) / sr
instr 1
{read}
{lines}
  amix = {cur}
  amix dcblock2 amix
  amix = tanh(amix * 1.2) * 0.8
  aenv linen 1, 0.008, p3, 0.05
  out amix * aenv
endin
</CsInstruments>
<CsScore>
i1 0 {round(dur, 3)}
e
</CsScore>
</CsoundSynthesizer>
"""
    return csd, [s.name for s in chain]


TARGET_RMS = 0.12          # aim here; peak-capped so transients survive
PEAK_CAP = 0.85


def _normalise(path):
    """Scale a rendered 16-bit WAV toward TARGET_RMS (peak-capped). Returns False if the
    render is effectively silent, which means the chain failed rather than being quiet."""
    import array as _a
    import wave as _w
    with _w.open(path, "rb") as fh:
        nch, sw, sr, n = fh.getnchannels(), fh.getsampwidth(), fh.getframerate(), fh.getnframes()
        raw = fh.readframes(n)
    if sw != 2 or n == 0:
        return True                       # not 16-bit: leave it to the caller
    v = _a.array("h")
    v.frombytes(raw)
    if not len(v):
        return False
    peak = max(abs(x) for x in v) / 32768.0
    rms = (sum(float(x) * x for x in v) / len(v)) ** 0.5 / 32768.0
    if peak < 0.002 or rms < 1e-5:
        return False                      # silent -> the graph produced nothing
    gain = min(TARGET_RMS / rms, PEAK_CAP / peak)
    if abs(gain - 1.0) > 0.05:
        for k in range(len(v)):
            v[k] = max(-32767, min(32767, int(v[k] * gain)))
        with _w.open(path, "wb") as fh:
            fh.setnchannels(nch); fh.setsampwidth(2); fh.setframerate(sr)
            fh.writeframes(v.tobytes())
    return True


def render(src, dst, seed=None, dur=None):
    """Mangle `src` -> `dst` through a freshly assembled graph; returns the stage names.
    Raises on failure — no silent fallback: it either mangles or it doesn't."""
    if not available():
        raise RuntimeError(f"offline Csound not present at {CS_BIN}")
    rng = random.Random(seed)
    dur = min(MAX_DUR, dur or 4.0)
    # the device root fs is full: scratch must live on /data, not /tmp
    scratch = os.path.join(PH, "tmp")
    os.makedirs(scratch, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="phcs_", dir=scratch)
    try:
        csd, names = build_csd(rng, src, dst, dur, nch=_src_channels(src))
        path = os.path.join(tmp, "job.csd")
        with open(path, "w") as fh:
            fh.write(csd)
        p = subprocess.run([CS_BIN, path], env=csound_env(), cwd=tmp,
                           capture_output=True, text=True, timeout=180)
        if not os.path.isfile(dst) or os.path.getsize(dst) < 1024:
            raise RuntimeError("csound produced no audio:\n" + (p.stderr or "")[-1500:])
        if not _normalise(dst):
            raise RuntimeError("render was silent: " + " -> ".join(names))
        return names
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
