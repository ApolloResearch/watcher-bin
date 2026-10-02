import { spawn } from "node:child_process";

/** Send a bounded subprocess snapshot. Errors stay observational and never change tool output. */
export function deliver(payload, { recordOnly = false } = {}) {
  return new Promise((resolve) => {
    if (!process.env.WATCHER_PYTHON) {
      process.stderr.write("WATCHER_PYTHON is required for Watcher observation.\n");
      resolve(); return;
    }
    const child = spawn(process.env.WATCHER_PYTHON, ["-m", "watcher_opencode_bridge.integration", ...(recordOnly ? ["--record-only"] : [])], {
      stdio: ["pipe", "ignore", "inherit"], timeout: 15000,
    });
    child.on("error", () => { process.stderr.write("Watcher bridge failed.\n"); resolve(); });
    child.stdin.on("error", () => {});
    child.on("close", resolve);
    child.stdin.end(JSON.stringify(payload));
  });
}

async function watcherPlugin({ client }, { recordOnly = false } = {}) {
  return { event: async ({ event }) => {
    if (event.type !== "session.idle") return;
    try {
      const session_id = event.properties.sessionID;
      const response = await client.session.messages({ path: { id: session_id } });
      if (response.error || !Array.isArray(response.data)) throw new Error("Snapshot unavailable");
      await deliver({ session_id, messages: response.data }, { recordOnly });
    } catch {
      process.stderr.write("Watcher native snapshot failed.\n");
    }
  } };
}

export default { id: "watcher-sdk-example-opencode", server: watcherPlugin };
