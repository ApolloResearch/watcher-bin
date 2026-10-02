import observe from "./plugin.mjs";
import { requireApproval } from "./approval.mjs";

/** Throwing from the awaited native callback withholds execution; idle records the completed transcript. */
async function watcherPlugin(context) {
  const hooks = await observe.server(context, { recordOnly: true });
  return { ...hooks, "tool.execute.before": async (input, output) => {
    const response = await context.client.session.messages({ path: { id: input.sessionID } });
    if (response.error || !Array.isArray(response.data)) throw new Error("Native snapshot unavailable");
    await requireApproval({ session_id: input.sessionID, messages: response.data, cwd: context.directory,
      call: { id: input.callID, function: input.tool, arguments: output.args } });
  } };
}

export default { id: "watcher-sdk-enforcement-kilocode", server: watcherPlugin };
