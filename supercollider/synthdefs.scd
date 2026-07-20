// PoundHard — voice SynthDefs.
//
// A 16-track groovebox. Each active step SPAWNS a fresh one-shot voice synth
// that plays its envelope and frees itself (DetectSilence -> doneAction:2), so
// CPU is only spent on notes that are actually sounding — essential on the
// Move's low-power ARM (16 always-on voices, each DRUM computing all 7 modes,
// overloads it). The engine passes the track's stored params + note + vel at
// spawn time; the amp envelope fires on creation.
//
// Shared interface: \note (drum=pitch, tonal=fundamental), \vel 0..2, \amp \pan,
// \out (the stereo master bus). Tracks 1-8 are DRUM; 9-16 add FM7/BUCHLOID/
// SAMPLER. Output is stereo (the Move shadow-JACK sink is 2ch).
~buildDefs = { |nchan = 2|
	~spread = { |sig, pan = 0| Pan2.ar(sig, pan.clip(-1, 1)) };
	~killbad = { |sig| LeakDC.ar(sig).clip2(4) };

	// STK rawwave path: the STK physical-model UGens (ModalBar / BandedWG / etc.) load
	// excitation wavetables (e.g. marmstk1.raw) from this directory. Run once at boot
	// BEFORE any STK voice spawns, or those instruments excite silence. (StkShakers is
	// stochastic and needs no rawwaves, which is why it worked without this.)
	SynthDef(\phStkInit, { StkGlobals.ar(1, 1, "/data/UserData/poundhard/rawwaves"); Line.kr(0, 1, 0.3, doneAction: 2) }).add;

	// master bus clear: zero the private sum bus at the head of each block.
	SynthDef(\phClear, { |bus = 16| ReplaceOut.ar(bus, DC.ar(0) ! nchan) }).add;

	// master: sum bus -> optional global lowpass -> limiter -> hardware out.
	SynthDef(\phMaster, { |in = 16, out = 0, gain = 1.0, cutoff = 20000, res = 0.0|
		var sig = In.ar(in, nchan) * gain;
		var fc = cutoff.clip(40, 20000);
		sig = Select.ar(cutoff < 19000, [sig, RLPF.ar(sig, fc, (1 - (res.clip(0, 1) * 0.9)).clip(0.05, 1))]);
		sig = Limiter.ar(LeakDC.ar(sig), 0.95, 0.01);
		Out.ar(out, sig);
	}).add;

	// ================= DRUM (one hit, self-freeing) =================
	// Split into 7 per-mode SynthDefs (\phDrumKick .. \phDrumNoise) so a hit runs
	// ONLY its mode's DSP — the old all-modes-then-Select voice cost ~5-7x more
	// (it computed kick+snare+hat+6-osc metalBank+metal+clap+tom+noise every
	// sample) and XRun-froze the Move under dense patterns. The engine picks the
	// def from the track's `mode` param. `bodyFn.(e)` returns the mode's raw voice;
	// the shared preamble (envs/click) + postamble (filter/grit/free) wrap it.
	~mkDrum = { |name, bodyFn|
		SynthDef(name, { |out = 16, note = 40, vel = 1, mode = 0,
			pitchMod = 0.6, pitchDecay = 0.05, ampDecay = 0.25, ampCurve = -4,
			transient = 0.6, transTone = 0.5, transDecay = 0.004,
			noiseAmt = 0.3, noiseTone = 0.5, noiseDecay = 0.12,
			cutoff = 9000, res = 0.2, filterType = 0, filterEnv = 0.3,
			fold = 0, drive = 1, crush = 0, downsample = 0,
			ratio = 1.5, fmAmt = 0.0, harmonics = 0.5, snap = 0.5,
			amp = 0.8, pan = 0|
			var v, f0, dsr, bits, fcut, pEnv, aEnv, nEnv, clickEnv, click, body, sig, e;
			v = vel.clip(0, 2).max(0.03);
			f0 = note.clip(6, 110).midicps;
			pEnv = EnvGen.ar(Env.perc(0.0002, pitchDecay.clip(0.002, 0.6), 1, -4));
			aEnv = EnvGen.ar(Env.perc(0.0004, ampDecay.clip(0.004, 4), 1, ampCurve.clip(-8, -1)));
			nEnv = EnvGen.ar(Env.perc(0.0004, noiseDecay.clip(0.004, 3), 1, -3));
			clickEnv = EnvGen.ar(Env.perc(0.00003, transDecay.clip(0.0005, 0.03), 1, -6));
			click = ((SinOsc.ar(transTone.linexp(0, 1, 900, 7000))
				+ (HPF.ar(WhiteNoise.ar, 2500) * 0.9)) * clickEnv * transient).tanh;
			e = (f0: f0, aEnv: aEnv, pEnv: pEnv, nEnv: nEnv, pitchMod: pitchMod,
				noiseTone: noiseTone, noiseAmt: noiseAmt, noiseDecay: noiseDecay,
				snap: snap, res: res, ratio: ratio, fmAmt: fmAmt, harmonics: harmonics);
			body = bodyFn.(e);
			fcut = (cutoff * (2 ** (aEnv * filterEnv * 3))).clip(30, 18000);
			body = Select.ar(filterType.round.clip(0, 2), [
				RLPF.ar(body, fcut, (1 - (res * 0.9)).clip(0.05, 1)),
				BPF.ar(body, fcut, (1 - (res * 0.9)).clip(0.05, 1)),
				RHPF.ar(body, fcut, (1 - (res * 0.9)).clip(0.05, 1))]);
			sig = body + click;
			sig = SelectX.ar(fold.clip(0, 1), [sig, (sig * (1 + (fold * 5))).fold2(1)]);
			sig = (sig * (1 + (drive.clip(0, 6) * 2))).tanh;
			bits = crush.clip(0, 1).linexp(0, 1, 24, 3);
			sig = (sig * (2 ** bits)).round / (2 ** bits);
			dsr = downsample.clip(0, 1).linexp(0, 1, 20000, 800);
			sig = Select.ar((downsample.clip(0, 1) > 0.01), [sig, Latch.ar(sig, Impulse.ar(dsr))]);
			sig = LeakDC.ar(sig) * v * amp;
			Line.kr(0, 1, ampDecay.clip(0.004, 4).max(noiseDecay.clip(0.004, 3)) + 0.25, doneAction: 2);
			Out.ar(out, ~killbad.(~spread.(sig, pan)));
		}).add;
	};
	~mkDrum.(\phDrumKick, { |e|
		SinOsc.ar((e[\f0] * (1 + (e[\pEnv] * e[\pitchMod] * 12))).clip(16, 4000)) * e[\aEnv] });
	~mkDrum.(\phDrumSnare, { |e|
		((SinOsc.ar(e[\f0] * 2) + LFTri.ar(e[\f0] * 3.01)) * 0.4 * e[\aEnv])
		+ (BPF.ar(WhiteNoise.ar, e[\noiseTone].linexp(0, 1, 1200, 7000), (1 - (e[\res] * 0.7)).clip(0.1, 1))
			* e[\nEnv] * (0.5 + (e[\snap] * 0.5))) });
	~mkDrum.(\phDrumHat, { |e|
		var mb = Mix(Pulse.ar((e[\f0] * [2, 3.03, 4.16, 5.43, 6.79, 8.21]).clip(40, 16000))) * 0.16;
		(HPF.ar(mb, e[\noiseTone].linexp(0, 1, 3000, 11000)) * e[\aEnv])
		+ (HPF.ar(WhiteNoise.ar, 6000) * e[\nEnv] * e[\noiseAmt] * 0.5) });
	~mkDrum.(\phDrumMetal, { |e|
		var mv = SinOsc.ar((e[\f0] + (SinOsc.ar((e[\f0] * e[\ratio].clip(0.2, 12))) * e[\fmAmt] * e[\f0] * 4)).clip(20, 16000));
		mv = (mv * (1 - e[\harmonics])) + ((mv * SinOsc.ar((e[\f0] * e[\ratio] * 1.7).clip(20, 16000))) * e[\harmonics]);
		RLPF.ar(mv, (e[\f0] * 5).clip(200, 13000), (1 - (e[\res] * 0.8)).clip(0.08, 1)) * e[\aEnv] });
	~mkDrum.(\phDrumClap, { |e|
		var ce = EnvGen.ar(Env.new([0, 1, 0.35, 0.9, 0.25, 0.75, 0, 0.6, 0],
			[0.001, 0.006, 0.001, 0.006, 0.001, 0.006, 0.001, e[\noiseDecay].clip(0.02, 1)], -3));
		BPF.ar(WhiteNoise.ar, e[\noiseTone].linexp(0, 1, 900, 2500), (1 - (e[\res] * 0.6)).clip(0.15, 1))
			* ce * (0.7 + (e[\snap] * 0.5)) });
	~mkDrum.(\phDrumTom, { |e|
		LFTri.ar((e[\f0] * (1 + (e[\pEnv] * e[\pitchMod] * 3))).clip(26, 3000)) * e[\aEnv] });
	~mkDrum.(\phDrumNoise, { |e|
		(PinkNoise.ar + (WhiteNoise.ar * 0.5)) * e[\aEnv] });

	// ================= FM7 — real 6-operator FM (sc3-plugins), self-freeing ==========
	// A full DX7-style 6-operator FM voice with a bank of 6 modulation topologies
	// ("algorithms"). Each operator's frequency is a RATIO of the note; a modulator-index
	// envelope makes the tone brighten then dull (classic FM). `algo` picks the topology,
	// so the generator can target bells, e-pianos, metallic clangs, FM basses and brassy
	// stabs — using all six operators, not a token 2-op pair.
	SynthDef(\phFm7, { |out = 16, note = 48, vel = 1,
		algo = 0, r1 = 1, r2 = 1, r3 = 1, r4 = 2, r5 = 1, r6 = 3.5,
		index = 1.0, fb = 0.1, bright = 1.0,
		attack = 0.004, decay = 0.6, ampCurve = -4, mDecay = 0.6,
		cutoff = 16000, amp = 0.55, pan = 0|
		var v, f0, aEnv, mEnv, ratios, ctlMatrix, modMatrix, ops, sig, fcut;
		// algorithm bank: each entry = ( mods: 6x6 modulation weights [row = carrier being
		// modulated, col = modulator; diagonal = feedback op], carr: 6 output-carrier gains ).
		var algos = [
			// 0 EPIANO/BELL — three parallel 2-op stacks (op0<-op1, op2<-op3, op4<-op5)
			( mods: [[0,1,0,0,0,0],[0,1,0,0,0,0],[0,0,0,1,0,0],[0,0,0,1,0,0],[0,0,0,0,0,1],[0,0,0,0,0,1]],
			  carr: [1,0,1,0,1,0] ),
			// 1 CLANG — one long 6-op chain, feedback on op5 (metallic, inharmonic)
			( mods: [[0,1,0,0,0,0],[0,0,1,0,0,0],[0,0,0,1,0,0],[0,0,0,0,1,0],[0,0,0,0,0,1],[0,0,0,0,0,1]],
			  carr: [1,0,0,0,0,0] ),
			// 2 ORGAN/ADDITIVE — four carriers, two shared modulators (op4, op5)
			( mods: [[0,0,0,0,1,0],[0,0,0,0,1,0],[0,0,0,0,0,1],[0,0,0,0,0,1],[0,0,0,0,1,0],[0,0,0,0,0,1]],
			  carr: [1,1,1,1,0,0] ),
			// 3 FMBASS — carrier+modulator (fb) plus a sub carrier+modulator
			( mods: [[0,1,0,0,0,0],[0,1,0,0,0,0],[0,0,0,1,0,0],[0,0,0,0,0,0],[0,0,0,0,0,0],[0,0,0,0,0,0]],
			  carr: [1,0,1,0,0,0] ),
			// 4 BELL CLUSTER — one carrier hit by three modulators + a body carrier (op5)
			( mods: [[0,1,1,1,0,0],[0,0,0,0,1,0],[0,0,0,0,0,0],[0,0,0,0,0,0],[0,0,0,0,1,0],[0,0,0,0,0,0]],
			  carr: [1,0,0,0,0,1] ),
			// 5 STAB/BRASS — two stacked 3-op branches, feedback on op2 & op5
			( mods: [[0,1,0,0,0,0],[0,0,1,0,0,0],[0,0,1,0,0,0],[0,0,0,0,1,0],[0,0,0,0,0,1],[0,0,0,0,0,1]],
			  carr: [1,0,0,1,0,0] )
		];
		v = vel.clip(0, 2).max(0.03);
		f0 = note.clip(0, 127).midicps;
		aEnv = EnvGen.ar(Env.perc(attack.clip(0.0005, 2), decay.clip(0.01, 8), 1, ampCurve.clip(-8, -1)));
		// modulator-index envelope: FM brightness rises fast, then decays (its own, shorter tail).
		// Control-rate — it only feeds the modulation matrix, keeping it uniform-rate.
		mEnv = EnvGen.kr(Env.perc(0.002, (decay * mDecay).clip(0.01, 6), 1, -3.5));
		ratios = [r1, r2, r3, r4, r5, r6].collect { |r| r.clip(0.01, 24) };
		// FM7 control matrix is 6x3 per operator: [frequency, phase, amplitude].
		ctlMatrix = ratios.collect { |rr| [(rr * f0).clip(1, 20000), 0, 1] };
		// build the modulation matrix: off-diagonal = topology weight * FM index * index-env;
		// diagonal = per-op feedback (topology feedback-mask * fb param).
		modMatrix = 6.collect { |i|
			6.collect { |j|
				var w = Select.kr(algo, algos.collect { |a| a[\mods][i][j] });
				(i == j).if(
					{ w * fb.clip(0, 1) * 1.6 },
					{ w * index.clip(0, 12) * mEnv }
				)
			}
		};
		ops = FM7.ar(ctlMatrix, modMatrix);
		sig = 6.collect { |k| ops[k] * Select.kr(algo, algos.collect { |a| a[\carr][k] }) }.sum;
		sig = sig * aEnv;
		fcut = (cutoff * bright.clip(0.1, 4)).clip(60, 19000);
		sig = LPF.ar(sig, fcut);
		sig = LeakDC.ar(sig) * v * amp * 0.5;
		Line.kr(0, 1, attack.clip(0.0005, 2) + decay.clip(0.01, 8) + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= BUCHLOID (complex osc, self-freeing) =================
	SynthDef(\phBuchloid, { |out = 16, note = 45, vel = 1,
		fm1Ratio = 0.66, fm1Amount = 0.0, fm2Ratio = 3.3, fm2Amount = 0.0,
		waveShape = 0.0, waveFolds = 0.0, timbre = 0.0,
		attack = 0.02, decay = 1.0, peak = 8000, res = 0.2,
		pressure = 0.0, drive = 1.0, amp = 0.5, pan = 0|
		var v, f0, aEnv, fEnv, m1, m2, osc, sig, fc;
		v = vel.clip(0, 2).max(0.03);
		f0 = note.clip(0, 127).midicps;
		aEnv = EnvGen.ar(Env.new([0, 1, 0], [attack.clip(0.001, 4), decay.clip(0.01, 8)], -4));
		fEnv = EnvGen.ar(Env.perc(attack.clip(0.001, 4), decay.clip(0.01, 8), 1, -3));
		m1 = SinOsc.ar(f0 * fm1Ratio.clip(0.1, 12)) * fm1Amount.clip(0, 1) * f0 * 4;
		m2 = SinOsc.ar(f0 * fm2Ratio.clip(0.1, 24)) * fm2Amount.clip(0, 1) * f0 * 4;
		osc = SelectX.ar(waveShape.clip(0, 1), [
			SinOsc.ar((f0 + m1 + m2).clip(10, 18000)),
			VarSaw.ar((f0 + m1 + m2).clip(10, 18000), 0, 0.3 + (timbre.clip(0, 1) * 0.6))]);
		osc = (osc * (1 + (waveFolds.clip(0, 3) * 2) + (timbre.clip(0, 1) * 3))).fold2(1);
		sig = osc * aEnv;
		sig = (sig * (1 + (pressure.clip(0, 1) * 4))).tanh * (1 + (drive.clip(0.1, 4)));
		fc = (peak.clip(100, 12000) * (0.4 + (fEnv * 0.9))).clip(80, 14000);
		sig = RLPF.ar(sig, fc, (1 - (res.clip(0, 1) * 0.9)).clip(0.05, 1));
		sig = LeakDC.ar(sig) * v * amp * 0.6;
		Line.kr(0, 1, attack.clip(0.001, 4) + decay.clip(0.01, 8) + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= SAMPLER (slice, self-freeing) =================
	SynthDef(\phSampler, { |out = 16, buf = 0, note = 60, vel = 1,
		pitch = 0, direction = 0, posStart = 0.0, posWindow = 0.5, scrub = 1.0,
		attack = 0.001, decay = 0.8, ampCurve = -4,
		cutoff = 14000, res = 0.15, crush = 0.0, downsample = 0.0, drive = 1.0,
		amp = 0.6, pan = 0|
		var v, hasBuf, durFrames, rateScale, dir, startFrame, winFrames, rate;
		var phase, sig, fcut, bits, dsr, pos01, edge, aEnv, ptrans;
		v = vel.clip(0, 2).max(0.03);
		hasBuf = buf > 0;
		durFrames = BufFrames.kr(buf).max(1);
		rateScale = BufRateScale.kr(buf);
		dir = Select.kr(direction.clip(0, 1), [1, -1]);
		startFrame = posStart.clip(0, 0.999) * durFrames;
		winFrames = (posWindow.clip(0.01, 1) * durFrames).max(64);
		ptrans = ((note - 60) + pitch).clip(-48, 48);
		rate = (2 ** (ptrans / 12)) * dir * scrub.clip(-8, 8) * rateScale;
		aEnv = EnvGen.ar(Env.perc(attack.clip(0.0005, 2), decay.clip(0.005, 6), 1, ampCurve.clip(-8, -1)));
		phase = Phasor.ar(0, rate, startFrame, startFrame + winFrames, startFrame);
		sig = BufRd.ar(1, buf, phase, 1, 4);
		pos01 = ((phase - startFrame) / winFrames).clip(0, 1);
		edge = (SampleRate.ir * 0.004 / winFrames).clip(0.001, 0.5);
		sig = sig * (pos01 / edge).min((1 - pos01) / edge).clip(0, 1);
		bits = crush.clip(0, 1).linexp(0, 1, 16, 3);
		sig = (sig * (2 ** bits)).round / (2 ** bits);
		dsr = downsample.clip(0, 1).linexp(0, 1, 18000, 1200);
		sig = Select.ar((downsample.clip(0, 1) > 0.01), [sig, Latch.ar(sig, Impulse.ar(dsr))]);
		fcut = cutoff.clip(20, 18000);
		sig = RLPF.ar(sig, fcut, (1 - (res.clip(0, 1) * 0.9)).clip(0.05, 1));
		sig = (sig * (1 + (drive.clip(0.1, 4) * 3))).tanh;
		sig = LeakDC.ar(sig) * aEnv * v * amp * 0.6 * (hasBuf.asInteger);
		Line.kr(0, 1, attack.clip(0.0005, 2) + decay.clip(0.005, 6) + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= MOLLY (Molly-the-Poly analogue voice, gate-triggered) =====
	// Full 2-osc + sub + noise analogue voice with filter/amp ADSRs, LFO, ring-mod,
	// drive and chorus (ported from wildrider-mele). A step gates it for `hold`
	// seconds (ADSR attack/sustain), then it releases and self-frees.
	SynthDef(\phMolly, { |out = 16, note = 48, vel = 1, detune = 7, oscShape = 0.5, pulseWidth = 0.5,
		subLevel = 0, noiseLevel = 0, cutoff = 1200, resonance = 0.2, lpType = 1, filterEnvAmt = 0.3,
		fAtk = 0.05, fDec = 0.3, fSus = 0.6, fRel = 0.6, aAtk = 0.01, aDec = 0.3, aSus = 0.8, aRel = 0.5,
		lfoRate = 4, lfoToCutoff = 0, lfoToPitch = 0, lfoToPW = 0, lfoToAmp = 0,
		ringMod = 0, drive = 0, chorus = 0, hold = 0.3, amp = 0.3, pan = 0,
		fmAmt = 0, fold = 0, crush = 0, downsample = 0, grit = 0|
		var v = vel.clip(0, 2).max(0.03);
		var glen = hold.clip(0.01, 8);
		var gate = EnvGen.kr(Env([1, 1, 0], [glen, 0.0]));   // hold high for glen, then release
		var freq = note.clip(0, 127).midicps;
		var lfo = SinOsc.kr(lfoRate);
		var fA = freq * (1 + (lfo * lfoToPitch * 0.06));
		var fB = fA * (2 ** (detune / 1200));
		var pw = (pulseWidth + (lfo * lfoToPW * 0.4)).clip(0.05, 0.95);
		var wave = { |f| SelectX.ar(oscShape * 2, [VarSaw.ar(f, 0, 0.5), Saw.ar(f), Pulse.ar(f, pw)]) };
		// GRIT stage 1 — cross-FM: osc B modulates osc A into inharmonic, metallic territory
		var modB = SinOsc.ar(fB) * fmAmt * fA * 3;
		var oscA = wave.((fA + modB).clip(20, 12000)), oscB = wave.(fB);
		var sub = Pulse.ar(fA * 0.5, 0.5) * subLevel;
		// GRIT stage 2 — crackle/dust on top of the noise source
		var noise = WhiteNoise.ar(noiseLevel) + (Dust2.ar((2000 * grit).max(1)) * grit * 0.7);
		var mix = ((oscA + oscB) * 0.5) + sub + noise;
		var fenv = EnvGen.ar(Env.adsr(fAtk, fDec, fSus, fRel), gate);
		var aenv = EnvGen.ar(Env.adsr(aAtk, aDec, aSus, aRel), gate);
		var fc = (cutoff * (2 ** ((filterEnvAmt * fenv * 4) + (lfo * lfoToCutoff * 2)))).clip(20, 18000);
		var filt, sig, cho, bits, lv, dsr;
		mix = XFade2.ar(mix, oscA * oscB * 2, (ringMod * 2 - 1));
		// GRIT stage 3 — WAVEFOLDER before the filter: reflected harmonics, Buchla-ish bite
		mix = XFade2.ar(mix, (mix * (1 + (fold * 10))).fold2(1) * 0.7, (fold.clip(0, 1) * 2 - 1));
		filt = Select.ar(lpType.clip(0, 1), [
			RLPF.ar(mix, fc, (1 - (resonance * 0.95)).max(0.05)),
			MoogFF.ar(mix, fc, (resonance * 4).clip(0, 3.95))]);
		// GRIT stage 4 — harder, ASYMMETRIC drive (bias -> even harmonics, not just tanh fizz)
		sig = filt * (1 + (drive * 14));
		sig = (sig + (drive * 0.3)).tanh;
		sig = sig / (1 + (drive * 2.2));
		// GRIT stage 5 — digital: bit-crush + sample-rate reduction
		bits = (16 - (crush * 13)).clip(3, 16);
		lv = 2 ** bits;
		sig = XFade2.ar(sig, (sig * lv).round / lv, (crush.clip(0, 1) * 2 - 1));
		dsr = (SampleRate.ir / (1 + (downsample * 80))).clip(800, SampleRate.ir);
		sig = XFade2.ar(sig, Latch.ar(sig, Impulse.ar(dsr)), (downsample.clip(0, 1) * 2 - 1));
		sig = sig * aenv * (1 - (lfoToAmp * (lfo * 0.5 + 0.5)));
		cho = Mix(DelayC.ar(sig, 0.06, LFNoise2.kr([0.5, 0.7]).range(0.004, 0.02))) * 0.7;
		sig = XFade2.ar(sig, cho, (chorus * 2 - 1)) * amp * v;
		Line.kr(0, 1, glen + aRel.clip(0.001, 8) + 0.15, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(LeakDC.ar(sig), pan)));
	}).add;

	// ================= RINGS (Mutable Instruments resonator, gate-triggered) =====
	// One pluck per step (internal exciter fired by an Impulse at synth birth);
	// note -> pitch, damp controls the ring; self-frees after its decay. Requires the
	// MiRings UGen (mi-UGens); fails LOUDLY at build if absent — intended, no fallback.
		// RINGS: Mutable Instruments modal/string resonator (MiRings), ported faithfully
		// from wildrider. ONE strike per step (the sequencer drives timing — no internal
		// drift clock), but otherwise authentic: internal exciter, STEREO out, 2-voice
		// poly for real resonance, and NO perc envelope to choke the natural ring — the
		// resonator's own `damp` sets the decay, we only fade in/out to avoid clicks.
		SynthDef(\phRings, { |out = 16, note = 48, vel = 1,
			struct = 0.25, bright = 0.5, damp = 0.7, pos = 0.25, model = 0,
			decay = 1.2, amp = 0.9, pan = 0|
			var v = vel.clip(0, 2).max(0.03);
			var life = decay.clip(0.1, 12);
			var trig = Impulse.kr(0);                          // single strike on note-on
			var pitS = note.clip(24, 108);
			// MiRings: in, trig, pit, struct, bright, damp, pos, model, poly, intern_exc, easteregg, bypass
			var sig = MiRings.ar(Silent.ar(1), trig, pitS, struct.clip(0, 1),
				bright.clip(0, 1), damp.clip(0, 1), pos.clip(0, 1), model, 2, 1, 0, 0);
			// MiRings' 2 outputs are odd/even resonator taps, NOT a balanced L/R pair — so
			// panning them with Balance2 is broken (leans right, vanishes hard-left). Sum to
			// mono, then Pan2 exactly like every other voice: full-field, equal-power, robust.
			var mono = sig.sum * 0.5;
			// shell only: 4ms fade-in, hold (resonator rings on its own via `damp`), then a
			// long gentle release so the tail dies away naturally instead of being cut.
			var rel = 0.8;
			var aEnv = EnvGen.ar(Env([0, 1, 1, 0], [0.004, life, rel], [0, 0, -3]));
			var s = LeakDC.ar(mono) * aEnv * v * amp * 0.9;
			Line.kr(0, 1, life + rel + 0.15, doneAction: 2);
			Out.ar(out, ~killbad.(~spread.(s, pan)));   // Pan2 mono -> stereo; robust, live-settable pan
		}).add;

	// ----- PLAITS: the real MiPlaits UGen (v7b1/mi-UGens) -------------------
	// Mutable Instruments Plaits — a 16-model macro-oscillator. Not a reconstruction:
	// this is the actual ported DSP, the same plugin family as MiRings above.
	//   MiPlaits.ar(pitch, engine, harm, timbre, morph, trigger, level,
	//               fm_mod, timb_mod, morph_mod, decay, lpg_colour, mul)
	// `pitch` is a MIDI note. `engine` selects the model (0-15) and completely changes
	// what harm/timbre/morph mean — hence the per-model targeting table in kits.py.
	// Triggering fires Plaits' own internal envelope + LPG (`decay`, `lpg_colour`),
	// which is exactly the per-hit behaviour PoundHard's voice model wants.
	SynthDef(\phPlaits, { |out = 16, note = 48, vel = 1,
		model = 0, harm = 0.5, timbre = 0.5, morph = 0.5,
		decay = 0.5, lpgColour = 0.5, aux = 0.0, amp = 0.5, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		// Plaits' internal decay is 0..1 -> roughly 0.1..4s depending on the model; give the
		// voice a lifetime that outlasts it so nothing is cut off, then self-free.
		var life = 0.3 + (decay.clip(0, 1) * 4.5);
		var trig = Impulse.ar(0);                     // one strike at spawn
		var sig = MiPlaits.ar(
			pitch: note.clip(0, 127),
			engine: model.round.clip(0, 15),
			harm: harm.clip(0, 1), timbre: timbre.clip(0, 1), morph: morph.clip(0, 1),
			trigger: trig,
			level: v.clip(0, 1),                      // LEVEL cv: velocity/accent into the VCA
			decay: decay.clip(0, 1), lpg_colour: lpgColour.clip(0, 1));
		// MiPlaits returns [OUT, AUX] — two DIFFERENT signals per model, NOT a stereo pair
		// (same trap as MiRings' odd/even taps). Blend them, then Pan2 like every other
		// voice. AUX is a genuine second voice of each model, so it's worth a knob.
		var mono = XFade2.ar(sig[0], sig[1], (aux.clip(0, 1) * 2) - 1);
		// PER-MODEL OUTPUT TRIM. Measured on-device (record each model, peak-analyse the
		// WAV): Plaits' models differ enormously in level — `string` peaked at 0.059 while
		// `chord`/`noise` hit 0.95, a ~16x spread. Without this the generator's per-category
		// mix decisions would be meaningless: a string voice would vanish under a chord.
		// Normalised toward a ~0.7 peak; the string boost is capped so a hot roll can't clip.
		var trim = Select.kr(model.round.clip(0, 15), [
			0.76, 0.99, 0.82, 1.54, 0.97, 1.01, 0.74, 1.77,
			0.78, 0.74, 1.25, 6.00, 1.29, 2.70, 1.44, 1.71]);
		var s = LeakDC.ar(mono) * trim * amp;
		Line.kr(0, 1, life, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(s, pan)));
	}).add;

	// ================= BEN — Benjolin (Rob Hordijk) chaotic generative voice ==========
	// Ported to follow the Benjolis SC engine's signal flow
	// (github.com/scazan/benjolis, after Alberto de Campo), adapted to PoundHard's
	// spawn-per-hit voice model (amp envelope + self-free).
	//
	// The RUNGLER is the machine: an 8-stage shift register clocked by osc2 and fed by
	// osc1's comparator. Its weighted 8-bit DAC (stage n weighted 1/2^(8-n)) is scaled to
	// a MIDI value and run through .midicps, giving a FREQUENCY that is then ADDED to both
	// oscillator frequencies and to the filter cutoff. That additive, midicps-scaled
	// feedback (not exponential modulation) is what gives the Benjolin its stepped,
	// self-patterning chaos.
	SynthDef(\phBen, { |out = 16, note = 48, vel = 1,
		freq2 = 4, scale = 1, rungler1 = 0.16, rungler2 = 0.0, runglerFilt = 9,
		filtFreq = 40, q = 0.82, filterType = 0, outSignal = 6, gain = 1,
		decay = 1.0, amp = 0.35, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var life = decay.clip(0.05, 12);
		var freq1 = note.clip(0, 127).midicps;          // the sequencer's note drives osc1
		var fb = LocalIn.ar(2);
		var rIn = fb[0];                                // last block's rungler (in Hz)
		// rungler ADDS to the oscillator frequencies
		var f1 = ((rIn * rungler1) + freq1).clip(0.01, 12000);
		var f2 = ((rIn * rungler2) + freq2).clip(0.01, 12000);
		var tri1 = LFTri.ar(f1), tri2 = LFTri.ar(f2);
		var osc1 = PulseDPW.ar(f1), osc2 = PulseDPW.ar(f2);
		var pwm = (tri1 + tri2) > 0;                    // the classic XOR-ish output
		var sh0 = (osc1 > 0.5);                         // comparator feeding the register
		var sh = Array.newClear(8);
		var prev = sh0;
		var dac = 0, rungler, ffreq, qq, filt, sig, aEnv;
		// 8-stage shift register, clocked by osc2. Delay1 makes each stage latch the
		// PREVIOUS stage's pre-clock value (without it every stage takes the same new bit).
		8.do { |i| sh[i] = Latch.ar(prev, osc2); prev = Delay1.ar(sh[i]) };
		// weighted binary DAC: the LAST stage weighs most (1/2), the first least (1/256)
		8.do { |i| dac = dac + (sh[i] / (2 ** (8 - i))) };
		rungler = (dac * scale.clip(0, 1).linlin(0, 1, 0, 127)).midicps;   // -> a frequency
		LocalOut.ar([rungler, DC.ar(0)]);
		ffreq = ((rungler * runglerFilt) + filtFreq).clip(20, 16000);      // cutoff: ADDITIVE
		qq = ((q.clip(0, 1) * -1) + 1).max(0.02);
		filt = Select.ar(filterType.clip(0, 3), [
			RLPF.ar(pwm, ffreq, qq),
			RHPF.ar(pwm, ffreq, qq),
			SVF.ar(pwm, ffreq, q.clip(0, 1)),
			DFM1.ar(pwm, ffreq, q.clip(0, 1))
		]);
		sig = Select.ar(outSignal.clip(0, 6), [tri1, osc1, tri2, osc2, pwm, sh0, filt]);
		sig = (sig * gain.max(0.01)).tanh;
		aEnv = EnvGen.ar(Env([0, 1, 1, 0], [0.004, (life - 0.12).max(0.02), 0.12], [0, 0, -3]));
		sig = LeakDC.ar(sig) * aEnv * v * amp;
		Line.kr(0, 1, life + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ----- NOIZEOP: faithful port of deeg's NoizeOp Norns engine ------------
	//   github.com/deeg-deeg-deeg/noizeop/blob/main/lib/Engine_NoizeOp.sc
	// Four sine oscillators combined through six nonlinear "algorithms" (products,
	// ratios, truncation, hypotenuse, sum-of-squares), mixed by weight, then run
	// through a hipass -> lowpass -> resonz filter bank. The divisions cross zero
	// constantly, so the output is spiky, glitchy, rhythmic noise — exactly the
	// point. The ONLY adaptation for PoundHard: the four oscillator frequencies are
	// note-relative RATIOS (osc freq = note.midicps * freqNN) so the sequencer can
	// transpose the whole cluster while keeping the ratios that give it its voice,
	// and a per-hit amp envelope replaces the original's continuous drone. Every
	// algo, mul, a_mod, a_vol, filter and Resonz is verbatim. Denominators get a
	// tiny 1e-9 bias (kills 0/0 = NaN, inaudible) and the algos are magnitude-
	// clamped so infinities never reach the DAC — the spikes stay, the NaNs don't.
	SynthDef(\phNoizeop, { |out = 16, note = 48, vel = 1,
		freq01 = 1.0, freq02 = 1.5, freq03 = 2.0, freq04 = 3.0,
		mul01 = 1, mul02 = 1, mul03 = 1, mul04 = 1,
		a_mod_01 = 1, a_mod_02 = 1, a_mod_03 = 0.02, a_mod_04 = 1, a_mod_05 = 1, a_mod_06 = 1,
		a_vol_01 = 0.5, a_vol_02 = 0.5, a_vol_03 = 0.5, a_vol_04 = 0.5, a_vol_05 = 0.5, a_vol_06 = 0.5,
		ffreq01 = 40, ffreq02 = 12000, ffreq03 = 1200, q01 = 1, q02 = 1, q03 = 1,
		gain = 1, decay = 1.0, amp = 0.5, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var life = decay.clip(0.05, 12);
		var base = note.clip(0, 127).midicps;                    // note transposes the cluster
		var f01 = (base * freq01).clip(0.001, 18000);
		var f02 = (base * freq02).clip(0.001, 18000);
		var f03 = (base * freq03).clip(0.001, 18000);
		var f04 = (base * freq04).clip(0.001, 18000);
		var osc01 = SinOsc.ar(f01, 0, mul01, 0);
		var osc02 = SinOsc.ar(f02, 0, mul02, 0);
		var osc03 = SinOsc.ar(f03, 0, mul03, 0);
		var osc04 = SinOsc.ar(f04, 0, mul04, 0);
		// +1e-9 bias on each denominator: prevents exact 0/0 (= NaN); inaudible.
		var algo01, algo02, algo03, algo04, algo05, algo06, combo, sig, aEnv;
		algo01 = ((osc01 * osc02) / ((osc03 * osc04) + 1e-9)) / a_mod_01.max(1e-3);
		algo02 = ((osc02 * osc04) / ((osc03 - osc01) + 1e-9)) / a_mod_02.max(1e-3);
		algo03 = ((osc01 + osc02) - (osc03 + osc04)).trunc(a_mod_03.max(1e-4));
		// clamp the first three before they multiply, so the product stays finite
		algo01 = algo01.clip2(50); algo02 = algo02.clip2(50); algo03 = algo03.clip2(50);
		// original does (algo01*algo02*algo03).sqrt; the product goes negative
		// constantly (sqrt -> NaN there), so take the magnitude — same envelope.
		algo04 = ((algo01 * algo02 * algo03).abs.sqrt) / a_mod_04.max(1e-3);
		algo05 = (hypot(osc01, osc02) + hypot(osc03, osc04)) * a_mod_05;
		algo06 = ((osc01 ** 2) + (osc02 ** 2) + (osc03 ** 2) + (osc04 ** 2)) * a_mod_06;
		combo = (algo01 * a_vol_01) + (algo02 * a_vol_02) + (algo03 * a_vol_03)
		      + (algo04 * a_vol_04) + (algo05 * a_vol_05) + (algo06 * a_vol_06);
		combo = combo.clip2(20);
		// verbatim filter bank: BHiPass4 -> BLowPass4 -> Resonz
		sig = BLowPass4.ar(BHiPass4.ar(combo, ffreq01.clip(20, 18000), q01, 1, 0),
			ffreq02.clip(20, 18000), q02, 1, 0);
		sig = Resonz.ar(sig, ffreq03.clip(20, 18000), q03, 1.0, 0.0);
		sig = (sig * gain.max(0.01)).tanh;
		aEnv = EnvGen.ar(Env([0, 1, 1, 0], [0.004, (life - 0.12).max(0.02), 0.12], [0, 0, -3]));
		sig = LeakDC.ar(sig) * aEnv * v * amp;
		Line.kr(0, 1, life + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ----- ICARUS: faithful port of schollz's Icarus Norns engine -----------
	//   github.com/schollz/icarus/blob/main/lib/Engine_Icarus.sc
	// A "dreamcrusher" pad/drone: a VarSaw main oscillator + a Pulse sub, both with
	// LFO-modulated PWM and slow randomized detune, run into a feedback delay network
	// (OnePole tilt -> Rotate2 -> DelayC -> softclip), a MoogLadder low-pass, and a
	// Dust-gated "destruction" dropout. The whole chain and its constants are the
	// engine's own. Adaptation for PoundHard's spawn-per-hit model: the original is
	// gate-driven (envgate on/off); here the note fires a one-shot cubic AR envelope
	// (attack -> decay-to-sustain -> release) whose length is set by `decay`+`release`,
	// so long values give the sustained drones/pads it's made for, and the voice
	// self-frees. `hz` comes from the played note.
	SynthDef(\phIcarus, { |out = 16, note = 48, vel = 1,
		subpitch = 1, sublevel = 0.3, detuning = 0.1, portamento = 0.1,
		pwmcenter = 0.5, pwmwidth = 0.05, pwmfreq = 10,
		lpf = 6000, resonance = 0.2, feedback = 0.5, delaytime = 0.25, destruction = 0,
		attack = 0.02, decay = 1.0, release = 1.5, sustain = 0.8,
		gain = 1, amp = 0.5, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var hz = note.clip(0, 127).midicps;
		var life = attack + decay + release + 0.3;
		var ender, in, subdiv, hzd, hzs, ampcheck, local, snd;
		// one-shot cubic envelope (no gate): rise -> fall to sustain -> release to 0
		ender = EnvGen.ar(Env.new(
			curve: 'cubed', levels: [0, 1, sustain, 0],
			times: [attack + 0.015, decay, release]));
		// main VarSaw with LFO PWM + slow randomized detune (dreamcrusher)
		hzd = (Lag.kr(hz + (SinOsc.kr(LFNoise0.kr(1)) * (((hz.cpsmidi + 1).midicps) - hz) * detuning), portamento).cpsmidi).midicps;
		in = VarSaw.ar(hzd, width: LFTri.kr(pwmfreq + Rand(0.1, 0.3), mul: pwmwidth / 2, add: pwmcenter), mul: 0.5);
		// sub-oscillator (Pulse), subpitch octaves below
		subdiv = 2 ** subpitch;
		hzs = (Lag.kr((hz / subdiv) + (SinOsc.kr(LFNoise0.kr(1)) * ((((hz / subdiv).cpsmidi + 1).midicps) - (hz / subdiv)) * detuning), portamento).cpsmidi).midicps;
		in = in + Pulse.ar(hzs, width: LFTri.kr(pwmfreq + Rand(0.1, 0.3), mul: pwmwidth / 2, add: pwmcenter), mul: 0.5 * sublevel);
		in = Splay.ar(in);
		in = Balance2.ar(in[0], in[1], SinOsc.kr(LinLin.kr(LFNoise0.kr(0.1), -1, 1, 0.05, 0.2)) * 0.1);
		in = in * ender;
		ampcheck = Amplitude.kr(Mix.ar(in));
		in = in * (ampcheck > 0.02);                               // noise gate
		// feedback delay network
		local = LocalIn.ar(2);
		local = OnePole.ar(local, 0.4);
		local = OnePole.ar(local, -0.08);
		local = Rotate2.ar(local[0], local[1], 0.2);
		local = DelayC.ar(local, 0.5, Lag.kr(delaytime, 0.2));
		local = LeakDC.ar(local);
		local = ((local + in) * 1.25).softclip;
		local = MoogLadder.ar(local, Lag.kr(lpf.clip(20, 18000), 1), res: Lag.kr(resonance.clip(0, 1), 1));
		// Dust-gated dropouts ("destruction")
		local = ((local * (1 - EnvGen.kr(Env([0, 1, 0], [0.1, 0.1], curve: \sine), gate: Dust.kr(destruction)))) + local) / 2;
		LocalOut.ar(local * Lag.kr(feedback.clip(0, 0.98), 1));
		snd = Balance2.ar(local[0] * 0.2, local[1] * 0.2, SinOsc.kr(LinLin.kr(LFNoise0.kr(0.1), -1, 1, 0.05, 0.2)) * 0.1);
		snd = Mix.ar([Pan2.ar(snd[0], -1 + (2 * pan.clip(-1, 1)), 1), Pan2.ar(snd[1], 1 + (2 * pan.clip(-1, 1)), 1)]);
		snd = snd * v * amp * gain.max(0.01);
		Line.kr(0, 1, life, doneAction: 2);
		Out.ar(out, ~killbad.(snd));
	}).add;

	// ================= SHAKER — STK Shakers (sc3-plugins), self-freeing ==============
	// STK's stochastic shaker/scraper models (maraca, cabasa, sekere, guiro, tambourine,
	// sleigh bells, bamboo chimes, sand...): `instr` picks the model; energy/decay/objects/
	// resfreq shape the gesture. Energy is enveloped so each hit is ONE shake that decays;
	// the note shifts the resonance so the sequencer tilts the shaker brighter/darker.
	SynthDef(\phShaker, { |out = 16, note = 60, vel = 1,
		instr = 0, energy = 90, decay = 70, objects = 40, resfreq = 64,
		atk = 0.001, dec = 0.35, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var eEnv = EnvGen.kr(Env.perc(0.001, dec.clip(0.02, 3), 1, -4));
		var aEnv = EnvGen.ar(Env.perc(atk.clip(0.0002, 0.2), (dec * 1.5).clip(0.02, 4), 1, -3));
		var rf = (resfreq + (note - 60)).clip(0, 128);
		var sig = StkShakers.ar(instr.round.clip(0, 22), (energy * eEnv).clip(0, 128),
			decay.clip(0, 128), objects.clip(0, 128), rf);
		sig = sig * aEnv * v * amp * 4.5;    // STK Shakers output is low — bring it up to engine level
		Line.kr(0, 1, atk + (dec * 1.5) + 0.3, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(LeakDC.ar(sig), pan)));
	}).add;

	// ================= MEMBRANE — 2D waveguide struck membrane (sc3-plugins) =========
	// MembraneCircle: a struck circular membrane (toms, frame drums, gongs, warped skins).
	// A short filtered-noise STRIKE excites the mesh; `tension` sets pitch/character, `loss`
	// the ring time. The note shifts tension so the sequencer tunes the drum. Frees on
	// silence (the membrane's own decay), with a hard time cap for safety.
	SynthDef(\phMembrane, { |out = 16, note = 48, vel = 1,
		tension = 0.05, loss = 0.9995, tone = 0.5, strike = 0.5, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var sEnv = EnvGen.ar(Env.perc(0.0002, (0.002 + (strike * 0.03)).clip(0.001, 0.08), 1, -6));
		var exc = LPF.ar(WhiteNoise.ar, tone.clip(0, 1).linexp(0, 1, 600, 9000)) * sEnv * (0.4 + (v * 0.6));
		var tns = (tension * (2 ** ((note.clip(24, 96) - 48) / 24))).clip(0.004, 0.22);
		var sig = MembraneCircle.ar(exc, tns, loss.clip(0.9, 0.99998));
		sig = LeakDC.ar(sig) * v * amp * 2.0;
		DetectSilence.ar(sig, 0.0003, 0.15, doneAction: 2);
		Line.kr(0, 1, 8.0, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= MALLET — STK ModalBar (sc3-plugins), self-freeing ============
	// Struck modal bars: marimba, vibraphone, agogo, wood, reso, beats. `instrument` picks
	// the model; the note tunes it (freq in Hz). One strike at spawn; a perc amp env sets
	// how long it rings (short = damped mallet, long = ringing vibraphone). Frees on silence.
	SynthDef(\phMallet, { |out = 16, note = 60, vel = 1,
		instrument = 0, stickhardness = 64, stickposition = 28, vibratogain = 8,
		vibratofreq = 20, directmix = 40, decay = 1.0, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var f0 = note.clip(0, 127).midicps.clip(20, 8000);
		var sig = StkModalBar.ar(f0, instrument.round.clip(0, 8), stickhardness.clip(0, 128),
			stickposition.clip(0, 128), vibratogain.clip(0, 128), vibratofreq.clip(0, 128),
			directmix.clip(0, 128), 110, Impulse.ar(0));
		var aEnv = EnvGen.ar(Env.perc(0.001, decay.clip(0.05, 6), 1, -3));
		sig = LeakDC.ar(sig) * aEnv * v * amp * 4.0;
		DetectSilence.ar(sig, 0.0003, 0.1, doneAction: 2);
		Line.kr(0, 1, decay.clip(0.05, 6) + 1.0, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= BOWED — STK BandedWG (sc3-plugins), self-freeing =============
	// Banded waveguide: uniform/tuned bar, glass harmonica, Tibetan bowl — struck or bowed
	// metal/glass. `instr` picks the model; note tunes it. `striking` toggles struck vs bowed.
	SynthDef(\phBowed, { |out = 16, note = 60, vel = 1,
		instr = 0, bowpressure = 70, bowmotion = 30, integration = 0, modalresonance = 90,
		bowvelocity = 80, striking = 0, decay = 1.5, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var f0 = note.clip(0, 127).midicps.clip(20, 7000);
		var sig = StkBandedWG.ar(f0, instr.round.clip(0, 3), bowpressure.clip(0, 128),
			bowmotion.clip(0, 128), integration.round.clip(0, 1), modalresonance.clip(0, 128),
			bowvelocity.clip(0, 128), striking.round.clip(0, 1), Impulse.ar(0));
		var aEnv = EnvGen.ar(Env.perc(0.005, decay.clip(0.05, 8), 1, -3));
		sig = LeakDC.ar(sig) * aEnv * v * amp * 4.0;
		DetectSilence.ar(sig, 0.0003, 0.12, doneAction: 2);
		Line.kr(0, 1, decay.clip(0.05, 8) + 1.5, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= PLUCK — DWG plucked stiff string (sc3-plugins), self-freeing =====
	// A digital-waveguide plucked string with stiffness (inharmonic) — koto / clav / harp /
	// muted-string plucks. A short noise burst excites the string; pos/decay/damp/bright
	// shape it. Note tunes it (freq in Hz). Frees on silence.
	SynthDef(\phPluck, { |out = 16, note = 60, vel = 1,
		pos = 0.14, decay = 1.0, damp = 30, bright = 0.5, excite = 0.008, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var f0 = note.clip(0, 127).midicps.clip(20, 6000);
		var exc = WhiteNoise.ar * EnvGen.ar(Env.perc(0.0005, excite.clip(0.001, 0.05), 1, -4)) * (0.5 + (v * 0.5));
		var c1 = (1.0 / decay.clip(0.05, 8)).clip(0.1, 30);   // loop decay: lower = longer sustain
		var sig = DWGPluckedStiff.ar(f0, 1.0, 1, pos.clip(0.02, 0.5), c1, damp.clip(1, 80),
			exc, 0.1, bright.clip(0, 1) * 6);
		sig = LeakDC.ar(sig) * v * amp * 1.5;
		DetectSilence.ar(sig, 0.0003, 0.1, doneAction: 2);
		Line.kr(0, 1, decay.clip(0.05, 8) + 2.0, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= TUBE — TwoTube waveguide (sc3-plugins), self-freeing =============
	// A two-tube (vocal-tract-ish) waveguide: hollow, formant plucks and reedy tones. Tube
	// lengths (set from the note) fix the resonance; `k` is the junction, `balance` splits the
	// two tube lengths. A short burst excites it.
	SynthDef(\phTube, { |out = 16, note = 60, vel = 1,
		k = 0.01, loss = 0.99, balance = 0.5, excite = 0.01, decay = 1.0, amp = 0.9, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var f0 = note.clip(0, 127).midicps.clip(30, 4000);
		var totLen = (SampleRate.ir / (2 * f0)).clip(4, 2000);
		var bal = balance.clip(0.1, 0.9);
		var d1 = (totLen * bal).clip(2, 1500);
		var d2 = (totLen * (1 - bal)).clip(2, 1500);
		var exc = (WhiteNoise.ar + Impulse.ar(0)) * EnvGen.ar(Env.perc(0.0005, excite.clip(0.001, 0.08), 1, -4)) * (0.5 + (v * 0.5));
		var aEnv = EnvGen.ar(Env.perc(0.002, decay.clip(0.05, 6), 1, -3));
		var sig = TwoTube.ar(exc, k.clip(0.001, 0.2), loss.clip(0.9, 1.0), d1, d2);
		sig = LeakDC.ar(sig) * aEnv * v * amp * 1.5;
		DetectSilence.ar(sig, 0.0003, 0.12, doneAction: 2);
		Line.kr(0, 1, decay.clip(0.05, 6) + 1.5, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= CHAOS — chaotic-map oscillator (core UGens), self-freeing =========
	// A voice built from SuperCollider's audio-rate CHAOS generators (feedback sine + iterated
	// maps). `type` selects the map; the note sets the iteration frequency, chaosA/chaosB steer
	// the attractor (from tone to noise), plus a wavefolder and resonant filter. Glitch/noise
	// in the spirit of BEN and NOIZEOP, from core UGens (no plugin).
	SynthDef(\phChaos, { |out = 16, note = 48, vel = 1,
		type = 0, chaosA = 1.1, chaosB = 0.5, fold = 0.0, cutoff = 6000, res = 0.2,
		attack = 0.003, decay = 0.5, ampCurve = -4, amp = 0.55, pan = 0|
		var v = vel.clip(0, 2).max(0.03);
		var f0 = note.clip(0, 127).midicps.clip(20, 8000);
		var aEnv = EnvGen.ar(Env.perc(attack.clip(0.0005, 2), decay.clip(0.01, 8), 1, ampCurve.clip(-8, -1)));
		var srcs = [
			FBSineC.ar(f0 * 2, chaosA.clip(0.1, 4), chaosB.clip(0, 3), 1.0, 0.5),
			LatoocarfianC.ar(f0, chaosA.linlin(0, 4, -3, 3), chaosB.linlin(0, 3, 0.5, 1.5), 1.5, 0.5),
			HenonC.ar(f0, chaosA.linlin(0, 4, 1.0, 1.4), chaosB.linlin(0, 3, 0.2, 0.4)),
			StandardL.ar(f0, chaosA.linlin(0, 4, 0.3, 3.0)),
			CuspL.ar(f0, chaosA.linlin(0, 4, 0.9, 1.2), chaosB.linlin(0, 3, 1.7, 2.0))
		];
		var sig = Select.ar(type.round.clip(0, 4), srcs).tanh;
		sig = SelectX.ar(fold.clip(0, 1), [sig, (sig * (1 + (fold * 4))).fold2(1)]);
		sig = RLPF.ar(sig, cutoff.clip(40, 16000), (1 - (res.clip(0, 1) * 0.9)).clip(0.05, 1));
		sig = LeakDC.ar(sig) * aEnv * v * amp * 2.8;   // chaotic maps have low RMS — bring up
		Line.kr(0, 1, attack.clip(0.0005, 2) + decay.clip(0.01, 8) + 0.2, doneAction: 2);
		Out.ar(out, ~killbad.(~spread.(sig, pan)));
	}).add;

	// ================= FX (per-track insert chain) =================
	// Each FX reads its track bus (`in`), processes, and REPLACES the bus (`out`
	// == `in`) — so a track's FX run in place, in canonical chain order. Stereo.
	// Dry/wet is equal-power (XFade2 on wet*2-1); bypass hard-crossfades to dry.
	~panOut = { |sig, pan| Balance2.ar(sig[0], sig[1], pan.clip(-1, 1)) };
	// Pedalboard insert wrapper — STEREO (processes both channels), so the track's
	// pan is preserved through the FX. `y` is a stereo signal, not a mono sum.
	~fxOut = { |dry, y, amp, enable, wet, bypass|
		var w = LeakDC.ar(y) * amp * enable;
		~killbad.(XFade2.ar(dry, w, (wet * 2 - 1)) * (1 - bypass) + (dry * bypass));
	};

	// per-track send: track bus -> master bus (summed)
	SynthDef(\phSend, { |in = 16, out = 16| Out.ar(out, In.ar(in, 2)) }).add;

	// LIVING-STEP FX send: a fired living step routes its hit here. Stereo feedback delay
	// into FreeVerb2 (both core UGens — no plugin dependency), summed into master. Only the
	// fired hit is routed here, so it never bleeds onto other steps. Params are set live per
	// fire (dMix/vMix pick delay-heavy vs reverb-heavy). Dry passes through so the hit stays
	// present; the delay echoes + reverb tail ring out on the shared bus.
	SynthDef(\phLivingFx, { |in = 16, out = 16,
		dTime = 0.25, dFb = 0.35, dMix = 0.4, vMix = 0.35, vRoom = 0.72, vDamp = 0.4|
		var dry = In.ar(in, 2);
		var fb = LocalIn.ar(2);
		var d = DelayC.ar(dry + (fb * dFb.clip(0, 0.85)), 1.0, dTime.clip(0.02, 0.9));
		var delayed = LeakDC.ar(d);
		var wet, verb, sig;
		LocalOut.ar(delayed);
		wet = dry + (delayed * dMix.clip(0, 1));                 // dry + delay echoes
		verb = FreeVerb2.ar(wet[0], wet[1], vMix.clip(0, 1), vRoom.clip(0, 1), vDamp.clip(0, 1));
		Out.ar(out, ~killbad.(verb));
	}).add;

	// RECORDER: stream the FINAL master output (hardware bus 0, post-limiter) to a
	// stereo WAV via DiskOut. Runs after the master node so it captures what's heard.
	SynthDef(\phRec, { |buf = 0| DiskOut.ar(buf, In.ar(0, 2)) }).add;

	// LEVEL MONITOR: reports the master output amplitude while a take is recording. The
	// controller watches it to decide when a take's tail has died away (so reverb/delay
	// tails are captured before the file is closed).
	SynthDef(\phAmp, {
		var sig = Mix(In.ar(0, 2)) * 0.5;
		SendReply.kr(Impulse.kr(10), '/ph/amprep', Amplitude.kr(sig, 0.01, 0.25));
	}).add;

	// ---- OVERDRIVE: tilt EQ -> asymmetric drive -> WAVEFOLDER -> hard-clip grit (stereo).
	// Not a polite tube sim: bias adds even harmonics, the folder reflects peaks back for
	// Buchla-ish metallic bite, and the grit stage hard-clips for fizz/breakup.
	SynthDef(\phOverdrive, { |out = 0, in = 0, drive = 4, tone = 0, fold = 0, bias = 0, grit = 0,
		shape = 0, glitch = 0, glitchfreq = 1200,
		amp = 0.8, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2), y;
		y = BHiShelf.ar(dry, 1500, 1.0, tone * 9);
		y = BLowShelf.ar(y, 220, 1.0, tone.neg * 6);
		y = y * drive.max(0.01);
		y = (y + bias).tanh;                                                     // asymmetry -> even harmonics
		y = XFade2.ar(y, (y * (1 + (fold * 9))).fold2(1) * 0.8, (fold.clip(0, 1) * 2 - 1));
		y = XFade2.ar(y, (y * (1 + (grit * 6))).clip2(0.6) * 1.25, (grit.clip(0, 1) * 2 - 1));
		// SineShaper: sinusoidal waveshaping fold (lower limit = harder)
		y = XFade2.ar(y, SineShaper.ar(y, (1 - (shape.clip(0, 1) * 0.9)).clip(0.1, 1)), (shape.clip(0, 1) * 2 - 1));
		// GlitchRHPF: glitchy resonant highpass (low rq = screaming resonance)
		y = XFade2.ar(y, GlitchRHPF.ar(y, glitchfreq.clip(60, 12000), (1 - (glitch.clip(0, 1) * 0.9)).clip(0.05, 1)), (glitch.clip(0, 1) * 2 - 1));
		y = LeakDC.ar(y) / (1 + (drive * 0.10));                                 // level compensation
		ReplaceOut.ar(out, ~fxOut.(dry, y, amp, enable, wet, bypass));
	}).add;

	// ---- AMPSIM: preamp dist + 3-band + cab roll-off (stereo) ----
	SynthDef(\phAmpsim, { |out = 0, in = 0, gain = 6, bass = 0, mid = 0, treble = 0, amp = 0.8, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2), y;
		y = (dry * gain.max(0.01)).tanh;
		y = BLowShelf.ar(y, 120, 1.0, bass);
		y = BPeakEQ.ar(y, 750, 0.8, mid);
		y = BHiShelf.ar(y, 3000, 1.0, treble);
		y = LPF.ar(y, 5500);
		ReplaceOut.ar(out, ~fxOut.(dry, y, amp, enable, wet, bypass));
	}).add;

	// ---- DEGRADE: sample-rate crush + waveform-dropout + probabilistic mangle (sc3-plugins) ----
	// Three glitch/lo-fi stages in series: SmoothDecimator (anti-aliased rate crush),
	// WaveLoss (deletes `drop`-of-`outof` waveform segments — stutter/aliasing artifacts),
	// and Disintegrator (probabilistically mangles samples). The IDM degrade unit.
	SynthDef(\phBitcrusher, { |out = 0, in = 0, rate = 12000, smooth = 0.5, drop = 6, outof = 40, prob = 0.0, mult = 0.0, amp = 0.9, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2), y;
		y = SmoothDecimator.ar(dry, rate.clip(400, 44100), smooth.clip(0, 1));
		y = WaveLoss.ar(y, drop.clip(0, 60).round, outof.clip(1, 60).round.max(1), 1);
		y = Select.ar(prob > 0.001, [y, Disintegrator.ar(y, prob.clip(0, 1), mult.clip(0, 1))]);
		ReplaceOut.ar(out, ~fxOut.(dry, y, amp, enable, wet, bypass));
	}).add;

	// ---- RING: DiodeRingMod — analog diode ring modulator (sc3-plugins) ----
	// Gnarlier and more metallic than a clean multiply: asymmetric diode shaping produces
	// extra sidebands. `drive` pushes the carrier harder into the diodes for more bite.
	SynthDef(\phRingmod, { |out = 0, in = 0, freq = 200, drive = 1.0, amp = 0.9, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2);
		var modOsc = SinOsc.ar(freq.clip(0.1, 12000));
		var d = drive.clip(0.1, 6);
		var y = [DiodeRingMod.ar(dry[0] * d, modOsc), DiodeRingMod.ar(dry[1] * d, modOsc)];
		ReplaceOut.ar(out, ~fxOut.(dry, y, amp, enable, wet, bypass));
	}).add;

	// ---- FLANGER: LFO-swept short delay + feedback (stereo) ----
	SynthDef(\phFlanger, { |out = 0, in = 0, rate = 0.3, depth = 0.6, feedback = 0.4, amp = 1, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2), lfo, dt, fb, y;
		lfo = SinOsc.kr(rate, 0, 0.5, 0.5);
		dt = (0.0006 + (depth * 0.006 * lfo)).clip(0.0001, 0.02);
		fb = LocalIn.ar(2);
		y = DelayC.ar(dry + (fb * feedback.clip(0, 0.95)), 0.02, dt);
		LocalOut.ar(~killbad.(y));
		ReplaceOut.ar(out, ~fxOut.(dry, y, amp, enable, wet, bypass));
	}).add;

	// ---- SDLY: stereo ping-pong delay (true stereo) ----
	// ---- DLY: Greyhole — diffuse, pitch-modulated feedback delay/reverb (sc3-plugins) ----
	// A dark, smeary delay that blurs toward reverb as diffusion/size rise — the
	// characterful IDM space-maker (after ValhallaDSP's Greyhole).
	SynthDef(\phGreyhole, { |out = 0, in = 0, dTime = 0.28, damp = 0.4, size = 1.6, diff = 0.7, feedback = 0.4, modDepth = 0.1, modFreq = 2.0, width = 1.0, amp = 1, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2), inL = dry[0], inR = dry[1];
		var g = Greyhole.ar(dry, dTime.clip(0.01, 4), damp.clip(0, 1), size.clip(0.5, 5),
			diff.clip(0, 1), feedback.clip(0, 1), modDepth.clip(0, 1), modFreq.clip(0, 10)) * enable;
		var wL = g[0], wR = g[1];
		var mid = (wL + wR) * 0.5, side = (wL - wR) * 0.5 * width;
		var wetL = (mid + side) * amp, wetR = (mid - side) * amp, outSig;
		outSig = [XFade2.ar(inL, wetL, wet * 2 - 1), XFade2.ar(inR, wetR, wet * 2 - 1)];
		ReplaceOut.ar(out, ~killbad.(~panOut.((outSig * (1 - bypass)) + (dry * bypass), pan)));
	}).add;

	// ---- VERB: JPverb algorithmic reverb (needs sc3-plugins) ----
	SynthDef(\phVerb, { |out = 0, in = 0, size = 2.2, decay = 5, damp = 0.3, modDepth = 0.2, modFreq = 2, earlyDiff = 0.7, lowCut = 180, highCut = 9000, width = 1, amp = 1, pan = 0, bypass = 0, wet = 0.5, enable = 1, freeze = 0|
		var dry = In.ar(in, 2), inL = dry[0], inR = dry[1];
		var t60 = Select.kr(freeze, [decay, 240]);
		var rev = JPverb.ar([inL, inR], t60, damp, size, earlyDiff, modDepth, modFreq, 1.0, 1.0, 1.0, lowCut, highCut) * enable;
		var wL = rev[0], wR = rev[1];
		var mid = (wL + wR) * 0.5, side = (wL - wR) * 0.5 * width;
		var wetL = (mid + side) * amp, wetR = (mid - side) * amp, outSig;
		outSig = [XFade2.ar(inL, wetL, wet * 2 - 1), XFade2.ar(inR, wetR, wet * 2 - 1)];
		ReplaceOut.ar(out, ~killbad.(~panOut.((outSig * (1 - bypass)) + (dry * bypass), pan)));
	}).add;

	// ---- CLOUDS: Mutable Instruments Clouds granular texture processor (mi-UGens) ----
	// A live granular cloud over the track bus: grain size/density/texture/position, stereo
	// spread, an internal reverb and feedback, plus a pitch shift and a freeze. `mode`
	// selects Clouds' engines (0 granular, 1 pitch-shifter, 2 looping delay, 3 spectral).
	SynthDef(\phClouds, { |out = 0, in = 0, pit = 0, pos = 0.5, size = 0.35, dens = 0.4, tex = 0.5, spread = 0.6, rvb = 0.2, fb = 0.0, freeze = 0, mode = 0, lofi = 0, amp = 1, pan = 0, bypass = 0, wet = 0.5, enable = 1|
		var dry = In.ar(in, 2);
		// drywet=1: Clouds returns full wet; we manage dry/wet ourselves with `wet`.
		var g = MiClouds.ar(dry, pit.clip(-36, 36), pos.clip(0, 1), size.clip(0, 1), dens.clip(0, 1),
			tex.clip(0, 1), 1.0, 1.0, spread.clip(0, 1), rvb.clip(0, 1), fb.clip(0, 1),
			freeze, mode.round.clip(0, 3), lofi.round.clip(0, 1)) * enable;
		var wL = g[0] * amp, wR = g[1] * amp, outSig;
		outSig = [XFade2.ar(dry[0], wL, wet * 2 - 1), XFade2.ar(dry[1], wR, wet * 2 - 1)];
		ReplaceOut.ar(out, ~killbad.(~panOut.((outSig * (1 - bypass)) + (dry * bypass), pan)));
	}).add;
};
