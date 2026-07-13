#!/bin/sh
# Run the headless PoundHard controller daemon on the Move.
# Talks OSC to the local sclang engine (127.0.0.1:57120), runs the sequencer /
# control loop, and reads/writes share/{control,status}.json for the ui.js.
PH=/data/UserData/poundhard
export HOME=/data/UserData          # menu launch has HOME unset (see run-engine.sh)
export SC_HOST=127.0.0.1
export SC_PORT=57120              # sclang langPort (engine.scd OSCdefs)
export CONTROLLER_PORT=57140      # engine -> controller telemetry/ready
export PH_CONTROL_PORT=57150      # reserved (ui.js talks over the file bridge)
export PH_CONTROL_RATE=30            # UI poll / status loop Hz (the step clock lives
                                    # in the SC engine, so Python stays relaxed here)
# IPC dir (control/status/heartbeat) — run-stack.sh symlinks $PH/ipc to tmpfs so
# I/O is on RAM. Separate from $PH/share (the SuperCollider bundle class library).
export PH_SHARE=$PH/ipc
# poundhard package + vendored pythonosc.
export PYTHONPATH=$PH/controller:$PH/controller/vendor
# Pin the controller to core 0 so its Python churn never preempts scsynth's
# audio thread (isolated onto cores 1-2). Core 3 = SPI/display.
exec taskset -c 0 python3 -m poundhard.headless
