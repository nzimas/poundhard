// The Move's built-in microphone.
//
// Not an audio input in the JACK sense — the device exposes none. This reads the shared-memory
// ring published by PoundHard's Schwung DSP plugin, which is the only code able to see the
// mic (it lives in the SPI mailbox, visible to a loaded plugin and nothing else).
//
// Outputs silence when the tap is absent, so a graph using it is always safe to build.
PhMicIn : UGen {
	*ar { arg gain = 1.0, mul = 1.0, add = 0.0;
		^this.multiNew('audio', gain).madd(mul, add);
	}
}
