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

# A HALF-DEAD STACK IS WORSE THAN A DEAD ONE, and it is the state a relaunch cannot escape.
# supernova can die on its own while everything around it survives — JACK drops a client that
# misses its deadline often enough, which is what happens if the stack is started while
# MoveOriginal is still hammering the CPU after a reboot. sclang, jackd, the controller and
# csound all keep running, so the guard below (which only asks whether OUR sclang exists)
# skips the engine start and the relaunch does nothing at all: ready stays false, nodes stay
# 0, and pressing the button again changes nothing forever. Observed exactly that: 877 xruns,
# "Server 'localhost' exited with exit code 0", and a stack that could not be restarted.
#
# So: an sclang with no server under it is not a running engine, it is wreckage. Clear it.
if pgrep -f "$PH/bin/sclang" >/dev/null 2>&1 \
   && ! pgrep -x supernova >/dev/null 2>&1 && ! pgrep -x scsynth >/dev/null 2>&1; then
    echo "[stack] sclang is up but the server is gone — tearing the stack down first"
    sh "$PH/stop-stack.sh" >/dev/null 2>&1
    sleep 2
fi

# Engine: jackd -d shadow + sclang(boot). Guard against double-start — match OUR
# sclang by full path, or a sibling takeover's sclang would suppress our engine.
if ! pgrep -f "$PH/bin/sclang" >/dev/null 2>&1; then
    nohup sh "$PH/run-engine.sh" > "$LOGS/stack_engine.log" 2>&1 &
fi

# CSOUND (engine 20): its own JACK client, feeding supernova's inputs 3-34. Launched from
# HERE rather than from run-engine.sh, which runs under `set -e` and exits on the first
# non-zero command — so the launch at its tail was simply never reached and engine 20 came
# up silent with nothing in the log to explain it. Waits for supernova's ports to exist,
# since there is nothing to connect to before that.
if [ -x "$PH/run-csound.sh" ]; then
    (
        i=0
        while [ $i -lt 90 ]; do
            pgrep -x supernova >/dev/null 2>&1 && break
            pgrep -x scsynth   >/dev/null 2>&1 && break
            i=$((i+1)); sleep 1
        done
        sleep 3                      # let the server finish registering its input ports
        sh "$PH/run-csound.sh"
    ) > "$LOGS/csound_start.log" 2>&1 &
fi

# Suspend-detection flag (mirrors RNBO): mark that shadow JACK is up.
echo 1 > /data/UserData/schwung/jack_running 2>/dev/null

# Controller: starts in parallel — it pings the engine until ready.
if ! pgrep -f poundhard.headless >/dev/null 2>&1; then
    nohup sh "$PH/run-controller.sh" > "$LOGS/controller.log" 2>&1 &
fi
