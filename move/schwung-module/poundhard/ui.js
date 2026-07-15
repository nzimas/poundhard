// PoundHard — Schwung overtake runner (16-track groovebox).
//
// TRACKS view (default): the 16 STEP buttons are the 16 tracks; the TOP ROW of pads
// (cells 0..7) is the ENGINE PALETTE — one pad per assignable engine, in its hue.
//   Step buttons:
//   * short tap                      mute / unmute that track
//   * double tap                     solo that track (double-tap again to un-solo)
//   * hold                           open that track in the 32-step EDIT view
//   Engine palette (top-row pads):
//   * short press                    audition that engine's current sound (one hit)
//   * Shift + pad                    regenerate that engine's sound
//   * hold pad + tap a step button   ASSIGN that engine + sound to the track
//   Buttons / knobs:
//   * Shift + Track 1                re-roll the OPEN track's sound (its engine)
//   * Play (green while running)     start / stop the sequencer
//   * Knob 1                         tempo (BPM)
//   * Back                           exit the runner
//   Tracks start EMPTY (dark, silent) until an engine is assigned from the palette.
// EDIT view (a track open): the 32 pads are that track's step sequencer.
//   * pad short tap                  toggle that step (in-length pads glow dim)
//   * Shift + pad                    set that pad as the LAST step (polymeter)
//   * pad HOLD (active step)         PARAM-LOCK that step — Knob 1 pitch,
//                                    Knob 2 velocity, Knob 3 pan / macro
//   * jog = pitch · cursors = rate · Knob 3 = voice macro
//   * playhead pad                   white while running

import {
    Black, VividYellow, White, BrightGreen,
    MoveShift, MoveBack, MovePlay, MoveKnob1, MoveKnob1Touch, MoveKnob8Touch,
    MoveMasterTouch, MoveRow1, MoveRow2, MoveRow3, MoveMenu, MoveLeft, MoveRight, MoveMainKnob, MoveMainTouch
} from '/data/UserData/move-anything/shared/constants.mjs';
import { setLED, setButtonLED, decodeDelta } from '/data/UserData/move-anything/shared/input_filter.mjs';

const PH = '/data/UserData/poundhard';
const MODULE_DIR = '/data/UserData/schwung/modules/overtake/poundhard';
const HOOKS_DIR = '/data/UserData/schwung/hooks';
// IPC dir under /data/UserData (the Schwung host only reads files there). A real
// directory — NOT the SC bundle's $PH/share, and NOT a tmpfs symlink (the host
// hangs reading through one).
const STATUS_FILE = PH + '/ipc/status.json';
const CONTROL_FILE = PH + '/ipc/control.json';
const HB_FILE = PH + '/ipc/ui_hb.txt';

const PAD_NOTES = [
    92, 93, 94, 95, 96, 97, 98, 99,
    84, 85, 86, 87, 88, 89, 90, 91,
    76, 77, 78, 79, 80, 81, 82, 83,
    68, 69, 70, 71, 72, 73, 74, 75
];
const NOTE_TO_CELL = {};
for (let i = 0; i < 32; i++) NOTE_TO_CELL[PAD_NOTES[i]] = i;
const STEP_BASE = 16;
const N_TRACKS = 16, N_STEPS = 32;
const HOLD_MS = 350;
const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
const RATES = [0.125, 0.25, 0.5, 1, 2, 4, 8];    /* clock rate ladder: /8 /4 /2 1 x2 x4 x8 */
const RATE_CENTER = 3;                            /* index of x1 (master clock) */

const TRACK_COLOR = VividYellow;    /* active step / unmuted track */
const DIM_COLOR = 74;               /* very-dark-yellow: in-length inactive step */
const SEL_COLOR = White;            /* playhead / selected edit track */
const OFF_COLOR = Black;            /* muted track / out-of-length step */
/* 8 distinct FX pad colours (canonical chain order: OD AMP CRSH RING FLNG GRN DLY VRB) */
const FX_COLORS = [3, 27, 14, 21, 12, 31, 16, 20];
const BYPASS_COLOR = 118;           /* light grey: a track whose FX are bypassed (visible) */
const N_FX = 8;
const FX_CELL0 = 24;                /* FX pads occupy the bottom row (cells 24..31) */

/* Per-generator-type step-button colours [bright, dim] — same hue, two brightnesses.
 * The step buttons are grouped by generator (see kits.py) so each block is one hue:
 * DRUM=yellow, RINGS=cyan, BUCHLOID=magenta, FMTONE=green, MOLLY=blue. A track with
 * events PULSES bright<->dim at its sequence pace; muted/empty tracks sit steady dim. */
const TYPE_COL = {
    DRUM:     [7, 74],    /* VividYellow / VeryDarkYellow */
    RINGS:    [14, 87],   /* Cyan / DarkTeal */
    BUCHLOID: [21, 107],  /* HotMagenta / DarkPurple */
    FMTONE:   [8, 80],    /* BrightGreen / VeryDarkGreen */
    MOLLY:    [16, 95],   /* RoyalBlue / DarkBlue — dim MUST come from the dark band (74-107),
                           * not the bright band: Navy(17) reads as lit and swamped the pulse. */
    BEN:      [2, 67],    /* OrangeRed / Brick — the Benjolin chaos machine */
    NOIZEOP:  [23, 109],  /* NeonPink / DeepMagenta — deeg's NoizeOp glitch-noise */
    ICARUS:   [18, 105],  /* BlueViolet / MutedViolet — schollz's Icarus drone/pad */
};
/* Engine palette: the 8 assignable engines, one per top-row pad (cells 0..7).
 * Same order & colours as TYPE_COL. Short-press = audition, Shift+pad = regenerate,
 * hold pad + tap a track (step button) = assign that engine's current sound. */
const ENGINE_TYPES = ['DRUM', 'FMTONE', 'BUCHLOID', 'MOLLY', 'RINGS', 'BEN', 'NOIZEOP', 'ICARUS'];
const N_ENGINES = ENGINE_TYPES.length;

/* ---- runtime state (mirrors status.json) ---- */
let phase = 0, launched = false, lastStatusAt = -100;
let ready = false, engine = false, cpu = 0;
let running = false, tempo = 120, step = -1, kitName = '';
let editTrack = -1;
let muted = new Array(N_TRACKS).fill(false);
let active = new Array(N_TRACKS).fill(false);
let types = new Array(N_TRACKS).fill('EMPTY');
let names = new Array(N_TRACKS).fill('');
let trackNote = new Array(N_TRACKS).fill(60);
let trackVel = new Array(N_TRACKS).fill(1.0);
let trackVol = new Array(N_TRACKS).fill(0.8);
let trackPan = new Array(N_TRACKS).fill(0.0);
let trackRate = new Array(N_TRACKS).fill(1.0);
let trackLen = new Array(N_TRACKS).fill(N_STEPS);
let voiceMacro = new Array(N_TRACKS).fill(0.5);   /* knob-3 voice-macro position per track */
/* PATTERN + PROJECT views (Track3 button / Menu button): 32 pads = 32 slots. */
let patView = false, projView = false;
let patFilled = new Array(N_STEPS).fill(false), patCur = -1, patPending = -1;
let projFilled = new Array(N_STEPS).fill(false);
/* RECORDER view (Shift + Track3): 8 pads = 8 recording slots. */
let recView = false;
let recSlots = new Array(8).fill(false), recSlot = -1, recState = 'idle', recElapsed = 0;
let webPort = 7177;
/* SOLO: double-tap a step button. (Shift+step is NOT used — Shift + step-13 is a fatal
 * Move firmware combo that floods MIDI and gets the module watchdog-killed.) */
let solo = -1;
let lastTapAt = new Array(N_TRACKS).fill(0);
const DOUBLE_MS = 320;
let editSteps = new Array(N_STEPS).fill(0);
let editName = '', editType = '';
let stepNote = new Array(N_STEPS).fill(60);
let stepVel = new Array(N_STEPS).fill(1.0);
let stepPan = new Array(N_STEPS).fill(0.0);
let stepMacro = new Array(N_STEPS).fill(0.5);   /* per-step voice-macro lock position */
/* step-button pulse: a local beat clock (tempo-driven) drives the per-track pulse so
 * event-tracks blink at their sequence pace. lastStepCol dedups setLED (only send on change). */
let seqBeats = 0, lastPulseMs = 0, wasRunning = false;
let lastStepCol = new Array(N_TRACKS).fill(-1);

let shiftHeld = false, masterTouched = false;
let seq = 0, cmdQueue = [];
let tempoLocal = 120, tempoDirty = false, controlDirty = false;
/* pad hold -> per-step param lock */
let heldCell = -1, heldStart = 0, heldStepEdit = false;
let stepEditCell = -1;
/* track-button hold -> track settings */
let trackHeld = -1, trackHeldStart = 0, trackActive = false;
/* engine palette (default tracks view, top row): hold an engine pad, tap a track to
 * assign. paletteConsumed suppresses the pad-release audition once an assign happened. */
let paletteHeld = -1, paletteHeldStart = 0, paletteConsumed = false;
let knobShow = null;                /* 'pitch'|'vel'|'pan'|null (big readout) */
let rateView = -1, rateViewUntil = 0;   /* transient big clock-rate readout (cursor keys) */
/* FX view */
let fxView = false, fxHeld = -1;
let fxTop = new Array(N_TRACKS).fill(-1);
let fxOn = [];                       /* per-track list of assigned fx indices (from status) */
for (let i = 0; i < N_TRACKS; i++) fxOn.push([]);
let fxBypass = new Array(N_TRACKS).fill(false);
let fxMacro = new Array(N_FX).fill(0.5);
let fxWet = new Array(N_FX).fill(0.5);   /* per-fx dry/wet (Shift + FX macro knob) */
let fxNames = ['OD', 'AMP', 'CRSH', 'RING', 'FLNG', 'GRN', 'DLY', 'VRB'];
let overlay = null, overlayUntil = -1;
let ledDirty = true, screenDirty = true, lastLedSig = '', lastScreenSig = '', lastDrawAt = -100;

function sys(cmd) { if (typeof host_system_cmd === 'function') host_system_cmd(cmd); }
function clampi(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x; }
function clampf(x, lo, hi) { return x < lo ? lo : x > hi ? hi : x; }
function noteName(n) { n = Math.round(n); return NOTE_NAMES[((n % 12) + 12) % 12] + (Math.floor(n / 12) - 1); }
function velMidi(v) { return Math.round(clampf(v, 0, 2) / 2 * 127); }
function panLbl(p) { return Math.abs(p) < 0.01 ? 'C' : (p > 0 ? 'R' + Math.round(p * 100) : 'L' + Math.round(-p * 100)); }
function rateLbl(r) { return r === 1 ? '1' : (r < 1 ? ('/' + Math.round(1 / r)) : ('x' + Math.round(r))); }
function rateIndex(r) { var bi = 0, bd = 1e9; for (var i = 0; i < RATES.length; i++) { var d = Math.abs(RATES[i] - r); if (d < bd) { bd = d; bi = i; } } return bi; }
function editLen() { return (editTrack >= 0 && trackLen[editTrack]) ? trackLen[editTrack] : N_STEPS; }

/* ---- big block-glyph renderer (accessibility: values must be large) ---- */
const FONT = {
    '0': ['###', '# #', '# #', '# #', '###'], '1': [' # ', '## ', ' # ', ' # ', '###'],
    '2': ['###', '  #', '###', '#  ', '###'], '3': ['###', '  #', ' ##', '  #', '###'],
    '4': ['# #', '# #', '###', '  #', '  #'], '5': ['###', '#  ', '###', '  #', '###'],
    '6': ['###', '#  ', '###', '# #', '###'], '7': ['###', '  #', '  #', '  #', '  #'],
    '8': ['###', '# #', '###', '# #', '###'], '9': ['###', '# #', '###', '  #', '###'],
    'A': [' # ', '# #', '###', '# #', '# #'], 'B': ['## ', '# #', '## ', '# #', '## '],
    'C': ['###', '#  ', '#  ', '#  ', '###'], 'D': ['## ', '# #', '# #', '# #', '## '],
    'E': ['###', '#  ', '## ', '#  ', '###'], 'F': ['###', '#  ', '## ', '#  ', '#  '],
    'G': ['###', '#  ', '# #', '# #', '###'], 'H': ['# #', '# #', '###', '# #', '# #'],
    'I': ['###', ' # ', ' # ', ' # ', '###'], 'J': ['  #', '  #', '  #', '# #', '###'],
    'K': ['# #', '# #', '## ', '# #', '# #'], 'L': ['#  ', '#  ', '#  ', '#  ', '###'],
    'M': ['# #', '###', '###', '# #', '# #'], 'N': ['# #', '###', '###', '###', '# #'],
    'O': ['###', '# #', '# #', '# #', '###'], 'P': ['###', '# #', '###', '#  ', '#  '],
    'Q': ['###', '# #', '# #', '###', '  #'], 'R': ['## ', '# #', '## ', '# #', '# #'],
    'S': ['###', '#  ', '###', '  #', '###'], 'T': ['###', ' # ', ' # ', ' # ', ' # '],
    'U': ['# #', '# #', '# #', '# #', '###'], 'V': ['# #', '# #', '# #', '# #', ' # '],
    'W': ['# #', '# #', '###', '###', '# #'], 'X': ['# #', ' # ', ' # ', ' # ', '# #'],
    'Y': ['# #', '# #', ' # ', ' # ', ' # '], 'Z': ['###', '  #', ' # ', '#  ', '###'],
    '#': ['# #', '###', '# #', '###', '# #'], '-': ['   ', '   ', '###', '   ', '   '],
    '.': ['   ', '   ', '   ', '   ', ' # '], '/': ['  #', '  #', ' # ', '#  ', '#  '],
    ':': ['   ', ' # ', '   ', ' # ', '   '], ' ': ['   ', '   ', '   ', '   ', '   ']
};
function drawBig(text, yTop, maxScale) {
    if (typeof fill_rect !== 'function') return;
    text = String(text).toUpperCase();
    var n = text.length || 1;
    var scale = Math.max(3, Math.min(maxScale || 11, Math.floor(122 / (4 * n - 1))));
    var gw = 3 * scale, gap = scale, totalW = n * gw + (n - 1) * gap;
    var x0 = Math.max(0, Math.floor((128 - totalW) / 2));
    for (var i = 0; i < text.length; i++) {
        var g = FONT[text[i]] || FONT[' '];
        var gx = x0 + i * (gw + gap);
        for (var r = 0; r < 5; r++) {
            var row = g[r], c = 0;
            while (c < 3) {                          /* draw contiguous '#' as one wide rect (fewer host calls) */
                if (row.charCodeAt(c) === 35) {
                    var s = c;
                    while (c < 3 && row.charCodeAt(c) === 35) c++;
                    fill_rect(gx + s * scale, yTop + r * scale, (c - s) * scale, scale, 1);
                } else { c++; }
            }
        }
    }
}

/* ---- control.json (ui.js -> controller), queued so rapid commands aren't lost ---- */
function writeControl() {
    if (typeof host_write_file !== 'function') return;
    const doc = { seq: seq, cmds: cmdQueue };
    if (tempoDirty) doc.tempo = tempoLocal;
    host_write_file(CONTROL_FILE, JSON.stringify(doc));
}
function sendCmd(cmd, arg, extra) {
    seq++;
    const entry = { seq: seq, cmd: cmd, arg: arg };
    if (extra && extra.p) entry.p = extra.p;
    cmdQueue.push(entry);
    if (cmdQueue.length > 24) cmdQueue = cmdQueue.slice(-24);
    /* Coalesce: flag dirty and let tick() flush at most once per frame. Rapid
     * navigation / knob sweeps otherwise burst host_write_file calls, and every
     * write loads the SD card and raises the odds of the read-stall that freezes us.
     * The queue + seq dedup on the controller make batching lossless. */
    controlDirty = true;
}
function showAction(label) { overlay = label; overlayUntil = phase + 24; screenDirty = true; }

/* ---- LEDs ---- */
function btnLED(cc, color) { try { setButtonLED(cc, color); } catch (e) {} }   /* buttons use CC */
/* Is track t's pulse in its bright phase right now? Pulses at the beat scaled by the
 * track's clock rate (so a x2 track blinks twice as fast, /2 half), a brief flash each. */
function trackPulseOn(t) {
    var ph = seqBeats * (trackRate[t] || 1);
    return (ph - Math.floor(ph)) < 0.4;
}
/* Colour for track t's step button: white if it's the open edit track; otherwise the
 * track's generator hue — pulsing bright when it has events & is playing, else dim. */
function stepColor(t) {
    if (editTrack === t) return SEL_COLOR;
    var pair = TYPE_COL[types[t]];
    if (!pair) return OFF_COLOR;                /* empty / unassigned track -> dark */
    /* a soloed track silences every other one — show them as muted without touching flags */
    if (muted[t] || (solo >= 0 && solo !== t)) return pair[1];   /* muted / not-soloed -> dim */
    if (active[t]) return (running ? (trackPulseOn(t) ? pair[0] : pair[1]) : pair[0]);  /* events */
    return pair[1];                             /* unmuted but empty -> steady dim */
}
/* Push the 16 step-button LEDs, only re-sending the ones whose colour changed. */
function renderStepButtons() {
    for (let t = 0; t < N_TRACKS; t++) {
        var col = stepColor(t);
        if (col !== lastStepCol[t]) { setLED(STEP_BASE + t, col); lastStepCol[t] = col; }
    }
}
function renderLEDs() {
    if (patView || projView || recView) {              /* pads = slots */
        for (let c = 0; c < 32; c++) {
            let color;
            if (recView) {                                          /* 8 recording slots */
                if (c >= 8) color = Black;
                else if (c === recSlot && recState === 'recording') color = (phase % 16 < 8) ? 1 : 66;   /* red pulse */
                else if (c === recSlot && recState === 'tail') color = (phase % 20 < 10) ? 28 : 66;      /* amber: capturing tail */
                else if (c === recSlot && recState === 'armed') color = (phase % 30 < 15) ? 28 : Black;   /* amber blink */
                else color = recSlots[c] ? BrightGreen : 124;       /* green = has a take / dark-grey empty */
            } else if (projView) color = projFilled[c] ? 16 : 95;   /* RoyalBlue filled / DarkBlue empty */
            else if (c === patPending) color = trackPulseOn(0) ? White : 50;  /* queued: pulse periwinkle */
            else if (c === patCur) color = White;                   /* currently playing */
            else color = patFilled[c] ? 50 : 102;                   /* LavenderBlue(periwinkle) / DarkIndigo empty */
            setLED(PAD_NOTES[c], color);
        }
        renderStepButtons();
        btnLED(MoveRow1, TRACK_COLOR); btnLED(MoveRow2, Black);
        btnLED(MoveRow3, recView ? 1 : (patView ? White : Black)); btnLED(MoveMenu, projView ? White : Black);
        btnLED(MovePlay, running ? BrightGreen : Black);
        ledDirty = false;
        return;
    }
    if (fxView) {
        for (let c = 0; c < 32; c++) {
            let color = Black;
            if (c < N_TRACKS) {                        /* rows 0-1: tracks (dimly lit by default) */
                if (fxHeld >= 0) {                     /* holding an FX -> show ITS membership per track */
                    let has = fxOn[c] && fxOn[c].indexOf(fxHeld) >= 0;
                    color = has ? FX_COLORS[fxHeld] : DIM_COLOR;
                } else {
                    let top = fxTop[c];
                    color = (top < 0) ? DIM_COLOR : (fxBypass[c] ? BYPASS_COLOR : FX_COLORS[top]);
                }
            } else if (c >= FX_CELL0) {                /* bottom row: 8 FX pads */
                let k = c - FX_CELL0;
                color = (fxHeld === k) ? White : FX_COLORS[k];
            }
            setLED(PAD_NOTES[c], color);
        }
        renderStepButtons();
        btnLED(MoveRow1, TRACK_COLOR); btnLED(MoveRow2, White);   /* Row2 lit = FX view active */
        btnLED(MoveRow3, Black); btnLED(MoveMenu, Black);
        btnLED(MovePlay, running ? BrightGreen : Black);
        ledDirty = false;
        return;
    }
    if (editTrack < 0) {
        /* DEFAULT tracks view: top row (cells 0..7) = the engine palette; rest dark.
         * A held engine pad shows white; the others glow in their engine hue. */
        for (let c = 0; c < 32; c++) {
            let color = OFF_COLOR;
            if (c < N_ENGINES) {
                let pair = TYPE_COL[ENGINE_TYPES[c]];
                color = (paletteHeld === c) ? White : (pair ? pair[0] : DIM_COLOR);
            }
            setLED(PAD_NOTES[c], color);
        }
    } else {
        const len = editLen();
        for (let c = 0; c < 32; c++) {
            let color;
            if (c >= len) color = OFF_COLOR;                       /* past the last step */
            else if (running && c === step) color = SEL_COLOR;     /* playhead */
            else color = editSteps[c] ? TRACK_COLOR : DIM_COLOR;   /* active / dim idle */
            setLED(PAD_NOTES[c], color);
        }
    }
    renderStepButtons();
    btnLED(MoveRow1, TRACK_COLOR);
    btnLED(MoveRow2, Black);
    btnLED(MoveRow3, Black); btnLED(MoveMenu, Black);
    btnLED(MovePlay, running ? BrightGreen : Black);
    ledDirty = false;
}

/* ---- screen ---- */
function bar(frac) {
    if (typeof draw_rect === 'function') draw_rect(6, 46, 116, 14, 1);
    if (typeof fill_rect === 'function') fill_rect(8, 48, Math.max(0, Math.round(frac * 112)), 10, 1);
}
function bbar(val) {
    if (typeof draw_rect !== 'function') return;
    draw_rect(6, 46, 116, 14, 1);
    var cx = 64, w = Math.round(Math.abs(val) * 56);
    if (val >= 0) fill_rect(cx, 48, w, 10, 1); else fill_rect(cx - w, 48, w, 10, 1);
    fill_rect(cx, 46, 1, 14, 1);
}
function drawParamBig(head, valStr, kind, frac) {
    clear_screen();
    print(0, 0, head, 1);
    if (kind === null) { drawBig(valStr, 12, 10); }        /* no bar -> value can be huge */
    else { drawBig(valStr, 4, 7); if (kind === 'uni') bar(frac); else bbar(frac); }
}
function drawTempoBig() { drawParamBig('TEMPO', '' + Math.round(tempo), 'uni', clampf((tempo - 20) / 280, 0, 1)); }
function drawStepParam() {
    var c = stepEditCell;
    if (knobShow === 'pitch') drawParamBig('STEP PITCH', noteName(stepNote[c]), null, 0);
    else if (knobShow === 'vel') drawParamBig('STEP VELOCITY', '' + velMidi(stepVel[c]), 'uni', clampf(stepVel[c] / 2, 0, 1));
    else if (knobShow === 'pan') drawParamBig('STEP PAN', panLbl(stepPan[c]), 'bi', clampf(stepPan[c], -1, 1));
    else if (knobShow === 'macro') drawParamBig('STEP MACRO', '' + Math.round(stepMacro[c] * 100), 'uni', clampf(stepMacro[c], 0, 1));
    else {
        clear_screen();
        print(0, 2, 'STEP ' + (c + 1), 2);
        print(0, 30, noteName(stepNote[c]) + ' v' + velMidi(stepVel[c]) + ' ' + panLbl(stepPan[c]), 2);
        print(0, 54, 'jog pit k1vel k2pan k3macro', 1);
    }
}
function drawTrackParam() {
    var t = (trackHeld >= 0) ? trackHeld : editTrack;
    if (t < 0) return;
    var L = 'T' + (t + 1);
    if (knobShow === 'pitch') drawParamBig(L + ' PITCH', noteName(trackNote[t]), null, 0);
    else if (knobShow === 'vol') drawParamBig(L + ' VOLUME', '' + velMidi(trackVol[t]), 'uni', clampf(trackVol[t] / 2, 0, 1));
    else if (knobShow === 'pan') drawParamBig(L + ' PAN', panLbl(trackPan[t]), 'bi', clampf(trackPan[t], -1, 1));
    else if (knobShow === 'macro') drawParamBig(L + ' MACRO', '' + Math.round(voiceMacro[t] * 100), 'uni', clampf(voiceMacro[t], 0, 1));
    else {
        clear_screen();
        print(0, 2, L + ' ' + (names[t] || types[t]), 2);
        print(0, 30, noteName(trackNote[t]) + ' vol' + velMidi(trackVol[t]) + ' ' + panLbl(trackPan[t]), 2);
        print(0, 54, 'jog pit k1vol k2pan k3macro', 1);
    }
}
function drawRateBig(t) {
    clear_screen();
    print(0, 0, 'T' + (t + 1) + ' CLOCK RATE', 1);
    drawBig(rateLbl(trackRate[t]), 4, 7);
    bbar((rateIndex(trackRate[t]) - RATE_CENTER) / RATE_CENTER);
}
function drawFx() {
    clear_screen();
    if (knobShow && knobShow.indexOf('fw') === 0) {              /* an FX dry/wet knob is touched */
        var wk = parseInt(knobShow.slice(2), 10);
        print(0, 0, fxNames[wk] + ' DRY/WET', 1);
        drawBig('' + Math.round(fxWet[wk] * 100), 4, 7); bar(fxWet[wk]);
        return;
    }
    if (knobShow && knobShow.indexOf('fx') === 0) {              /* an FX macro knob is touched */
        var mk = parseInt(knobShow.slice(2), 10);
        print(0, 0, fxNames[mk] + ' MACRO', 1);
        drawBig('' + Math.round(fxMacro[mk] * 100), 4, 7); bar(fxMacro[mk]);
        return;
    }
    if (fxHeld >= 0) {
        print(0, 0, 'ASSIGN - tap tracks', 1); drawBig(fxNames[fxHeld], 12, 10);
        return;
    }
    if (overlay && phase < overlayUntil) { print(0, 22, overlay, 2); return; }
    print(0, 6, 'FX', 2);
    print(0, 30, 'hold fx + tap tracks', 1);
    print(0, 44, 'tap track=bypass  shift+knob=wet', 1);
    print(0, 56, 'knobs 1-8 = macros', 1);
}
function drawRec() {
    if (recState === 'recording' || recState === 'tail') {
        var mm = Math.floor(recElapsed / 60), ss = recElapsed % 60;
        drawParamBig((recState === 'tail' ? 'TAIL ' : 'REC ') + (recSlot + 1),
            mm + ':' + (ss < 10 ? ('0' + ss) : ('' + ss)), 'uni', clampf(recElapsed / 420, 0, 1));
        return;
    }
    clear_screen();
    if (overlay && phase < overlayUntil) { print(0, 22, overlay, 2); return; }
    print(0, 4, 'RECORDER', 2);
    if (recState === 'armed') {
        print(0, 30, 'ARMED ' + (recSlot + 1), 2);
        print(0, 54, 'press PLAY (or pad = now)', 1);
    } else {
        var n = 0; for (var i = 0; i < 8; i++) n += recSlots[i] ? 1 : 0;
        print(0, 30, n + '/8 takes   tap a pad', 1);
        print(0, 46, 'move.local:' + webPort, 1);
        print(0, 58, 'pad/play stops   max 7min', 1);
    }
}
function drawSlots() {
    clear_screen();
    if (overlay && phase < overlayUntil) { print(0, 22, overlay, 2); return; }
    if (projView) {
        var np = 0; for (var i = 0; i < 32; i++) np += projFilled[i] ? 1 : 0;
        print(0, 6, 'PROJECTS', 2);
        print(0, 32, np + '/32 saved', 1);
        print(0, 48, 'tap=load  shift+pad=save', 1);
    } else {
        var n = 0; for (var j = 0; j < 32; j++) n += patFilled[j] ? 1 : 0;
        print(0, 6, 'PATTERNS', 2);
        print(0, 32, n + '/32' + (patCur >= 0 ? ('  cur' + (patCur + 1)) : '') + (patPending >= 0 ? (' >' + (patPending + 1)) : ''), 1);
        print(0, 48, 'tap=load  shift+pad=save', 1);
    }
}
function drawScreen() {
    if (typeof clear_screen !== 'function' || typeof print !== 'function') return;
    if (recView) { drawRec(); return; }
    /* giant TEMPO readout while knob 1 is touched (tracks view + project view) */
    if (knobShow === 'tempo' && !fxView && !patView && !recView && editTrack < 0 && stepEditCell < 0) { drawTempoBig(); return; }
    if (patView || projView) { drawSlots(); return; }
    if (fxView) { drawFx(); return; }
    if (stepEditCell >= 0) { drawStepParam(); return; }
    if (rateView >= 0 && phase < rateViewUntil) { drawRateBig(rateView); return; }
    if ((trackHeld >= 0 && trackActive) || (editTrack >= 0 && knobShow)) { drawTrackParam(); return; }
    clear_screen();
    if (overlay && phase < overlayUntil) { print(0, 24, overlay, 2); return; }
    overlay = null;
    if (!ready) { print(0, 12, 'POUNDHARD', 2); print(0, 40, engine ? 'booting engine...' : 'starting...', 1); return; }
    if (editTrack < 0) {
        print(0, 6, 'POUNDHARD', 2);
        print(0, 30, Math.round(tempo) + ' BPM   ' + (running ? 'PLAY' : 'STOP'), 1);
        print(0, 44, 'pad=hear  shift+pad=gen', 1);
        print(0, 56, 'hold pad+trk=assign  cpu' + cpu + '%', 1);
    } else {
        var n = 0, len = editLen();
        for (var i = 0; i < len; i++) n += editSteps[i] ? 1 : 0;
        print(0, 6, 'T' + (editTrack + 1) + ' ' + (editName || editType), 2);
        print(0, 30, n + '/' + len + ' steps  ' + rateLbl(trackRate[editTrack] || 1), 1);
        print(0, 44, 'jog pit k1vol k2pan k3macro', 1);
        print(0, 56, 'Trk1=back   shift+pad=len', 1);
    }
}

/* ---- status.json (controller -> ui.js) ---- */
function readStatus() {
    if (typeof host_read_file !== 'function') return;
    const raw = host_read_file(STATUS_FILE);
    if (!raw) return;
    let s;
    try { s = JSON.parse(raw); } catch (e) { return; }
    ready = !!s.ready; engine = !!s.engine;
    cpu = s.cpu != null ? s.cpu : 0;
    running = !!s.running; tempo = s.tempo != null ? s.tempo : tempo;
    step = s.step != null ? s.step : -1;
    kitName = s.kit || '';
    if (Array.isArray(s.patFilled)) patFilled = s.patFilled;
    if (Array.isArray(s.projFilled)) projFilled = s.projFilled;
    if (s.solo != null) solo = s.solo;
    if (s.patCur != null) patCur = s.patCur;
    if (s.patPending != null) patPending = s.patPending;
    if (Array.isArray(s.recSlots)) recSlots = s.recSlots;
    if (s.recSlot != null) recSlot = s.recSlot;
    if (s.recState != null) recState = s.recState;
    if (s.recElapsed != null) recElapsed = s.recElapsed;
    if (s.webPort != null) webPort = s.webPort;
    if (Array.isArray(s.tracks)) {
        for (let i = 0; i < N_TRACKS; i++) {
            const tr = s.tracks[i] || {};
            muted[i] = !!tr.muted; active[i] = !!tr.active;
            if (tr.note != null && !(trackHeld === i || editTrack === i)) trackNote[i] = tr.note;   /* don't fight a live edit */
            if (tr.vel != null && !(trackHeld === i || editTrack === i)) trackVel[i] = tr.vel;
            if (tr.amp != null && !(trackHeld === i || editTrack === i)) trackVol[i] = tr.amp;
            if (tr.pan != null && !(trackHeld === i || editTrack === i)) trackPan[i] = tr.pan;
            if (tr.rate != null && !(trackHeld === i || editTrack === i)) trackRate[i] = tr.rate;
            if (tr.length != null) trackLen[i] = tr.length;
        }
    }
    if (Array.isArray(s.types)) types = s.types;
    if (Array.isArray(s.names)) names = s.names;
    if (Array.isArray(s.fxTop)) fxTop = s.fxTop;
    if (Array.isArray(s.fxOn) && fxHeld < 0) fxOn = s.fxOn;   /* don't clobber optimistic edits mid-hold */
    if (Array.isArray(s.fxBypass)) fxBypass = s.fxBypass;
    if (Array.isArray(s.fxNames)) fxNames = s.fxNames;
    if (Array.isArray(s.fxMacro)) { for (var fi = 0; fi < N_FX; fi++) if (fxHeld < 0) fxMacro[fi] = s.fxMacro[fi]; }
    if (Array.isArray(s.fxWet)) { for (var fw = 0; fw < N_FX; fw++) if (fxHeld < 0) fxWet[fw] = s.fxWet[fw]; }
    if (s.edit && Array.isArray(s.edit.steps) && s.editTrack === editTrack) {
        editSteps = s.edit.steps; editName = s.edit.name || ''; editType = s.edit.type || '';
        if (s.edit.stepNote) stepNote = s.edit.stepNote;
        if (s.edit.stepVel) stepVel = s.edit.stepVel;
        if (s.edit.stepPan) stepPan = s.edit.stepPan;
        if (s.edit.stepMacro) stepMacro = s.edit.stepMacro;
    }
    var fxSig = fxView ? ('X' + fxHeld + '|' + fxTop.join('.') + '|' + fxBypass.map(function (b) { return b ? '1' : '0'; }).join('') + '|' + fxOn.map(function (a) { return a.join(','); }).join(';')) : '';
    var base = (ready ? '1' : '0') + (running ? 'R' : 's') + editTrack + '/' + editLen() + (fxView ? 'F' : '') + 'S' + solo + '|' +
        muted.map(function (m) { return m ? '1' : '0'; }).join('') +
        active.map(function (a) { return a ? '1' : '0'; }).join('') + '|' + Math.round(tempo) + fxSig;
    /* LED sig includes the playhead (step) — a cheap 2-pad change. The SCREEN sig
     * does NOT: redrawing the (heavy block-font) screen on every step floods the
     * SPI display and freezes the Move UI. Screen redraws are driven by the input
     * handlers + real state changes only. */
    var slotSig = (patView || projView) ? ('|P' + (patView ? '1' : '0') + patCur + ',' + patPending + '|'
        + patFilled.map(function (b) { return b ? '1' : '0'; }).join('')
        + projFilled.map(function (b) { return b ? '1' : '0'; }).join(''))
        : recView ? ('|R' + recState + recSlot + ',' + recElapsed + ',' + recSlots.map(function (b) { return b ? '1' : '0'; }).join('')) : '';
    var ledSig = base + '|' + (editTrack >= 0 ? (editSteps.join('') + ':' + step) : '') + slotSig;
    var screenSig = base + '|' + (editTrack >= 0 ? editSteps.join('') : '') + slotSig;
    if (ledSig !== lastLedSig) { lastLedSig = ledSig; ledDirty = true; }
    if (screenSig !== lastScreenSig) { lastScreenSig = screenSig; screenDirty = true; }
}

/* ================= host entry points ================= */
globalThis.init = function () {
    if (typeof host_set_refresh_rate === 'function') host_set_refresh_rate(30);
    phase = 0; launched = false; lastStatusAt = -100;
    ready = false; engine = false; cpu = 0;
    running = false; tempo = 120; step = -1; kitName = '';
    editTrack = -1;
    muted = new Array(N_TRACKS).fill(false); active = new Array(N_TRACKS).fill(false);
    types = new Array(N_TRACKS).fill('EMPTY'); names = new Array(N_TRACKS).fill('');
    trackNote = new Array(N_TRACKS).fill(60); trackVel = new Array(N_TRACKS).fill(1.0);
    trackVol = new Array(N_TRACKS).fill(0.8);
    trackPan = new Array(N_TRACKS).fill(0.0); trackRate = new Array(N_TRACKS).fill(1.0);
    voiceMacro = new Array(N_TRACKS).fill(0.5);
    trackLen = new Array(N_TRACKS).fill(N_STEPS);
    editSteps = new Array(N_STEPS).fill(0); editName = ''; editType = '';
    stepNote = new Array(N_STEPS).fill(60); stepVel = new Array(N_STEPS).fill(1.0); stepPan = new Array(N_STEPS).fill(0.0);
    shiftHeld = false; masterTouched = false; seq = 0; cmdQueue = [];
    tempoLocal = 120; tempoDirty = false; controlDirty = false;
    heldCell = -1; heldStart = 0; heldStepEdit = false; stepEditCell = -1;
    trackHeld = -1; trackHeldStart = 0; trackActive = false; knobShow = null;
    rateView = -1; rateViewUntil = 0;
    fxView = false; fxHeld = -1;
    fxTop = new Array(N_TRACKS).fill(-1); fxBypass = new Array(N_TRACKS).fill(false);
    fxOn = []; for (var qi = 0; qi < N_TRACKS; qi++) fxOn.push([]);
    fxMacro = new Array(N_FX).fill(0.5); fxWet = new Array(N_FX).fill(0.5);
    overlay = null; overlayUntil = -1; ledDirty = true; screenDirty = true;
    lastLedSig = ''; lastScreenSig = ''; lastDrawAt = -100;
    seqBeats = 0; lastPulseMs = 0; wasRunning = false; lastStepCol = new Array(N_TRACKS).fill(-1);
    patView = false; projView = false; patCur = -1; patPending = -1;
    patFilled = new Array(N_STEPS).fill(false); projFilled = new Array(N_STEPS).fill(false);
    recView = false; recSlots = new Array(8).fill(false); recSlot = -1; recState = 'idle'; recElapsed = 0;
    solo = -1; lastTapAt = new Array(N_TRACKS).fill(0);
};

globalThis.tick = function () {
    phase++;
    if (phase === 2) {
        sys('mkdir -p ' + HOOKS_DIR);
        sys('cp ' + MODULE_DIR + '/exit-hook.sh ' + HOOKS_DIR + '/overtake-exit-poundhard.sh');
        sys('chmod +x ' + HOOKS_DIR + '/overtake-exit-poundhard.sh');
        sys('cp ' + MODULE_DIR + '/exit-hook.sh ' + HOOKS_DIR + '/overtake-exit.sh');
        sys('chmod +x ' + HOOKS_DIR + '/overtake-exit.sh');
    }
    if (phase === 3) {
        if (typeof clear_screen === 'function') { clear_screen(); print(0, 12, 'POUNDHARD', 2); print(0, 38, 'starting engine...', 1); }
        sys('sh -c "sh ' + PH + '/run-stack.sh &"');
        launched = true;
    }
    if (!launched) return;
    /* heartbeat (~0.13Hz, every 8s): a trickle — every host_write_file is a chance to
     * hit the SD I/O stall that hangs tick(), so keep diagnostic writes rare. */
    if (phase % 240 === 0 && typeof host_write_file === 'function') host_write_file(HB_FILE, '' + phase);
    /* flush any queued commands once per frame (coalesced from sendCmd) */
    if (controlDirty) { writeControl(); controlDirty = false; tempoDirty = false; }
    /* read status ~5Hz — the freeze is a synchronous host_read_file blocking the tick;
     * every read is exposure, so read as slowly as the playhead can tolerate. */
    if (phase - lastStatusAt >= 6) { readStatus(); lastStatusAt = phase; }
    /* pad held past threshold in EDIT view -> per-step param lock */
    if (editTrack >= 0 && heldCell >= 0 && !heldStepEdit && (Date.now() - heldStart) >= HOLD_MS) {
        heldStepEdit = true; stepEditCell = heldCell;
        if (!editSteps[heldCell]) { editSteps[heldCell] = 1; sendCmd('stepset', heldCell, { p: { track: editTrack, cell: heldCell, on: 1 } }); }
        knobShow = null; ledDirty = true; screenDirty = true;
    }
    /* step button held past threshold -> OPEN that track's edit view. Merged gesture:
     * the pads become its 32-step sequencer AND the jog/knobs/cursors edit its track
     * settings (pitch/vol/pan/rate). This replaces Shift+step, which is unusable on
     * track 13 (the hardware streams a fatal MIDI flood on Shift + that button). */
    if (trackHeld >= 0 && !trackActive && (Date.now() - trackHeldStart) >= HOLD_MS) {
        var _et = trackHeld;
        fxView = false; editTrack = _et; editSteps = new Array(N_STEPS).fill(0);
        stepEditCell = -1; heldCell = -1; heldStepEdit = false; knobShow = null;
        trackActive = true;   /* mark the hold consumed so the release doesn't also mute */
        sendCmd('editenter', _et); ledDirty = true; screenDirty = true; showAction('EDIT T' + (_et + 1));
    }
    if (rateView >= 0 && phase >= rateViewUntil) { rateView = -1; screenDirty = true; }
    /* advance the local beat clock that drives the step-button pulse (re-anchored to
     * play-start so the pulse tracks the sequence pace; tempo comes from status). */
    var _now = Date.now();
    if (running && !wasRunning) seqBeats = 0;
    if (running) seqBeats += Math.max(0, _now - lastPulseMs) / 1000 * (tempo / 60);
    wasRunning = running; lastPulseMs = _now;
    if (running && patView && patPending >= 0) ledDirty = true;   /* animate the queued-slot pulse */
    if (recView && recState !== 'idle') ledDirty = true;          /* animate the rec/armed pad */
    if (ledDirty) renderLEDs();
    if (running) renderStepButtons();   /* keep the pulse animating between full renders */
    if (overlay && phase >= overlayUntil) { overlay = null; screenDirty = true; }
    /* throttle screen redraws to ~10Hz — the block-font screens are heavy on the
     * SPI display; flooding it freezes the Move UI. */
    if (screenDirty && (phase - lastDrawAt >= 3)) { drawScreen(); screenDirty = false; lastDrawAt = phase; }
};

globalThis.onMidiMessageInternal = function (data) {
    /* Robustness guard: the Move emits a low background trickle of malformed zero-byte
     * messages ([0,0,0]), and holding Shift + track 13 turns that into a fatal FLOOD
     * (thousands/sec) that starves tick() and gets the module watchdog-killed. Real
     * channel-voice MIDI has a status byte in 0x80..0xEF — drop anything else cheaply. */
    if (!data || data.length < 3 || data[0] < 0x80 || data[0] >= 0xF0) return;
    const status = data[0] & 0xF0;
    const d1 = data[1];
    const d2 = data[2];

    /* volume-knob touch = modifier (whole-kit gesture) */
    if (d1 === MoveMasterTouch && (status === 0x90 || status === 0x80)) {
        masterTouched = (status === 0x90 && d2 >= 64); return;
    }
    /* jog-wheel touch: show PITCH big (pitch lives on the jog now) */
    if (d1 === MoveMainTouch && (status === 0x90 || status === 0x80)) {
        var jt = (status === 0x90 && d2 >= 64);
        if (stepEditCell >= 0 || editTrack >= 0) {
            if (jt) { knobShow = 'pitch'; screenDirty = true; }
            else if (knobShow === 'pitch') { knobShow = null; screenDirty = true; }
        }
        return;
    }
    /* encoder touch: show the value big for the active param context (k1/k2) */
    if (d1 >= MoveKnob1Touch && d1 <= MoveKnob8Touch && (status === 0x90 || status === 0x80)) {
        var ki = d1 - MoveKnob1Touch;
        var touched = (status === 0x90 && d2 >= 64);
        var which = null;
        if (fxView) which = (ki < N_FX) ? ((shiftHeld ? 'fw' : 'fx') + ki) : null;       /* FX macro / dry-wet N */
        else if (projView) which = (ki === 0) ? 'tempo' : null;                          /* project settings */
        else if (stepEditCell >= 0) which = (ki === 0) ? 'vel' : (ki === 1) ? 'pan' : (ki === 2) ? 'macro' : null;
        else if (editTrack >= 0) which = (ki === 0) ? 'vol' : (ki === 1) ? 'pan' : (ki === 2) ? 'macro' : null;
        else if (!patView && !recView) which = (ki === 0) ? 'tempo' : null;              /* tracks view: knob1 = tempo */
        /* Uniform rule: the giant readout shows the whole time the knob is TOUCHED
         * (not just while turning), and clears on release. */
        if (which) {
            if (touched) { knobShow = which; screenDirty = true; }
            else if (knobShow === which) { knobShow = null; screenDirty = true; }
        }
        return;
    }

    /* Step buttons (16..31) = tracks: tap=mute, double-tap=solo, hold=edit; while an
     * engine pad is held (default view), a tap ASSIGNS that engine's sound to the track. */
    if (status === 0x90 && d2 > 0 && d1 >= STEP_BASE && d1 <= STEP_BASE + 15) {
        const t = d1 - STEP_BASE;
        if (paletteHeld >= 0 && !fxView && !patView && !projView && !recView && editTrack < 0) {
            sendCmd('assign', -1, { p: { engine: paletteHeld, track: t } });
            types[t] = ENGINE_TYPES[paletteHeld]; names[t] = ENGINE_TYPES[paletteHeld];  /* optimistic */
            paletteConsumed = true;                       /* suppress the pad-release audition */
            showAction(ENGINE_TYPES[paletteHeld] + '->T' + (t + 1));
            ledDirty = true; screenDirty = true;
            return;
        }
        if (fxView) {                                     /* FX view: step button = mute only */
            muted[t] = !muted[t]; sendCmd('mute', t); ledDirty = true; screenDirty = true;
        } else {
            /* tap = mute (on release), long-press = open this track's edit view */
            trackHeld = t; trackHeldStart = Date.now(); trackActive = false; knobShow = null;
        }
        return;
    }
    if ((status === 0x80 || (status === 0x90 && d2 === 0)) && d1 >= STEP_BASE && d1 <= STEP_BASE + 15) {
        const t = d1 - STEP_BASE;
        if (trackHeld === t) {
            if (!trackActive) {
                var _now = Date.now();
                muted[t] = !muted[t]; sendCmd('mute', t);                  /* short tap = mute */
                if (_now - lastTapAt[t] < DOUBLE_MS) {                     /* DOUBLE-tap = solo */
                    /* the two taps' mute toggles cancel out, so the mute state is unchanged */
                    sendCmd('solo', t);
                    showAction((solo === t ? 'UNSOLO T' : 'SOLO T') + (t + 1));
                    lastTapAt[t] = 0;                                      /* consume the pair */
                } else {
                    lastTapAt[t] = _now;
                }
            }
            trackHeld = -1; trackActive = false; knobShow = null; ledDirty = true; screenDirty = true;
        }
        return;
    }

    /* PATTERN / PROJECT view: the 32 pads are 32 slots. Shift+pad = save, tap = load.
     * NOTE messages only — knob CCs (71-78) and Play CC (85) fall in the same numeric
     * range as the pad notes, so we must NOT swallow them here. */
    if ((patView || projView || recView) && (status === 0x90 || status === 0x80) && d1 >= 68 && d1 <= 99) {
        if (status === 0x90 && d2 > 0) {
            const slot = NOTE_TO_CELL[d1];
            if (recView) {
                if (slot < 8) { sendCmd('recpad', slot); }        /* arm/start/stop that recording slot */
            } else if (patView) {
                if (shiftHeld) { patFilled[slot] = true; sendCmd('savepat', slot); showAction('SAVE PAT ' + (slot + 1)); }
                else { sendCmd('loadpat', slot); showAction((running ? 'QUEUE ' : 'LOAD ') + 'PAT ' + (slot + 1)); }
            } else {
                if (shiftHeld) { projFilled[slot] = true; sendCmd('saveproj', slot); showAction('SAVE PROJ ' + (slot + 1)); }
                else { sendCmd('loadproj', slot); showAction('LOAD PROJ ' + (slot + 1)); }
            }
            ledDirty = true; screenDirty = true;
        }
        return;   /* slot views own all pad events (press + release) */
    }

    /* Pads in FX view: bottom row = FX (hold to arm), rows 0-1 = tracks (assign/bypass). */
    if (fxView && status === 0x90 && d2 > 0 && d1 >= 68 && d1 <= 99) {
        const cell = NOTE_TO_CELL[d1];
        if (cell >= FX_CELL0) { fxHeld = cell - FX_CELL0; ledDirty = true; screenDirty = true; }
        else if (cell < N_TRACKS) {
            if (fxHeld >= 0) {                          /* assign / unassign the held FX */
                if (!fxOn[cell]) fxOn[cell] = [];
                var idx = fxOn[cell].indexOf(fxHeld);
                if (idx >= 0) fxOn[cell].splice(idx, 1); else fxOn[cell].push(fxHeld);   /* optimistic */
                sendCmd('fxassign', -1, { p: { track: cell, fx: fxHeld } });
                showAction('T' + (cell + 1) + (idx >= 0 ? ' -' : ' +') + fxNames[fxHeld]);
            } else {
                fxBypass[cell] = !fxBypass[cell]; sendCmd('fxbypass', cell, { p: { track: cell } });
                showAction('T' + (cell + 1) + (fxBypass[cell] ? ' BYPASS' : ' FX ON'));
            }
            ledDirty = true; screenDirty = true;
        }
        return;
    }
    if (fxView && (status === 0x80 || (status === 0x90 && d2 === 0)) && d1 >= 68 && d1 <= 99) {
        const cell = NOTE_TO_CELL[d1];
        if (cell >= FX_CELL0) { fxHeld = -1; ledDirty = true; screenDirty = true; }   /* any FX-pad release clears the hold */
        return;
    }
    /* DEFAULT tracks view: top-row pads = engine palette. Short-press = audition the
     * engine's current sound; Shift+pad = regenerate it; hold + tap a track = assign
     * (handled in the step-button branch above). */
    const _defView = !fxView && !patView && !projView && !recView && editTrack < 0;
    if (_defView && status === 0x90 && d2 > 0 && d1 >= 68 && d1 <= 99) {
        const cell = NOTE_TO_CELL[d1];
        if (cell < N_ENGINES) {
            if (shiftHeld) { sendCmd('palettegen', cell); showAction('GEN ' + ENGINE_TYPES[cell]); }
            else { paletteHeld = cell; paletteHeldStart = Date.now(); paletteConsumed = false; }
            ledDirty = true; screenDirty = true;
        }
        return;
    }
    if (_defView && (status === 0x80 || (status === 0x90 && d2 === 0)) && d1 >= 68 && d1 <= 99) {
        const cell = NOTE_TO_CELL[d1];
        if (paletteHeld === cell) {
            if (!paletteConsumed) { sendCmd('audition', cell); showAction('HEAR ' + ENGINE_TYPES[cell]); }
            paletteHeld = -1; paletteConsumed = false; ledDirty = true; screenDirty = true;
        }
        return;
    }

    /* Pads (68..99): EDIT view only. Shift = set last step; else tap/hold. */
    if (status === 0x90 && d2 > 0 && d1 >= 68 && d1 <= 99) {
        if (editTrack < 0) return;
        const cell = NOTE_TO_CELL[d1];
        if (shiftHeld) {
            trackLen[editTrack] = cell + 1;                       /* optimistic polymeter length */
            sendCmd('setlen', cell, { p: { track: editTrack, len: cell + 1 } });
            ledDirty = true; screenDirty = true; showAction('LEN ' + (cell + 1));
            return;
        }
        heldCell = cell; heldStart = Date.now(); heldStepEdit = false;
        return;
    }
    if ((status === 0x80 || (status === 0x90 && d2 === 0)) && d1 >= 68 && d1 <= 99) {
        if (editTrack < 0) return;
        const cell = NOTE_TO_CELL[d1];
        if (heldCell === cell) {
            if (heldStepEdit) { stepEditCell = -1; knobShow = null; ledDirty = true; screenDirty = true; }
            else if (cell < editLen()) {
                editSteps[cell] = editSteps[cell] ? 0 : 1;
                sendCmd('stepset', cell, { p: { track: editTrack, cell: cell, on: editSteps[cell] } });
                ledDirty = true; screenDirty = true;
            }
        }
        heldCell = -1; heldStepEdit = false;
        return;
    }

    if (status === 0xB0) {
        if (d1 === MoveBack && d2 > 0) {
            sys('sh ' + PH + '/stop-stack.sh');
            if (typeof host_exit_module === 'function') host_exit_module();
            return;
        }
        if (d1 === MoveShift) { shiftHeld = d2 > 0; return; }
        /* Jog wheel = PITCH (note) — easier than the tiny knob for a step lock or track. */
        if (d1 === MoveMainKnob) {
            var jd = decodeDelta(d2);
            if (jd !== 0) {
                if (stepEditCell >= 0) {
                    var c = stepEditCell; stepNote[c] = clampi(Math.round(stepNote[c]) + jd, 0, 127);
                    knobShow = 'pitch'; sendCmd('steplock', c, { p: { track: editTrack, cell: c, param: 'pitch', value: stepNote[c] } }); screenDirty = true;
                } else if (editTrack >= 0) {
                    var t = editTrack; trackNote[t] = clampi(Math.round(trackNote[t]) + jd, 0, 127);
                    knobShow = 'pitch'; sendCmd('trackset', t, { p: { track: t, param: 'pitch', value: trackNote[t] } }); screenDirty = true;
                }
            }
            return;
        }
        /* Left/Right cursor = clock rate/division of the current track (held or in edit). */
        if ((d1 === MoveLeft || d1 === MoveRight) && d2 > 0) {
            var rt = (trackHeld >= 0) ? trackHeld : editTrack;
            if (rt >= 0) {
                var idx = clampi(rateIndex(trackRate[rt]) + (d1 === MoveRight ? 1 : -1), 0, RATES.length - 1);
                trackRate[rt] = RATES[idx];
                sendCmd('trackset', rt, { p: { track: rt, param: 'rate', value: trackRate[rt] } });
                rateView = rt; rateViewUntil = phase + 45; screenDirty = true;
            }
            return;
        }
        if (d1 === MoveRow2 && d2 > 0) {                  /* Track 2 = FX view toggle */
            fxView = !fxView; fxHeld = -1;
            if (fxView) { patView = false; projView = false; recView = false; editTrack = -1; stepEditCell = -1; trackHeld = -1; paletteHeld = -1; }
            ledDirty = true; screenDirty = true; showAction(fxView ? 'FX' : 'TRACKS');
            return;
        }
        if (d1 === MoveRow3 && d2 > 0) {                  /* Track 3 = PATTERN view; Shift+Track3 = RECORDER */
            if (shiftHeld) {
                recView = !recView;
                if (recView) { patView = false; projView = false; fxView = false; fxHeld = -1; editTrack = -1; stepEditCell = -1; trackHeld = -1; paletteHeld = -1; }
                showAction(recView ? 'RECORDER' : 'TRACKS');
            } else {
                patView = !patView;
                if (patView) { projView = false; recView = false; fxView = false; fxHeld = -1; editTrack = -1; stepEditCell = -1; trackHeld = -1; paletteHeld = -1; }
                showAction(patView ? 'PATTERNS' : 'TRACKS');
            }
            ledDirty = true; screenDirty = true;
            return;
        }
        if (d1 === MoveMenu && d2 > 0) {                  /* Menu = PROJECT view toggle */
            projView = !projView;
            if (projView) { patView = false; recView = false; fxView = false; fxHeld = -1; editTrack = -1; stepEditCell = -1; trackHeld = -1; paletteHeld = -1; }
            ledDirty = true; screenDirty = true; showAction(projView ? 'PROJECTS' : 'TRACKS');
            return;
        }
        if (d1 === MoveRow1 && d2 > 0) {
            /* Shift+Track1 = re-roll the OPEN track's sound within its assigned engine.
             * (Whole-kit regen is retired — the engine palette generates & assigns now.) */
            if (shiftHeld) {
                if (editTrack >= 0) { sendCmd('randtrack', editTrack, { p: { track: editTrack } }); showAction('RND T' + (editTrack + 1)); }
                else showAction('open a track first');
            } else { fxView = false; editTrack = -1; stepEditCell = -1; heldCell = -1; sendCmd('editexit', -1); showAction('TRACKS'); }
            ledDirty = true; screenDirty = true;
            return;
        }
        if (d1 === MovePlay && d2 > 0) {
            running = !running; sendCmd('run', running ? 1 : 0);
            showAction(running ? 'PLAY' : 'STOP'); ledDirty = true; screenDirty = true;
            return;
        }
        if (d1 >= MoveKnob1 && d1 <= MoveKnob1 + 7) {
            const ki = d1 - MoveKnob1;
            const dn = decodeDelta(d2);
            if (dn === 0) return;
            if (fxView) {                                        /* knob N = FX N macro; Shift = its dry/wet */
                if (shiftHeld) {
                    fxWet[ki] = clampf(fxWet[ki] + dn * 0.03, 0, 1);
                    sendCmd('fxwet', ki, { p: { fx: ki, wet: fxWet[ki] } });
                    knobShow = 'fw' + ki; screenDirty = true;
                    return;
                }
                fxMacro[ki] = clampf(fxMacro[ki] + dn * 0.03, 0, 1);
                sendCmd('fxmacro', ki, { p: { fx: ki, pos: fxMacro[ki] } });
                knobShow = 'fx' + ki; screenDirty = true;        /* giant readout, persists while touched */
                return;
            }
            if (stepEditCell >= 0 && ki <= 2) {                  /* step lock: k1 vel, k2 pan, k3 macro (pitch = jog) */
                const c = stepEditCell;
                if (ki === 0) { stepVel[c] = clampf(stepVel[c] + dn * (2 / 127), 0, 2); knobShow = 'vel'; sendCmd('steplock', c, { p: { track: editTrack, cell: c, param: 'vel', value: stepVel[c] } }); }
                else if (ki === 1) { stepPan[c] = clampf(stepPan[c] + dn * 0.02, -1, 1); knobShow = 'pan'; sendCmd('steplock', c, { p: { track: editTrack, cell: c, param: 'pan', value: stepPan[c] } }); }
                else { stepMacro[c] = clampf(stepMacro[c] + dn * 0.03, 0, 1); knobShow = 'macro'; sendCmd('stepmacro', c, { p: { track: editTrack, cell: c, pos: stepMacro[c] } }); }
                screenDirty = true; return;
            }
            if (editTrack >= 0 && ki <= 1) {                     /* track settings: k1 volume, k2 pan (pitch = jog, rate = cursors) */
                const t = editTrack;
                if (ki === 0) { trackVol[t] = clampf(trackVol[t] + dn * (2 / 127), 0, 2); knobShow = 'vol'; sendCmd('trackset', t, { p: { track: t, param: 'amp', value: trackVol[t] } }); }
                else { trackPan[t] = clampf(trackPan[t] + dn * 0.02, -1, 1); knobShow = 'pan'; sendCmd('trackset', t, { p: { track: t, param: 'pan', value: trackPan[t] } }); }
                screenDirty = true; return;
            }
            if (editTrack >= 0 && ki === 2) {                    /* knob 3 = voice macro: sculpt the whole voice */
                const t = editTrack;
                voiceMacro[t] = clampf(voiceMacro[t] + dn * 0.03, 0, 1); knobShow = 'macro';
                sendCmd('voicemacro', t, { p: { track: t, pos: voiceMacro[t] } });
                screenDirty = true; return;
            }
            if (ki === 0 && !patView && !recView) {              /* knob 1 = master tempo (tracks + project views) */
                tempoLocal = clampi(Math.round(tempo) + dn, 20, 300);
                tempo = tempoLocal; tempoDirty = true; controlDirty = true;
                knobShow = 'tempo'; screenDirty = true;          /* giant readout, persists while touched */
            }
            return;
        }
    }
};

globalThis.onMidiMessageExternal = function (data) {};

/* Defensive: never let a stray exception in a frame or input handler crash the
 * JS runtime / hang the Schwung host (a hung tick freezes the whole Move UI). */
(function () {
    var _tick = globalThis.tick, _mid = globalThis.onMidiMessageInternal;
    globalThis.tick = function () { try { _tick(); } catch (e) { ledDirty = false; screenDirty = false; } };
    globalThis.onMidiMessageInternal = function (data) { try { _mid(data); } catch (e) { } };
})();
