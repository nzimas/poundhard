#!/bin/bash
# Build the PhMicIn UGen — the engine's end of the microphone tap.
#
# The Move's mic is not a JACK input; it is only visible to a Schwung DSP plugin, which
# publishes it to a shm ring (see move/schwung-module/poundhard/dsp/phmic.c). This UGen reads
# that ring. Built with static libstdc++ like the other plugins, so it needs only libc/librt.
#
# Output: supercollider/plugins/PhMicIn/PhMicIn{,_supernova}.so — shipped by
# deploy-controller.sh. Requires Docker with linux/arm64 emulation.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC="$ROOT/supercollider/plugins/PhMicIn"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

git clone --branch Version-3.13.0 --depth 1 \
  https://github.com/supercollider/supercollider.git "$WORK/sc-src" >/dev/null 2>&1
mkdir -p "$WORK/out"
cat > "$WORK/build.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq build-essential cmake >/dev/null 2>&1
cmake -S /src -B /tmp/b -DSC_PATH=/sc -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-static-libstdc++ -static-libgcc -O3" \
  -DCMAKE_SHARED_LINKER_FLAGS="-static-libstdc++ -static-libgcc" >/dev/null
cmake --build /tmp/b -j"$(nproc)" 2>&1 | grep -iE "error" | head -n 12 || true
cp -v /tmp/b/PhMicIn.so /tmp/b/PhMicIn_supernova.so /out/
echo "--- needs:"; ldd /out/PhMicIn.so | awk '{print $1}' | head -n 6
BUILD
echo "-> building PhMicIn for aarch64"
docker run --rm --platform linux/arm64 -v "$SRC":/src:ro -v "$WORK/sc-src":/sc:ro \
  -v "$WORK/out":/out -v "$WORK":/w ubuntu:20.04 bash /w/build.sh
cp "$WORK/out/PhMicIn.so" "$WORK/out/PhMicIn_supernova.so" "$SRC/"
echo "-> $SRC/PhMicIn{,_supernova}.so"
