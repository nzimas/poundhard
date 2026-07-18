#!/bin/sh
# Bring up the PoundHard SC engine on the Move: shadow JACK + sclang(boot).
# Run on the device. Leaves jackd + sclang(+scsynth) running in the background;
# the headless controller (run-controller.sh) then drives it over OSC.
#
# PoundHard reuses the same scsynth/sclang bundle layout as the wildrider
# takeover (bin/ lib/ plugins/ share/ under $PH); DRUM/FMTONE/BUCHLOID/SAMPLER
# are pure-SC voices, so no mi-UGens are strictly required, but the bundle's
# sc3-plugins are harmless if present.
set -e
PH=/data/UserData/poundhard
RNBO=/data/UserData/rnbo
# The Schwung menu launches us with HOME unset; sclang then tries to mkdir
# /.local/share/SuperCollider (filesystem root) and fails -> Server.default is
# nil -> the engine never boots. Point HOME at an ableton-writable dir.
export HOME=/data/UserData
export LD_LIBRARY_PATH=$PH/lib:$RNBO/lib
export JACK_DRIVER_DIR=/data/UserData/schwung/lib/jack
export JACK_NO_AUDIO_RESERVATION=1
export SC_JACK_DEFAULT_OUTPUTS=system          # scsynth out -> shadow playback
export SC_PLUGIN_PATH=$PH/plugins              # UGen plugins (backup to ph-boot)
# Engine config (44.1k = the Move shadow rate; mono-in/stereo-out).
export PH_SR=44100
export PH_CHANNELS=2
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
pgrep -f "jackd -R" >/dev/null 2>&1 || { $RNBO/bin/jackd -R -P 70 -d shadow > "$JACKLOG" 2>&1 & sleep 2; }
grep -q "attached to shared memory" "$JACKLOG" 2>/dev/null && echo "[engine] shadow attached"

echo "[engine] starting sclang (ph-boot.scd) — pinned to cores 0-2"
taskset 0x7 $PH/bin/sclang -l $PH/share/sclang_conf.yaml $PH/sc/ph-boot.scd \
    > "$ENGLOG" 2>&1 &
echo "[engine] sclang pid=$!  (log: $ENGLOG)"
echo "[engine] waiting for boot ..."
i=0
while [ $i -lt 60 ]; do
    grep -q "server ready\|SuperCollider 3 server ready" "$ENGLOG" 2>/dev/null && break
    grep -qi "ERROR\|FAILURE\|Exception" "$ENGLOG" 2>/dev/null && { echo "[engine] error:"; tail -n 20 "$ENGLOG"; exit 1; }
    i=$((i+1)); sleep 1
done
echo "[engine] --- log tail ---"; tail -n 12 "$ENGLOG"

# Core pinning: keep the audio thread (scsynth + jackd) on cores 1-2, sclang +
# the Python controller on core 0, and leave core 3 for the SPI/display driver.
for p in $(pgrep -f "bin/scsynth") $(pgrep -f "jackd -R"); do taskset -pc 1-2 "$p" >/dev/null 2>&1; done
for p in $(pgrep -f "bin/sclang"); do taskset -pc 0 "$p" >/dev/null 2>&1; done

for p in $(pgrep -f "jackd -R") $(pgrep -f "bin/scsynth"); do
    echo "[engine] $(cat /proc/$p/comm 2>/dev/null) sched: $(chrt -p $p 2>/dev/null | tr '\n' ' ')"
done
