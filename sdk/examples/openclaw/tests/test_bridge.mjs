import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { invokeBridge } from "../packages/node/src/bridge.mjs";

async function interpreter(body) {
  const directory = await mkdtemp(path.join(tmpdir(), "watcher-bridge-"));
  const file = path.join(directory, "python");
  await writeFile(file, "#!/usr/bin/env node\n" + body, { mode: 0o700 });
  return { directory, file };
}

for (const fault of ["exit", "bad-json", "too-large"]) {
  test(`bridge refuses ${fault}`, async () => {
    const { file } = await interpreter(fault === "exit" ? "process.exit(1)" :
      fault === "bad-json" ? 'process.stdout.write("invalid")' : 'process.stdout.write("x".repeat(10000))');
    process.env.WATCHER_PYTHON = file;
    await assert.rejects(invokeBridge("unused", {}));
  });
}

test("bridge accepts exactly the returned JSON", async () => {
  const { file } = await interpreter('process.stdout.write(JSON.stringify({allow:true}))');
  process.env.WATCHER_PYTHON = file;
  assert.deepEqual(await invokeBridge("unused", {}), { allow: true });
});

for (const fault of ["cancellation"]) {
  test(`bridge kills and reaps child on ${fault}`, async () => {
    const { directory, file } = await interpreter('const fs=require("node:fs"); fs.writeFileSync(process.env.PID_FILE,String(process.pid)); setInterval(()=>{},1000);');
    const pidFile = path.join(directory, "pid");
    process.env.WATCHER_PYTHON = file;
    process.env.PID_FILE = pidFile;
    const controller = new AbortController();
    const promise = invokeBridge("unused", {}, { signal: controller.signal, timeoutMs: 60000 });
    // Attach the rejection assertion before the deadline can fire.
    const refused = assert.rejects(promise);
    let pid;
    for (let attempt = 0; attempt < 1000; attempt++) {
      try { pid = Number(await readFile(pidFile, "utf8")); break; } catch { await new Promise(resolve => setTimeout(resolve, 10)); }
    }
    assert.ok(pid, "native child did not start");
    if (fault === "cancellation") controller.abort();
    await refused;
    assert.throws(() => process.kill(pid, 0), { code: "ESRCH" });
  });
}

test("an unavailable interpreter rejects without cancellation", { timeout: 5000 }, async () => {
  process.env.WATCHER_PYTHON = "/does/not/exist";
  await assert.rejects(invokeBridge("unused", {}, { timeoutMs: 30000 }), /Watcher bridge failed/);
});

test("an already cancelled invocation does not spawn", async () => {
  const controller = new AbortController(); controller.abort();
  process.env.WATCHER_PYTHON = "/does/not/exist";
  await assert.rejects(invokeBridge("unused", {}, { signal: controller.signal }));
});
