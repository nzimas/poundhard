// One softcut VOICE: a read/write head on a buffer, with crossfaded looping, subsample-
// accurate resampling, live overdub, slewed rate and pre/post multimode filters.
//
// TWO OUTPUTS: [audio, head position in seconds]. The position output is norns' phase poll.
//
// `rate` may be NEGATIVE — true reverse playback of the recorded audio.
// `cut` jumps the play head when its VALUE CHANGES (a trigger, not a level); < 0 = no jump.
//
// The argument names are norns' softcut parameter names, so a script's call site and this
// call site read the same. Defaults are softcut-lib's own, not musical choices — a script
// sets what it wants and this leaves the rest alone.
PhSoftcut : MultiOutUGen {
	*ar { arg in = 0.0, buf = 0,
		rate = 1.0, rateSlew = 0.0, loopStart = 0.0, loopEnd = 1.0, cut = -1.0,
		fade = 0.0005, recLevel = 0.0, preLevel = 0.0, recPreSlew = 0.0,
		play = 0.0, rec = 0.0, loop = 1.0, phaseQuant = 1.0, recOffset = -0.00544,
		preFc = 12000.0, preRq = 2.0, preLp = 1.0, preHp = 0.0, preBp = 0.0, preBr = 0.0,
		preDry = 0.0,
		postFc = 12000.0, postRq = 2.0, postLp = 0.0, postHp = 0.0, postBp = 0.0,
		postBr = 0.0, postDry = 1.0;
		^this.multiNew('audio', in, buf,
			rate, rateSlew, loopStart, loopEnd, cut, fade,
			recLevel, preLevel, recPreSlew, play, rec, loop, phaseQuant, recOffset,
			preFc, preRq, preLp, preHp, preBp, preBr, preDry,
			postFc, postRq, postLp, postHp, postBp, postBr, postDry);
	}

	init { arg ...theInputs;
		inputs = theInputs;
		^this.initOutputs(2, rate);
	}

	checkInputs {
		if (inputs.at(0).rate != 'audio') {
			^("in is not audio rate: " + inputs.at(0) + inputs.at(0).rate);
		}
		^this.checkValidInputs;
	}
}
