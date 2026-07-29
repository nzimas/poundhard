#!/bin/bash
# Deploy the PoundHard headless controller + SC engine scripts to the Move.
#   - controller/poundhard      -> /data/UserData/poundhard/controller/poundhard
#   - controller/vendor/pythonosc -> .../controller/vendor/pythonosc
#   - supercollider/*.scd + move/sc/ph-boot.scd -> .../sc
#   - run-*.sh / stop-stack.sh  -> /data/UserData/poundhard
#   - csound/ph-engine.orc      -> .../csound/orc  (the CSOUND engine's orchestra)
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
# class (-> PoundHard's OWN SC Extensions dir, where its self-contained sclang_conf looks,
# alongside the other plugin classes). Rebuild the .so with move/build-bytebeat.sh.
echo "-> ByteBeat UGen (plugin .so + sclang class)"
BB="$ROOT/supercollider/plugins/ByteBeat"
EXT="$DEST/share/SuperCollider/Extensions/ByteBeat"
scp "$BB/ByteBeat.so" "root@$HOST:$DEST/plugins/ByteBeat.so"
ssh "root@$HOST" "mkdir -p $EXT"
scp "$BB/ByteBeat.sc" "$BB/ByteBeatController.sc" "root@$HOST:$EXT/"
ssh "root@$HOST" "chown ableton:users $DEST/plugins/ByteBeat.so $EXT/*.sc"

echo "-> launch scripts"
scp "$HERE/run-engine.sh" "$HERE/run-controller.sh" "$HERE/run-stack.sh" "$HERE/stop-stack.sh" "$HERE/run-csound.sh" "root@$HOST:$DEST/"
# the CSOUND engine's orchestra — code, not runtime, so it ships with the controller
ssh "root@$HOST" "mkdir -p $DEST/csound/orc"
scp "$HERE/../csound/ph-engine.orc" "root@$HOST:$DEST/csound/orc/"
# Chown ONLY what this script ships. `chown -R ableton:users $DEST` used to run here, and
# chown CLEARS file capabilities — so deploying the controller silently stripped cap_sys_nice
# off jackd, which then ran SCHED_OTHER, which meant libjack could not promote supernova's
# callback either. The whole audio chain quietly dropped out of realtime and XRan, with
# nothing in this script's output to say so.
ssh "root@$HOST" "
  chmod +x $DEST/run-*.sh $DEST/stop-stack.sh
  chown ableton:users $DEST/run-*.sh $DEST/stop-stack.sh
  chown -R ableton:users $DEST/controller $DEST/sc $DEST/csound/orc
  # belt and braces: re-assert the RT capabilities every deploy, so they can never be
  # missing after one, whatever else touched these files.
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/supernova
  setcap cap_ipc_lock,cap_sys_nice=eip $DEST/bin/jackd
  [ -x $DEST/csound/bin/csound ] && setcap cap_ipc_lock,cap_sys_nice=eip $DEST/csound/bin/csound
  getcap $DEST/bin/jackd $DEST/bin/supernova $DEST/csound/bin/csound
"
# Re-grant scsynth RT caps AFTER chown (chown clears file capabilities). Harmless
# if the bundle isn't there yet (deploy-bundle.sh sets them too).
ssh "root@$HOST" "setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth 2>/dev/null; getcap $DEST/bin/scsynth 2>/dev/null || true"
# supernova needs the SAME caps: its parallel DSP helper threads self-elevate to realtime
# (AcquireSelfRealTime), which requires cap_sys_nice on the binary. chown above cleared them.
ssh "root@$HOST" "[ -f $DEST/bin/supernova ] && setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/supernova 2>/dev/null; getcap $DEST/bin/supernova 2>/dev/null || true"
echo "Done."
