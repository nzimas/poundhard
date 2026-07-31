#!/bin/bash
# Reproducibly (re)build a Lua 5.4 interpreter for the Move's aarch64 Linux — the runtime
# the COMPASS modifier's norns script runs under.
#
# The device does ship /usr/bin/lua (5.4.4), and it works. This builds our own anyway, for
# the same reason CDP and Csound are vendored: /usr/bin lives on the 463 MB root partition
# that Ableton's firmware owns and keeps ~99% full, and a firmware update is free to change
# or remove anything on it. PoundHard's dependencies live in /data or they are not
# dependencies, they are assumptions.
#
# Statically linked apart from libc/libm, so there is nothing to vendor alongside it, and
# built without readline (no interactive console needed — it is driven over a pipe).
#
# Output: move/bundle/lua/bin/lua, tarred into move/bundle/poundhard-lua.tar.gz.
# Shipped by deploy-bundle.sh. Requires Docker with linux/arm64 emulation.
#
# Usage: ./move/build-lua.sh   (from anywhere in the repo)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
OUT="$ROOT/move/bundle/lua"
LUA_VER=5.4.6
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cat > "$WORK/build.sh" <<BUILD
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends build-essential curl ca-certificates \
    >/dev/null 2>&1
curl -sSL https://www.lua.org/ftp/lua-${LUA_VER}.tar.gz -o /tmp/lua.tgz
tar xzf /tmp/lua.tgz -C /tmp
cd /tmp/lua-${LUA_VER}
# "posix" without readline: os.time/os.clock/io are all we need, and the host drives it
# over stdin, so an interactive console would only add a dependency.
make -j"\$(nproc)" MYCFLAGS="-O2 -DLUA_USE_LINUX -DLUA_USE_POSIX" \
     MYLIBS="-Wl,-E -ldl" SYSLIBS="-Wl,-E -ldl" linux-noreadline >/dev/null 2>&1 || \
make -j"\$(nproc)" posix >/dev/null
mkdir -p /out/bin
cp src/lua /out/bin/lua
strip /out/bin/lua
echo "--- version: \$(/out/bin/lua -v)"
echo "--- needs:"; ldd /out/bin/lua | awk '{print \$1}' | head -n 6
BUILD

echo "-> building Lua ${LUA_VER} for aarch64"
rm -rf "$OUT"; mkdir -p "$OUT"
docker run --rm --platform linux/arm64 \
  -v "$WORK":/w -v "$OUT":/out ubuntu:22.04 bash /w/build.sh

( cd "$ROOT/move/bundle" && tar czf poundhard-lua.tar.gz lua )
echo "-> $OUT/bin/lua ($(du -h "$OUT/bin/lua" | cut -f1))"
