// On-device boot wrapper for the PoundHard SC engine (Move takeover).
//
// The bundled sclang was built with prefix /usr/local, so its default scsynth
// path / resourceDir don't exist on the Move. Point the Server at the bundled
// scsynth + UGen plugins, then hand off to boot.scd (which loads synthdefs +
// engine and auto-boots the server).
(
var dir = "/data/UserData/poundhard";
Server.program = dir +/+ "bin/scsynth";
Server.default.options.ugenPluginsPath = [dir +/+ "plugins"];
// boot.scd lives next to this file (both land in $PH/sc on deploy).
(thisProcess.nowExecutingPath.dirname +/+ "boot.scd").load;
)
