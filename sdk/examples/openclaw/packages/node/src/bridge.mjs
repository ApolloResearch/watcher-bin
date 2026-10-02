import { spawn } from "node:child_process";

/** Invoke an installed Python bridge, with bounded output and process cleanup.
 * Cancellation and timeout kill the child; completion waits for its close event.
 */
export function invokeBridge(module, payload, { signal, timeoutMs = 65000 } = {}) {
  return new Promise((resolve, reject) => {
    if (!process.env.WATCHER_PYTHON || signal?.aborted) {
      reject(new Error("Watcher bridge is unavailable")); return;
    }
    const child = spawn(process.env.WATCHER_PYTHON, ["-m", module], { stdio: ["pipe", "pipe", "pipe"] });
    let output = "";
    let failure;
    const stop = () => { failure = new Error("Watcher bridge was interrupted"); child.kill("SIGKILL"); };
    const timer = setTimeout(stop, timeoutMs);
    signal?.addEventListener("abort", stop, { once: true });
    child.stdout.on("data", chunk => { output += chunk; if (output.length > 4096) stop(); });
    child.stderr.resume();
    child.stdin.on("error", error => { failure = error; child.kill("SIGKILL"); });
    child.on("error", error => { failure = error; });
    child.on("close", code => {
      clearTimeout(timer); signal?.removeEventListener("abort", stop);
      try {
        if (failure || code !== 0) throw new Error("Watcher bridge failed");
        resolve(JSON.parse(output));
      } catch { reject(new Error("Watcher bridge failed")); }
    });
    child.stdin.end(JSON.stringify(payload));
  });
}
