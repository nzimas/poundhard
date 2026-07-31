#!/bin/bash
# Provision the SELF-CONTAINED scsynth/sclang runtime for PoundHard on the Move.
#
# PoundHard ships its own SuperCollider AND JACK runtime — this installs the vendored
# bundle (bin/ lib/ plugins/ share/ = scsynth, supernova, sclang, jackd, libjack, every
# UGen plugin it uses, the SC class library + Extensions, and a self-contained sclang_conf
# that points at PoundHard's own dirs). NO other project (wildrider, RNBO) is needed.
#
# The binaries in the bundle have their RPATH patched to PoundHard's own lib. That matters
# because scsynth/supernova/jackd carry RT file capabilities, and glibc runs a
# capability-carrying binary in secure-execution mode where LD_LIBRARY_PATH is discarded —
# so RPATH is the ONLY search path they have. The runtime was originally copied out of a
# wildrider install and kept ITS RPATH, which is why deploying to a device without
# wildrider produced "libsndfile.so.1: cannot open shared object file" and a stack stuck
# on "starting..." (issue #3). An RPATH can be shortened in place but never lengthened,
# so jackd (whose original path was too short to hold the full install path) points at
# /data/UserData/phlib, a symlink this script creates.
#
# The bundle is move/bundle/poundhard-sc-runtime.tar.gz in this repo. Refresh it from a
# working device with:
#   ssh root@<host> 'tar czf - -C /data/UserData/poundhard bin lib plugins share' \
#     > move/bundle/poundhard-sc-runtime.tar.gz
# ...and re-patch the RPATHs afterwards, or you will ship whatever paths that device had.
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
  # The RT binaries carry file capabilities — and glibc runs a capability-carrying binary
  # in secure-execution mode, where LD_LIBRARY_PATH is DISCARDED. Their baked-in RPATH is
  # therefore the only library search path that counts, which is why the bundle's binaries
  # are patched to point at PoundHard's own lib (see the header of this file).
  # chown clears file caps, so set them AFTER.
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/scsynth
  setcap cap_ipc_lock,cap_sys_nice,cap_sys_resource=eip $DEST/bin/supernova
  setcap cap_ipc_lock,cap_sys_nice=eip $DEST/bin/jackd
  # jackd's RPATH had no room for the full install path (an RPATH can be shortened in
  # place but never lengthened), so it names a short symlink instead.
  ln -sfn $DEST/lib /data/UserData/phlib
  getcap $DEST/bin/scsynth $DEST/bin/supernova $DEST/bin/jackd
"

# ---- CSOUND runtime (engine 20) --------------------------------------------------- #
# A second self-contained bundle: the realtime Csound that the CSOUND engine runs as a
# JACK client. The Csound previously on the device was an OFFLINE build (no librtjack,
# a partial opcode set) — it could render the SAMPLE mangler's files and nothing else.
CSBUNDLE="$HERE/bundle/poundhard-csound.tar.gz"
if [ -f "$CSBUNDLE" ]; then
  echo "Installing Csound runtime ($(du -h "$CSBUNDLE" | cut -f1)) -> $DEST/csound"
  ssh "root@$HOST" "rm -rf $DEST/csound.new && mkdir -p $DEST/csound.new"
  ssh "root@$HOST" "tar -C $DEST/csound.new -xzf -" < "$CSBUNDLE"
  ssh "root@$HOST" "
    set -e
    # keep whatever orchestra the controller already shipped
    [ -d $DEST/csound/orc ] && cp -a $DEST/csound/orc $DEST/csound.new/csound/ || true
    rm -rf $DEST/csound && mv $DEST/csound.new/csound $DEST/csound && rm -rf $DEST/csound.new
    mkdir -p $DEST/csound/orc
    chown -R ableton:users $DEST/csound
    chmod +x $DEST/csound/bin/csound $DEST/csound/bin/ph-jackconnect $DEST/csound/bin/ph-rtsched
    # Csound joins the realtime graph beside jackd and supernova and needs the same
    # privileges, or its JACK callback runs at normal priority and XRuns the whole graph.
    # Csound's binaries are RPATH'd to this short symlink, because a capability-carrying
    # binary never sees LD_LIBRARY_PATH (see build-csound.sh).
    ln -sfn $DEST/csound/lib /data/UserData/pcslib
    setcap cap_ipc_lock,cap_sys_nice=eip $DEST/csound/bin/csound
    # the helper that re-places Csound's RT threads needs the same privilege to do it
    setcap cap_sys_nice=eip $DEST/csound/bin/ph-rtsched
    getcap $DEST/csound/bin/csound
  "
else
  echo "WARNING: no Csound bundle ($CSBUNDLE) — run move/build-csound.sh; engine 20 will not sound"
fi

# ---- CDP (the CHURN modifier's transform engine) ---------------------------------- #
# ~400 aarch64 programs built from source (move/build-cdp.sh). CDP bundles its own
# soundfile library, so there is nothing to vendor alongside it and no capabilities to
# set — it only ever processes files, off the audio thread.
CDPBUNDLE="$HERE/bundle/poundhard-cdp.tar.gz"
if [ -f "$CDPBUNDLE" ]; then
  echo "Installing CDP ($(du -h "$CDPBUNDLE" | cut -f1)) -> $DEST/cdp"
  ssh "root@$HOST" "rm -rf $DEST/cdp.new && mkdir -p $DEST/cdp.new"
  ssh "root@$HOST" "tar -C $DEST/cdp.new -xzf -" < "$CDPBUNDLE"
  ssh "root@$HOST" "
    set -e
    rm -rf $DEST/cdp && mv $DEST/cdp.new/cdp $DEST/cdp && rm -rf $DEST/cdp.new
    chown -R ableton:users $DEST/cdp
    chmod +x $DEST/cdp/bin/* 2>/dev/null || true
    echo \"  CDP programs: \$(ls $DEST/cdp/bin | wc -l)\"
  "
else
  echo "WARNING: no CDP bundle ($CDPBUNDLE) — run move/build-cdp.sh; CHURN will do nothing"
fi

# Lua — the interpreter COMPASS runs Olivier Creurer's norns script under. The device does
# ship /usr/bin/lua, but that lives on the 463 MB root partition Ableton's firmware owns and
# keeps ~99% full; a dependency of PoundHard's belongs in /data. Build with move/build-lua.sh.
LUABUNDLE="$HERE/bundle/poundhard-lua.tar.gz"
if [ -f "$LUABUNDLE" ]; then
  echo "Installing Lua ($(du -h "$LUABUNDLE" | cut -f1)) -> $DEST/lua"
  ssh "root@$HOST" "rm -rf $DEST/lua.new && mkdir -p $DEST/lua.new"
  ssh "root@$HOST" "tar -C $DEST/lua.new -xzf -" < "$LUABUNDLE"
  ssh "root@$HOST" "
    set -e
    rm -rf $DEST/lua && mv $DEST/lua.new/lua $DEST/lua && rm -rf $DEST/lua.new
    chown -R ableton:users $DEST/lua
    chmod +x $DEST/lua/bin/lua
    echo \"  \$($DEST/lua/bin/lua -v 2>&1)\"
  "
else
  echo "WARNING: no Lua bundle ($LUABUNDLE) — run move/build-lua.sh; COMPASS will not run"
fi

# PREFLIGHT — run each RT binary with an EMPTY environment. That is exactly the situation
# the loader puts a capped binary in, so if a library is unreachable by RPATH alone it
# fails HERE, at deploy time, instead of silently leaving the device on 'starting...'.
echo "Verifying the runtime resolves its libraries with no LD_LIBRARY_PATH ..."
ssh "root@$HOST" "
  fail=0
  for b in scsynth supernova jackd sclang; do
    case \$b in jackd) arg=--version ;; *) arg=-v ;; esac
    if env -i $DEST/bin/\$b \$arg >/dev/null 2>$DEST/.pre.err; then
      echo \"  ok   \$b\"
    else
      if grep -q 'error while loading shared libraries' $DEST/.pre.err; then
        echo \"  FAIL \$b: \$(cat $DEST/.pre.err)\"; fail=1
      else
        echo \"  ok   \$b (no version flag, but the loader was happy)\"
      fi
    fi
  done
  rm -f $DEST/.pre.err
  [ \$fail -eq 0 ] || { echo 'A binary cannot find its libraries — the stack would hang on starting...' >&2; exit 1; }
"

echo "Done. Self-contained SC + JACK runtime provisioned (no wildrider, no RNBO needed)."
