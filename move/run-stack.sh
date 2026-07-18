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

# Engine: jackd -d shadow + sclang(boot). Guard against double-start.
if ! pgrep -f "bin/sclang" >/dev/null 2>&1; then
    nohup sh "$PH/run-engine.sh" > "$LOGS/stack_engine.log" 2>&1 &
fi

# Suspend-detection flag (mirrors RNBO): mark that shadow JACK is up.
echo 1 > /data/UserData/schwung/jack_running 2>/dev/null

# Controller: starts in parallel — it pings the engine until ready.
if ! pgrep -f poundhard.headless >/dev/null 2>&1; then
    nohup sh "$PH/run-controller.sh" > "$LOGS/controller.log" 2>&1 &
fi
