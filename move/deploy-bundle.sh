#!/bin/bash
# Provision the scsynth/sclang runtime bundle for PoundHard on the Move.
#
# PoundHard's four voices (DRUM/FMTONE/BUCHLOID/SAMPLER) are pure-SuperCollider —
# they need NO extra UGen plugins beyond the core, so the same scsynth/sclang
# bundle the wildrider takeover already ships works verbatim. This script copies
# that bundle (bin/ lib/ plugins/ share/) from an existing on-device wildrider
# install into /data/UserData/poundhard, then re-applies scsynth's RT caps.
#
# If wildrider isn't on the device, deploy its bundle first (wildrider-move:
# move/deploy.sh) or point run-engine.sh's $PH/bin at wherever sclang lives.
set -euo pipefail
HOST="${1:-move.local}"
SRC="${2:-/data/UserData/wildrider}"
DEST="/data/UserData/poundhard"

echo "Copying SC bundle $SRC -> $DEST on $HOST"
ssh "root@$HOST" "
  set -e
  mkdir -p $DEST
  for d in bin lib plugins share; do
    [ -d $SRC/\$d ] || { echo \"missing $SRC/\$d — deploy wildrider's bundle first\" >&2; exit 1; }
    cp -a $SRC/\$d $DEST/
  done
  chown -R ableton:users $DEST
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth
  getcap $DEST/bin/scsynth
  # RNBO's jackd needs RT caps too (shared binary; harmless to re-apply).
  JK=/data/UserData/rnbo/bin/jackd; [ -f \$JK ] && setcap cap_ipc_lock,cap_sys_nice=eip \$JK || true
"
echo "Done. scsynth + sclang provisioned for PoundHard."
