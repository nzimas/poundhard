#!/bin/bash
# Reproducibly (re)build the Composers Desktop Project binary set for the Move's aarch64
# Linux — the transform engine behind the CHURN modifier.
#
# CDP has no distribution package, so unlike the Csound bundle this is a real build from
# source. Ubuntu 22.04 ships glibc 2.35, identical to the Move, so the programs built here
# load against the device's own libc. CDP bundles its own soundfile library (portsf), so
# the runtime dependencies are just libc/libm plus libstdc++ for the handful of C++
# programs — nothing to vendor alongside them.
#
# The aarch64 fixes, all of which are load-bearing (recipe adapted from wildrider's
# Dockerfile.cdp, which is where they were worked out):
#   * USE_COMPILER_OPTIMIZATIONS=OFF — CDP's CompilerOptimizations.cmake injects x86-only
#     -msse2 / -mfpmath=sse, which are fatal on ARM.
#   * do NOT set CMAKE_BUILD_TYPE=Release — its Release flags include the Clang-only
#     -stdlib=libc++, which GCC rejects. -O2 is passed by hand instead.
#   * USE_LOCAL_PORTAUDIO=OFF — skips the play/record programs, which need an audio device.
#     Churn only ever processes files.
#   * make -k — a few of the ~400 programs fail to build and must not sink the set.
#
# Output: move/bundle/poundhard-cdp.tar.gz. Shipped by deploy-bundle.sh.
# Requires Docker with linux/arm64 emulation. This one is SLOW under emulation — expect
# tens of minutes.
#
# Usage: ./move/build-cdp.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$ROOT/move/bundle/cdp"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/build.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends git cmake build-essential ca-certificates \
    >/dev/null 2>&1
git clone --depth 1 https://github.com/ComposersDesktop/CDP8.git /src 2>/dev/null
cmake -S /src -B /src/build \
    -DUSE_COMPILER_OPTIMIZATIONS=OFF \
    -DUSE_LOCAL_PORTAUDIO=OFF \
    -DFAIL_MISSING=OFF \
    -DCMAKE_C_FLAGS="-O2 -Wno-format" \
    -DCMAKE_CXX_FLAGS="-O2" >/dev/null
make -C /src/build -k -j"$(nproc)" >/tmp/build.log 2>&1 || true

# Every built executable from NewRelease (CMAKE_RUNTIME_OUTPUT_DIRECTORY), ELF only.
mkdir -p /out/bin
find /src/NewRelease -maxdepth 1 -type f -perm -u+x -exec sh -c \
    'for f; do case "$(head -c4 "$f" | od -An -tx1 | tr -d " ")" in 7f454c46) cp -n "$f" /out/bin/ ;; esac; done' _ {} +
strip /out/bin/* 2>/dev/null || true
echo "--- CDP programs built: $(ls /out/bin | wc -l)"
echo "--- the ones CHURN needs:"
for p in pvoc blur stretch distort modify bounce housekeep; do
    [ -x "/out/bin/$p" ] && echo "    ok   $p" || echo "    MISSING $p"
done
echo "--- runtime deps across the set:"
for f in /out/bin/*; do ldd "$f" 2>/dev/null | awk '/=> \//{print $1}'; done | sort -u | head -n 10
BUILD

echo "-> building CDP for aarch64 (Ubuntu 22.04 = the device's glibc 2.35)"
echo "   this is a ~400-program build under emulation; it takes a while."
rm -rf "$OUT"
mkdir -p "$OUT"
docker run --rm --platform linux/arm64 \
  -v "$WORK":/w -v "$OUT":/out ubuntu:22.04 bash /w/build.sh

chmod +x "$OUT"/bin/* 2>/dev/null || true
( cd "$ROOT/move/bundle" && tar czf poundhard-cdp.tar.gz cdp )
echo "-> bundle at $OUT ($(du -sh "$OUT" | cut -f1)), tarball $(du -h "$ROOT/move/bundle/poundhard-cdp.tar.gz" | cut -f1)"
