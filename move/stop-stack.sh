#!/bin/sh
# Tear the PoundHard stack DOWN completely. Run by the overtake ui.js on Back,
# so nothing survives into the next session.
pkill -9 -f poundhard.headless 2>/dev/null
# supernova and csound were missing here. A surviving supernova makes the next boot attach
# to an orphan server (ready, zero nodes, no audio); a surviving csound loses its JACK
# server with jackd and then sits there dead-but-present, which was enough to make
# run-csound.sh skip starting a live one — the CSOUND engine came back silent.
killall -9 sclang scsynth supernova jackd csound 2>/dev/null
rm -f /dev/shm/SuperColliderServer_* 2>/dev/null
rm -f /data/UserData/schwung/jack_running 2>/dev/null
rm -f /data/UserData/poundhard/ipc/*.json /data/UserData/poundhard/ipc/ui_hb.txt /dev/shm/poundhard/* 2>/dev/null
