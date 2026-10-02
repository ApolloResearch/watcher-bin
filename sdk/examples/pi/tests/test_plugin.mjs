import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, chmod, readFile, access } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import plugin, { deliver } from "watcher-pi-example/plugin";

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
  const handlers = new Map();
  plugin({ on: (event, handler) => handlers.set(event, handler) });
  assert.equal(handlers.has("agent_end"), true);
  await handlers.get("agent_end")({}, { sessionManager: {
    getBranch: () => fixture.map(message => ({ type: "message", message })),
    getSessionId: () => "native-session",
  }});
  assert.deepEqual(JSON.parse(await readFile(capture, "utf8")), { session_id: "native-session", messages: fixture });
});

test("missing bridge configuration is observational", async () => {
  const previous = process.env.WATCHER_PYTHON;
  delete process.env.WATCHER_PYTHON;
  try { await deliver({ session_id: "s", messages: [] }); }
  finally { if (previous !== undefined) process.env.WATCHER_PYTHON = previous; }
});


test("monitored completion invokes transcript-only submission", async (t) => {
  const directory = await mkdtemp(path.join(tmpdir(), "watcher-pi-record-only-"));
  const executable = path.join(directory, "capture.sh");
  const capture = path.join(directory, "args.txt");
  await writeFile(executable, '#!/bin/sh\nprintf "%s\\n" "$@" > "$WATCHER_TEST_CAPTURE"\ncat > /dev/null\n');
  await chmod(executable, 0o700);
  const originalPython = process.env.WATCHER_PYTHON, originalCapture = process.env.WATCHER_TEST_CAPTURE;
  process.env.WATCHER_PYTHON = executable; process.env.WATCHER_TEST_CAPTURE = capture;
  t.after(() => {
    if (originalPython === undefined) delete process.env.WATCHER_PYTHON; else process.env.WATCHER_PYTHON = originalPython;
    if (originalCapture === undefined) delete process.env.WATCHER_TEST_CAPTURE; else process.env.WATCHER_TEST_CAPTURE = originalCapture;
  });
  await deliver({session_id: "native", messages: []}, {recordOnly: true});
  assert.match(await readFile(capture, "utf8"), /--record-only/);
});
