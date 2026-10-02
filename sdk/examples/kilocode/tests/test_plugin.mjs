import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, chmod, readFile, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import plugin, { deliver } from "watcher-kilocode-example/plugin";

test("native plugin contract reaches a bridge process with an intact snapshot", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "watcher-plugin-contract-"));
  const executable = path.join(directory, "capture.js");
  const capture = path.join(directory, "payload.json");
  await writeFile(executable, '#!/bin/sh\ncat > "$WATCHER_TEST_CAPTURE"\n');
  await chmod(executable, 0o700);
  const originalPython = process.env.WATCHER_PYTHON;
  const originalCapture = process.env.WATCHER_TEST_CAPTURE;
  process.env.WATCHER_PYTHON = executable;
  process.env.WATCHER_TEST_CAPTURE = capture;
  t.after(() => {
    if (originalPython === undefined) delete process.env.WATCHER_PYTHON; else process.env.WATCHER_PYTHON = originalPython;
    if (originalCapture === undefined) delete process.env.WATCHER_TEST_CAPTURE; else process.env.WATCHER_TEST_CAPTURE = originalCapture;
  });
  const fixture = JSON.parse(await readFile(new URL("./fixtures/fixture.json", import.meta.url), "utf8"));
  const hooks = await plugin.server({ client: { session: { messages: async (request) => {
    assert.deepEqual(request, { path: { id: "native-session" } });
    return { data: fixture };
  }}}});
  await hooks.event({ event: { type: "message.updated", properties: {} } });
  await assert.rejects(access(capture));
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: "native-session" } } });
  assert.deepEqual(JSON.parse(await readFile(capture, "utf8")), { session_id: "native-session", messages: fixture });
});

test("missing bridge configuration is observational", async () => {
  const previous = process.env.WATCHER_PYTHON;
  delete process.env.WATCHER_PYTHON;
  try { await deliver({ session_id: "s", messages: [] }); }
  finally { if (previous !== undefined) process.env.WATCHER_PYTHON = previous; }
});
