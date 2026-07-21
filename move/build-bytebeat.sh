#!/bin/bash
# Reproducibly (re)build the ByteBeat scsynth UGen for the Move's aarch64 Linux.
#
# The Move is a Raspberry Pi CM4 (aarch64) running scsynth 3.13.0. We cross-build the
# plugin in an arm64 Ubuntu-20.04 container (glibc 2.31 — below the device's 2.35) with
# libstdc++/libgcc STATICALLY linked, so the resulting .so needs only GLIBC_2.17 + libc
# and loads on the device regardless of its C++ runtime.
#
# Output: supercollider/plugins/ByteBeat/ByteBeat.so  (checked into the repo; shipped by
# deploy-controller.sh). Requires Docker with linux/arm64 emulation (Docker Desktop has it).
#
# Usage: ./move/build-bytebeat.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "-> fetching sources (bytebeat + SuperCollider 3.13.0 headers)"
git clone --depth 1 https://github.com/midouest/bytebeat.git "$WORK/bytebeat"
git clone --branch Version-3.13.0 --depth 1 \
  https://github.com/supercollider/supercollider.git "$WORK/sc-src"

mkdir -p "$WORK/out"
cat > "$WORK/build.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq build-essential cmake >/dev/null 2>&1
cmake -S /src -B /tmp/build \
  -DSC_PATH=/sc -DCMAKE_BUILD_TYPE=Release \
  -DSUPERNOVA=OFF -DTEST=OFF -DCLI=OFF -DNATIVE=OFF -DSTRICT=OFF \
  -DCMAKE_CXX_FLAGS="-static-libstdc++ -static-libgcc -O3" \
  -DCMAKE_SHARED_LINKER_FLAGS="-static-libstdc++ -static-libgcc"
cmake --build /tmp/build -j"$(nproc)"
find /tmp/build -name 'ByteBeat*.so' -exec cp -v {} /out/ByteBeat.so \;
BUILD

echo "-> building for aarch64 (Ubuntu 20.04 / static libstdc++)"
docker run --rm --platform linux/arm64 \
  -v "$WORK/bytebeat":/src:ro -v "$WORK/sc-src":/sc:ro \
  -v "$WORK/out":/out -v "$WORK/build.sh":/build.sh:ro \
  ubuntu:20.04 bash /build.sh

DEST="$ROOT/supercollider/plugins/ByteBeat"
mkdir -p "$DEST"
cp -v "$WORK/out/ByteBeat.so" "$DEST/ByteBeat.so"
cp -v "$WORK/bytebeat/plugins/ByteBeat/ByteBeat.sc" "$DEST/ByteBeat.sc"
cp -v "$WORK/bytebeat/plugins/ByteBeat/ByteBeatController.sc" "$DEST/ByteBeatController.sc"
cp -v "$WORK/bytebeat/LICENSE" "$DEST/LICENSE"
echo "Done. ByteBeat.so + classes refreshed in $DEST"
