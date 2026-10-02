import observe from "./plugin.mjs";
import { requireApproval } from "./approval.mjs";

/** Install awaited native tool_call enforcement plus transcript-only agent_end submission. */
export default function watcherExtension(pi) {
  observe(pi, {recordOnly: true});
  pi.on("tool_call", async (event, ctx) => {
    try {
      const entries = ctx.sessionManager.getBranch();
      if (entries.some((entry) => entry.type === "compaction")) throw new Error("Compacted history unsupported");
      const messages = entries.filter((entry) => entry.type === "message").map((entry) => entry.message);
      await requireApproval({ session_id: ctx.sessionManager.getSessionId(), messages, cwd: ctx.cwd,
        call: { id: event.toolCallId, function: event.toolName, arguments: event.input } });
      return {};
    } catch { return { block: true, reason: "Watcher did not confirm approval" }; }
  });
}
