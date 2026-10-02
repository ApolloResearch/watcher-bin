import { spawn } from "node:child_process";

/** Send a bounded subprocess snapshot. Errors stay observational and never change tool output. */
export function deliver(payload, {recordOnly = false} = {}) {
  return new Promise((resolve) => {
    if (!process.env.WATCHER_PYTHON) {
      process.stderr.write("WATCHER_PYTHON is required for Watcher observation.\n");
      resolve(); return;
    }
    const child = spawn(process.env.WATCHER_PYTHON, ["-m", "watcher_pi_bridge.integration", ...(recordOnly ? ["--record-only"] : [])], {
      stdio: ["pipe", "ignore", "inherit"], timeout: 15000,
    });
    child.on("error", () => { process.stderr.write("Watcher bridge failed.\n"); resolve(); });
    child.stdin.on("error", () => {});
    child.on("close", resolve);
    child.stdin.end(JSON.stringify(payload));
  });
}

export default function watcherExtension(pi, options = {}) {
  pi.on("agent_end", async (_event, ctx) => {
    const entries = ctx.sessionManager.getBranch();
    if (entries.some((entry) => entry.type === "compaction")) {
      process.stderr.write("Watcher does not support compacted Pi branches.\n");
      return;
    }
    const messages = entries.filter((entry) => entry.type === "message").map((entry) => entry.message);
    await deliver({ session_id: ctx.sessionManager.getSessionId(), messages }, options);
  });
}
