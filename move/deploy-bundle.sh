#!/bin/bash
# Provision the SELF-CONTAINED scsynth/sclang runtime for PoundHard on the Move.
#
# PoundHard ships its own SuperCollider runtime — this installs the vendored bundle
# (bin/ lib/ plugins/ share/ = scsynth, sclang, every UGen plugin it uses, the SC class
# library + Extensions, and a self-contained sclang_conf that points at PoundHard's own
# dirs). NO other project (wildrider, etc.) needs to be on the device.
#
# The bundle is move/bundle/poundhard-sc-runtime.tar.gz in this repo. Refresh it from a
# working device with:
#   ssh root@<host> 'tar czf - -C /data/UserData/poundhard bin lib plugins share' \
#     > move/bundle/poundhard-sc-runtime.tar.gz
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
HOST="${1:-move.local}"
DEST="/data/UserData/poundhard"
BUNDLE="$HERE/bundle/poundhard-sc-runtime.tar.gz"

[ -f "$BUNDLE" ] || { echo "missing runtime bundle: $BUNDLE" >&2; exit 1; }

echo "Installing self-contained SC runtime ($(du -h "$BUNDLE" | cut -f1)) -> $DEST on $HOST"
ssh "root@$HOST" "mkdir -p $DEST"
ssh "root@$HOST" "tar -C $DEST -xzf -" < "$BUNDLE"
ssh "root@$HOST" "
  set -e
  chown -R ableton:users $DEST/bin $DEST/lib $DEST/plugins $DEST/share
  # scsynth needs RT capabilities (cleared by chown, so set them AFTER)
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth
  getcap $DEST/bin/scsynth
  # the shared jackd (from the schwung/rnbo host) wants RT caps too — harmless if absent
  JK=/data/UserData/rnbo/bin/jackd; [ -f \$JK ] && setcap cap_ipc_lock,cap_sys_nice=eip \$JK || true
"
echo "Done. Self-contained scsynth + sclang provisioned for PoundHard (no wildrider needed)."
