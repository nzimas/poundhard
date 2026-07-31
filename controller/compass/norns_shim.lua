-- norns_shim.lua — enough of the norns API for Compass to run UNMODIFIED.
--
-- compass.lua in this directory is Olivier Creurer's script, byte for byte as published.
-- That is the point of this file: two previous attempts reimplemented the script's ideas in
-- another language and both were wrong in ways that were obvious the moment the real source
-- was read (one shared buffer instead of two, sub-second loop windows instead of integer
-- seconds, per-bar commands instead of per-beat, no rate slew). Paraphrasing a script is not
-- running it. So the script is not touched, and everything it calls is provided here.
--
-- WHAT IS REAL
--   softcut.*      — forwarded to the PhSoftcut UGens in scsynth, which ARE softcut-lib.
--   clock.*        — coroutine scheduler on a 1/16-beat tick from PoundHard's own clock, so
--                    `clock.sync(1/division)` lands on the same grid the sequencer plays on.
--   params.*       — values, defaults, actions, deltas. Actions are what push to softcut.
--   softcut.event_phase / poll_start_phase — driven by the UGen's real position output, so
--                    the script's `update_positions` runs for real. That matters: it is
--                    where loop points, rec level and pre level actually reach softcut.
--
-- WHAT IS A STUB, AND WHY
--   grid / arc / screen / crow — hardware the Move does not have. Their handlers stay
--   registered and harmless; the script's own logic never depends on them for sound.
--   metro — display counters only (LED brightness, edit blink). Fired off the phase poll.
--   pattern_time — the grid pattern recorder. No grid, so it is never exercised.
--
-- Talks to PoundHard over stdin/stdout in pipe-separated lines, which is why there is no
-- luasocket here and nothing to build: plain Lua, plain pipes.

local M = {}

-- --------------------------------------------------------------------------- --
-- out
-- --------------------------------------------------------------------------- --
local function emit(...)
	local parts = {...}
	for i = 1, #parts do parts[i] = tostring(parts[i]) end
	io.write(table.concat(parts, "|"), "\n")
end
M.emit = emit

local function log(s) emit("log", s) end
M.log = log

-- host clock, fed by the tick/phase messages; util.time() reads it
local host_time = 0.0
function M.set_time(t) host_time = t end

-- --------------------------------------------------------------------------- --
-- util
-- --------------------------------------------------------------------------- --
util = {}
function util.clamp(x, a, b) if x < a then return a elseif x > b then return b else return x end end
function util.round(x, q) q = q or 1; return math.floor(x / q + 0.5) * q end
function util.time() return host_time end
function util.linlin(a, b, c, d, x)
	if x <= a then return c elseif x >= b then return d end
	return (x - a) / (b - a) * (d - c) + c
end
util.wrap = function(x, a, b) return a + (x - a) % (b - a) end
util.scandir = function() return {} end
util.file_exists = function() return false end

-- --------------------------------------------------------------------------- --
-- softcut — every call the script makes, forwarded verbatim
-- --------------------------------------------------------------------------- --
softcut = {}
local phase_handler = nil

-- Per-voice parameter fan-out. `voice` 0 means "not per-voice" (buffer_clear, audio level).
local function sc(fn, voice, value)
	emit("sc", fn, voice, value)
end

local sc_voice_fns = {
	"rate", "rate_slew_time", "loop_start", "loop_end", "loop", "position",
	"level", "pan", "pan_slew_time", "level_slew_time",
	"rec_level", "pre_level", "recpre_slew_time", "rec_offset",
	"fade_time", "phase_quant", "rec", "play", "enable", "buffer",
	"pre_filter_dry", "pre_filter_lp", "pre_filter_hp", "pre_filter_bp", "pre_filter_br",
	"pre_filter_fc", "pre_filter_rq",
	"post_filter_dry", "post_filter_lp", "post_filter_hp", "post_filter_bp",
	"post_filter_br", "post_filter_fc", "post_filter_rq",
}
for _, name in ipairs(sc_voice_fns) do
	softcut[name] = function(i, x) sc(name, i, x) end
end

function softcut.buffer_clear() sc("buffer_clear", 0, 0) end
function softcut.buffer_clear_channel(ch) sc("buffer_clear", ch, 0) end
function softcut.level_input_cut(ch, voice, amp) emit("scin", ch, voice, amp) end
function softcut.event_phase(fn) phase_handler = fn end
function softcut.poll_start_phase() emit("pollphase", 1) end
function softcut.poll_stop_phase() emit("pollphase", 0) end
function M.phase(i, x) if phase_handler then phase_handler(i, x) end end

-- --------------------------------------------------------------------------- --
-- audio
-- --------------------------------------------------------------------------- --
audio = {}
function audio.level_cut(x) sc("audio_level_cut", 0, x) end
function audio.level_adc_cut(x) sc("audio_level_adc_cut", 0, x) end
function audio.level_eng_cut(x) sc("audio_level_eng_cut", 0, x) end
function audio.level_monitor(x) sc("audio_level_monitor", 0, x) end

-- --------------------------------------------------------------------------- --
-- clock — coroutines on a 1/16-beat tick
-- --------------------------------------------------------------------------- --
clock = {}
local TICKS_PER_BEAT = 16
local tick_n = 0
local coros = {}          -- id -> {co=coroutine, wake=tick}
local next_id = 1

function clock.run(f, ...)
	local id = next_id; next_id = id + 1
	local co = coroutine.create(f)
	coros[id] = { co = co, wake = tick_n }
	M.resume(id, ...)
	return id
end

function clock.cancel(id) coros[id] = nil end

function clock.sync(beats)
	coroutine.yield({ sync = beats })
end

function clock.sleep(sec)
	coroutine.yield({ sleep = sec })
end

function clock.get_beats() return tick_n / TICKS_PER_BEAT end
function clock.get_tempo() return M.tempo or 120 end

function M.resume(id, ...)
	local entry = coros[id]
	if not entry then return end
	local ok, req = coroutine.resume(entry.co, ...)
	if not ok then
		log("clock coroutine error: " .. tostring(req))
		coros[id] = nil
		return
	end
	if coroutine.status(entry.co) == "dead" then coros[id] = nil; return end
	if type(req) == "table" and req.sync then
		-- next absolute multiple of `sync` beats, exactly as norns' clock.sync does:
		-- the command stream stays locked to the sequencer's grid rather than free-running
		local period = math.max(1, math.floor(req.sync * TICKS_PER_BEAT + 0.5))
		entry.wake = (math.floor(tick_n / period) + 1) * period
	elseif type(req) == "table" and req.sleep then
		entry.wake = tick_n + math.max(1, math.floor(req.sleep * TICKS_PER_BEAT))
	else
		entry.wake = tick_n + 1
	end
end

function M.tick()
	tick_n = tick_n + 1
	local due = {}
	for id, e in pairs(coros) do
		if tick_n >= e.wake then due[#due + 1] = id end
	end
	table.sort(due)
	for _, id in ipairs(due) do M.resume(id) end
end

-- --------------------------------------------------------------------------- --
-- metro — display counters. Fired off the phase poll; nothing audible depends on them.
-- --------------------------------------------------------------------------- --
metro = {}
local metros = {}
local Metro = {}
Metro.__index = Metro
function Metro:start() self.running = true end
function Metro:stop() self.running = false end
function metro.init(fn, time, count)
	local m = setmetatable({ fn = fn, time = time, count = count, running = false }, Metro)
	metros[#metros + 1] = m
	return m
end
function M.metro_poll()
	for _, m in ipairs(metros) do
		if m.running and m.fn then pcall(m.fn) end
	end
end

-- --------------------------------------------------------------------------- --
-- params
-- --------------------------------------------------------------------------- --
controlspec = {}
function controlspec.new(min, max, warp, step, default, units)
	return { minval = min, maxval = max, warp = warp, step = step,
	         default = default, units = units }
end
controlspec.def = controlspec.new

local Params = { values = {}, actions = {}, specs = {}, options = {}, order = {} }
function Params:add_group() end
function Params:add_separator() end
function Params:_register(id, spec, default)
	if self.values[id] == nil then self.values[id] = default end
	self.specs[id] = spec
	self.order[#self.order + 1] = id
end
function Params:add_option(id, name, opts, default)
	self.options[id] = opts
	self:_register(id, { minval = 1, maxval = #opts, step = 1 }, default or 1)
end
function Params:add_control(id, name, spec)
	self:_register(id, spec, spec and spec.default or 0)
end
function Params:add_number(id, name, min, max, default)
	self:_register(id, { minval = min, maxval = max, step = 1 }, default or min)
end
function Params:add(t)
	if t.type == "control" then
		self:_register(t.id, t.controlspec, t.controlspec and t.controlspec.default or 0)
	elseif t.type == "option" then
		self.options[t.id] = t.options
		self:_register(t.id, { minval = 1, maxval = #(t.options or {1}), step = 1 }, t.default or 1)
	else
		self:_register(t.id, { minval = t.min or 0, maxval = t.max or 1, step = 1 }, t.default or 0)
	end
	if t.action then self.actions[t.id] = t.action end
end
function Params:set_action(id, fn) self.actions[id] = fn end
function Params:get(id) return self.values[id] end
function Params:set(id, v, silent)
	local sp = self.specs[id]
	if sp and sp.minval and sp.maxval then v = util.clamp(v, sp.minval, sp.maxval) end
	self.values[id] = v
	local a = self.actions[id]
	if a and not silent then a(v) end
end
function Params:delta(id, d)
	local sp = self.specs[id] or {}
	self:set(id, (self.values[id] or 0) + d * (sp.step or 1))
end
function Params:bang()
	for _, id in ipairs(self.order) do
		local a = self.actions[id]
		if a then a(self.values[id]) end
	end
end
function Params:string(id) return tostring(self.values[id]) end
params = Params
-- the script sets this before its own group exists
params.values["clock_tempo"] = 120

-- --------------------------------------------------------------------------- --
-- hardware stubs: grid, arc, screen, crow, norns
-- --------------------------------------------------------------------------- --
local function noop() end
local function stub_obj(fields)
	local t = fields or {}
	return setmetatable(t, { __index = function() return noop end })
end

grid = { connect = function() return stub_obj({ key = noop, all = noop, led = noop,
                                                refresh = noop, cols = 16, rows = 8 }) end }
arc = { connect = function() return stub_obj({}) end }

screen = stub_obj({})
screen.text_extents = function() return 0 end

crow = {
	output = { stub_obj({ volts = 0 }), stub_obj({ volts = 0 }),
	           stub_obj({ volts = 0 }), stub_obj({ volts = 0 }) },
	input  = { stub_obj({}), stub_obj({}) },
	send = noop,
}
-- crow.input[n].mode(...) is called as a plain function, and .change/.stream assigned
for i = 1, 2 do crow.input[i].mode = noop end

norns = { enc = { sens = noop, accel = noop }, state = { name = "compass" },
          script = { redraw = noop } }

-- `include` loads a library relative to the script; arcify is arc hardware we do not have
function include(path)
	if path:match("arcify") then
		return { new = function()
			return stub_obj({ register = noop, add_params = noop, update = noop })
		end }
	end
	error("include: no shim for " .. tostring(path))
end

-- pattern_time: the grid pattern recorder. Registered, never exercised without a grid.
package.preload["pattern_time"] = function()
	local P = {}
	P.__index = P
	function P.new()
		return setmetatable({ rec = 0, play = 0, count = 0, process = noop }, P)
	end
	function P:watch() end
	function P:rec_start() self.rec = 1 end
	function P:rec_stop() self.rec = 0 end
	function P:start() self.play = 1 end
	function P:stop() self.play = 0 end
	function P:clear() self.count = 0; self.play = 0; self.rec = 0 end
	return P
end

return M
