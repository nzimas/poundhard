#!/bin/bash
# Reproducibly (re)build the PhSoftcut scsynth UGen for the Move's aarch64 Linux — monome's
# softcut as a SuperCollider unit generator, which is what the COMPASS modifier runs on.
#
# Why a UGen rather than a separate JACK client (the route the CSOUND engine needed):
# softcut-lib has no audio I/O and no JACK dependency. It is five source files that process
# a block and let the caller own the buffer, so it drops straight onto a bus inside scsynth
# with no routing, no port-name pinning, no realtime placement and no added latency.
#
# Built in an arm64 Ubuntu 20.04 container with libstdc++/libgcc STATICALLY linked, exactly
# like the ByteBeat plugin, so the .so needs only GLIBC_2.17 + libc and loads on the CM4's
# scsynth 3.13 whatever its C++ runtime.
#
# Output: supercollider/plugins/Softcut/PhSoftcut.so (checked in; shipped by
# deploy-controller.sh). Requires Docker with linux/arm64 emulation.
#
# Usage: ./move/build-softcut.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC="$ROOT/supercollider/plugins/Softcut"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "-> fetching sources (softcut-lib + SuperCollider 3.13.0 headers)"
# softcut-lib is pinned: at HEAD, Voice.h declares an init(FadeCurves*) that Voice.cpp no
# longer defines, and the Softcut<N> convenience template never initialises its voices.
# Driving Voice directly is the supported shape; pinning keeps that from moving underneath.
git clone --depth 1 https://github.com/monome/softcut-lib.git "$WORK/softcut" >/dev/null 2>&1
( cd "$WORK/softcut" && git rev-parse --short HEAD > "$WORK/softcut-rev" )
git clone --branch Version-3.13.0 --depth 1 \
  https://github.com/supercollider/supercollider.git "$WORK/sc-src" >/dev/null 2>&1

mkdir -p "$WORK/out"
cat > "$WORK/build.sh" <<'BUILD'
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq build-essential cmake >/dev/null 2>&1
# 1) softcut itself, as a static library
cmake -S /softcut/softcut-lib -B /tmp/scb -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_CXX_FLAGS="-O2 -fPIC" >/dev/null
make -C /tmp/scb -j"$(nproc)" >/dev/null
# 2) the UGen, statically linking it
cmake -S /src -B /tmp/build \
  -DSC_PATH=/sc -DSOFTCUT_PATH=/softcut/softcut-lib \
  -DSOFTCUT_LIB=/tmp/scb/libsoftcut.a \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_FLAGS="-static-libstdc++ -static-libgcc -O3" \
  -DCMAKE_SHARED_LINKER_FLAGS="-static-libstdc++ -static-libgcc" >/dev/null
cmake --build /tmp/build -j"$(nproc)" 2>&1 | grep -E "error|Error" | head -n 12 || true
cp -v /tmp/build/PhSoftcut.so /tmp/build/PhSoftcut_supernova.so /out/
echo "--- needs:"; ldd /out/PhSoftcut.so | awk '{print $1}' | head -n 6
BUILD

echo "-> building for aarch64 (softcut $(cat "$WORK/softcut-rev"), static libstdc++)"
docker run --rm --platform linux/arm64 \
  -v "$SRC":/src:ro -v "$WORK/sc-src":/sc:ro -v "$WORK/softcut":/softcut:ro \
  -v "$WORK/out":/out ubuntu:20.04 bash /w/build.sh 2>/dev/null \
  || docker run --rm --platform linux/arm64 \
       -v "$SRC":/src:ro -v "$WORK/sc-src":/sc:ro -v "$WORK/softcut":/softcut:ro \
       -v "$WORK/out":/out -v "$WORK":/w ubuntu:20.04 bash /w/build.sh

cp "$WORK/out/PhSoftcut.so" "$WORK/out/PhSoftcut_supernova.so" "$SRC/"
echo "-> $SRC/PhSoftcut{,_supernova}.so ($(du -h "$SRC/PhSoftcut.so" | cut -f1) each)"
