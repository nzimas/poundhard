// On-device boot wrapper for the PoundHard SC engine (Move takeover).
//
// The bundled sclang was built with prefix /usr/local, so its default scsynth
// path / resourceDir don't exist on the Move. Point the Server at the bundled
// scsynth + UGen plugins, then hand off to boot.scd (which loads synthdefs +
// engine and auto-boots the server).
(
var dir = "/data/UserData/poundhard";
// SERVER CHOICE — PH_THREADS (set by run-engine.sh):
//   >0  -> supernova, the MULTICORE server, with that many DSP threads. It only
//          parallelises across ParGroups (see ~gVoices/~gFx in engine.scd); a plain
//          Group stays serial, so the graph decides how much of the CM4 gets used.
//   0/unset -> scsynth (single-threaded), the original path, untouched.
// NOTE: supernova loads ONLY the *_supernova.so plugin variants — the bundle ships
// both sets, so every engine works either way.
var tstr = "PH_THREADS".getenv;
var threads = tstr.notNil.if({ tstr.asInteger }, { 0 });
~phSupernova = threads > 0;
Server.program = dir +/+ (~phSupernova.if({ "bin/supernova" }, { "bin/scsynth" }));
~phSupernova.if { Server.default.options.threads = threads };
Server.default.options.ugenPluginsPath = [dir +/+ "plugins"];
// boot.scd lives next to this file (both land in $PH/sc on deploy).
(thisProcess.nowExecutingPath.dirname +/+ "boot.scd").load;
)
