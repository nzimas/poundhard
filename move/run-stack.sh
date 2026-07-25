#!/bin/sh
# Launch the full PoundHard stack (engine + headless controller) non-blocking.
# Called once by the overtake ui.js. Each sub-script daemonises its processes;
# we background the launchers so host_system_cmd returns immediately.
PH=/data/UserData/poundhard
LOGS=$PH/logs; mkdir -p "$LOGS"
# IPC dir for control/status/heartbeat (separate from $PH/share = the SC bundle).
# Real dir on /data (the Schwung host can only read files under /data/UserData, and
# reads through a tmpfs symlink hang the host — so keep it a plain directory here).
if [ -L "$PH/ipc" ]; then rm -f "$PH/ipc"; fi
mkdir -p "$PH/ipc"

# Only ONE takeover runs at a time, and the SC ports are SHARED with the sibling
# takeovers (57110 scsynth/supernova, 57120 sclang, 57140 controller telemetry). An
# unclean exit from wildrider/atelier/... leaves its engine running, which both MASKS
# our start-guard and HOLDS those ports — the stack then half-starts (controller up,
# engine dead) and PoundHard is silent. So clear any FOREIGN SC engine first.
# jackd is deliberately NOT touched: it's the shared shadow server we reuse.
for p in $(pgrep -f "bin/sclang" 2>/dev/null) $(pgrep -f "bin/scsynth" 2>/dev/null) \
         $(pgrep -f "bin/supernova" 2>/dev/null); do
    case "$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)" in
        *"$PH"*) ;;                                  # ours — leave it alone
        "") ;;                                       # vanished
        *) echo "[stack] clearing foreign SC engine pid $p"; kill -9 "$p" 2>/dev/null ;;
    esac
done
# A foreign headless controller squatting on the telemetry port (57140) blocks ours too.
for p in $(pgrep -f "\.headless" 2>/dev/null); do
    case "$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null)" in
        *poundhard.headless*) ;;                     # ours
        "") ;;
        *) echo "[stack] clearing foreign controller pid $p"; kill -9 "$p" 2>/dev/null ;;
    esac
done
rm -f /dev/shm/SuperColliderServer_* 2>/dev/null   # stale shm segment breaks World_New

# Engine: jackd -d shadow + sclang(boot). Guard against double-start — match OUR
# sclang by full path, or a sibling takeover's sclang would suppress our engine.
if ! pgrep -f "$PH/bin/sclang" >/dev/null 2>&1; then
    nohup sh "$PH/run-engine.sh" > "$LOGS/stack_engine.log" 2>&1 &
fi

# Suspend-detection flag (mirrors RNBO): mark that shadow JACK is up.
echo 1 > /data/UserData/schwung/jack_running 2>/dev/null

# Controller: starts in parallel — it pings the engine until ready.
if ! pgrep -f poundhard.headless >/dev/null 2>&1; then
    nohup sh "$PH/run-controller.sh" > "$LOGS/controller.log" 2>&1 &
fi
