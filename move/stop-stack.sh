#!/bin/sh
# Tear the PoundHard stack DOWN completely. Run by the overtake ui.js on Back,
# so nothing survives into the next session.
pkill -9 -f poundhard.headless 2>/dev/null
killall -9 sclang scsynth jackd 2>/dev/null
rm -f /dev/shm/SuperColliderServer_* 2>/dev/null
rm -f /data/UserData/schwung/jack_running 2>/dev/null
rm -f /data/UserData/poundhard/ipc/*.json /data/UserData/poundhard/ipc/ui_hb.txt /dev/shm/poundhard/* 2>/dev/null
