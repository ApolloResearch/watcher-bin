-- Gate client-executed tools at Kong's buffered response boundary. No provider
-- body is released until the private bridge returns an affirmative verdict.
local cjson = require "cjson.safe"
local http = require "resty.http"
local uuid = require "kong.tools.uuid"

local Watcher = { PRIORITY = 780, VERSION = "0.1.0" }

local function verdict(conf, path, body)
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
  return type(result) == "table" and result.verdict == true
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
  -- Pass JSON as text so Lua's number representation cannot change tool args.
  local allowed = verdict(conf, "/validate", { request_json = body })
  if allowed == nil then
    return kong.response.exit(503, { error = { message = "Watcher is unavailable" } })
  elseif not allowed then
    return kong.response.exit(422, { error = { message = "Unsupported model request" } })
  end
  local identity = "kong:" .. uuid.uuid()
  kong.ctx.plugin.user_agent = kong.request.get_header("user-agent")
  kong.ctx.plugin.request_json = body
  kong.ctx.plugin.conversation_id = identity
  kong.response.set_header("X-Watcher-Conversation-Id", identity)
  kong.service.request.enable_buffering()
end

function Watcher:response(conf)
  -- Auth or request validation may have ended the access phase before proxying.
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
  local allowed = verdict(conf, "/evaluate", {
    request_json = kong.ctx.plugin.request_json,
    response_json = body,
    user_agent = kong.ctx.plugin.user_agent,
    metadata = { watcher_conversation_id = kong.ctx.plugin.conversation_id },
  })
  if allowed == nil then
    return kong.response.exit(503, { error = { message = "Watcher is unavailable" } })
  elseif not allowed then
    return kong.response.exit(403, { error = { message = "Response withheld by Watcher" } })
  end
end

return Watcher
