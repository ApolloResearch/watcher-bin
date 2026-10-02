const vscode = require("vscode");
const { spawn } = require("node:child_process");
exports.activate = async function activate(context) {
  const extension = vscode.extensions.getExtension("RooVeterinaryInc.roo-cline");
  if (!extension) throw new Error("Roo Code is not installed in this development host");
  const api = await extension.activate();
  const sessions = new Map();
  const onMessage = (event) => {
    const events = sessions.get(event.taskId) || [];
    events.push(event); sessions.set(event.taskId, events);
  };
  const onComplete = (taskId) => {
    if (!process.env.WATCHER_PYTHON) { process.stderr.write("WATCHER_PYTHON is required.\n"); return; }
    const child = spawn(process.env.WATCHER_PYTHON, ["-m", "watcher_roo_code_bridge.integration"], {
      stdio: ["pipe", "ignore", "inherit"], timeout: 15000,
    });
    child.on("error", () => process.stderr.write("Watcher bridge failed.\n"));
    child.stdin.on("error", () => {});
    child.stdin.end(JSON.stringify({ session_id: taskId, messages: sessions.get(taskId) || [] }));
  };
  api.on("message", onMessage); api.on("taskCompleted", onComplete);
  context.subscriptions.push({ dispose() { api.off("message", onMessage); api.off("taskCompleted", onComplete); } });
};
