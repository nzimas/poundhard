#!/bin/bash
# Build phmic.so — PoundHard's microphone tap, a Schwung overtake DSP plugin.
#
# The Move's microphone is not reachable from a JACK client: there is no ALSA on the device,
# and the shadow driver's capture ports carry a dead noise floor. The input lives in the SPI
# MAILBOX, and the host hands a pointer to it only to a loaded DSP plugin —
# host->mapped_memory + host->audio_in_offset, 128 frames of stereo interleaved int16. So the
# tap has to BE a plugin. Schwung loads an overtake module's `dsp` and looks for a V2
# generator or FX entry point; this exports the FX one and passes audio through untouched.
#
# Built in an arm64 container against glibc 2.35 (Ubuntu 22.04 = the device's own), with no
# dependencies beyond libc and librt.
#
# Output: move/schwung-module/poundhard/dsp.so — shipped by deploy-module.sh.
# Requires Docker with linux/arm64 emulation.
#
# Usage: ./move/build-micdsp.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC="$ROOT/move/schwung-module/poundhard/dsp"
OUT="$ROOT/move/schwung-module/poundhard"

cat > "$SRC/build-in-container.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq build-essential >/dev/null 2>&1
cd /src
gcc -O2 -fPIC -shared -Wall -Wextra -o /src/dsp.so phmic.c -lrt
echo "--- exported entry points:"
nm -D --defined-only /src/dsp.so | grep -E "move_(audio_fx|plugin)_init" || echo "  NONE — the host will reject this"
echo "--- needs:"; ldd /src/dsp.so | awk '{print $1}' | head -n 6
BUILD

echo "-> building phmic tap for aarch64"
docker run --rm --platform linux/arm64 -v "$SRC":/src ubuntu:22.04 bash /src/build-in-container.sh
mv "$SRC/dsp.so" "$OUT/dsp.so"
rm -f "$SRC/build-in-container.sh"
echo "-> $OUT/dsp.so ($(du -h "$OUT/dsp.so" | cut -f1))"
