-- Gate client-executed tools at Kong's buffered response boundary. No provider
-- body is released until the private bridge returns an affirmative verdict.
--
-- A refused proposal is not returned as an error: the bridge asks the model
-- for an alternative through this same route and returns a replacement
-- response with Watcher's notices. Those nested requests carry the bridge's
-- X-Watcher-Alternative marker; once the bridge has verified it against the
-- exact body, this plugin passes the exchange through without the system
-- notice or grading (the outer request grades the alternative) and removes
-- the marker before the request goes upstream.
local cjson = require "cjson.safe"
local http = require "resty.http"
local uuid = require "kong.tools.uuid"

local Watcher = { PRIORITY = 780, VERSION = "0.2.0" }

local ALTERNATIVE_HEADER = "x-watcher-alternative"

-- Return the bridge's decoded reply, or nil when it is unreachable or failed.
local function call_bridge(conf, path, body)
  local client = http.new()
  client:set_timeouts(5000, 10000, conf.timeout_ms)
  local response = client:request_uri(conf.bridge_url .. path, {
    method = "POST",
    body = cjson.encode(body),
    headers = {
      ["Content-Type"] = "application/json",
      ["Authorization"] = "Bearer " .. conf.bridge_token,
    },
    ssl_verify = true,
  })
  if not response or response.status ~= 200 then
    return nil
  end
  local result = cjson.decode(response.body)
  if type(result) ~= "table" then
    return nil
  end
  return result
end

-- The client's own credential, forwarded by the bridge on its nested requests
-- so they authenticate as this client. key-auth with hide_credentials removes
-- the header before this plugin runs, so fall back to the key of the
-- credential key-auth authenticated. Kept in request memory only, never logged.
local function client_credential(conf)
  local value = kong.request.get_header(conf.credential_header)
  if type(value) == "string" and value ~= "" then
    return value
  end
  local credential = kong.client.get_credential()
  if type(credential) == "table" and type(credential.key) == "string" and credential.key ~= "" then
    return credential.key
  end
  return nil
end

-- The headers Kong's router matched this request on: the raw Host header and
-- the client's value for each header the matched route requires. The bridge
-- sends them on its nested requests so they reach this same route when other
-- routes share the path; no other client header is forwarded.
local MAX_ROUTE_HEADERS = 16

local function route_headers(conf)
  local route = kong.router.get_route()
  if type(route) ~= "table" or type(route.headers) ~= "table" then
    return nil
  end
  local result, count = {}, 0
  for name in pairs(route.headers) do
    -- The credential travels separately; the bridge refuses it as a predicate.
    local forwarded = type(name) == "string" and name:lower() ~= conf.credential_header:lower()
    local value = forwarded and kong.request.get_header(name) or nil
    if type(value) == "string" then
      count = count + 1
      if count > MAX_ROUTE_HEADERS then
        return nil
      end
      result[name:lower()] = value
    end
  end
  if count == 0 then
    return nil
  end
  return result
end

function Watcher:access(conf)
  if kong.request.get_method() ~= "POST" or kong.request.get_path() ~= conf.chat_path then
    return kong.response.exit(404, { error = { message = "Unsupported AI gateway route" } })
  end
  -- Connection upgrades can skip the buffered response phase that checks tools.
  if kong.request.get_header("upgrade") ~= nil then
    return kong.response.exit(400, { error = { message = "Protocol upgrades are unsupported on this route" } })
  end
  -- Permit bounded spooled bodies while retaining Kong's normal disk buffering.
  local body = kong.request.get_raw_body(conf.max_body_bytes)
  if not body or #body > conf.max_body_bytes then
    return kong.response.exit(413, { error = { message = "Invalid or oversized request" } })
  end
  local marker = kong.request.get_header(ALTERNATIVE_HEADER)
  if marker ~= nil then
    -- Pass JSON as text so the marker is verified against the exact bytes.
    local result = call_bridge(conf, "/validate", { request_json = body, alternative_marker = marker })
    if result == nil then
      return kong.response.exit(503, { error = { message = "Watcher is unavailable" } })
    elseif result.verdict ~= true then
      return kong.response.exit(403, { error = { message = "Invalid Watcher alternative marker" } })
    end
    kong.service.request.clear_header(ALTERNATIVE_HEADER)
    return
  end
  -- Pass JSON as text so Lua's number representation cannot change tool args.
  local result = call_bridge(conf, "/validate", { request_json = body })
  if result == nil then
    return kong.response.exit(503, { error = { message = "Watcher is unavailable" } })
  elseif result.verdict ~= true or type(result.request_json) ~= "string" then
    return kong.response.exit(422, { error = { message = "Unsupported model request" } })
  end
  local noticed = result.request_json
  if #noticed > conf.max_body_bytes then
    return kong.response.exit(413, { error = { message = "Invalid or oversized request" } })
  end
  -- This replaces the downstream body that ai-proxy, which runs after this
  -- plugin, parses and sends upstream.
  if noticed ~= body then
    kong.service.request.set_raw_body(noticed)
  end
  local identity = "kong:" .. uuid.uuid()
  kong.ctx.plugin.user_agent = kong.request.get_header("user-agent")
  kong.ctx.plugin.request_json = noticed
  kong.ctx.plugin.credential = client_credential(conf)
  kong.ctx.plugin.route_host = kong.request.get_header("host")
  kong.ctx.plugin.route_headers = route_headers(conf)
  kong.ctx.plugin.conversation_id = identity
  kong.response.set_header("X-Watcher-Conversation-Id", identity)
  kong.service.request.enable_buffering()
end

function Watcher:response(conf)
  -- Auth or request validation may have ended the access phase before
  -- proxying, and alternatives requested by the bridge are graded by it.
  if not kong.ctx.plugin.request_json then
    return
  end
  local status = kong.service.response.get_status()
  if status < 200 or status >= 300 then
    return
  end
  local body = kong.service.response.get_raw_body()
  if not body or #body > conf.max_body_bytes then
    return kong.response.exit(502, { error = { message = "Unsupported model response" } })
  end
  local identity = kong.ctx.plugin.conversation_id
  local result = call_bridge(conf, "/evaluate", {
    request_json = kong.ctx.plugin.request_json,
    response_json = body,
    user_agent = kong.ctx.plugin.user_agent,
    metadata = { watcher_conversation_id = identity },
    route_path = conf.chat_path,
    credential_header = conf.credential_header,
    credential = kong.ctx.plugin.credential,
    route_host = kong.ctx.plugin.route_host,
    route_headers = kong.ctx.plugin.route_headers,
    max_body_bytes = conf.max_body_bytes,
  })
  if result == nil then
    return kong.response.exit(503, { error = { message = "Watcher is unavailable" } })
  elseif result.verdict ~= true then
    return kong.response.exit(403, { error = { message = "Response withheld by Watcher" } })
  elseif type(result.response_json) == "string" then
    -- The bridge shortens a replacement to fit max_body_bytes; one that still
    -- does not fit (a provider text near the limit) is withheld whole.
    if #result.response_json > conf.max_body_bytes then
      return kong.response.exit(403, { error = { message = "Response withheld by Watcher" } })
    end
    -- 403 carries the bridge's error for a refusal inside requested structured
    -- output; any other replacement is a completion.
    return kong.response.exit(result.status == 403 and 403 or 200, result.response_json, {
      ["Content-Type"] = "application/json",
      ["X-Watcher-Conversation-Id"] = identity,
    })
  end
end

return Watcher
