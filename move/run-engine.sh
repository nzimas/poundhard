#!/bin/sh
# Bring up the PoundHard SC engine on the Move: shadow JACK + sclang(boot).
# Run on the device. Leaves jackd + sclang(+scsynth) running in the background;
# the headless controller (run-controller.sh) then drives it over OSC.
#
# PoundHard ships its OWN self-contained scsynth/sclang bundle (bin/ lib/ plugins/
# share/ under $PH, installed by move/deploy-bundle.sh) — no other takeover needs to
# be on the device. $PH/share/sclang_conf.yaml points at PoundHard's own class
# library + Extensions.
set -e
PH=/data/UserData/poundhard
RNBO=/data/UserData/rnbo
# The Schwung menu launches us with HOME unset; sclang then tries to mkdir
# /.local/share/SuperCollider (filesystem root) and fails -> Server.default is
# nil -> the engine never boots. Point HOME at an ableton-writable dir.
export HOME=/data/UserData
# NOTE: this only helps sclang. scsynth/supernova/jackd carry RT file capabilities, and
# glibc DISCARDS LD_LIBRARY_PATH for a capability-carrying binary — they find their
# libraries through the RPATH baked into them (patched at bundle time to $PH/lib).
export LD_LIBRARY_PATH=$PH/lib:$RNBO/lib
# The shadow driver comes from Schwung (a hard prerequisite); fall back to RNBO's copy.
JACK_DRIVER_DIR=/data/UserData/schwung/lib/jack
[ -d "$JACK_DRIVER_DIR" ] || JACK_DRIVER_DIR=$RNBO/lib/jack
export JACK_DRIVER_DIR
export JACK_NO_AUDIO_RESERVATION=1
export SC_JACK_DEFAULT_OUTPUTS=system          # scsynth out -> shadow playback
export SC_PLUGIN_PATH=$PH/plugins              # UGen plugins (backup to ph-boot)
# SERVER: supernova (multicore) when >0, scsynth when 0. ph-boot.scd reads this and
# picks the binary + thread count. Supernova needs the *_supernova.so plugin set (shipped)
# and cap_sys_nice on its binary so its parallel DSP threads can go realtime.
export PH_THREADS="${PH_THREADS:-3}"
# Engine config (44.1k = the Move shadow rate; mono-in/stereo-out).
export PH_SR=44100
export PH_CHANNELS=2
# INPUTS: 2 (microphone) + 32 (the CSOUND engine's 16 stereo track returns over JACK).
# The extra ports cost nothing when no track uses the engine.
export PH_INPUTS=34
export PH_BLOCK=128                 # match the shadow JACK period (128)
# Telemetry / handshake target = the local headless controller.
export CONTROLLER_HOST=127.0.0.1
export CONTROLLER_PORT=57140
export PATH=$PH/bin:$PATH
LOGS=$PH/logs; mkdir -p "$LOGS"
JACKLOG=$LOGS/jackd.log; ENGLOG=$LOGS/engine.log

echo "[engine] starting jackd -R -d shadow (realtime)"
# Realtime audio chain — -R -P70 puts jackd on SCHED_FIFO; libjack then promotes
# scsynth's audio callback thread to RT too (scsynth has cap_sys_nice). Needs
# cap_sys_nice+cap_ipc_lock on the jackd binary. Priority 70 stays BELOW the
# SPI/IRQ kernel threads (chrt 90/91) so the DAC/display path is never starved.
# PoundHard ships its own jackd; RNBO's is only a fallback for older installs. Whichever
# is already RUNNING wins — the shadow JACK is shared with the rest of the box.
JACKBIN=$PH/bin/jackd
[ -x "$JACKBIN" ] || JACKBIN=$RNBO/bin/jackd
pgrep -f "jackd -R" >/dev/null 2>&1 || { "$JACKBIN" -R -P 70 -d shadow > "$JACKLOG" 2>&1 & sleep 2; }
grep -q "attached to shared memory" "$JACKLOG" 2>/dev/null && echo "[engine] shadow attached"

echo "[engine] starting sclang (ph-boot.scd) — pinned to cores 0-2"
taskset 0x7 $PH/bin/sclang -l $PH/share/sclang_conf.yaml $PH/sc/ph-boot.scd \
    > "$ENGLOG" 2>&1 &
echo "[engine] sclang pid=$!  (log: $ENGLOG)"
echo "[engine] waiting for boot ..."
i=0
while [ $i -lt 60 ]; do
    grep -q "server ready\|SuperCollider 3 server ready\|Supernova ready" "$ENGLOG" 2>/dev/null && break
    grep -qi "ERROR\|FAILURE\|Exception" "$ENGLOG" 2>/dev/null && { echo "[engine] error:"; tail -n 20 "$ENGLOG"; exit 1; }
    i=$((i+1)); sleep 1
done
echo "[engine] --- log tail ---"; tail -n 12 "$ENGLOG"

# Core pinning: keep the audio thread (scsynth + jackd) on cores 1-2, sclang +
# the Python controller on core 0, and leave core 3 for the SPI/display driver.
for p in $(pgrep -f "$PH/bin/scsynth") $(pgrep -f "jackd -R"); do taskset -pc 1-2 "$p" >/dev/null 2>&1; done
# supernova is NOT pinned here: it self-pins its DSP threads one per core (masks 1/2/4 =
# cores 0-2), which is already the layout we want — 3 DSP threads on 3 cores, core 3 left
# to the SPI/display driver. Forcing affinity afterwards does not stick (the threads are
# inside sclang's inherited 0x7 mask). Measured: 0 XRuns at ~143% CPU on the dense rig.
for p in $(pgrep -f "$PH/bin/sclang"); do taskset -pc 0 "$p" >/dev/null 2>&1; done

for p in $(pgrep -f "jackd -R") $(pgrep -f "$PH/bin/scsynth") $(pgrep -f "$PH/bin/supernova"); do
    echo "[engine] $(cat /proc/$p/comm 2>/dev/null) sched: $(chrt -p $p 2>/dev/null | tr '\n' ' ')"
done

