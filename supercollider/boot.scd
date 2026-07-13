// PoundHard boot entry. Loads the voice SynthDefs, then the engine OSC host,
// then boots the server. Run headless via: sclang boot.scd
(
var here = thisProcess.nowExecutingPath.dirname;
s = Server.default;
s.options.numOutputBusChannels = ("PH_CHANNELS".getenv ? "2").asInteger;
s.options.numInputBusChannels = ("PH_CHANNELS".getenv ? "2").asInteger;
s.options.sampleRate = ("PH_SR".getenv ? "44100").asInteger;
s.options.blockSize = ("PH_BLOCK".getenv ? "128").asInteger;
s.options.memSize = 256 * 1024;

(here +/+ "synthdefs.scd").load;    // defines ~buildDefs
(here +/+ "engine.scd").load;       // defines ~boot + OSC host

~boot.(s.options.sampleRate, s.options.blockSize, s.options.numOutputBusChannels);
)
