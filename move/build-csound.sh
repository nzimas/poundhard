#!/bin/bash
# Reproducibly (re)build the Csound runtime bundle for the Move's aarch64 Linux.
#
# The Move is a Raspberry Pi CM4 (aarch64) on glibc 2.35 — Ubuntu 22.04's glibc exactly —
# so the distro's own arm64 Csound packages drop straight onto the device. We take:
#   * the `csound` binary and libcsound64
#   * ALL 40 opcode plugin libraries (the earlier bundle shipped 19; the realtime engine
#     draws on far more of them, and the whole set is only a few MB)
#   * librtjack.so, the realtime JACK module — the piece the offline bundle lacked, and
#     the reason Csound could render files but never make a sound in realtime
#   * the shared libraries they need, EXCEPT libjack (the device has its own vendored
#     jack in $PH/lib and both must agree on the running server's ABI)
#
# Output: move/bundle/csound/{bin,lib,plugins}. Shipped by deploy-bundle.sh.
# Requires Docker with linux/arm64 emulation (Docker Desktop has it).
#
# Usage: ./move/build-csound.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$ROOT/move/bundle/csound"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/build.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq csound libjack-jackd2-0 >/dev/null 2>&1
ARCH=aarch64-linux-gnu
mkdir -p /out/bin /out/lib /out/plugins

cp -L "$(command -v csound)" /out/bin/csound

# A CURATED plugin set. Shipping all 40 drags in LLVM (via Faust), CPython, HDF5 and ICU —
# 177 MB for opcodes a groovebox will never call. These are the ones the engine actually
# draws on: chaotic oscillators, STK physical models, PADsynth, the extra spectral and
# noise generators, array/matrix maths, and the realtime JACK module.
# (libftsamplebank / libstdutil are also what the offline SAMPLE mangler has always had —
# never ship a set smaller than the one that engine already relies on. libscansyn is NOT
# here: 22.04 folded the scanned-synthesis opcodes into the core library.)
KEEP="librtjack libchua libstkops libpadsynth libpvsops libfractalnoise liblfsr \
      libarrayops liblinear_algebra libmixer libdoppler libtrigenvsegs liburandom \
      libcontrol libdeprecated libsignalflowgraph libbformdec2 libampmidid \
      libftsamplebank libstdutil"
for k in $KEEP; do
  cp -L /usr/lib/$ARCH/csound/plugins64-*/$k.so /out/plugins/ 2>/dev/null || echo "MISSING $k"
done
cp -L /usr/lib/$ARCH/libcsound64.so.6.0 /out/lib/
ln -sf libcsound64.so.6.0 /out/lib/libcsound64.so

# every shared library the binary + libcsound + the plugins pull in, minus the ones the
# device already provides (libc/libm/... come from the system; libjack from $PH/lib, which
# MUST be the same build the running jackd server speaks)
for f in /out/bin/csound /out/lib/libcsound64.so.6.0 /out/plugins/*.so; do
  ldd "$f" 2>/dev/null | awk '/=> \//{print $3}'
done | sort -u | while read -r so; do
  base="$(basename "$so")"
  case "$base" in
    libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|ld-linux*|libgcc_s.so*) continue ;;
    libjack.so*|libjackserver.so*) continue ;;   # the device's own vendored jack wins
    libcsound64.so*) continue ;;
  esac
  [ -e "/out/lib/$base" ] || cp -L "$so" "/out/lib/$base"
done

# ph-jackconnect: the device has no jack_connect, and letting Csound auto-connect by port
# enumeration order would silently mis-wire 32 channels the day anything else joins the
# graph. 40 lines against libjack is the robust answer.
apt-get install -y -qq libjack-jackd2-dev gcc >/dev/null 2>&1
cat > /tmp/phjc.c <<'CSRC'
/* ph-jackconnect <client> — connect one client's output ports to a target's inputs.
   usage: ph-jackconnect <srcclient> <srcfirst> <dstclient> <dstfirst> <count> */
#include <jack/jack.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
int main(int argc, char **argv) {
    if (argc != 6) { fprintf(stderr, "usage: %s src sfirst dst dfirst count\n", argv[0]); return 2; }
    int sf = atoi(argv[2]), df = atoi(argv[4]), n = atoi(argv[5]), i, bad = 0;
    jack_status_t st;
    jack_client_t *c = jack_client_open("ph-connect", JackNoStartServer, &st);
    if (!c) { fprintf(stderr, "no jack server\n"); return 1; }
    for (i = 0; i < n; i++) {
        char s[256], d[256];
        snprintf(s, sizeof s, "%s:output_%d", argv[1], sf + i);
        snprintf(d, sizeof d, "%s:input_%d", argv[3], df + i);
        int r = jack_connect(c, s, d);
        if (r && r != EEXIST) { fprintf(stderr, "FAIL %s -> %s (%d)\n", s, d, r); bad++; }
    }
    jack_client_close(c);
    printf("connected %d/%d\n", n - bad, n);
    return bad ? 1 : 0;
}
CSRC
gcc -O2 -o /out/bin/ph-jackconnect /tmp/phjc.c -ljack
echo "--- ph-jackconnect built"

# ph-rtsched: place a process's REALTIME threads. Csound and supernova share the JACK
# cycle and Csound feeds supernova, so Csound must outrank it — but JACK hands every
# client the same priority, and neither chrt nor taskset may touch a SCHED_FIFO thread
# without CAP_SYS_NICE, which the `ableton` user running the stack does not have. A tiny
# helper carrying that capability is the same answer ph-jackconnect is for jack_connect.
cat > /tmp/phrt.c <<'CSRC'
/* ph-rtsched <pid> <priority> <cpu>  — retune a process's realtime threads.
   cpu < 0 leaves affinity alone. Non-RT threads are ignored. */
#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
int main(int argc, char **argv) {
    if (argc != 4) { fprintf(stderr, "usage: %s pid prio cpu\n", argv[0]); return 2; }
    int prio = atoi(argv[2]), cpu = atoi(argv[3]), done = 0, bad = 0;
    char dir[128];
    snprintf(dir, sizeof dir, "/proc/%s/task", argv[1]);
    DIR *d = opendir(dir);
    if (!d) { perror("opendir"); return 1; }
    struct dirent *e;
    while ((e = readdir(d))) {
        if (e->d_name[0] == '.') continue;
        int tid = atoi(e->d_name);
        if (tid <= 0) continue;
        if (sched_getscheduler(tid) != SCHED_FIFO) continue;   /* only the RT ones */
        struct sched_param sp; memset(&sp, 0, sizeof sp); sp.sched_priority = prio;
        if (sched_setscheduler(tid, SCHED_FIFO, &sp)) { perror("setscheduler"); bad++; continue; }
        if (cpu >= 0) {
            cpu_set_t set; CPU_ZERO(&set); CPU_SET(cpu, &set);
            if (sched_setaffinity(tid, sizeof set, &set)) { perror("setaffinity"); bad++; continue; }
        }
        printf("tid %d -> SCHED_FIFO prio %d", tid, prio);
        if (cpu >= 0) printf(" cpu %d", cpu);
        printf("\n");
        done++;
    }
    closedir(d);
    if (!done) fprintf(stderr, "no realtime threads found\n");
    return (done && !bad) ? 0 : 1;
}
CSRC
gcc -O2 -o /out/bin/ph-rtsched /tmp/phrt.c
echo "--- ph-rtsched built"

# RPATH. Csound carries RT capabilities on the device (it joins the realtime graph beside
# jackd and supernova), and glibc runs a capability-carrying binary in secure-execution
# mode where LD_LIBRARY_PATH is DISCARDED. Without a baked-in path Csound cannot find
# libcsound64 at all — it is a straight choice between "starts" and "runs realtime", and
# an RPATH is how you get both. Same trick, and the same short symlink, as the SC bundle.
# DT_RPATH (not RUNPATH): RPATH propagates to transitively-loaded libraries, RUNPATH
# does not, and the opcode plugins are dlopened.
apt-get install -y -qq patchelf >/dev/null 2>&1
for f in /out/bin/csound /out/lib/*.so* /out/plugins/*.so; do
  # BOTH paths: pcslib is Csound's own lib dir, phlib is PoundHard's — librtjack.so needs
  # libjack from there, and libjack is deliberately NOT vendored into the Csound bundle
  # (it must be the same build the running jackd speaks). Miss it and the JACK module
  # silently fails to load, which surfaces as "could not connect to JACK server".
  patchelf --force-rpath --set-rpath /data/UserData/pcslib:/data/UserData/phlib "$f" 2>/dev/null || true
done
echo "--- rpath on csound: $(patchelf --print-rpath /out/bin/csound)"

echo "--- csound:"; /out/bin/csound --version 2>&1 | head -n 2
echo "--- plugins: $(ls /out/plugins | wc -l)"
echo "--- realtime modules:"; ls /out/plugins | grep -E '^librt|^libvirtual'
echo "--- librtjack needs:"; ldd /out/plugins/librtjack.so | awk '{print $1}' | head -n 12
BUILD

echo "-> building the aarch64 Csound bundle (Ubuntu 22.04 = the device's glibc 2.35)"
rm -rf "$OUT"
mkdir -p "$OUT"
docker run --rm --platform linux/arm64 \
  -v "$WORK":/w -v "$OUT":/out ubuntu:22.04 bash /w/build.sh

chmod +x "$OUT/bin/csound" "$OUT/bin/ph-jackconnect" "$OUT/bin/ph-rtsched"
# tracked as a tarball, like the SC runtime beside it — not 58 loose binaries
( cd "$ROOT/move/bundle" && tar czf poundhard-csound.tar.gz csound )
echo "-> bundle at $OUT ($(du -sh "$OUT" | cut -f1)), tarball $(du -h "$ROOT/move/bundle/poundhard-csound.tar.gz" | cut -f1)"
