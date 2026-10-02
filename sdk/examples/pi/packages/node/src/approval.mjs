import { spawn } from "node:child_process";

/** Apply matching Watcher policy before native dispatch; subprocess failures withhold the call. */
export function requireApproval(payload) {
  return new Promise((resolve, reject) => {
    if (!process.env.WATCHER_PYTHON) { reject(new Error("WATCHER_PYTHON is required")); return; }
    const child = spawn(process.env.WATCHER_PYTHON, ["-m", "watcher_pi_bridge.pre_tool"], {
      stdio: ["pipe", "pipe", "inherit"], timeout: 460000,
    });
    let output = "";
    child.stdout.on("data", (chunk) => { output += chunk; if (output.length > 4096) child.kill(); });
    child.on("error", reject);
    child.stdin.on("error", reject);
    child.on("close", (code) => {
      try {
        const decision = JSON.parse(output);
        if (code !== 0 || decision.allow !== true || decision.tool_use_id !== payload.call.id || decision.session_id !== payload.session_id) {
          throw new Error("Watcher did not confirm approval");
        }
        resolve();
      } catch { reject(new Error("Watcher did not confirm approval")); }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}
