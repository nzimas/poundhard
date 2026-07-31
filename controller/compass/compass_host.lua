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

-- Recording is a TOGGLE in the script (`::` and key 3 both flip recLevel), so wanting a
-- state means comparing and pressing. Reading recLevel back is what makes that possible.
local function set_rec(want)
	local cur = (peek("recLevel") or 0) > 0
	if cur ~= want then press(3) end
end

local function perform()
	performed = performed + 1

	if performed == 1 then
		-- The script starts with every step set to command 1, which only resets the clock,
		-- so without this nothing ever happens.
		press(2)
		-- Overdub is what stops the tape running away. The script's default is 1, meaning
		-- new = old + input on every lap with NO decay: leave it there with recording on and
		-- the buffer accumulates until it swamps everything. On a norns you reach for this
		-- knob; here that is this line.
		params:set("Overdub", math.random(45, 80) / 100)
		params:set("Fade", math.random(2, 12) / 100)
		-- THE FRAME DECIDES HOW LONG A LAP TAKES, and that is the difference between a tape
		-- loop and silence. The script's default is the whole 64-second tape, which means
		-- the heads need 64 seconds to come back around to anything they recorded — a
		-- 40-second take measured 3.7 dB QUIETER with Compass on than off, because for the
		-- whole take the heads were playing buffer that had never been written. A norns
		-- player pulls End point down for exactly this reason; that is this line.
		--
		-- The other end of the range matters just as much: collapse the frame to a second
		-- or two and a loop with recording on IS a short delay. Eight to twenty-four
		-- seconds is long enough to be a tape and short enough to fill.
		params:set("Start point", 1)
		params:set("End point", math.random(9, 25))
		set_rec(true)                             -- lay something down to work with
		report()
		return
	end

	-- THE RECORDER GOES ON AND OFF, and is off more than it is on. That is the difference
	-- between a tape loop and a delay line: with recording on continuously the heads are
	-- always chewing the last few seconds of live input, which is a delay however cleverly
	-- the loop points move. With it off, they are chewing something captured a while ago
	-- and now being played backwards, at half speed, from the wrong place.
	local r = math.random()
	if r < 0.34 then
		set_rec(true)
	elseif r < 0.72 then
		set_rec(false)
	end

	local q = math.random()
	if q < 0.22 then
		press(2)                                  -- fresh command sequence
	elseif q < 0.32 then
		with_key1(function() enc(1, math.random(-4, 4)) end)   -- sequence length
	elseif q < 0.40 then
		press(3, 1.4)                             -- long hold: cutReset, wipe the tape
	elseif q < 0.56 then
		params:set("Pan (L)", -math.random(0, 90) / 100)
		params:set("Pan (R)", math.random(0, 90) / 100)
	elseif q < 0.66 then
		params:set("Fade", math.random(1, 30) / 100)
	elseif q < 0.76 then
		params:set("Rate (slew)", math.random(0, 60) / 100)
	elseif q < 0.86 then
		params:set("Overdub", math.random(40, 85) / 100)
	elseif q < 0.94 then
		-- Re-frame the tape, both bounds at once and always wide, so the frame moves
		-- without ever collapsing.
		local a = math.random(1, 40)
		params:set("Start point", a)
		params:set("End point", math.min(65, a + math.random(8, 24)))
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
