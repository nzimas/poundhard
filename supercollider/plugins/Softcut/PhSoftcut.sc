// One softcut VOICE: a read/write head on a shared buffer, with crossfaded looping,
// subsample-accurate resampling, live overdub and a multimode post filter.
// Several instances in one SynthDef share a buffer, exactly as norns' six voices do.
//
// `rate` may be NEGATIVE — that is true reverse playback of the recorded audio, which is
// the tape gesture the step sequencer cannot express.
// `cut` jumps the play head when its VALUE CHANGES (a trigger, not a level); < 0 = no jump.
PhSoftcut : UGen {
    *ar { arg in = 0.0, buf = 0, rate = 1.0, loopStart = 0.0, loopEnd = 4.0, cut = -1.0,
              fade = 0.02, recLevel = 1.0, preLevel = 0.75,
              play = 1.0, rec = 1.0, loop = 1.0,
              fc = 12000.0, rq = 2.0, lp = 1.0, hp = 0.0, bp = 0.0, dry = 0.0,
              mul = 1.0, add = 0.0;
        ^this.multiNew('audio', in, buf, rate, loopStart, loopEnd, cut, fade,
                       recLevel, preLevel, play, rec, loop,
                       fc, rq, lp, hp, bp, dry).madd(mul, add);
    }

    checkInputs {
        if (inputs.at(0).rate != 'audio') {
            ^("in is not audio rate: " + inputs.at(0) + inputs.at(0).rate);
        }
        ^this.checkValidInputs;
    }
}
