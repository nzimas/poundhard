#!/bin/sh
# PoundHard overtake exit cleanup — called by the Schwung shim on clean exit.
# Tear the whole on-device stack down and release the shadow-JACK flag.
pkill -9 -f poundhard.headless 2>/dev/null
killall -9 sclang   2>/dev/null
killall -9 scsynth  2>/dev/null
killall -9 jackd    2>/dev/null
# scsynth's shared-memory server segment must go too, or the next launch (as the
# same user) can fail in World_New if a stale one is present.
rm -f /dev/shm/SuperColliderServer_* 2>/dev/null
rm -f /data/UserData/schwung/jack_running
# Drop the hand-off files so a stale grid can't flash on relaunch.
rm -f /data/UserData/poundhard/ipc/*.json /data/UserData/poundhard/ipc/ui_hb.txt /dev/shm/poundhard/* 2>/dev/null
