-- compass_host.lua — runs Olivier Creurer's Compass, unmodified, and plays it.
--
-- Loads the norns shim, loads compass.lua verbatim, calls init(), then services messages
-- from PoundHard on stdin and writes softcut calls to stdout.
--
-- THE ALGORITHMIC PERFORMER (below) does not poke the script's internals. It presses the
-- script's own keys and turns its own encoders — key(2) short to randomise the command
-- sequence, key(3) short to arm recording, key(1)+enc(1) for sequence length, key(1)+enc(2/3)
-- for the loop window, params:set for pan and fade. Everything it does, a person sitting in
-- front of a norns could do, which is the only way to be sure the behaviour is the script's
-- and not a reimplementation of it wearing the script's name.
--
-- Reading state back uses debug.getupvalue. Nearly all of Compass's state is file-local —
-- `pos`, `division`, `recLevel`, `loopStart` — so it is reachable as upvalues of the global
-- functions that close over it. That is a read-only window for the readout and the log; the
-- script is never written to from outside.

local here = arg[0]:match("(.*)/") or "."
package.path = here .. "/?.lua;" .. package.path

local shim = dofile(here .. "/norns_shim.lua")
dofile(here .. "/compass.lua")

-- --------------------------------------------------------------------------- --
-- a read-only window onto the script's locals
-- --------------------------------------------------------------------------- --
local function upval(fn, name)
	if type(fn) ~= "function" then return nil end
	local i = 1
	while true do
		local n, v = debug.getupvalue(fn, i)
		if not n then return nil end
		if n == name then return v end
		i = i + 1
	end
end

-- each name paired with a global function known to close over it
local WATCH = {
	pos = "count", division = "metroInc", recLevel = "toggleRec",
	loopStart = "loopRnd", loopEnd = "loopRnd", sPoint = "loopRnd", ePoint = "loopRnd",
	rate_pos = "rateInc", STEPS = "update_positions", act = "count", step = "count",
}
local function peek(name)
	local holder = WATCH[name]
	return holder and upval(_G[holder], name) or nil
end

local RATES = { -2, -1, -0.5, 0.5, 1, 2 }

local function glyph()
	local act, step, pos = peek("act"), peek("step"), peek("pos")
	if not (act and step and pos) then return "?" end
	local idx = step[pos]
	return (act.label and act.label[idx]) or "?"
end

local function report()
	local rp = peek("rate_pos") or 5
	shim.emit("state", glyph(), peek("division") or 1,
		RATES[rp] or 1, peek("loopStart") or 1, peek("loopEnd") or 65,
		(peek("recLevel") or 0) > 0 and 1 or 0, peek("STEPS") or 16)
end

-- --------------------------------------------------------------------------- --
-- the performer
-- --------------------------------------------------------------------------- --
local now = 0.0
local function press(n, hold)
	shim.set_time(now); key(n, 1)
	now = now + (hold or 0.2)
	shim.set_time(now); key(n, 0)
end

local function with_key1(fn)
	shim.set_time(now); key(1, 1)
	fn()
	shim.set_time(now); key(1, 0)
end

local performed = 0

local function perform()
	performed = performed + 1
	local r = math.random()

	-- A new command sequence is the single biggest gesture available, and the script starts
	-- with every step set to command 1 (a no-op that only resets the clock), so the first
	-- perform MUST randomise or nothing ever happens.
	if performed == 1 then
		press(2)                                  -- randomize_steps
		press(3)                                  -- recLevel 0 -> 1, start recording
		report()
		return
	end

	if r < 0.16 then
		press(2)                                  -- fresh command sequence
	elseif r < 0.26 then
		with_key1(function() enc(1, math.random(-4, 4)) end)   -- sequence length
	elseif r < 0.42 then
		-- move the loop window. Start/End point are the bounds loopRnd draws inside, so
		-- this is what decides whether the tape roams the whole 64 seconds or worries at
		-- a few of them.
		with_key1(function()
			enc(2, math.random(-12, 12))
			enc(3, math.random(-12, 12))
		end)
	elseif r < 0.50 then
		press(3)                                  -- arm / disarm recording
	elseif r < 0.54 then
		press(3, 1.4)                             -- long hold: cutReset, wipe the tape
	elseif r < 0.68 then
		params:set("Pan (L)", -math.random(0, 90) / 100)
		params:set("Pan (R)", math.random(0, 90) / 100)
	elseif r < 0.76 then
		params:set("Fade", math.random(1, 40) / 100)
	elseif r < 0.84 then
		params:set("Rate (slew)", math.random(0, 60) / 100)
	elseif r < 0.90 then
		params:set("Overdub", math.random(70, 100) / 100)
	end
	now = now + 0.5
	report()
end

-- --------------------------------------------------------------------------- --
-- run
-- --------------------------------------------------------------------------- --
io.stdout:setvbuf("line")

local ok, err = pcall(init)
if not ok then
	shim.emit("log", "init failed: " .. tostring(err))
	os.exit(1)
end
shim.emit("ready", 1)

local phase_since_metro = 0

for line in io.lines() do
	local f = {}
	for part in line:gmatch("[^|]+") do f[#f + 1] = part end
	local kind = f[1]

	if kind == "tick" then
		now = tonumber(f[2]) or now
		shim.set_time(now)
		shim.tick()
	elseif kind == "phase" then
		now = tonumber(f[4]) or now
		shim.set_time(now)
		shim.phase(tonumber(f[2]), tonumber(f[3]))
		phase_since_metro = phase_since_metro + 1
		if phase_since_metro >= 3 then phase_since_metro = 0; shim.metro_poll() end
	elseif kind == "perform" then
		now = tonumber(f[2]) or now
		shim.set_time(now)
		local pok, perr = pcall(perform)
		if not pok then shim.emit("log", "perform: " .. tostring(perr)) end
	elseif kind == "tempo" then
		shim.tempo = tonumber(f[2])
	elseif kind == "report" then
		report()
	elseif kind == "quit" then
		break
	end
end
