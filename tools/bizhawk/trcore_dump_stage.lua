-- trcore_dump_stage.lua
-- Read-only helper for Super Monkey Ball: Touch & Roll (USA, game code AMOE) in BizHawk.
--
-- What it does: every time a stage is loaded and has stayed loaded for half a
-- second, it saves the whole 4 MiB DS Main RAM to a .bin file, a .txt file with
-- the stage IDs and the stage-data pointer, and a screenshot. Each stage load is
-- saved once. Files go into the folder this script is in (about 4 MiB per dump).
-- It never writes to emulated memory.
--
-- Use: Tools > Lua Console > Script > Open Script... > pick this file, then play
-- into stages. The console prints where the files went. Compare a dump with:
--     py -3 -m trcore ramdump-compare <dump>.bin --rom <the ROM you were playing>
--
-- Addresses come from static analysis of the USA ROM's code (trcore/rom.py
-- PROFILES). Other regions/revisions use different addresses.

local RAM_BASE          = 0x02000000
local RAM_SIZE          = 0x00400000
local ADDR_LOADED_ID    = 0x020E8FC8
local ADDR_REQUESTED_ID = 0x020E8FD8
local ADDR_STAGE_PTR    = 0x020E9208
local SETTLE_FRAMES     = 30
local CHUNK             = 0x10000
local MAX_DUMPS         = 10             -- stop after this many stage dumps

local function log(msg) console.log("[trcore] " .. msg) end

-- Folder of this script, read once at the top level of the chunk (level 1 = this file).
local SCRIPT_SOURCE = nil
if debug ~= nil and debug.getinfo ~= nil then
  local info = debug.getinfo(1, "S")
  if info ~= nil then SCRIPT_SOURCE = info.source end
end

local function script_dir()
  if type(SCRIPT_SOURCE) == "string" and SCRIPT_SOURCE:sub(1, 1) == "@" then
    local dir = SCRIPT_SOURCE:sub(2):match("^(.*)[/\\]")
    if dir and dir ~= "" then return dir end
  end
  return "."   -- falls back to BizHawk's working folder (usually the EmuHawk folder)
end

local function pick_domain()
  local names = {}
  for _, v in pairs(memory.getmemorydomainlist()) do names[#names + 1] = tostring(v) end
  for _, n in ipairs(names) do if n == "Main RAM" then return n, names end end
  for _, n in ipairs(names) do if n:lower():find("main") then return n, names end end
  return nil, names
end

local domain, all_domains = pick_domain()
if not domain then
  log("Could not find a Main RAM memory domain. Domains: " .. table.concat(all_domains, ", "))
  return
end
local dsize = memory.getmemorydomainsize(domain)
if dsize ~= RAM_SIZE then
  log(string.format("Domain '%s' is 0x%X bytes, expected 0x%X. Stopping.", domain, dsize, RAM_SIZE))
  return
end
if io == nil or io.open == nil then
  log("This BizHawk Lua environment has no file access (io library missing). Stopping.")
  return
end

local function rd32(addr) return memory.read_u32_le(addr - RAM_BASE, domain) end

local function stage_ready()
  local ptr = rd32(ADDR_STAGE_PTR)
  if ptr < RAM_BASE or ptr > RAM_BASE + RAM_SIZE - 0x100 then return false, ptr end
  local magic = memory.read_bytes_as_binary_string(ptr - RAM_BASE, 4, domain)
  return magic == "LCTS", ptr
end

local function safe(s) return (tostring(s):gsub("[^%w%-_]", "")) end

local function dump(loaded, requested, ptr)
  local dir = script_dir()
  local romhash = safe(gameinfo.getromhash() or "unknown"):sub(1, 8)
  local base = string.format("%s/trcore_ram_%s_stage%03d_f%d", dir, romhash, loaded, emu.framecount())
  local f, err = io.open(base .. ".bin", "wb")
  if not f then log("Cannot write " .. base .. ".bin: " .. tostring(err)); return false end
  for off = 0, RAM_SIZE - 1, CHUNK do
    f:write(memory.read_bytes_as_binary_string(off, CHUNK, domain))
  end
  f:close()
  local m = io.open(base .. ".txt", "w")
  if m then
    m:write("tool=trcore_dump_stage.lua 1\n")
    m:write("bizhawk_version=" .. tostring(client.getversion()) .. "\n")
    m:write("system=" .. tostring(emu.getsystemid()) .. "\n")
    m:write("rom_name=" .. tostring(gameinfo.getromname()) .. "\n")
    m:write("rom_hash=" .. tostring(gameinfo.getromhash()) .. "\n")
    m:write("frame=" .. tostring(emu.framecount()) .. "\n")
    m:write("domain=" .. domain .. "\n")
    m:write(string.format("loaded_stage_id=%d\nrequested_stage_id=%d\nstage_data_ptr=0x%08X\n", loaded, requested, ptr))
    m:close()
  end
  pcall(client.screenshot, base .. ".png")
  log("Saved " .. base .. ".bin (+ .txt, .png)")
  return true
end

log(string.format("Using domain '%s'. Play into a stage; each newly loaded stage is saved once.", domain))
log(string.format("Stop the script in the Lua Console when you are done (it also stops after %d dumps).", MAX_DUMPS))
local last, stable, dumps = -1, 0, 0
local done = {}          -- key "id@ptr" -> true once dumped
while dumps < MAX_DUMPS do
  local ok, ptr = stage_ready()
  local loaded = rd32(ADDR_LOADED_ID)
  local requested = rd32(ADDR_REQUESTED_ID)
  if ok and loaded == requested and loaded == last then
    stable = stable + 1
  else
    stable = 0
  end
  last = loaded
  local key = string.format("%d@%08X", loaded, ok and ptr or 0)
  if ok and stable == SETTLE_FRAMES and not done[key] then
    log(string.format("Stage %d loaded at 0x%08X; dumping Main RAM...", loaded, ptr))
    if dump(loaded, requested, ptr) then
      done[key] = true
      dumps = dumps + 1
    end
  end
  emu.frameadvance()
end
log(string.format("Saved %d dump(s); script finished.", dumps))
