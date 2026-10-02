import { readVisibleSessionTranscriptMessageEntries } from "openclaw/plugin-sdk/session-transcript-runtime";
import { invokeBridge } from "./bridge.mjs";

/** Register observation and, when selected, an awaited recorded tool approval.
 * The embedded runtime supplies native identity; other harness relays are unverified.
 * Other plugins must not rewrite tool arguments after or before this assessment.
 */
export default function register(api) {
  const policy = api.config.plugins?.entries?.["watcher-openclaw-example"]?.hooks;
  if (policy?.allowConversationAccess !== true) {
    throw new Error("Watcher requires explicit allowConversationAccess");
  }
  const mode = api.pluginConfig?.mode;
  if (!["observe", "enforce"].includes(mode)) throw new Error("Select observe or enforce mode");
  api.on("agent_end", async (event, ctx) => {
    try {
      if (!ctx.sessionId) throw new Error("Missing session identity");
      await invokeBridge("watcher_openclaw_bridge.integration", { session_id: ctx.sessionId, messages: event.messages, record_only: mode === "enforce" });
    } catch { api.logger.warn("Watcher did not finish observing this turn."); }
  }, { timeoutMs: 70000 });
  if (mode === "enforce") {
    api.on("before_tool_call", async (event, ctx) => {
      try {
        if (!ctx.sessionId || !ctx.agentId || !ctx.sessionKey || !event.toolCallId) throw new Error("Missing native identity");
        const entries = await readVisibleSessionTranscriptMessageEntries({
          agentId: ctx.agentId, sessionId: ctx.sessionId, sessionKey: ctx.sessionKey,
        });
        if (!entries.length) throw new Error("Missing native history");
        const payload = { session_id: ctx.sessionId, messages: entries.map(entry => entry.message),
          call: { id: event.toolCallId, function: event.toolName, arguments: event.params } };
        const result = await invokeBridge("watcher_openclaw_bridge.pre_tool", payload, { signal: ctx.abortSignal });
        if (result.allow !== true || result.session_id !== ctx.sessionId || result.tool_use_id !== event.toolCallId) {
          throw new Error("Mismatched Watcher result");
        }
        return {};
      } catch { return { block: true, blockReason: "Watcher did not confirm approval" }; }
    }, { timeoutMs: 70000 });
  }
}
