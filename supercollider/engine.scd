// PoundHard — SC engine: 16-track voice host + step clock + OSC dispatch.
//
// The Python controller is authoritative for musical state (kits, patterns,
// mutes, tempo) and pushes it here over OSC (/ph/...). This engine realises it:
//   * per-step it SPAWNS a fresh one-shot voice synth for each active, unmuted
//     track (the synth frees itself on silence) — so idle tracks cost no CPU,
//     which is what keeps the Move's ARM from XRun-freezing
//   * a TempoClock step routine drives the timing
//   * telemetry back to the controller: /ph/ready (once), /ph/step, /ph/cpu
//
// Node order: gClear (zero master bus) -> gVoices (spawned voices Out.ar +=) ->
// gMaster (limiter -> hardware out). Private buses aren't auto-zeroed -> gClear.
(
~ctrlHost = "CONTROLLER_HOST".getenv ? "127.0.0.1";
~ctrlPort = ("CONTROLLER_PORT".getenv ? "57140").asInteger;
~sampleDir = "SAMPLER_DIR".getenv ? "/data/samples";

~nTracks = 16;
~maxSteps = 32;
~typeDefs = [\phDrum, \phFm7, \phBuchloid, \phMolly, \phRings, \phBen, \phNoizeop, \phIcarus, \phPlaits, \phShaker, \phMembrane, \phMallet, \phBowed];  // /ph/track type index (-1 = empty/unassigned)
// DRUM is split into per-mode defs (chosen from the track's `mode` param at spawn).
~drumDefs = [\phDrumKick, \phDrumSnare, \phDrumHat, \phDrumMetal, \phDrumClap, \phDrumTom, \phDrumNoise];

~ctrl = NetAddr(~ctrlHost, ~ctrlPort);
~ready = false;

// ---- runtime state (mirror of the controller's authoritative state) ----
~nSteps    = 32;
~curStep   = -1;
~running   = false;
~bpm       = 120;
~stepsPerBeat = 4;                                   // 32 steps = 2 bars of 16ths
~trackType = Array.fill(~nTracks, { 0 });            // all DRUM by default
~pattern   = Array.fill(~nTracks, { Array.fill(~maxSteps, { 0 }) });
~mute      = Array.fill(~nTracks, { 0 });
~note      = Array.fill(~nTracks, { 40 });
~vel       = Array.fill(~nTracks, { 1.0 });
~length    = Array.fill(~nTracks, { 32 });     // per-track pattern length (polymeter)
~rate      = Array.fill(~nTracks, { 1.0 });    // clock rate vs master (steps / master tick)
~pos       = Array.fill(~nTracks, { -1 });     // each track's own play position
~acc       = Array.fill(~nTracks, { 0.0 });    // per-track phase accumulator
~globalTick = -1;
~uiEdit    = -1;                               // track the UI is editing (for playhead telemetry)
// per-step locks (nil = inherit the track default); set by /ph/steplock
~stepNote  = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
~stepVel   = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
~stepPan   = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
// per-step voice-macro lock: nil, or a flat [\sym, val, ...] arg array overriding timbre.
~stepMacro = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
// per-step ratchet count (1 = single hit) — living steps re-roll this over time
~stepRatchet = Array.fill(~nTracks, { Array.fill(~maxSteps, { 1 }) });
// per-step send flag (1 = route this hit through the living-FX delay/reverb bus)
~stepSend = Array.fill(~nTracks, { Array.fill(~maxSteps, { 0 }) });
~pstore    = Array.fill(~nTracks, { IdentityDictionary.new });   // param name -> value
~sampBuf   = Array.fill(~nTracks, { nil });
~sampFiles = [];
~maxPoly   = 3;                                      // per-track voice cap (steal oldest)
~trackVoices = Array.fill(~nTracks, { List.new });   // live voices per track
// FX: per-track insert chains. Canonical chain order (verb last); pad index == fx index.
~fxDefs   = [\phOverdrive, \phAmpsim, \phBitcrusher, \phRingmod, \phFlanger, \phClouds, \phGreyhole, \phVerb];
~nFx      = 8;
~assigned = Array.fill(~nTracks, { Array.fill(8, { 0 }) });   // [track][fx] on/off
~fxBypass = Array.fill(~nTracks, { 0 });                      // per-track FX bypass
~fxStore  = Array.fill(8, { IdentityDictionary.new });        // per-fx-type param values (macro)
~fxSynth  = Array.fill(~nTracks, { Array.fill(8, { nil }) }); // live FX synths

// ---- one-time graph scaffold (buses + groups + master) ----
~scaffold = {
	Synth(\phStkInit);   // set the STK rawwave path before any physical-model voice spawns
	~masterBus = Bus.audio(s, 2);
	~trackBus  = Array.fill(~nTracks, { Bus.audio(s, 2) });   // one private stereo bus per track
	~livingBus = Bus.audio(s, 2);   // LIVING-STEP send: a fired living hit routes here (delay+reverb)
	~silentBuf = Buffer.alloc(s, 1024, 1);   // default (silent) buffer for empty samplers
	// order: clear -> voices -> fx -> send -> master
	~gClear  = Group.head(s);
	~gVoices = Group.after(~gClear);
	~gFx     = Group.after(~gVoices);
	~gSend   = Group.after(~gFx);
	~gMaster = Group.after(~gSend);
	// clears (private buses aren't auto-zeroed; voices Out.ar ADD onto them)
	Synth(\phClear, [\bus, ~masterBus.index], ~gClear);
	Synth(\phClear, [\bus, ~livingBus.index], ~gClear);
	~nTracks.do { |t| Synth(\phClear, [\bus, ~trackBus[t].index], ~gClear) };
	// per-track FX subgroup (keeps each track's chain in canonical order) + send to master
	~fxGroup = Array.fill(~nTracks, { Group.tail(~gFx) });
	~nTracks.do { |t| Synth.tail(~gSend, \phSend, [\in, ~trackBus[t].index, \out, ~masterBus.index]) };
	// living-step FX send: reads ~livingBus (fired hits), delay -> reverb, sums into master.
	~livingFxSynth = Synth.tail(~gSend, \phLivingFx, [\in, ~livingBus.index, \out, ~masterBus.index]);
	~masterSynth = Synth(\phMaster, [\in, ~masterBus.index, \out, 0, \gain, 1.0], ~gMaster);
	~recGroup = Group.after(~gMaster);   // performance recorder taps bus 0 AFTER the master
};

// ---- performance recording (master output -> stereo WAV via DiskOut) ----
~recBuf = nil; ~recSynth = nil; ~ampSynth = nil;
~recStop = {
	~ampSynth.notNil.if { ~ampSynth.free; ~ampSynth = nil };
	~recSynth.notNil.if { ~recSynth.free; ~recSynth = nil };       // stop writing first
	~recBuf.notNil.if { ~recBuf.close; ~recBuf.free; ~recBuf = nil };   // close finalizes the WAV header
};
~recStart = { |path|
	~recStop.value;
	~recBuf = Buffer.alloc(s, 65536, 2);
	~recSynth = Synth.basicNew(\phRec, s);
	// open the file (leaveOpen -> cue for DiskOut streaming); start the recorder synth
	// ONLY once the write is set up, via the write's completion message.
	// int16: universally playable in browsers (some reject 24-bit WAV in <audio>)
	~recBuf.write(path, "wav", "int16", 0, 0, true,
		~recSynth.newMsg(~recGroup, [\buf, ~recBuf], \addToTail));
	// report the master level while recording -> the controller ends the take on silence
	~ampSynth = Synth.tail(~recGroup, \phAmp);
};

// (re)build a track's FX chain: free existing, recreate assigned FX in canonical
// order, wired in==out==the track bus (each FX ReplaceOut's the bus in place),
// restoring the per-fx-type macro params + current bypass.
~rebuildFx = { |t|
	8.do { |k| ~fxSynth[t][k].notNil.if { ~fxSynth[t][k].free; ~fxSynth[t][k] = nil } };
	8.do { |k|
		(~assigned[t][k] == 1).if {
			var syn = Synth.tail(~fxGroup[t], ~fxDefs[k],
				[\in, ~trackBus[t].index, \out, ~trackBus[t].index, \wet, 0.5, \bypass, ~fxBypass[t]]);
			~fxStore[k].keysValuesDo { |name, v| syn.set(name, v) };
			~fxSynth[t][k] = syn;
		};
	};
};

// ---- step clock ----
~applyTempo = { ~clock.tempo = (~bpm / 60) * ~stepsPerBeat; };   // 1 beat == 1 step
~clock = TempoClock.new((120 / 60) * 4);

// spawn one voice for track t. Voices free themselves on decay (Line doneAction);
// a hard per-track polyphony cap steals the oldest so dense patterns can't pile
// up unbounded (that's what XRun-froze the box). onFree keeps the list accurate.
~spawn = { |t, step, velScale = 1.0|
	var typeIdx = ~trackType[t];
	// typeIdx < 0 == an empty/unassigned track: it never spawns (no engine, no sound).
	(typeIdx >= 0).if {
		var def, nn, vv, pp, sm, merged, args, syn, lst;
		def = (typeIdx == 0).if(
			{ ~drumDefs[(~pstore[t][\mode] ? 0).round.clip(0, 6).asInteger] },   // per-mode drum
			{ ~typeDefs[typeIdx.clip(0, ~typeDefs.size - 1)] });
		nn = ~stepNote[t][step] ? ~note[t];
		vv = (~stepVel[t][step] ? ~vel[t]) * velScale;    // ratchet sub-hits decay in velocity
		pp = ~stepPan[t][step] ? (~pstore[t][\pan] ? 0);
		sm = ~stepMacro[t][step];
		// Merge the per-step macro override INTO a copy of the track params, so the override
		// wins UNAMBIGUOUSLY. Passing pstore ++ sm as a flat Synth arg list left duplicate
		// control names (e.g. \crush from both), and the override only won if scsynth honoured
		// last-write — which it did NOT reliably, so per-step fx/tonal transforms were silently
		// swallowed by the voice defaults (ratchets, a separate path, still worked). Merging
		// dedups: this is what makes living-step fx/tonal changes actually sound.
		merged = ~pstore[t].copy;
		sm.notNil.if { sm.pairsDo { |k, val| merged[k] = val } };
		merged[\pan] = pp;                                // step pan lock, deduped
		// a LIVING step whose transform requested a send routes THIS hit to the living-FX
		// bus (delay/reverb) instead of the track bus — so only the fired hit is affected.
		merged[\out] = ((~stepSend[t][step] ? 0) > 0).if({ ~livingBus.index }, { ~trackBus[t].index });
		args = [\note, nn, \vel, vv] ++ merged.getPairs;
		(def == \phSampler).if {
			args = args ++ [\buf, ~sampBuf[t].notNil.if({ ~sampBuf[t].bufnum }, { ~silentBuf.bufnum })];
		};
		lst = ~trackVoices[t];
		syn = Synth(def, args, ~gVoices);
		syn.register;
		syn.onFree({ lst.remove(syn) });
		lst.add(syn);
		while ({ lst.size > ~maxPoly }) { lst.removeAt(0).free };
	};
};

// Per-track accumulator clock: each master tick advances every track by its
// `rate` (steps/tick); a track fires when its accumulator crosses a step, and
// wraps at its own `length` — so tracks of different lengths/rates run
// polymetrically against the shared master clock. Playhead telemetry reports the
// UI's edit track's own position.
~advance = {
	~nTracks.do { |t|
		~acc[t] = ~acc[t] + ~rate[t];
		while ({ ~acc[t] >= 1.0 }) {
			~acc[t] = ~acc[t] - 1.0;
			~pos[t] = (~pos[t] + 1) % ~length[t].max(1);
			((~pattern[t][~pos[t]] == 1) and: { ~mute[t] == 0 }).if {
				var st = ~pos[t];
				var k = (~stepRatchet[t][st] ? 1).asInteger.clip(1, 8);
				~spawn.(t, st, 1.0);
				// RATCHET: retrigger k-1 more times within this step's own duration. On the
				// step clock 1 beat == 1 step at rate 1, so a track's step lasts 1/rate beats;
				// space the sub-hits evenly across it and duck their velocity for a natural roll.
				(k > 1).if {
					var span = 1.0 / ~rate[t].max(0.0625);
					(1..(k - 1)).do { |j|
						~clock.sched(j * span / k, {
							~spawn.(t, st, 1.0 - (0.12 * j)); nil
						});
					};
				};
			};
		};
	};
	~globalTick = ~globalTick + 1;
	// Fixed 16-step bar grid: fire /ph/cycle on the LAST step of each bar so the
	// controller can apply a queued pattern switch in time for the next downbeat.
	~ready.if {
		((~globalTick % 16) == 15).if { ~ctrl.sendMsg("/ph/cycle") };
		~ctrl.sendMsg("/ph/step", (~uiEdit >= 0).if({ ~pos[~uiEdit] }, { -1 }));
	};
};

~startSeq = {
	~running.not.if {
		~running = true;
		~globalTick = -1;
		~nTracks.do { |t| ~pos[t] = -1; ~acc[t] = 0.0 };
		~seqTask = Routine({ loop { ~advance.value; 1.wait } });
		~applyTempo.value;
		~seqTask.play(~clock);
	};
};
~stopSeq = {
	~running = false;
	~seqTask.notNil.if { ~seqTask.stop; ~seqTask = nil; };
	~globalTick = -1;
	~ready.if { ~ctrl.sendMsg("/ph/step", -1) };
};

// ---- sampler buffer load ----
~sampScan = {
	~sampFiles = (~sampleDir ++ "/*.wav").pathMatch ++ (~sampleDir ++ "/*.WAV").pathMatch;
};
~sampLoad = { |t, index|
	var i, path;
	(~sampFiles.size > 0).if {
		i = (index < 0).if({ ~sampFiles.size.rand }, { index.clip(0, ~sampFiles.size - 1) });
		path = ~sampFiles[i];
		Buffer.readChannel(s, path, channels: [0], action: { |b|
			var old = ~sampBuf[t];
			~sampBuf[t] = b;
			old.notNil.if { old.free };
		});
	};
};

// ================= OSC dispatch (/ph/...) =================
~defs = [
	OSCdef(\phTempo, { |m| ~bpm = m[1].clip(20, 300); ~applyTempo.value; }, '/ph/tempo'),
	OSCdef(\phRun,   { |m| (m[1] > 0).if({ ~startSeq.value }, { ~stopSeq.value }); }, '/ph/run'),
	OSCdef(\phSteps, { |m| ~nSteps = m[1].asInteger.clip(1, ~maxSteps); }, '/ph/steps'),
	OSCdef(\phTrack, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		// -1 == empty/unassigned (never spawns); otherwise a valid engine index.
		~trackType[t] = m[2].asInteger.clip(-1, ~typeDefs.size - 1);
	}, '/ph/track'),
	// AUDITION: spawn ONE preview voice of an engine straight to the master bus (no
	// track, no per-track FX). Used by the engine-palette pad-audition gesture.
	// Args: typeIdx, note, vel, drumMode, then flat [nameStr, val, nameStr, val, ...].
	OSCdef(\phPreview, { |m|
		var typeIdx = m[1].asInteger;
		var nn = m[2].asFloat, vv = m[3].asFloat, mode = m[4].asInteger;
		var pairs = [], i = 5;
		while { i < (m.size - 1) } { pairs = pairs ++ [m[i].asSymbol, m[i + 1].asFloat]; i = i + 2 };
		(typeIdx >= 0).if {
			var def = (typeIdx == 0).if(
				{ ~drumDefs[mode.clip(0, 6)] },
				{ ~typeDefs[typeIdx.clip(0, ~typeDefs.size - 1)] });
			Synth(def, [\out, ~masterBus.index, \note, nn, \vel, vv] ++ pairs, ~gVoices);
		};
	}, '/ph/preview'),
	OSCdef(\phParam, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var sym = m[2].asSymbol;                     // string arg arrives as Symbol
		var val = m[3].asFloat;
		~pstore[t][sym] = val;                       // default for future strikes
		~trackVoices[t].do { |v| v.set(sym, val) };  // update currently-ringing voices live (fixes pan, enables live macro)
	}, '/ph/param'),
	OSCdef(\phPattern, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		~maxSteps.do { |i| ~pattern[t][i] = (m[2 + i] ? 0).asInteger };
	}, '/ph/pattern'),
	OSCdef(\phStepset, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		~pattern[t][m[2].asInteger.clip(0, ~maxSteps - 1)] = m[3].asInteger;
	}, '/ph/stepset'),
	OSCdef(\phMute, { |m| ~mute[m[1].asInteger.clip(0, ~nTracks - 1)] = m[2].asInteger; }, '/ph/mute'),
	OSCdef(\phNote, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var nn = m[2].asFloat;
		~note[t] = nn;                                   // default for future strikes
		~trackVoices[t].do { |v| v.set(\note, nn) };     // re-pitch currently-ringing voices live
	}, '/ph/note'),
	OSCdef(\phLength, { |m| ~length[m[1].asInteger.clip(0, ~nTracks - 1)] = m[2].asInteger.clip(1, ~maxSteps); }, '/ph/length'),
	OSCdef(\phRate, { |m| ~rate[m[1].asInteger.clip(0, ~nTracks - 1)] = m[2].asFloat.clip(0.0625, 16.0); }, '/ph/rate'),
	OSCdef(\phEdit, { |m| ~uiEdit = m[1].asInteger.clip(-1, ~nTracks - 1); }, '/ph/edittrack'),
	OSCdef(\phFxAssign, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1), k = m[2].asInteger.clip(0, 7);
		~assigned[t][k] = m[3].asInteger; ~rebuildFx.(t);
	}, '/ph/fxassign'),
	// Wipe EVERY track's FX assignments and free their synths. A full state push (pattern
	// switch / generate / project load) sends this first, then re-assigns only the current
	// FX — otherwise the engine's ~assigned array would only ever grow, and stale FX chains
	// (a reverb is ~10% CPU each) would pile up across generations until the box XRuns.
	OSCdef(\phFxClear, { |m|
		~nTracks.do { |t| 8.do { |k| ~assigned[t][k] = 0 }; ~rebuildFx.(t) };
	}, '/ph/fxclear'),
	OSCdef(\phFxBypass, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1), on = m[2].asInteger;
		~fxBypass[t] = on;
		8.do { |k| ~fxSynth[t][k].notNil.if { ~fxSynth[t][k].set(\bypass, on) } };
	}, '/ph/fxbypass'),
	OSCdef(\phFxSet, { |m|
		var k = m[1].asInteger.clip(0, 7), name = m[2].asSymbol, v = m[3].asFloat;
		~fxStore[k][name] = v;                       // applies to every instance of this fx type
		~nTracks.do { |t| ~fxSynth[t][k].notNil.if { ~fxSynth[t][k].set(name, v) } };
	}, '/ph/fxset'),
	OSCdef(\phSteplock, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		~stepNote[t][c] = m[3].asFloat; ~stepVel[t][c] = m[4].asFloat; ~stepPan[t][c] = m[5].asFloat;
	}, '/ph/steplock'),
	OSCdef(\phStepMacro, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		var pairs = [];
		((m.size - 3) div: 2).do { |i| pairs = pairs ++ [m[3 + (i * 2)].asSymbol, m[4 + (i * 2)].asFloat] };
		~stepMacro[t][c] = (pairs.size > 0).if({ pairs }, { nil });   // applied at this step's next hit
	}, '/ph/stepmacro'),
	OSCdef(\phStepRatchet, { |m|                    // per-step ratchet count (living steps)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		~stepRatchet[t][c] = m[3].asInteger.clip(1, 8);
	}, '/ph/stepratchet'),
	OSCdef(\phStepSend, { |m|                       // per-step living-FX send flag (0/1)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		~stepSend[t][c] = m[3].asInteger.clip(0, 1);
	}, '/ph/stepsend'),
	OSCdef(\phLivingFx, { |m|                       // set the living-FX bus params (per fire)
		~livingFxSynth.notNil.if {
			~livingFxSynth.set(\dTime, m[1].asFloat, \dFb, m[2].asFloat, \dMix, m[3].asFloat,
				\vMix, m[4].asFloat, \vRoom, m[5].asFloat, \vDamp, m[6].asFloat);
		};
	}, '/ph/livingfx'),
	OSCdef(\phClearLocks, { |m|                     // wipe all per-step locks for a track (pattern load)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		~maxSteps.do { |c| ~stepNote[t][c] = nil; ~stepVel[t][c] = nil; ~stepPan[t][c] = nil; ~stepMacro[t][c] = nil; ~stepRatchet[t][c] = 1; ~stepSend[t][c] = 0 };
	}, '/ph/clearlocks'),
	OSCdef(\phVel,  { |m| ~vel[m[1].asInteger.clip(0, ~nTracks - 1)] = m[2].asFloat; }, '/ph/vel'),
	OSCdef(\phSamp, { |m| ~sampLoad.(m[1].asInteger.clip(0, ~nTracks - 1), m[2].asInteger); }, '/ph/samp'),
	OSCdef(\phMgain, { |m| ~masterSynth.notNil.if { ~masterSynth.set(\gain, m[1].asFloat) }; }, '/ph/mastergain'),
	OSCdef(\phMfilter, { |m|
		~masterSynth.notNil.if { ~masterSynth.set(\cutoff, m[1].asFloat, \res, m[2].asFloat) };
	}, '/ph/masterfilter'),
	OSCdef(\phPanic, { |m| ~stopSeq.value; ~gVoices.notNil.if { ~gVoices.freeAll }; ~trackVoices.do { |l| l.clear }; }, '/ph/panic'),
	OSCdef(\phRecStart, { |m| ~recStart.value(m[1].asString); }, '/ph/recstart'),
	OSCdef(\phRecStop,  { |m| ~recStop.value; }, '/ph/recstop'),
	// master level from \phAmp -> forward to the controller (drives tail-end detection)
	OSCdef(\phAmpRep,   { |m| ~ready.if { ~ctrl.sendMsg("/ph/amp", m[3].asFloat) }; }, '/ph/amprep'),
	OSCdef(\phPing, { |m| ~ready.if { ~ctrl.sendMsg("/ph/ready") }; }, '/ph/ping'),
];

// ================= boot =================
~boot = { |sr = 44100, block = 128, channels = 2|
	s.options.numOutputBusChannels = channels;
	s.options.numInputBusChannels = channels;
	s.options.sampleRate = sr;
	s.options.blockSize = block;
	s.options.memSize = 256 * 1024;
	s.options.maxNodes = 4096;
	s.waitForBoot({
		~buildDefs.(2);            // from synthdefs.scd
		s.sync;
		~sampScan.value;
		~scaffold.value;           // buses + groups + master + silent buffer
		s.sync;
		s.startAliveThread;
		~ready = true;
		~ctrl.sendMsg("/ph/ready");
		("PoundHard engine ready — " ++ ~sampFiles.size ++ " samples").postln;
		SystemClock.sched(1.0, {
			~ready.if { ~ctrl.sendMsg("/ph/cpu", s.avgCPU.round(0.1), s.peakCPU.round(0.1), s.numSynths) };
			1.0;
		});
	});
};
)
