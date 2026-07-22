#!/bin/bash
# Disable the Move's AUTOMATIC firmware updates, so an OS update can never silently
# overwrite the schwung / PoundHard takeover. Idempotent — safe to re-run any time
# (e.g. after a reflash or a manual update that swapped the rootfs).
#
# Turns off BOTH ends of the update pipeline:
#   - swupdate            : the engine that applies an update to the B slot and reboots
#   - UpdateDBusService   : the service that checks Ableton's servers and downloads
#
# Nothing is deleted — everything is renamed, and the exact re-enable commands are left
# on the device at /root/schwung-update-disabled/README.txt. To update by hand later,
# follow that note, update from the Move UI, then re-run this script.
#
# Usage: ./move/disable-updates.sh [host]      (default host: move.local)
set -euo pipefail
HOST="${1:-move.local}"

ssh "root@$HOST" 'bash -s' <<'REMOTE'
# --- swupdate (apply engine): stop now + never start at boot ---
/etc/init.d/swupdate stop 2>/dev/null || true
kill "$(pidof swupdate 2>/dev/null)" 2>/dev/null || true
for d in 2 3 4 5; do
  [ -e "/etc/rc$d.d/S70swupdate" ] && mv "/etc/rc$d.d/S70swupdate" "/etc/rc$d.d/DISABLED_S70swupdate" || true
done

# --- UpdateDBusService (check/download): kill + make un-runnable ---
kill "$(pidof UpdateDBusService 2>/dev/null)" 2>/dev/null || true
SVC=/usr/share/dbus-1/system-services/com.ableton.update.service
[ -e "$SVC" ] && mv "$SVC" "$SVC.disabled" || true
[ -e /opt/move/UpdateDBusService ] && mv /opt/move/UpdateDBusService /opt/move/UpdateDBusService.disabled || true
dbus-send --system --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig 2>/dev/null || true

# --- revert note ---
mkdir -p /root/schwung-update-disabled
cat > /root/schwung-update-disabled/README.txt <<'NOTE'
Automatic Ableton OS/firmware updates are DISABLED (protects the schwung/PoundHard
takeover). Nothing deleted — all renamed. To RE-ENABLE (for a manual update):

  mv /opt/move/UpdateDBusService.disabled /opt/move/UpdateDBusService
  mv /usr/share/dbus-1/system-services/com.ableton.update.service.disabled \
     /usr/share/dbus-1/system-services/com.ableton.update.service
  for d in 2 3 4 5; do mv /etc/rc$d.d/DISABLED_S70swupdate /etc/rc$d.d/S70swupdate; done
  /etc/init.d/swupdate start
  dbus-send --system --type=method_call --dest=org.freedesktop.DBus / org.freedesktop.DBus.ReloadConfig

Then update from the Move UI, and re-run move/disable-updates.sh afterward.
NOTE

echo "update machinery:"
pidof swupdate          >/dev/null 2>&1 && echo "  swupdate:          STILL RUNNING" || echo "  swupdate:          off"
pidof UpdateDBusService >/dev/null 2>&1 && echo "  UpdateDBusService: STILL RUNNING" || echo "  UpdateDBusService: off"
REMOTE

echo "Done — automatic updates disabled on $HOST."
