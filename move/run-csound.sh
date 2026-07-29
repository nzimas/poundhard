#!/bin/sh
# Bring up the PoundHard CSOUND engine (engine 20) as a JACK client.
#
# Csound is a SEPARATE PROCESS from the SC server, but it is not a separate instrument:
# it writes one stereo pair per track into supernova's input ports, and an SC voice reads
# that pair onto the track bus. So a Csound track goes through the per-track filter, the
# 8-slot FX chain, the living-FX sends, the mixer and the master exactly like every other
# engine — which is the whole reason for wiring it this way instead of letting Csound talk
# to the hardware.
#
# CHANNEL MAP. supernova boots with 34 inputs: 1-2 are the microphone (untouched), 3-34
# are the 16 Csound track pairs. Csound's own channels 1-2 are dead — its JACK module
# auto-connects the first two to the hardware playback ports and there is no flag to stop
# it, so they are left silent and the tracks start at channel 3.
#
#   csound output_3+2t / output_4+2t   ->   supernova input_3+2t / input_4+2t   (track t)
#
# The connections are made explicitly with ph-jackconnect rather than left to Csound's
# auto-connect, which wires by port enumeration order and would silently mis-route all 32
# channels the day another client joins the graph.
set -e
PH=/data/UserData/poundhard
CS=$PH/csound
LOGS=$PH/logs; mkdir -p "$LOGS"
CSLOG=$LOGS/csound.log

export OPCODE6DIR64=$CS/plugins
export LD_LIBRARY_PATH=$CS/lib:$PH/lib
export PATH=$CS/bin:$PH/bin:$PATH

# already running? (idempotent — the stack launcher may be re-run)
pgrep -f "csound.*ph-engine" >/dev/null 2>&1 && { echo "[csound] already running"; exit 0; }

[ -f "$CS/orc/ph-engine.orc" ] || { echo "[csound] no orchestra at $CS/orc — not installed"; exit 1; }

# The orchestra is driven entirely over UDP ($-prefixed score events from sclang), so the
# score holds nothing but a 100-year-long dummy note to keep the performance alive.
cat > "$CS/orc/ph-run.sco" <<'SCO'
i999 0 3153600000
e
SCO

echo "[csound] starting (jack client 'poundhard_cs', UDP 11000)"
csound \
  -+rtaudio=jack -odac -+jack_client=poundhard_cs \
  -b128 -B1024 --sample-rate=44100 --nchnls=34 \
  --port=11000 --nodisplays -d -m0 \
  "$CS/orc/ph-engine.orc" "$CS/orc/ph-run.sco" </dev/null > "$CSLOG" 2>&1 &
CSPID=$!
echo "[csound] pid=$CSPID (log: $CSLOG)"

# wait for its JACK ports to exist before connecting
i=0
while [ $i -lt 40 ]; do
    grep -q "Jack output ports" "$CSLOG" 2>/dev/null && break
    kill -0 "$CSPID" 2>/dev/null || { echo "[csound] died on startup:"; tail -n 15 "$CSLOG"; exit 1; }
    i=$((i+1)); sleep 0.25
done
sleep 1

# 32 channels: csound output_3..34 -> supernova input_3..34
if "$CS/bin/ph-jackconnect" poundhard_cs 3 supernova 3 32; then
    echo "[csound] track pairs wired into supernova inputs 3-34"
else
    echo "[csound] WARNING: some connections failed — see above"
fi

# Keep Csound off the display core (3) and out of the way of the SC DSP threads.
taskset -pc 0-2 "$CSPID" >/dev/null 2>&1 || true
echo "[csound] up"
