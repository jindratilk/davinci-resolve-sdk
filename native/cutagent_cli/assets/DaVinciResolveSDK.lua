-- CutAgent embedded DaVinci Resolve bridge.
-- Installed into Fusion/Scripts/Utility and run from Workspace > Scripts > DaVinciResolveSDK.

local PROTOCOL_VERSION = __CUTAGENT_PROTOCOL_VERSION__
local BRIDGE_VERSION = "__CUTAGENT_BRIDGE_VERSION__"
local DEFAULT_HOST = "__CUTAGENT_DEFAULT_HOST__"
local DEFAULT_PORT = __CUTAGENT_DEFAULT_PORT__
local DEFAULT_AUTH_PATH = "__CUTAGENT_AUTH_PATH__"
local SPOOL_AUTH_PATH = "__CUTAGENT_SPOOL_AUTH_PATH__"
local SPOOL_REQUEST_PATH = "__CUTAGENT_SPOOL_REQUEST_PATH__"
local SPOOL_RESPONSE_PATH = "__CUTAGENT_SPOOL_RESPONSE_PATH__"
local SPOOL_RESPONSE_KEY = "__CUTAGENT_SPOOL_RESPONSE_KEY__"
local CUTAGENT_BUNDLE_ID = "ai.cutagent.app"
local FOCUS_DEEP_LINK = ""
local HTTP_POLL_TIMEOUT_SECONDS = 35
local HTTP_POLL_MAX_FAILURES = 6
local HTTP_POLL_RETRY_MAX_SECONDS = 10
local IS_WINDOWS = package and package.config and package.config:sub(1, 1) == "\\"

-- Ignore a duplicate menu invocation while this Lua state is already polling.
if rawget(_G, "__DAVINCI_RESOLVE_SDK_BRIDGE_RUNNING") then return end
_G.__DAVINCI_RESOLVE_SDK_BRIDGE_RUNNING = true

local function run_cutagent_bridge()
local function windows_http_poll_fallback_allowed()
  if not IS_WINDOWS then return true end
  return os.getenv("CUTAGENT_ALLOW_WINDOWS_CURL_HTTP_POLL") == "1"
end

local function path_join(left, right)
  if IS_WINDOWS then
    return tostring(left):gsub("[/\\]+$", "") .. "\\" .. tostring(right):gsub("^[/\\]+", "")
  end
  return tostring(left):gsub("/+$", "") .. "/" .. tostring(right):gsub("^/+", "")
end

local function prepend_package_path(field, paths)
  if not package then return end
  local current = package[field] or ""
  for index = #paths, 1, -1 do
    local item = paths[index]
    if item and item ~= "" and not current:find(item, 1, true) then
      current = item .. ";" .. current
    end
  end
  package[field] = current
end

local function configure_windows_socket_transport_paths()
  if not IS_WINDOWS then return end
  local appdata = os.getenv("APPDATA") or os.getenv("USERPROFILE")
  if not appdata then return end
  local modules = path_join(path_join(path_join(path_join(path_join(appdata, "Blackmagic Design"), "DaVinci Resolve"), "Support"), "Fusion"), "Modules")
  local lua_modules = path_join(modules, "Lua")
  prepend_package_path("cpath", {
    path_join(lua_modules, "?.dll"),
    path_join(lua_modules, "?\\?.dll"),
  })
  prepend_package_path("path", {
    path_join(lua_modules, "?.lua"),
    path_join(lua_modules, "?\\init.lua"),
  })
end

local function log(message)
  if not io or type(io.open) ~= "function" then return end
  local path = nil
  if IS_WINDOWS then
    local appdata = os.getenv("APPDATA") or os.getenv("USERPROFILE")
    if not appdata then return end
    path = path_join(path_join(appdata, "DaVinciResolveSDK"), "DaVinciResolveSDK.log")
  else
    local home = os.getenv("HOME")
    if not home then return end
    path = home .. "/Library/Logs/DaVinciResolveSDK.log"
  end
  local file = io.open(path, "a")
  if not file then return end
  file:write(os.date("!%Y-%m-%dT%H:%M:%SZ"), " ", tostring(message), "\n")
  file:close()
end

local function shell_quote(value)
  if IS_WINDOWS then
    return '"' .. tostring(value):gsub('"', '\\"') .. '"'
  end
  return "'" .. tostring(value):gsub("'", [['"'"']]) .. "'"
end

local function windows_curl_path()
  if not IS_WINDOWS then
    return "/usr/bin/curl"
  end
  local windir = os.getenv("WINDIR") or os.getenv("SystemRoot")
  if windir and windir ~= "" then
    return path_join(path_join(windir, "System32"), "curl.exe")
  end
  return "curl.exe"
end

local function payload_temp_path()
  if IS_WINDOWS then
    local temp = os.getenv("TEMP") or os.getenv("TMP") or os.getenv("APPDATA") or "."
    local suffix = tostring(os.time()) .. "-" .. tostring(math.random(100000, 999999))
    return path_join(temp, "cutagent-bridge-" .. suffix .. ".json")
  end
  return os.tmpname()
end

local function bring_cutagent_to_front()
  if IS_WINDOWS then return end
  if not os or type(os.execute) ~= "function" then return end
  if not FOCUS_DEEP_LINK or FOCUS_DEEP_LINK == "" then return end
  local command = "/usr/bin/open -b " .. shell_quote(CUTAGENT_BUNDLE_ID) .. " " .. shell_quote(FOCUS_DEEP_LINK) .. " >/dev/null 2>&1 &"
  local ok, result = pcall(function() return os.execute(command) end)
  if not ok then
    log("Could not request CutAgent focus: " .. tostring(result))
  end
end

log("starting bridge script")
bring_cutagent_to_front()
configure_windows_socket_transport_paths()

local ok_socket = false
local socket = nil
if type(require) == "function" then
  ok_socket, socket = pcall(require, "socket")
end
if not ok_socket then
  local message = "LuaSocket unavailable; using HTTP polling fallback."
  print("[DaVinci Resolve SDK] " .. message)
  log(message)
  log("LuaSocket load details: " .. tostring(socket))
  socket = nil
else
  log("LuaSocket loaded")
end

-- Small JSON implementation for the RPC subset CutAgent needs.
local json = {}

local function encode_string(value)
  local replacements = {
    ['"'] = '\\"',
    ["\\"] = "\\\\",
    ["\b"] = "\\b",
    ["\f"] = "\\f",
    ["\n"] = "\\n",
    ["\r"] = "\\r",
    ["\t"] = "\\t",
  }
  return '"' .. tostring(value):gsub('[%z\1-\31\\"]', function(char)
    return replacements[char] or string.format("\\u%04x", char:byte())
  end) .. '"'
end

local function is_array(value)
  local max = 0
  local count = 0
  for key, _ in pairs(value) do
    if key ~= "__flags" then
      if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
        return false
      end
      if key > max then max = key end
      count = count + 1
    end
  end
  return max == count
end

function json.encode(value)
  local t = type(value)
  if value == nil then
    return "null"
  elseif t == "boolean" then
    return value and "true" or "false"
  elseif t == "number" then
    return tostring(value)
  elseif t == "string" then
    return encode_string(value)
  elseif t == "table" then
    local parts = {}
    if is_array(value) then
      for i = 1, #value do
        parts[#parts + 1] = json.encode(value[i])
      end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for key, item in pairs(value) do
      if key ~= "__flags" then
        parts[#parts + 1] = encode_string(key) .. ":" .. json.encode(item)
      end
    end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return encode_string(tostring(value))
end

function json.decode(text)
  local i = 1
  local function skip_ws()
    while true do
      local c = text:sub(i, i)
      if c == " " or c == "\n" or c == "\r" or c == "\t" then
        i = i + 1
      else
        break
      end
    end
  end

  local parse_value

  local function parse_string()
    i = i + 1
    local out = {}
    while i <= #text do
      local c = text:sub(i, i)
      if c == '"' then
        i = i + 1
        return table.concat(out)
      elseif c == "\\" then
        local esc = text:sub(i + 1, i + 1)
        if esc == '"' or esc == "\\" or esc == "/" then
          out[#out + 1] = esc
          i = i + 2
        elseif esc == "b" then
          out[#out + 1] = "\b"
          i = i + 2
        elseif esc == "f" then
          out[#out + 1] = "\f"
          i = i + 2
        elseif esc == "n" then
          out[#out + 1] = "\n"
          i = i + 2
        elseif esc == "r" then
          out[#out + 1] = "\r"
          i = i + 2
        elseif esc == "t" then
          out[#out + 1] = "\t"
          i = i + 2
        elseif esc == "u" then
          out[#out + 1] = "?"
          i = i + 6
        else
          error("invalid json escape")
        end
      else
        out[#out + 1] = c
        i = i + 1
      end
    end
    error("unterminated json string")
  end

  local function parse_number()
    local start = i
    while text:sub(i, i):match("[%d%+%-%.eE]") do
      i = i + 1
    end
    return tonumber(text:sub(start, i - 1))
  end

  local function parse_array()
    i = i + 1
    local out = {}
    skip_ws()
    if text:sub(i, i) == "]" then
      i = i + 1
      return out
    end
    while true do
      out[#out + 1] = parse_value()
      skip_ws()
      local c = text:sub(i, i)
      if c == "]" then
        i = i + 1
        return out
      end
      if c ~= "," then error("expected comma in json array") end
      i = i + 1
    end
  end

  local function parse_object()
    i = i + 1
    local out = {}
    skip_ws()
    if text:sub(i, i) == "}" then
      i = i + 1
      return out
    end
    while true do
      skip_ws()
      local key = parse_string()
      skip_ws()
      if text:sub(i, i) ~= ":" then error("expected colon in json object") end
      i = i + 1
      out[key] = parse_value()
      skip_ws()
      local c = text:sub(i, i)
      if c == "}" then
        i = i + 1
        return out
      end
      if c ~= "," then error("expected comma in json object") end
      i = i + 1
    end
  end

  function parse_value()
    skip_ws()
    local c = text:sub(i, i)
    if c == '"' then return parse_string() end
    if c == "{" then return parse_object() end
    if c == "[" then return parse_array() end
    if c == "t" and text:sub(i, i + 3) == "true" then i = i + 4; return true end
    if c == "f" and text:sub(i, i + 4) == "false" then i = i + 5; return false end
    if c == "n" and text:sub(i, i + 3) == "null" then i = i + 4; return nil end
    return parse_number()
  end

  return parse_value()
end

local BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"

local function base64_encode(data)
  local output = {}
  local length = #data
  local index = 1
  while index <= length do
    local a = data:byte(index) or 0
    local b = data:byte(index + 1) or 0
    local c = data:byte(index + 2) or 0
    local value = a * 65536 + b * 256 + c
    local i1 = math.floor(value / 262144) % 64
    local i2 = math.floor(value / 4096) % 64
    local i3 = math.floor(value / 64) % 64
    local i4 = value % 64
    output[#output + 1] = BASE64_ALPHABET:sub(i1 + 1, i1 + 1)
    output[#output + 1] = BASE64_ALPHABET:sub(i2 + 1, i2 + 1)
    output[#output + 1] = index + 1 <= length and BASE64_ALPHABET:sub(i3 + 1, i3 + 1) or "="
    output[#output + 1] = index + 2 <= length and BASE64_ALPHABET:sub(i4 + 1, i4 + 1) or "="
    index = index + 3
  end
  return table.concat(output)
end

local function base64_decode(data)
  if type(data) ~= "string" then return nil end
  local values = {}
  for index = 1, #BASE64_ALPHABET do
    values[BASE64_ALPHABET:sub(index, index)] = index - 1
  end
  local output = {}
  local cleaned = data:gsub("%s", "")
  if #cleaned % 4 ~= 0 then return nil end
  for index = 1, #cleaned, 4 do
    local c1 = cleaned:sub(index, index)
    local c2 = cleaned:sub(index + 1, index + 1)
    local c3 = cleaned:sub(index + 2, index + 2)
    local c4 = cleaned:sub(index + 3, index + 3)
    local v1 = values[c1]
    local v2 = values[c2]
    local v3 = c3 == "=" and 0 or values[c3]
    local v4 = c4 == "=" and 0 or values[c4]
    if v1 == nil or v2 == nil or v3 == nil or v4 == nil then return nil end
    local value = v1 * 262144 + v2 * 4096 + v3 * 64 + v4
    output[#output + 1] = string.char(math.floor(value / 65536) % 256)
    if c3 ~= "=" then output[#output + 1] = string.char(math.floor(value / 256) % 256) end
    if c4 ~= "=" then output[#output + 1] = string.char(value % 256) end
  end
  return table.concat(output)
end

local function load_spool_payload(path)
  if type(loadfile) ~= "function" then return nil, "loadfile_unavailable" end
  local loader, load_error = loadfile(path)
  if not loader then return nil, tostring(load_error or "load_failed") end
  local ok_run, encoded = pcall(loader)
  if not ok_run or type(encoded) ~= "string" then
    return nil, tostring(encoded or "invalid_lua_payload")
  end
  local decoded = base64_decode(encoded)
  if not decoded then return nil, "invalid_base64_payload" end
  local ok_json, payload = pcall(json.decode, decoded)
  if not ok_json or type(payload) ~= "table" then
    return nil, tostring(payload or "invalid_json_payload")
  end
  return payload, nil
end

local auth_token = nil
local bridge_host = DEFAULT_HOST
local bridge_port = DEFAULT_PORT
local desktop_focus_host = nil
local desktop_focus_port = nil
local desktop_focus_token = nil
local http_client_id = tostring(os.time()) .. "-" .. tostring({}):gsub("[^%w]", "")

local function load_auth_config()
  local payload = nil
  local spool_payload = load_spool_payload(SPOOL_AUTH_PATH)
  if type(spool_payload) == "table" then
    payload = spool_payload
  elseif io and type(io.open) == "function" then
    local file = io.open(DEFAULT_AUTH_PATH, "r")
    if file then
      local text = file:read("*a")
      file:close()
      local ok_decode, decoded = pcall(json.decode, text or "")
      if ok_decode and type(decoded) == "table" then payload = decoded end
    end
  end
  if type(payload) == "table" and type(payload.auth_token) == "string" then
    auth_token = payload.auth_token
    if type(payload.host) == "string" and payload.host ~= "" then
      bridge_host = payload.host
    end
    if type(payload.port) == "number" and payload.port > 0 and payload.port < 65536 then
      bridge_port = payload.port
    end
    if type(payload.desktop_focus) == "table" then
      local focus = payload.desktop_focus
      if type(focus.host) == "string" and focus.host ~= "" then
        desktop_focus_host = focus.host
      end
      if type(focus.port) == "number" and focus.port > 0 and focus.port < 65536 then
        desktop_focus_port = focus.port
      end
      if type(focus.auth_token) == "string" and focus.auth_token ~= "" then
        desktop_focus_token = focus.auth_token
      end
    end
    return true
  end
  log("embedded auth token file is unavailable or invalid")
  return false
end

local function attach_auth(payload)
  payload.auth_token = auth_token
  return payload
end

local function request_auth_ok(request)
  return type(request) == "table"
    and type(auth_token) == "string"
    and request.auth_token == auth_token
end

local function request_cutagent_focus_via_broker()
  if not IS_WINDOWS or not socket then return end
  if not load_auth_config() then return end
  if desktop_focus_host and desktop_focus_port and desktop_focus_token then
    local ok_focus_tcp, focus_tcp = pcall(function() return socket.tcp() end)
    if ok_focus_tcp and focus_tcp then
      focus_tcp:settimeout(1.5)
      local ok_focus_connect = focus_tcp:connect(desktop_focus_host, desktop_focus_port)
      if ok_focus_connect then
        local focus_payload = {
          auth_token = desktop_focus_token,
          source = "DaVinciResolveSDK.lua",
          event = "resolve_free_script_started",
        }
        pcall(function() focus_tcp:send(json.encode(focus_payload) .. "\n") end)
        pcall(function() focus_tcp:close() end)
        return
      end
      pcall(function() focus_tcp:close() end)
    end
  end
  local ok_tcp, tcp = pcall(function() return socket.tcp() end)
  if not ok_tcp or not tcp then return end
  tcp:settimeout(1.5)
  local ok_connect = tcp:connect(bridge_host, bridge_port)
  if not ok_connect then
    pcall(function() tcp:close() end)
    return
  end
  local payload = attach_auth({
    id = "lua-focus",
    method = "focus",
    params = {
      role = "lua",
      client_id = http_client_id,
      bridge_version = BRIDGE_VERSION,
      protocol_version = PROTOCOL_VERSION,
    },
  })
  pcall(function() tcp:send(json.encode(payload) .. "\n") end)
  pcall(function() tcp:close() end)
end

-- Standalone runtime does not focus a commercial desktop application.

local function is_resolve_root_candidate(candidate)
  if not candidate then return false end
  local ok_pm, pm = pcall(function()
    if not candidate.GetProjectManager then return nil end
    return candidate:GetProjectManager()
  end)
  if not ok_pm or not pm then return false end
  local ok_project_call = pcall(function()
    return pm:GetCurrentProject()
  end)
  return ok_project_call
end

local function resolve_from_fusion_candidate(candidate)
  if not candidate then return nil end
  local ok_method, resolved = pcall(function()
    if candidate.GetResolve then
      return candidate:GetResolve()
    end
    return nil
  end)
  if ok_method and is_resolve_root_candidate(resolved) then return resolved end
  return nil
end

local function acquire_resolve()
  local resolved = rawget(_G, "resolve")
  if not is_resolve_root_candidate(resolved) then resolved = nil end
  if not resolved and type(rawget(_G, "Resolve")) == "function" then
    local ok_resolve, candidate = pcall(function() return Resolve() end)
    if ok_resolve and is_resolve_root_candidate(candidate) then resolved = candidate end
  end
  if not resolved and bmd and bmd.scriptapp then
    local ok_bmd, candidate = pcall(function() return bmd.scriptapp("Resolve") end)
    if ok_bmd and is_resolve_root_candidate(candidate) then resolved = candidate end
  end
  if not resolved then
    resolved = resolve_from_fusion_candidate(rawget(_G, "fu"))
  end
  if not resolved then
    resolved = resolve_from_fusion_candidate(rawget(_G, "fusion"))
  end
  if not resolved then
    resolved = resolve_from_fusion_candidate(rawget(_G, "app"))
  end
  return resolved
end

local function sleep_seconds(seconds)
  if socket and socket.sleep then
    socket.sleep(seconds)
  else
    os.execute("sleep " .. tostring(seconds))
  end
end

local resolve = acquire_resolve()
local resolve_attempt = 0
while not resolve do
  resolve_attempt = resolve_attempt + 1
  if resolve_attempt == 1 or resolve_attempt % 6 == 0 then
    local message = "Waiting for DaVinci Resolve API before starting CutAgent bridge."
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
  end
  sleep_seconds(5)
  resolve = acquire_resolve()
end
log("DaVinci Resolve API available")

local refs = {
  resolve = resolve,
}
local ref_counter = 0
local unpack_values = table.unpack or unpack

local function make_ref(prefix, value)
  if not value then return nil end
  ref_counter = ref_counter + 1
  local ref = prefix .. ":" .. tostring(ref_counter)
  refs[ref] = value
  return ref
end

local function stable_ref(name, value)
  if value then refs[name] = value end
  return name
end

local function ref_for_method(method, value)
  if method == "GetProjectManager" then return stable_ref("project_manager", value)
  elseif method == "GetCurrentProject" or method == "LoadProject" or method == "CreateProject" then return stable_ref("project", value)
  elseif method == "GetMediaPool" then return stable_ref("media_pool", value)
  elseif method == "GetCurrentTimeline" then return stable_ref("timeline", value)
  elseif method == "GetRootFolder" then return stable_ref("root_folder", value)
  elseif method == "GetCurrentFolder" then return stable_ref("current_folder", value)
  end
  return make_ref("object", value)
end

local function hydrate_stable_ref(target, force)
  if refs[target] and not force then return refs[target] end
  if target == "resolve" then
    local refreshed = acquire_resolve()
    if refreshed then
      resolve = refreshed
      refs.resolve = refreshed
      return refreshed
    end
  elseif target == "project_manager" then
    if force then hydrate_stable_ref("resolve", true) end
    local ok_pm, pm = pcall(function() return resolve:GetProjectManager() end)
    if ok_pm and pm then return stable_ref("project_manager", pm) end
  elseif target == "project" then
    local pm = hydrate_stable_ref("project_manager", force)
    if pm then
      local ok_project, project = pcall(function() return pm:GetCurrentProject() end)
      if ok_project and project then return stable_ref("project", project) end
    end
  elseif target == "media_pool" then
    local project = hydrate_stable_ref("project", force)
    if project then
      local ok_media_pool, media_pool = pcall(function() return project:GetMediaPool() end)
      if ok_media_pool and media_pool then return stable_ref("media_pool", media_pool) end
    end
  elseif target == "timeline" then
    local project = hydrate_stable_ref("project", force)
    if project then
      local ok_timeline, timeline = pcall(function() return project:GetCurrentTimeline() end)
      if ok_timeline and timeline then return stable_ref("timeline", timeline) end
    end
  elseif target == "root_folder" then
    local media_pool = hydrate_stable_ref("media_pool", force)
    if media_pool then
      local ok_root, root = pcall(function() return media_pool:GetRootFolder() end)
      if ok_root and root then return stable_ref("root_folder", root) end
    end
  elseif target == "current_folder" then
    local media_pool = hydrate_stable_ref("media_pool", force)
    if media_pool then
      local ok_folder, folder = pcall(function() return media_pool:GetCurrentFolder() end)
      if ok_folder and folder then return stable_ref("current_folder", folder) end
    end
  end
  return nil
end

local object_list_return_methods = {
  GetClipList = true,
  GetSubFolderList = true,
  GetTimelineList = true,
  GetItemListInTrack = true,
  ImportMedia = true,
  AddItemListToMediaPool = true,
  AppendToTimeline = true,
}

local function wrap_object_list(value)
  local out = {}
  for key, item in pairs(value) do
    if key ~= "__flags" then
      local item_type = type(item)
      if item_type == "table" or item_type == "userdata" then
        out[key] = { __cutagent_ref__ = make_ref("object", item) }
      else
        out[key] = item
      end
    end
  end
  return out
end

local function is_resolve_object(value)
  if type(value) ~= "table" and type(value) ~= "userdata" then return false end
  local checks = { "GetName", "GetMediaPool", "GetCurrentTimeline", "GetClipList", "GetDuration" }
  for _, name in ipairs(checks) do
    local ok, attr = pcall(function() return value[name] end)
    if ok and type(attr) == "function" then return true end
  end
  return false
end

local function unwrap(value)
  if type(value) ~= "table" then return value end
  if value.__cutagent_ref__ then
    return refs[value.__cutagent_ref__]
  end
  local out = {}
  for key, item in pairs(value) do
    out[key] = unwrap(item)
  end
  return out
end

local function wrap(value, target, method)
  if value == nil then return nil end
  local t = type(value)
  if t == "string" or t == "number" or t == "boolean" then return value end
  if t == "table" then
    if object_list_return_methods[method] then
      return wrap_object_list(value)
    end
    if is_resolve_object(value) then
      return { __cutagent_ref__ = ref_for_method(method, value) }
    end
    local out = {}
    for key, item in pairs(value) do
      out[key] = wrap(item, target, method)
    end
    return out
  end
  if t == "userdata" then
    return { __cutagent_ref__ = ref_for_method(method, value) }
  end
  return tostring(value)
end

local quit_after_response = false

local function call_known_stable_method(object, target, method, args)
  if target == "resolve" then
    -- Resolve's Lua userdata does not consistently expose root methods through
    -- dynamic indexing. Dispatch application-level methods explicitly so the
    -- embedded Free transport matches the supported Python proxy contract.
    if method == "GetProductName" then return true, object:GetProductName() end
    if method == "GetProjectManager" then return true, object:GetProjectManager() end
    if method == "Quit" then
      -- DaVinci Resolve Free does not complete Resolve:Quit() while this
      -- persistent utility script is still servicing the bridge request.
      -- Acknowledge the request first, then call Quit and unwind the poll loop
      -- so DaVinci Resolve can process the application shutdown.
      quit_after_response = true
      return true, true
    end
  elseif target == "project_manager" then
    if method == "GetCurrentProject" then return true, object:GetCurrentProject() end
    if method == "LoadProject" then return true, object:LoadProject(args[1]) end
    if method == "CreateProject" then
      if args[2] ~= nil then return true, object:CreateProject(args[1], args[2]) end
      return true, object:CreateProject(args[1])
    end
    if method == "CloseProject" then return true, object:CloseProject(args[1]) end
    if method == "SaveProject" then return true, object:SaveProject() end
    if method == "GetProjectListInCurrentFolder" then return true, object:GetProjectListInCurrentFolder() end
    if method == "GetFolderListInCurrentFolder" then return true, object:GetFolderListInCurrentFolder() end
    if method == "GetCurrentDatabase" then return true, object:GetCurrentDatabase() end
    if method == "GetDatabaseList" then return true, object:GetDatabaseList() end
  elseif target == "project" then
    if method == "GetName" then return true, object:GetName() end
    if method == "GetMediaPool" then return true, object:GetMediaPool() end
    if method == "GetCurrentTimeline" then return true, object:GetCurrentTimeline() end
    if method == "GetTimelineCount" then return true, object:GetTimelineCount() end
    if method == "GetSetting" then return true, object:GetSetting(args[1]) end
    if method == "SetRenderSettings" then return true, object:SetRenderSettings(args[1]) end
    if method == "AddRenderJob" then return true, object:AddRenderJob() end
    if method == "StartRendering" then return true, object:StartRendering(unpack_values(args)) end
    if method == "IsRenderingInProgress" then return true, object:IsRenderingInProgress() end
    if method == "GetRenderJobList" then return true, object:GetRenderJobList() end
    if method == "GetRenderJobStatus" then return true, object:GetRenderJobStatus(args[1]) end
    if method == "GetRenderFormats" then return true, object:GetRenderFormats() end
    if method == "GetRenderCodecs" then return true, object:GetRenderCodecs(args[1]) end
    if method == "SetCurrentRenderFormatAndCodec" then return true, object:SetCurrentRenderFormatAndCodec(args[1], args[2]) end
  elseif target == "media_pool" then
    if method == "GetRootFolder" then return true, object:GetRootFolder() end
    if method == "GetCurrentFolder" then return true, object:GetCurrentFolder() end
  elseif target == "timeline" then
    if method == "GetName" then return true, object:GetName() end
    if method == "GetSetting" then return true, object:GetSetting(args[1]) end
    if method == "GetStartFrame" then return true, object:GetStartFrame() end
    if method == "GetTrackCount" then return true, object:GetTrackCount(args[1]) end
    if method == "GetTrackName" then return true, object:GetTrackName(args[1], args[2]) end
    if method == "GetTrackSubType" then return true, object:GetTrackSubType(args[1], args[2]) end
    if method == "GetItemListInTrack" then return true, object:GetItemListInTrack(args[1], args[2]) end
  end
  return false, nil
end

local function call_method(params)
  local target = params.target
  local method = params.method
  local args = params.args or {}
  local object = refs[target] or hydrate_stable_ref(target)
  if not object then
    error("unknown target ref: " .. tostring(target))
  end
  local unpacked = {}
  for index, item in ipairs(args) do
    unpacked[index] = unwrap(item)
  end
  local known_ok, known_result = call_known_stable_method(object, target, method, unpacked)
  if known_ok then
    return wrap(known_result, target, method)
  end
  local fn = object[method]
  if type(fn) ~= "function" then
    object = hydrate_stable_ref(target, true) or object
    known_ok, known_result = call_known_stable_method(object, target, method, unpacked)
    if known_ok then
      return wrap(known_result, target, method)
    end
    fn = object[method]
    if type(fn) ~= "function" then
      error("method not available: " .. tostring(method))
    end
  end
  local result = fn(object, unpack_values(unpacked))
  return wrap(result, target, method)
end

local function execute(params)
  if params.op == "call" then
    return call_method(params)
  elseif params.op == "get_version" then
    local version = nil
    local version_string = nil
    local product = nil
    pcall(function() version = resolve:GetVersion() end)
    pcall(function() version_string = resolve:GetVersionString() end)
    pcall(function() product = resolve:GetProductName() end)
    return {
      version = version,
      version_string = version_string,
      product = product,
      bridge_version = BRIDGE_VERSION,
      protocol_version = PROTOCOL_VERSION,
    }
  end
  error("unknown execute op: " .. tostring(params.op))
end

local function send_line(tcp, payload)
  tcp:send(json.encode(payload) .. "\n")
end

local function response_error_message(response)
  if type(response) ~= "table" then
    return "invalid bridge response"
  end
  if type(response.error) == "table" then
    local code = tostring(response.error.code or "API_CALL_FAILED")
    local message = tostring(response.error.message or "Bridge request failed.")
    if code == "EMBEDDED_BRIDGE_OUTDATED" then
      return "DaVinciResolveSDK.lua is out of date. Reinstall the DaVinci Resolve utility script from CutAgent."
    end
    if code == "EMBEDDED_BRIDGE_AUTH_FAILED" then
      return "Embedded bridge authentication failed. Restart the CutAgent script from Workspace > Scripts > DaVinciResolveSDK."
    end
    return code .. ": " .. message
  end
  local result = response.result
  if type(result) == "table" and result.ok == false then
    if result.status == "outdated" then
      return "DaVinciResolveSDK.lua is out of date. Reinstall the DaVinci Resolve utility script from CutAgent."
    end
    return "Embedded bridge rejected DaVinciResolveSDK.lua: " .. tostring(result.status or "unknown")
  end
  return nil
end

local function client_info(connection)
  return {
    role = "lua",
    client_id = http_client_id,
    connection = connection,
    bridge_version = BRIDGE_VERSION,
    protocol_version = PROTOCOL_VERSION,
    resolve_version = (resolve.GetVersionString and resolve:GetVersionString()) or nil,
    product = (resolve.GetProductName and resolve:GetProductName()) or nil,
  }
end

local function write_spool_response(payload)
  payload = attach_auth(payload)
  payload.client = client_info("file_spool")
  payload.updated_at = os and type(os.time) == "function" and os.time() or nil
  local encoded = base64_encode(json.encode(payload))
  local ok_set = pcall(function() fusion:SetData(SPOOL_RESPONSE_KEY, encoded) end)
  if not ok_set then return false, "response_set_failed" end
  local ok_save, save_error = pcall(function() fusion:SavePrefs(SPOOL_RESPONSE_PATH) end)
  pcall(function() fusion:SetData(SPOOL_RESPONSE_KEY, nil) end)
  if not ok_save then return false, tostring(save_error or "response_save_failed") end
  return true, nil
end

local function wait_for_spool_request_release(request_id)
  -- The broker removes the request only after it observes our accepted
  -- response. Do not mutate until that acknowledgement is durable; if the
  -- broker dies, a later script restart must not replay the request.
  for _ = 1, 60 do
    local pending = load_spool_payload(SPOOL_REQUEST_PATH)
    if type(pending) ~= "table" or pending.id ~= request_id then return true end
    bmd.wait(0.05)
  end
  return false
end

local function run_spool_bridge()
  if not fusion or type(fusion.SetData) ~= "function" or type(fusion.SavePrefs) ~= "function" then
    print("[DaVinci Resolve SDK] DaVinci Resolve file-spool transport is unavailable.")
    return
  end
  if not bmd or type(bmd.wait) ~= "function" or type(loadfile) ~= "function" then
    print("[DaVinci Resolve SDK] DaVinci Resolve file-spool polling is unavailable.")
    return
  end
  if not load_auth_config() then
    print("[DaVinci Resolve SDK] Could not read embedded bridge auth token. Start CutAgent before running this script.")
    return
  end

  write_spool_response({
    id = "lua-spool-hello",
    state = "complete",
    result = { ok = true, status = "registered", connection = "file_spool" },
    error = nil,
  })
  print("[DaVinci Resolve SDK] Embedded bridge connected with the DaVinci Resolve file transport. Keep this script running while using CutAgent with DaVinci Resolve 21.1+ Free.")

  local last_request_id = nil
  while true do
    local request = load_spool_payload(SPOOL_REQUEST_PATH)
    if type(request) == "table" and type(request.id) == "string" and request.id ~= last_request_id then
      last_request_id = request.id
      if not request_auth_ok(request) then
        load_auth_config()
      end
      local expired = type(request.expires_at) == "number"
        and os and type(os.time) == "function"
        and os.time() > request.expires_at
      if expired then
        write_spool_response({
          id = request.id,
          state = "complete",
          result = nil,
          error = {
            code = "EMBEDDED_BRIDGE_TIMEOUT",
            message = "The embedded file-spool request expired before execution.",
            details = { source = "DaVinciResolveSDK.lua", connection = "file_spool" },
          },
        })
      elseif not request_auth_ok(request) then
        write_spool_response({
          id = request.id,
          state = "complete",
          result = nil,
          error = {
            code = "EMBEDDED_BRIDGE_AUTH_FAILED",
            message = "Embedded bridge request authentication failed.",
            details = { source = "DaVinciResolveSDK.lua", connection = "file_spool" },
          },
        })
      elseif request.method == "probe" then
        write_spool_response({
          id = request.id,
          state = "complete",
          result = { ok = true, status = "registered", client = client_info("file_spool") },
          error = nil,
        })
      elseif request.method == "execute" then
        local accepted_written = write_spool_response({
          id = request.id,
          state = "accepted",
          result = nil,
          error = nil,
        })
        if not accepted_written then
          print("[DaVinci Resolve SDK] Could not acknowledge the embedded file-spool request; refusing to execute it.")
        elseif not wait_for_spool_request_release(request.id) then
          write_spool_response({
            id = request.id,
            state = "complete",
            result = nil,
            error = {
              code = "EMBEDDED_BRIDGE_NOT_ACKNOWLEDGED",
              message = "CutAgent did not acknowledge the embedded request before execution.",
              details = { source = "DaVinciResolveSDK.lua", connection = "file_spool" },
            },
          })
        else
          local ok_exec, result = pcall(execute, request.params or {})
          if ok_exec then
            write_spool_response({ id = request.id, state = "complete", result = result, error = nil })
            if quit_after_response then
              pcall(function() resolve:Quit() end)
              break
            end
          else
            write_spool_response({
              id = request.id,
              state = "complete",
              result = nil,
              error = {
                code = "API_CALL_FAILED",
                message = tostring(result),
                details = { source = "DaVinciResolveSDK.lua", connection = "file_spool" },
              },
            })
          end
        end
      else
        write_spool_response({
          id = request.id,
          state = "complete",
          result = nil,
          error = {
            code = "VALIDATION_ERROR",
            message = "Unknown embedded file-spool request method.",
            details = { source = "DaVinciResolveSDK.lua", method = request.method },
          },
        })
      end
    end
    bmd.wait(0.05)
  end
end

local function run_socket_bridge()
  local tcp = assert(socket.tcp())
  if not load_auth_config() then
    local message = "Could not read embedded bridge auth token. Start the CutAgent embedded server before running this script."
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    return
  end
  tcp:settimeout(5)
  local ok_connect, err = tcp:connect(bridge_host, bridge_port)
  if not ok_connect then
    local message = "Could not connect to embedded bridge server at " .. bridge_host .. ":" .. tostring(bridge_port) .. ": " .. tostring(err)
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    return
  end
  tcp:settimeout(0)

  send_line(tcp, attach_auth({
    id = "lua-hello",
    method = "hello",
    params = client_info("lua_socket"),
  }))

  tcp:settimeout(5)
  local hello_line, hello_err = tcp:receive("*l")
  tcp:settimeout(0)
  if not hello_line then
    local message = "Embedded bridge did not acknowledge DaVinciResolveSDK.lua: " .. tostring(hello_err)
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    pcall(function() tcp:close() end)
    return
  end
  local ok_hello, hello_response = pcall(json.decode, hello_line)
  local hello_failure = nil
  if ok_hello then
    hello_failure = response_error_message(hello_response)
  else
    hello_failure = "invalid bridge response"
  end
  if hello_failure then
    print("[DaVinci Resolve SDK] " .. hello_failure)
    log(hello_failure)
    pcall(function() tcp:close() end)
    return
  end

  print("[DaVinci Resolve SDK] Embedded bridge connected. Keep this script running while using CutAgent with DaVinci Resolve 20+ Free.")
  log("embedded bridge connected via LuaSocket")

  while true do
    local ready = socket.select({ tcp }, nil, 0.1)
    if #ready > 0 then
      local line, read_err = tcp:receive("*l")
      if line then
        local ok_decode, request = pcall(json.decode, line)
        if ok_decode and request then
          if not request_auth_ok(request) then
            send_line(tcp, attach_auth({
              id = request.id,
              result = nil,
              error = {
                code = "EMBEDDED_BRIDGE_AUTH_FAILED",
                message = "Embedded bridge request authentication failed.",
                details = { source = "DaVinciResolveSDK.lua" },
              },
            }))
          else
            local ok_exec, result = pcall(execute, request.params or {})
            if ok_exec then
              send_line(tcp, attach_auth({ id = request.id, result = result, error = nil }))
              if quit_after_response then
                pcall(function() resolve:Quit() end)
                break
              end
            else
              send_line(tcp, attach_auth({
                id = request.id,
                result = nil,
                error = {
                  code = "API_CALL_FAILED",
                  message = tostring(result),
                  details = { source = "DaVinciResolveSDK.lua" },
                },
              }))
            end
          end
        else
          send_line(tcp, attach_auth({
            id = nil,
            result = nil,
            error = {
              code = "VALIDATION_ERROR",
              message = tostring(request),
              details = { source = "DaVinciResolveSDK.lua" },
            },
          }))
        end
      elseif read_err == "closed" then
        print("[DaVinci Resolve SDK] Embedded bridge disconnected.")
        log("embedded bridge disconnected")
        break
      end
    end
  end

  pcall(function() tcp:close() end)
  log("bridge script stopped")
end

local function http_post(path, payload, timeout_s)
  local url = "http://" .. bridge_host .. ":" .. tostring(bridge_port) .. path
  local payload_file = payload_temp_path()
  local file = io.open(payload_file, "w")
  if not file then return nil, "payload_file_unavailable" end
  file:write(json.encode(attach_auth(payload)))
  file:close()
  local command = windows_curl_path() .. " -sS --max-time " .. tostring(timeout_s or 5)
    .. " -H " .. shell_quote("Content-Type: application/json")
    .. " --data-binary " .. shell_quote("@" .. payload_file)
    .. " " .. shell_quote(url)
    .. " 2>&1"
  local handle = io.popen(command, "r")
  if not handle then
    os.remove(payload_file)
    return nil, "curl_unavailable"
  end
  local output = handle:read("*a")
  local ok_close, _, exit_code = handle:close()
  os.remove(payload_file)
  if not ok_close then
    return nil, "curl_failed:" .. tostring(exit_code) .. ":" .. tostring(output)
  end
  if not output or output == "" then
    return nil, "empty_response"
  end
  local ok_decode, decoded = pcall(json.decode, output)
  if not ok_decode then
    return nil, "invalid_json:" .. tostring(decoded)
  end
  local bridge_error = response_error_message(decoded)
  if bridge_error then
    return nil, bridge_error
  end
  return decoded, nil
end

local function respond_http(request)
  if not request_auth_ok(request) then
    http_post("/lua/respond", {
      id = request.id,
      result = nil,
      error = {
        code = "EMBEDDED_BRIDGE_AUTH_FAILED",
        message = "Embedded bridge request authentication failed.",
        details = { source = "DaVinciResolveSDK.lua" },
      },
    }, 5)
    return
  end
  local ok_exec, result = pcall(execute, request.params or {})
  if ok_exec then
    http_post("/lua/respond", { id = request.id, result = result, error = nil }, 5)
    if quit_after_response then
      pcall(function() resolve:Quit() end)
      return true
    end
  else
    http_post("/lua/respond", {
      id = request.id,
      result = nil,
      error = {
        code = "API_CALL_FAILED",
        message = tostring(result),
        details = { source = "DaVinciResolveSDK.lua" },
      },
    }, 5)
  end
end

local function run_http_bridge()
  if not windows_http_poll_fallback_allowed() then
    local message = "LuaSocket unavailable and Windows curl HTTP polling is disabled to avoid focus-stealing console windows. Reinstall CutAgent support with the packaged Windows socket transport, or set CUTAGENT_ALLOW_WINDOWS_CURL_HTTP_POLL=1 only for local debugging."
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    return
  end
  if not load_auth_config() then
    local message = "Could not read embedded bridge auth token. Start the CutAgent embedded server before running this script."
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    return
  end
  local hello, hello_err = http_post("/lua/hello", { params = client_info("http_poll") }, 5)
  if not hello then
    local message = "Could not connect to embedded HTTP bridge at " .. bridge_host .. ":" .. tostring(bridge_port) .. ": " .. tostring(hello_err)
    print("[DaVinci Resolve SDK] " .. message)
    log(message)
    return
  end
  local hello_failure = response_error_message(hello)
  if hello_failure then
    print("[DaVinci Resolve SDK] " .. hello_failure)
    log(hello_failure)
    return
  end

  print("[DaVinci Resolve SDK] Embedded bridge connected with HTTP polling. Keep this script running while using CutAgent with DaVinci Resolve 20+ Free.")
  log("embedded bridge connected via HTTP polling")

  local poll_failures = 0
  while true do
    local poll, poll_err = http_post("/lua/poll", {
      protocol_version = PROTOCOL_VERSION,
      client_id = http_client_id,
    }, HTTP_POLL_TIMEOUT_SECONDS)
    if poll and poll.request then
      poll_failures = 0
      if respond_http(poll.request) then
        break
      end
    elseif poll then
      poll_failures = 0
    elseif poll_err then
      if tostring(poll_err):find("EMBEDDED_BRIDGE_CLIENT_REPLACED", 1, true) then
        log("embedded HTTP poll replaced by newer client; stopping old script")
        break
      end
      poll_failures = poll_failures + 1
      log("embedded HTTP poll failed: " .. tostring(poll_err))
      if poll_failures >= HTTP_POLL_MAX_FAILURES then
        log("embedded HTTP polling failed repeatedly; stopping script")
        break
      end
      sleep_seconds(math.min(poll_failures * 2, HTTP_POLL_RETRY_MAX_SECONDS))
      load_auth_config()
    end
  end

  log("HTTP bridge script stopped")
end

  if socket then
    run_socket_bridge()
  elseif type(loadfile) == "function" and fusion and type(fusion.SavePrefs) == "function" then
    run_spool_bridge()
  else
    run_http_bridge()
  end
end

local bridge_ok, bridge_error = pcall(run_cutagent_bridge)
_G.__DAVINCI_RESOLVE_SDK_BRIDGE_RUNNING = nil
if not bridge_ok then
  local failure = "embedded bridge stopped unexpectedly: " .. tostring(bridge_error)
  print("[DaVinci Resolve SDK] " .. failure)
end
