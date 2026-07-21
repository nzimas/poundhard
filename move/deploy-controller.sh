#!/bin/bash
# Deploy the PoundHard headless controller + SC engine scripts to the Move.
#   - controller/poundhard      -> /data/UserData/poundhard/controller/poundhard
#   - controller/vendor/pythonosc -> .../controller/vendor/pythonosc
#   - supercollider/*.scd + move/sc/ph-boot.scd -> .../sc
#   - run-*.sh / stop-stack.sh  -> /data/UserData/poundhard
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
HOST="${1:-move.local}"
DEST="/data/UserData/poundhard"

# NOTE: do NOT create $DEST/share here — that's the SC bundle's class-library dir
# (provided by deploy-bundle.sh). IPC lives in $DEST/ipc (symlinked to tmpfs at run).
ssh "root@$HOST" "mkdir -p $DEST/controller/vendor $DEST/sc $DEST/logs"

echo "-> controller (poundhard + pythonosc)"
tar -C "$ROOT/controller" -czf - poundhard | ssh "root@$HOST" "tar -C $DEST/controller -xzf -"
tar -C "$ROOT/controller/vendor" -czf - pythonosc | ssh "root@$HOST" "tar -C $DEST/controller/vendor -xzf -"

echo "-> SC engine (.scd)"
tar -C "$ROOT/supercollider" -czf - boot.scd engine.scd synthdefs.scd | ssh "root@$HOST" "tar -C $DEST/sc -xzf -"
tar -C "$HERE/sc" -czf - ph-boot.scd | ssh "root@$HOST" "tar -C $DEST/sc -xzf -"

echo "-> STK rawwaves (excitation wavetables for ModalBar/BandedWG etc.)"
ssh "root@$HOST" "mkdir -p $DEST/rawwaves"
tar -C "$ROOT/supercollider/rawwaves" -czf - . | ssh "root@$HOST" "tar -C $DEST/rawwaves -xzf -"

# BYTEBEAT engine: the prebuilt ByteBeat UGen (.so -> scsynth plugin dir) and its sclang
# class (-> the SC Extensions dir the engine's sclang_conf points at, alongside the other
# plugin classes). Rebuild the .so with move/build-bytebeat.sh.
echo "-> ByteBeat UGen (plugin .so + sclang class)"
BB="$ROOT/supercollider/plugins/ByteBeat"
EXT="/data/UserData/wildrider/share/SuperCollider/Extensions/ByteBeat"
scp "$BB/ByteBeat.so" "root@$HOST:$DEST/plugins/ByteBeat.so"
ssh "root@$HOST" "mkdir -p $EXT"
scp "$BB/ByteBeat.sc" "$BB/ByteBeatController.sc" "root@$HOST:$EXT/"
ssh "root@$HOST" "chown ableton:users $DEST/plugins/ByteBeat.so $EXT/*.sc"

echo "-> launch scripts"
scp "$HERE/run-engine.sh" "$HERE/run-controller.sh" "$HERE/run-stack.sh" "$HERE/stop-stack.sh" "root@$HOST:$DEST/"
ssh "root@$HOST" "chmod +x $DEST/run-*.sh $DEST/stop-stack.sh; chown -R ableton:users $DEST"
# Re-grant scsynth RT caps AFTER chown (chown clears file capabilities). Harmless
# if the bundle isn't there yet (deploy-bundle.sh sets them too).
ssh "root@$HOST" "setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth 2>/dev/null; getcap $DEST/bin/scsynth 2>/dev/null || true"
echo "Done."
