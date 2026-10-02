local typedefs = require "kong.db.schema.typedefs"

return {
  name = "watcher",
  fields = {
    { protocols = typedefs.protocols_http },
    { config = {
      type = "record",
      fields = {
        { bridge_url = { type = "string", required = true, match = "^https?://" } },
        { bridge_token = { type = "string", required = true, encrypted = true, referenceable = true } },
        { chat_path = { type = "string", default = "/v1/chat/completions" } },
        { timeout_ms = { type = "integer", default = 420000, between = { 1000, 600000 } } },
        { max_body_bytes = { type = "integer", default = 8388608, between = { 1024, 8388608 } } },
      },
    } },
  },
}
