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
~typeDefs = [\phDrum, \phFm7, \phBuchloid, \phMolly, \phRings, \phBen, \phNoizeop, \phIcarus, \phPlaits, \phShaker, \phMembrane, \phMallet, \phBowed, \phPluck, \phTube, \phChaos, \phWtable, \phBytebeat, \phSampleVoice, \phCsound];  // /ph/track type index (-1 = empty/unassigned)
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
// PER-STEP FX: a bitmask over the 8 insert slots, or -1 = "no lock, use the track's own
// assignment". Applied at step time as a parameter lock on each FX's `enable`, so a step
// can turn effects on or off for its own hit without rebuilding the chain.
~stepFx = Array.fill(~nTracks, { Array.fill(~maxSteps, { -1 }) });
// CYCLE FREQUENCY: how often a step may fire, in PATTERN REPETITIONS (1 = every cycle,
// 8 = once every eight). ~cycle[t] counts how many times the track has come round, so a
// short pattern can evolve over a span far longer than its own length.
~stepCycle = Array.fill(~nTracks, { Array.fill(~maxSteps, { 1 }) });
// per-step SAMPLE window (nil = inherit the track's own start/end)
~stepStart = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
~stepEnd   = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
// per-step FILTER lock: nil = follow the track, else [cutoff, res, type]. Like the FX
// enable p-lock, this drives ONE shared insert, so an unlocked step has to put the
// track's own values back or a lock would leak into every hit after it.
~stepFilt = Array.fill(~nTracks, { Array.fill(~maxSteps, { nil }) });
~filtNow  = Array.fill(~nTracks, { nil });   // what the insert has been told to become
~filtGlide = 0.03;                           // the filter's slew time (see \phTrackFilter)
~cycle     = Array.fill(~nTracks, { -1 });   // -1 so the FIRST pass is cycle 0 (fires)
// what each insert's \enable is set to right now (avoids re-sending the same value
// every hit) and which FX a track needs instantiated because SOME step locks it.
~fxEnable = Array.fill(~nTracks, { Array.fill(8, { 0 }) });
~stepFxNeed = { |t|                             // OR of every step lock on this track
	var need = 0;
	~maxSteps.do { |c| ((~stepFx[t][c] ? -1) > 0).if { need = need | ~stepFx[t][c] } };
	need;
};
~pstore    = Array.fill(~nTracks, { IdentityDictionary.new });   // param name -> value
~sampBuf   = Array.fill(~nTracks, { nil });
~sampFiles = [];
// WTABLE: Ableton Wavetable sprites (each a bank of 1024-sample frames). Per-track, per-osc
// buffer, loaded on demand from the shared, alphabetically-sorted sprite list so the
// controller's `wt1`/`wt2` index selects the same sprite here.
~wtSpriteDir = "/opt/move/Dsp/Vector/Sprites";
~wtSprites = [];
~wtBuf1    = Array.fill(~nTracks, { nil });
~wtBuf2    = Array.fill(~nTracks, { nil });
~wtBufPrev = Array.fill(2, { nil });   // audition (palette-preview) sprite pair
// BYTEBEAT: a curated bank of bytebeat expressions (the "presets"). Each track holds an
// index into this bank; on spawn the engine pushes that expression to the voice's ByteBeat
// UGen with the /eval unit command (see ~spawn + ~bbUgenIndex). All are valid in the
// plugin's grammar (t, ints, + - * / %, & | ^ << >> ~, relational, ?:, subscript).
~bbExprs = [
	"t*(t>>5|t>>8)",
	"t*(((t>>12)|(t>>8))&(63&(t>>4)))",
	"(t>>6|t|t>>(t>>16))*10+((t>>11)&7)",
	"(t&t>>7)*(t>>8&t>>11)|t>>2",
	"t*9&t>>4|t*5&t>>7|t*3&t/1024",
	"t>>4|t&(t>>5)|t>>7",
	"t*(t>>6&t>>9)|t>>3&t*5",
	"t*(t>>9&t>>13)|t*(t>>7&t>>11)",
	"t*(42&t>>10)",
	"(t>>2)*(t>>5&t>>9|t>>3)",
	"t*((t>>9|t>>13)&25&t>>6)",
	"(t>>7|t|t>>6)*10+4*(t&t>>13|t>>6)",
	"t*(t>>11&t>>8&123&t>>3)",
	"(t>>13|t)&(t>>7|t)&(t>>4|t)",
	"t*(t>>7|t>>10)^(t>>5)",
	"(t/8)&(t>>10)|(t*4)&(t>>7)|(t*2)&(t>>5)",
	"t*(((t>>16)|(t>>8))&(63&(t>>4)))",
	"t>>4|t*(t>>12|t>>8)&(63&t>>4)",
	"(t&t>>12)*(t>>4|t>>8)"
];
// SAMPLE engine: one PAD buffer (the capture currently held by the palette pad) plus a
// per-track buffer, so assigning to a track hands the sound over and RELEASES the pad.
~smpPad   = nil;                       // buffer held by the SAMPLE palette pad
~smpBuf   = Array.fill(~nTracks, { nil });   // per-track assigned sample
~smpCapSy = nil;                       // the live \phCapture synth, if any
~smpCapBuf = nil;                      // buffer being recorded into
~smpMaxDur = 2.0;                      // cap a take (buffer length caps RecordBuf)
~bbExprIdx = Array.fill(~nTracks, { 0 });   // per-track expression index into ~bbExprs
// BYTEBEAT STREAM POSITION. A bytebeat expression is a function of a FREE-RUNNING counter
// and most of the bank is silent near t=0 (`t*(42&t>>10)` is zero until t passes 1024,
// `t&t>>8` until 256). A voice counts from zero and a percussive hit is over in a few
// thousand counts, so every hit played the dead head of the stream — the engine read as
// mostly silent. Each track now keeps its own position and every hit continues where the
// stream would have been, so a pattern walks THROUGH the expression the way bytebeat is
// meant to be heard, instead of replaying its first moment forever.
~bbOrigin     = Array.fill(~nTracks, { nil });   // running position (counts)
~bbOriginBase = Array.fill(~nTracks, { nil });   // the track's Origin param, to detect a re-roll
// THE LIVE BYTEBEAT VOICES. One per track, plus one for the palette audition. They are
// created when a track takes the engine and live until it gives it up: the UGen parses its
// expression once, and each step re-triggers the envelope instead of building a new
// (silent-until-parsed) instance. See the SynthDef header for why.
~bbVoice = Array.fill(~nTracks, { nil });
~bbPrevVoice = nil;
~bbPrevExpr = nil;   // expression currently parsed into the preview voice
~bbExprPrev = 0;                            // audition expression index
// ~bbUgenIndex (the ByteBeat UGen's graph index for /eval) is set in synthdefs.scd.
~maxPoly   = 3;                                      // per-track voice cap (steal oldest)
~trackVoices = Array.fill(~nTracks, { List.new });   // live voices per track
// FX: per-track insert chains. Canonical chain order (verb last); pad index == fx index.
// Chain order matters: GREY (diffuse echo) feeds VERB (plate) at the very END, so the
// reverb hears everything before it. FLNG (flanger) was dropped to make room and keep the
// chain at 8 slots.
~fxDefs   = [\phOverdrive, \phAmpsim, \phBitcrusher, \phRingmod, \phClouds, \phStreson, \phGreyhole, \phVerb];
~nFx      = 8;
~assigned = Array.fill(~nTracks, { Array.fill(8, { 0 }) });   // [track][fx] on/off
~fxBypass = Array.fill(~nTracks, { 0 });                      // per-track FX bypass
~fxStore  = Array.fill(8, { IdentityDictionary.new });        // per-fx-type param values (macro)
~fxSynth  = Array.fill(~nTracks, { Array.fill(8, { nil }) }); // live FX synths
// per-track multimode filter (one always-on insert per track, ahead of the FX chain)
~filtSynth = Array.fill(~nTracks, { nil });
~filt      = Array.fill(~nTracks, { [18000, 0.0, 0] });   // cutoff, res, type (0=LP 1=HP)

// ---- one-time graph scaffold (buses + groups + master) ----
~scaffold = {
	Synth(\phStkInit);   // set the STK rawwave path before any physical-model voice spawns
	~masterBus = Bus.audio(s, 2);
	~trackBus  = Array.fill(~nTracks, { Bus.audio(s, 2) });   // one private stereo bus per track
	~livingBus = Bus.audio(s, 2);   // LIVING-STEP send: a fired living hit routes here (delay+reverb)
	~silentBuf = Buffer.alloc(s, 1024, 1);   // default (silent) buffer for empty samplers
	// order: clear -> voices -> fx -> send -> master
	~gClear  = Group.head(s);
	// MULTICORE TOPOLOGY. supernova only parallelises across ParGroups — a plain Group
	// stays serial — so the graph decides how much of the CM4 gets used. What is safe to
	// run in parallel is decided by WHICH BUS a node writes:
	//   * each track owns a PRIVATE stereo bus, so different tracks are independent
	//     -> ~gVoices is a ParGroup of one serial group PER TRACK, and ~gFx is a ParGroup
	//        of the per-track FX chains (each ReplaceOut's only its own track bus).
	//   * voices WITHIN a track sum into that one bus, so they stay serial (parallel
	//     additive writes to a shared bus would race) — hence the per-track subgroup.
	//   * voices writing a SHARED bus (living-step hits from any track -> ~livingBus;
	//     palette auditions -> ~masterBus) get ONE serial group, ~gSharedVoices.
	//   * ~gSend / master stay serial: every send sums into the master bus.
	// On scsynth a ParGroup is just a Group, so that path is bit-identical to before.
	~gVoices = ParGroup.after(~gClear);
	~gTrackVoices  = Array.fill(~nTracks, { Group.tail(~gVoices) });
	~gSharedVoices = Group.tail(~gVoices);
	// the per-track filter sits between the voices and the FX chain: it shapes the track,
	// then the inserts work on the filtered signal (a filter after the FX would be
	// filtering reverb tails, which is not what a channel filter is for).
	~gFilt   = ParGroup.after(~gVoices);
	~gFx     = ParGroup.after(~gFilt);
	~gSend   = Group.after(~gFx);
	~gMaster = Group.after(~gSend);
	// clears (private buses aren't auto-zeroed; voices Out.ar ADD onto them)
	Synth(\phClear, [\bus, ~masterBus.index], ~gClear);
	Synth(\phClear, [\bus, ~livingBus.index], ~gClear);
	~nTracks.do { |t| Synth(\phClear, [\bus, ~trackBus[t].index], ~gClear) };
	~nTracks.do { |t|
		~filtSynth[t] = Synth.tail(~gFilt, \phTrackFilter,
			[\in, ~trackBus[t].index, \out, ~trackBus[t].index,
				\cutoff, ~filt[t][0], \res, ~filt[t][1], \type, ~filt[t][2]]);
	};
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
	// An insert exists if the track is assigned it OR any step locks it. A step-only
	// insert sits in the chain with \enable 0 — inaudible until a locked hit opens it.
	// This is INCREMENTAL: an insert that is still wanted is left running. Tearing the
	// whole chain down on every edit restarted GREY/CLDS tails mid-performance and raced
	// the per-step \enable sets (server-side "node not found" spam).
	var need = ~stepFxNeed.(t);
	// The controller starts pushing tracks the moment sclang answers — long before the
	// server has booted and ~scaffold has run. Building an insert then targets a group
	// that doesn't exist yet (the server answers "node not found: 1" and the synth is
	// never created, leaving a phantom in ~fxSynth). ~ready is the only safe gate: it is
	// set after the whole scaffold is up, and everything pushed early is applied there.
	(~ready == true).if {
		var added = false;
		8.do { |k|
			var on = ~assigned[t][k] == 1;
			var want = on or: { ((need >> k) & 1) == 1 };
			(want and: { ~fxSynth[t][k].isNil }).if {
				// new insert: assigned ones open, step-only ones start closed
				var syn = Synth.tail(~fxGroup[t], ~fxDefs[k],
					[\in, ~trackBus[t].index, \out, ~trackBus[t].index, \wet, 0.5,
						\bypass, ~fxBypass[t], \enable, on.if({ 1 }, { 0 })]);
				~fxStore[k].keysValuesDo { |name, v| syn.set(name, v) };
				~fxSynth[t][k] = syn;
				~fxEnable[t][k] = on.if({ 1 }, { 0 });
				added = true;
			};
			(want.not and: { ~fxSynth[t][k].notNil }).if {
				~fxSynth[t][k].free; ~fxSynth[t][k] = nil; ~fxEnable[t][k] = 0;
			};
			// a still-wanted insert only needs its resting state re-asserted
			(want and: { ~fxSynth[t][k].notNil and: { ~fxEnable[t][k] != on.if({ 1 }, { 0 }) } }).if {
				~fxSynth[t][k].set(\enable, on.if({ 1 }, { 0 }));
				~fxEnable[t][k] = on.if({ 1 }, { 0 });
			};
		};
		// a new insert lands at the tail, so re-assert canonical chain order (VERB last)
		// by walking the slots in index order — a move, not a rebuild: no tail is lost.
		added.if { 8.do { |k| ~fxSynth[t][k].notNil.if { ~fxSynth[t][k].moveToTail(~fxGroup[t]) } } };
	};
};

// Make sure track `t` has its persistent bytebeat voice, parsed with the track's current
// expression. Returns the synth (or nil before the graph exists).
// ---- CSOUND (engine 20) -----------------------------------------------------------
// Csound is a separate JACK client writing a stereo pair per track into supernova's
// inputs. Two halves: a PERSISTENT SC voice carrying that pair onto the track bus (so
// the FX chain, filter, sends and master all apply), and a score event fired at Csound
// over UDP per hit. Nothing spawns per hit on this side — the audio is already flowing.
~csAddr  = NetAddr("127.0.0.1", 11000);        // Csound's UDP server (--port=11000)
~csVoice = Array.fill(~nTracks, { nil });
~csEnsure = { |t|
	((~ready == true) and: { ~csVoice[t].isNil }).if {
		var syn = Synth.tail(~gTrackVoices[t] ? ~gVoices, \phCsound, [
			\out, ~trackBus[t].index,
			// inputs 0-1 are the microphone; the Csound pairs start at 2
			\in, 2 + (2 * t),
			\amp, (~pstore[t][\amp] ? 0.85),
			\pan, (~pstore[t][\pan] ? 0.0)]);
		syn.register;
		syn.onFree({ ~csVoice[t] = nil });
		~csVoice[t] = syn;
	};
	~csVoice[t];
};
~csFree = { |t| ~csVoice[t].notNil.if { ~csVoice[t].free; ~csVoice[t] = nil } };
// AUDITION. The palette pad must make a sound on a track that does not exist yet, so the
// engine keeps a 17th stereo pair ("track 16", supernova inputs 35-36) purely for preview,
// carried to the MASTER bus rather than a track bus. Without this, auditioning the Csound
// engine spawned a passthrough with no note behind it and was silent every time — which is
// exactly what trying out a new engine looks like.
~csPrevVoice = nil;
~csPrevEnsure = {
	((~ready == true) and: { ~csPrevVoice.isNil }).if {
		var syn = Synth.tail(~gSharedVoices, \phCsound,
			[\out, ~masterBus.index, \in, 2 + (2 * 16), \amp, 0.9, \pan, 0.0]);
		syn.register;
		syn.onFree({ ~csPrevVoice = nil });
		~csPrevVoice = syn;
	};
	~csPrevVoice;
};
// Fire one note. A $-prefixed line on Csound's UDP port is a score event (a bare line is
// compiled as orchestra code and errors; `&` is silently ignored) — this is the whole
// note path, so it has to be exactly right.
~csHit = { |t, nn, vv, params, dur|
	var arch = ((params[\arch] ? 0).round.clip(0, 9)).asInteger;
	var freq = nn.midicps;
	var m = (1..8).collect { |i| (params[("m" ++ i).asSymbol] ? 0.5).clip(0, 1) };
	var line = "$i" ++ (11 + arch) ++ " 0 " ++ dur.clip(0.02, 12)
		++ " " ++ t ++ " " ++ freq ++ " " ++ vv.clip(0, 2)
		++ " " ++ m.join(" ") ++ "\n";
	~csAddr.sendRaw(line);
};

~bbEnsure = { |t|
	((~ready == true) and: { ~bbVoice[t].isNil }).if {
		var syn = Synth.tail(~gTrackVoices[t] ? ~gVoices, \phBytebeat,
			[\out, ~trackBus[t].index] ++ ~pstore[t].getPairs);
		syn.register;                                // onFree only fires for a REGISTERED node
		syn.onFree({ ~bbVoice[t] = nil });          // panic/free -> rebuilt on the next hit
		~bbVoice[t] = syn;
		// Parse ONCE, here — but NOT in the same instant as the /s_new. A unit command sent
		// back-to-back with the node's creation is delivered to a node the server has not
		// instantiated yet and is dropped, leaving the UGen on its silent `Undefined`
		// expression forever. A few control blocks of daylight is all it needs.
		SystemClock.sched(0.05, { ~bbEval.(t); nil });
	};
	~bbVoice[t];
};
~bbFree = { |t| ~bbVoice[t].notNil.if { ~bbVoice[t].free; ~bbVoice[t] = nil } };
// Push a (possibly new) expression to a track's live voice.
~bbEval = { |t|
	~bbVoice[t].notNil.if {
		s.sendMsg('/u_cmd', ~bbVoice[t].nodeID, ~bbUgenIndex, '/eval',
			~bbExprs[(~bbExprIdx[t] ? 0).clip(0, ~bbExprs.size - 1)]);
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
		// SAMPLE's buffer must go through `merged`: appending a second \buf after
		// merged.getPairs loses to any stale \buf already in ~pstore for this track (pstore
		// is never cleared on engine change), which silently played the 1024-frame silent
		// buffer. A dictionary key can only hold one value, so this can't collide.
		// per-step FX lock: flip the track's insert enables for this hit
		block { |brk|
			var lock;
			lock = ~stepFx[t][step] ? -1;
			8.do { |k|
				var want = (lock >= 0).if({ (lock >> k) & 1 }, { ~assigned[t][k] });
				((~fxEnable[t][k] != want) and: { ~fxSynth[t][k].notNil }).if {
					~fxSynth[t][k].set(\enable, want); ~fxEnable[t][k] = want;
				};
			};
		};
		(def == \phSampleVoice).if {
			merged[\buf] = ~smpBuf[t].notNil.if({ ~smpBuf[t].bufnum }, { ~silentBuf.bufnum });
			// per-step slice: a step can play a different part of the same buffer
			~stepStart[t][step].notNil.if { merged[\start] = ~stepStart[t][step] };
			~stepEnd[t][step].notNil.if { merged[\end] = ~stepEnd[t][step] };
		};
		// BYTEBEAT does not spawn: its voice is PERSISTENT. The UGen parses its expression
		// per instance and starts out silent, so a fresh instance per hit raced the async
		// /eval against the note — long notes won and screamed, short ones came out
		// inaudible, and the "same" sound was unrepeatable. Set this hit's values on the
		// live voice and re-trigger it; its counter free-runs, which is what bytebeat is.
		(def == \phBytebeat).if {
			var voice = ~bbEnsure.(t);
			voice.notNil.if {
				voice.set(*([\note, nn, \vel, vv] ++ merged.getPairs ++ [\t_trig, 1]));
			};
		};
		// CSOUND does not spawn either: its audio comes from another process. Update the
		// carrier voice's mixer position for this hit, then fire the note at Csound.
		(def == \phCsound).if {
			var voice = ~csEnsure.(t);
			voice.notNil.if {
				voice.set(\amp, (merged[\amp] ? 0.85) * vv, \pan, (merged[\pan] ? 0.0),
					\out, (merged[\out] ? ~trackBus[t].index));
				~csHit.(t, nn, vv, merged, (merged[\dur] ? 0.9));
			};
		};
		args = [\note, nn, \vel, vv] ++ merged.getPairs;
		(def == \phSampler).if {
			args = args ++ [\buf, ~sampBuf[t].notNil.if({ ~sampBuf[t].bufnum }, { ~silentBuf.bufnum })];
		};
		(def == \phWtable).if {
			args = args ++ [
				\buf1, ~wtBuf1[t].notNil.if({ ~wtBuf1[t].bufnum }, { ~silentBuf.bufnum }),
				\buf2, ~wtBuf2[t].notNil.if({ ~wtBuf2[t].bufnum }, { ~silentBuf.bufnum })];
		};
		lst = ~trackVoices[t];
		// Parallel-safe placement: a normal hit goes to its TRACK's group (private bus →
		// runs alongside other tracks); a living-FX hit writes the shared ~livingBus, so it
		// goes to the serial shared group instead. Mirrors merged[\out] above.
		// SAMPLE voices go in the SERIAL shared group, not the per-track ParGroup child: they
		// read a shared buffer, and the identical synth+args only sounded from there.
		((def != \phBytebeat) and: { def != \phCsound }).if {   // both are persistent voices, handled above
			syn = Synth(def, args,
				(((~stepSend[t][step] ? 0) > 0) || (def == \phSampleVoice)).if(
					{ ~gSharedVoices }, { ~gTrackVoices[t] }));
			syn.register;
			syn.onFree({ lst.remove(syn) });
			lst.add(syn);
			while ({ lst.size > ~maxPoly }) { lst.removeAt(0).free };
		};
	};
};

// Per-track accumulator clock: each master tick advances every track by its
// `rate` (steps/tick); a track fires when its accumulator crosses a step, and
// wraps at its own `length` — so tracks of different lengths/rates run
// polymetrically against the shared master clock. Playhead telemetry reports the
// UI's edit track's own position.
~advance = {
	// the controller restores a running transport the moment sclang answers, which can
	// beat ~scaffold — spawning before the buses exist is pure error flood, no audio.
	~ready.if { ~nTracks.do { |t|
		~acc[t] = ~acc[t] + ~rate[t];
		while ({ ~acc[t] >= 1.0 }) {
			~acc[t] = ~acc[t] - 1.0;
			~pos[t] = (~pos[t] + 1) % ~length[t].max(1);
			// a wrap to 0 is one more repetition of this track's pattern
			(~pos[t] == 0).if { ~cycle[t] = ~cycle[t] + 1 };
			// PER-STEP FILTER, HANDED OVER EARLY. The filter is one insert per track, so a
			// locked step has to set it — but setting it AT the hit means the glide that
			// stops it clicking also smears that hit's own attack. Instead the NEXT step's
			// values are scheduled one glide-time before it arrives: the change happens
			// during the previous note's tail (where a glide is what you want) and the new
			// hit starts with its filter already in place. An unlocked step hands back the
			// track's own values, so a lock can never leak forward.
			~filtSynth[t].notNil.if {
				var nxt = (~pos[t] + 1) % ~length[t].max(1);
				var want = ~stepFilt[t][nxt] ? ~filt[t];
				(~filtNow[t] != want).if {
					var stepDur = (60 / ~bpm.max(20)) / ~stepsPerBeat / ~rate[t].max(0.0625);
					~filtNow[t] = want;
					// ~clock runs one beat per step, so this is a fraction of a step
					~clock.sched((1 - (~filtGlide / stepDur)).clip(0, 1), {
						~filtSynth[t].notNil.if {
							~filtSynth[t].set(\cutoff, want[0], \res, want[1], \type, want[2]);
						};
						nil;
					});
				};
			};
			((~pattern[t][~pos[t]] == 1) and: { ~mute[t] == 0 }
				// CYCLE FREQUENCY: only fire on every Nth repetition of the pattern
				and: { (~cycle[t] % (~stepCycle[t][~pos[t]] ? 1).max(1)) == 0 }).if {
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
	} };
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
		// -1 so the first pass counts as cycle 0: an every-Nth step fires on the downbeat
		// and then every N repetitions, rather than staying silent until the Nth bar.
		~nTracks.do { |t| ~cycle[t] = -1 };
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
// WTABLE sprite enumeration + on-demand loading (osc = 1 or 2 -> ~wtBuf1/~wtBuf2).
~wtScan = { ~wtSprites = (~wtSpriteDir ++ "/*.wav").pathMatch.sort; };
~wtLoad = { |t, osc, index|
	(~wtSprites.size > 0).if {
		var i = index.asInteger.clip(0, ~wtSprites.size - 1);
		Buffer.readChannel(s, ~wtSprites[i], channels: [0], action: { |b|
			var slot = (osc == 2).if({ ~wtBuf2 }, { ~wtBuf1 });
			var old = slot[t];
			slot[t] = b;
			old.notNil.if { old.free };
		});
	};
};
// audition: load a sprite into the shared preview slot (osc = 0 or 1).
~wtLoadPrev = { |osc, index|
	(~wtSprites.size > 0).if {
		var i = index.asInteger.clip(0, ~wtSprites.size - 1);
		Buffer.readChannel(s, ~wtSprites[i], channels: [0], action: { |b|
			var old = ~wtBufPrev[osc];
			~wtBufPrev[osc] = b;
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
		// The controller pushes state (and the UI can fire an audition) the moment sclang
		// answers — long before the server has booted and ~scaffold has run. Touching
		// ~masterBus then throws inside the OSC dispatcher, and a throw there can take the
		// boot down with it: the engine never reaches ready and the device sits on
		// "starting...". Nothing can be auditioned before there is a graph anyway.
		var typeIdx = (~ready == true).if({ m[1].asInteger }, { -1 });
		var nn = m[2].asFloat, vv = m[3].asFloat, mode = m[4].asInteger;
		var pairs = [], i = 5;
		while { i < (m.size - 1) } { pairs = pairs ++ [m[i].asSymbol, m[i + 1].asFloat]; i = i + 2 };
		(typeIdx >= 0).if {
			var def = (typeIdx == 0).if(
				{ ~drumDefs[mode.clip(0, 6)] },
				{ ~typeDefs[typeIdx.clip(0, ~typeDefs.size - 1)] });
			(def == \phCsound).if({
				// CSOUND audition: nothing spawns — fire the note at Csound on the preview
				// pair and make sure the carrier voice exists to bring it back in.
				var pd = IdentityDictionary.new, j = 0;
				while { j < pairs.size } { pd[pairs[j]] = pairs[j + 1]; j = j + 2 };
				~csPrevEnsure.value;
				~csPrevVoice.notNil.if {
					~csPrevVoice.set(\amp, 0.9 * vv);
					~csHit.(16, nn, vv, pd, (pd[\dur] ? 0.9));
				};
			}, {
			(def == \phWtable).if({
				// WTABLE audition: wt1/wt2 are sprite selectors, not synth args. Load
				// them into the preview slots, strip them from the args, then spawn once
				// the buffers are in (readChannel is async).
				var clean = [], j = 0;
				while { j < pairs.size } {
					var k = pairs[j], val = pairs[j + 1];
					(k == \wt1).if({ ~wtLoadPrev.(0, val) },
					{ (k == \wt2).if({ ~wtLoadPrev.(1, val) },
					{ clean = clean ++ [k, val] }) });
					j = j + 2;
				};
				SystemClock.sched(0.18, {
					Synth(def, [\out, ~masterBus.index, \note, nn, \vel, vv,
						\buf1, ~wtBufPrev[0].notNil.if({ ~wtBufPrev[0].bufnum }, { ~silentBuf.bufnum }),
						\buf2, ~wtBufPrev[1].notNil.if({ ~wtBufPrev[1].bufnum }, { ~silentBuf.bufnum })]
						++ clean, ~gSharedVoices);
					nil;
				});
			}, {
				(def == \phBytebeat).if({
					// BYTEBEAT audition: the preview voice is PERSISTENT too, for the same
					// reason the track voices are — a fresh instance is silent until its
					// /eval lands, so auditioning built a new one that usually never spoke
					// (and never twice the same). Keep one, re-parse it, re-trigger it.
					var clean = [], j = 0, ei = ~bbExprPrev;
					while { j < pairs.size } {
						var k = pairs[j], val = pairs[j + 1];
						(k == \expr).if({ ei = val.asInteger }, { clean = clean ++ [k, val] });
						j = j + 2;
					};
					ei = ei.clip(0, ~bbExprs.size - 1);
					~bbPrevVoice.isNil.if {
						~bbPrevVoice = Synth.tail(~gSharedVoices, def, [\out, ~masterBus.index]);
						~bbPrevVoice.register;       // ditto: without this the ref outlives the node
						~bbPrevVoice.onFree({ ~bbPrevVoice = nil });
						~bbPrevExpr = nil;
					};
					(~bbPrevExpr != ei).if {          // parse only when the expression changes
						~bbPrevExpr = ei;
						// deferred for the same reason as the track voices (see ~bbEnsure)
						SystemClock.sched(0.05, {
							~bbPrevVoice.notNil.if {
								s.sendMsg('/u_cmd', ~bbPrevVoice.nodeID, ~bbUgenIndex, '/eval',
									~bbExprs[ei]);
							};
							nil;
						});
					};
					~bbPrevVoice.set(*([\note, nn, \vel, vv] ++ clean ++ [\t_trig, 1]));
				}, {
					// SAMPLE auditions the buffer the PAD holds (nothing captured -> silence)
					Synth(def, [\out, ~masterBus.index, \note, nn, \vel, vv]
						++ (def == \phSampleVoice).if(
							{ [\buf, ~smpPad.notNil.if({ ~smpPad.bufnum }, { ~silentBuf.bufnum })] }, { [] })
						++ pairs, ~gSharedVoices);
				});
			});
			});
		};
	}, '/ph/preview'),
	OSCdef(\phParam, { |m|
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var sym = m[2].asSymbol;                     // string arg arrives as Symbol
		var val = m[3].asFloat;
		// wt1/wt2 are sprite selectors, not synth args: (re)load the buffer for that osc.
		((sym == \wt1) || (sym == \wt2)).if({
			~wtLoad.(t, (sym == \wt2).if({ 2 }, { 1 }), val);
		}, {
			// `expr` is a bytebeat bank index, not a synth arg: store it, and live-update
			// any currently-ringing bytebeat voices with the /eval unit command.
			(sym == \expr).if({
				~bbExprIdx[t] = val.asInteger.clip(0, ~bbExprs.size - 1);
				~bbEval.(t);                                 // re-parse the LIVE voice
			}, {
				~pstore[t][sym] = val;                       // default for future strikes
				~trackVoices[t].do { |v| v.set(sym, val) };  // update currently-ringing voices live
				~bbVoice[t].notNil.if { ~bbVoice[t].set(sym, val) };   // ...and the bytebeat voice
			});
		});
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
	OSCdef(\phStepSmp, { |m|                       // per-step SAMPLE window (-1 = inherit)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		var st = m[3].asFloat, en = m[4].asFloat;
		~stepStart[t][c] = (st < 0).if({ nil }, { st.clip(0, 1) });
		~stepEnd[t][c]   = (en < 0).if({ nil }, { en.clip(0, 1) });
	}, '/ph/stepsmp'),
	OSCdef(\phFilter, { |m|                        // per-track filter: cutoff, res, LP/HP
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var cut = m[2].asFloat.clip(20, 19000);
		var rs = m[3].asFloat.clip(0, 1);
		var ty = m[4].asInteger.clip(0, 1);
		~filt[t] = [cut, rs, ty];
		~filtNow[t] = ~filt[t];
		~filtSynth[t].notNil.if { ~filtSynth[t].set(\cutoff, cut, \res, rs, \type, ty) };
	}, '/ph/filter'),
	OSCdef(\phStepFilt, { |m|                      // per-step filter lock (cutoff < 0 = clear)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		var cut = m[3].asFloat;
		~stepFilt[t][c] = (cut < 0).if({ nil },
			{ [cut.clip(20, 19000), m[4].asFloat.clip(0, 1), m[5].asInteger.clip(0, 1)] });
	}, '/ph/stepfilt'),
	OSCdef(\phStepCycle, { |m|                     // how often a step fires (pattern cycles)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		~stepCycle[t][c] = m[3].asInteger.clip(1, 8);
	}, '/ph/stepcycle'),
	OSCdef(\phStepFx, { |m|                        // per-step FX mask (-1 = no lock)
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var c = m[2].asInteger.clip(0, ~maxSteps - 1);
		var before = ~stepFxNeed.(t);
		~stepFx[t][c] = m[3].asInteger;
		// a newly-locked FX that isn't in the chain has to be instantiated (and one that
		// no longer appears anywhere can go away again)
		(~stepFxNeed.(t) != before).if { ~rebuildFx.(t) };
	}, '/ph/stepfx'),
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
		~maxSteps.do { |c|
			~stepNote[t][c] = nil; ~stepVel[t][c] = nil; ~stepPan[t][c] = nil;
			~stepMacro[t][c] = nil; ~stepRatchet[t][c] = 1; ~stepSend[t][c] = 0;
			~stepStart[t][c] = nil; ~stepEnd[t][c] = nil; ~stepCycle[t][c] = 1;
			~stepFilt[t][c] = nil; ~stepFx[t][c] = -1;
		};
		~rebuildFx.(t);                             // the per-step FX locks just went away
	}, '/ph/clearlocks'),
	OSCdef(\phVel,  { |m| ~vel[m[1].asInteger.clip(0, ~nTracks - 1)] = m[2].asFloat; }, '/ph/vel'),
	OSCdef(\phSamp, { |m| ~sampLoad.(m[1].asInteger.clip(0, ~nTracks - 1), m[2].asInteger); }, '/ph/samp'),
	OSCdef(\phMgain, { |m| ~masterSynth.notNil.if { ~masterSynth.set(\gain, m[1].asFloat) }; }, '/ph/mastergain'),
	OSCdef(\phMfilter, { |m|
		~masterSynth.notNil.if { ~masterSynth.set(\cutoff, m[1].asFloat, \res, m[2].asFloat) };
	}, '/ph/masterfilter'),
	// deepFree (not freeAll): ~gVoices now CONTAINS the per-track subgroups, and freeAll
	// would delete those groups too — leaving ~gTrackVoices pointing at dead nodes so no
	// voice could spawn again. deepFree kills every synth but keeps the group structure.
	// ---- SAMPLE engine: threshold capture + buffer hand-off ----------------------
	// /ph/smparm <srcEngine> <thresh>: arm a threshold capture on the MASTER bus. The
	// gesture auditions the tapped engine (/ph/preview -> masterBus), so master is where
	// that sound actually appears — a track bus would only carry a SEQUENCED track. The capture synth latches on the
	// first crossing and frees itself when the buffer fills (or times out).
	OSCdef(\phSmpTrig, { |m|            // \phCapture's SendTrig -> tell the controller
		(m[2].asInteger == 1701).if { ~ctrl.sendMsg("/ph/smprec") };
	}, '/tr'),
	OSCdef(\phSmpArm, { |m|                        // same pre-scaffold guard as /ph/preview
		(~ready == true).if {
			var src = m[1].asInteger.clip(0, ~nTracks - 1);
			var th = (m[2] ? 0.02).asFloat.clip(0.001, 0.5);
			~smpCapSy.notNil.if { ~smpCapSy.free; ~smpCapSy = nil };
			~smpCapBuf.notNil.if { ~smpCapBuf.free };
			// NOTE: an OSC handler is NOT a Routine, so s.sync here fails with _RoutineYield and
			// silently aborts the handler. Use Buffer.alloc's completion action instead.
			~smpCapBuf = Buffer.alloc(s, (~smpMaxDur * s.sampleRate).asInteger, 1, { |b|
				// MUST run AFTER the voices and FX have written the track bus: inside ~gVoices it
				// would read the bus ~gClear zeroes each block (and could race the writers under
				// supernova), so it goes at the head of the serial ~gSend stage — exactly where
				// the fully-processed track signal exists.
				~smpCapSy = Synth.head(~gSend, \phCapture,
					[\in, ~masterBus.index, \buf, b.bufnum, \thresh, th, \timeout, 8]);
				~smpCapSy.onFree({ ~smpCapSy = nil; ~ctrl.sendMsg("/ph/smpdone") });
			});
		};
	}, '/ph/smparm'),
	// /ph/smpwrite "<path>": flush the captured buffer to disk for the Csound mangler.
	OSCdef(\phSmpWrite, { |m|
		var path = m[1].asString;
		~smpCapBuf.notNil.if({
			~smpCapBuf.write(path, "wav", "int16", -1, 0, false,
				{ ~ctrl.sendMsg("/ph/smpwritten", path) });
		}, { ~ctrl.sendMsg("/ph/smpwritten", "") });
	}, '/ph/smpwrite'),
	// /ph/smpload "<path>": the MANGLED result becomes the pad's sound (auditionable).
	OSCdef(\phSmpLoad, { |m|
		var path = m[1].asString;
		Buffer.readChannel(s, path, channels: [0], action: { |b|
			var old = ~smpPad; ~smpPad = b; old.notNil.if { old.free };
			~ctrl.sendMsg("/ph/smpready", b.numFrames / s.sampleRate);
		});
	}, '/ph/smpload'),
	// /ph/smpassign <track>: hand the pad's buffer to a TRACK and RELEASE the pad, so the
	// engine is immediately free for the next capture. The track owns its buffer from here.
	OSCdef(\phSmpAssign, { |m|
		// Assign by FILE, not by handing over the pad's Buffer object: the pad's buffer lives
		// through capture/alloc/free churn, so sharing it risks the track pointing at a
		// recycled (zeroed) bufnum. Reading a fresh buffer per track is aliasing-proof, and
		// the pad is released either way.
		var t = m[1].asInteger.clip(0, ~nTracks - 1);
		var path = m[2].asString;
		File.exists(path).if({
			Buffer.readChannel(s, path, channels: [0], action: { |b|
				var old = ~smpBuf[t];
				~smpBuf[t] = b;
				old.notNil.if { old.free };
			});
		});
		~smpPad.notNil.if { ~smpPad.free; ~smpPad = nil };   // pad released for the next take
	}, '/ph/smpassign'),
	// /ph/smpcopy <src> <dst>: give the destination track its OWN copy of the source track's
	// sample. A COPY, not a shared reference — the two tracks must be able to diverge, and a
	// later re-assign or free on one must not pull the buffer out from under the other.
	OSCdef(\phSmpCopy, { |m|
		var a = m[1].asInteger.clip(0, ~nTracks - 1), b = m[2].asInteger.clip(0, ~nTracks - 1);
		var src = ~smpBuf[a];
		(a != b).if {
			src.notNil.if({
				// Allocate, WAIT for the server, then copy, then WAIT again before the track
				// points at it. An alloc completion-message can\'t be used here: it is built
				// (and its side effects run) before /b_alloc is even sent, so the copy would
				// race the allocation and land on a buffer that does not exist yet.
				fork {
					var nb = Buffer.alloc(s, src.numFrames, src.numChannels);
					s.sync;
					src.copyData(nb);
					s.sync;
					{ var old = ~smpBuf[b]; ~smpBuf[b] = nb; old.notNil.if { old.free } }.value;
				};
			}, {
				~smpBuf[b].notNil.if { ~smpBuf[b].free; ~smpBuf[b] = nil };
			});
		};
	}, '/ph/smpcopy'),
	// PANIC frees everything under ~gVoices, which includes the persistent bytebeat voices —
	// forget them here so the next hit rebuilds (and re-parses) them.
	OSCdef(\phPanic, { |m|
		~stopSeq.value; ~gVoices.notNil.if { ~gVoices.deepFree }; ~trackVoices.do { |l| l.clear };
		~nTracks.do { |t| ~bbVoice[t] = nil; ~csVoice[t] = nil }; ~bbPrevVoice = nil; ~bbPrevExpr = nil;
	}, '/ph/panic'),
	OSCdef(\phRecStart, { |m| ~recStart.value(m[1].asString); }, '/ph/recstart'),
	OSCdef(\phRecStop,  { |m| ~recStop.value; }, '/ph/recstop'),
	// master level from \phAmp -> forward to the controller (drives tail-end detection)
	OSCdef(\phAmpRep,   { |m| ~ready.if { ~ctrl.sendMsg("/ph/amp", m[3].asFloat) }; }, '/ph/amprep'),
	OSCdef(\phPing, { |m| ~ready.if { ~ctrl.sendMsg("/ph/ready") }; }, '/ph/ping'),
];

// ================= boot =================
~boot = { |sr = 44100, block = 128, channels = 2, inputs|
	s.options.numOutputBusChannels = channels;
	// INPUTS are no longer the same count as outputs: 0-1 are the microphone, 2-33 are the
	// CSOUND engine's 16 stereo track returns over JACK. Defaulting this to `channels`
	// silently un-did boot.scd's setting and left supernova with 2 inputs, so every one of
	// the 32 Csound connections failed.
	s.options.numInputBusChannels = inputs ? channels;
	s.options.sampleRate = sr;
	s.options.blockSize = block;
	s.options.memSize = 256 * 1024;
	s.options.maxNodes = 4096;
	s.waitForBoot({
		~buildDefs.(2);            // from synthdefs.scd
		s.sync;
		~sampScan.value;
		~wtScan.value;             // enumerate Ableton Wavetable sprites
		~scaffold.value;           // buses + groups + master + silent buffer
		s.sync;
		s.startAliveThread;
		~ready = true;
		~nTracks.do { |t| ~rebuildFx.(t) };   // apply everything pushed before the scaffold
		~ctrl.sendMsg("/ph/ready");
		("PoundHard engine ready — " ++ ~sampFiles.size ++ " samples").postln;
		SystemClock.sched(1.0, {
			~ready.if { ~ctrl.sendMsg("/ph/cpu", s.avgCPU.round(0.1), s.peakCPU.round(0.1), s.numSynths) };
			1.0;
		});
	});
};
)
