/** Exercise a namespaced Pi ToolCall through the installed session and Watcher extension.
 *
 * Run only in the network-disabled native image under the shared Watcher relay.
 * The public streamFunction supplies a scripted provider message; native Pi owns
 * persistence, extension events, built-in Bash execution, and result generation.
 * This proves the native dispatch boundary, not a hosted provider's serialization.
 */
import assert from "node:assert/strict";
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { networkInterfaces } from "node:os";
import { join } from "node:path";
import {
  createAgentSession,
  DefaultResourceLoader,
  SessionManager,
  SettingsManager,
} from "/opt/native/node_modules/@earendil-works/pi-coding-agent/dist/index.js";
import watcherExtension from "/opt/adapter/node_modules/watcher-pi-example/src/plugin.enforce.mjs";

assert.deepEqual(Object.keys(networkInterfaces()), ["lo"]);
assert.equal(process.env.HOME, "/home/probe");
assert.ok(process.env.WATCHER_URL && process.env.WATCHER_API_KEY);
assert.ok(["0", "1"].includes(process.env.WATCHER_EXPECT_TOOL_EXECUTION));
const expected = process.env.WATCHER_EXPECT_TOOL_EXECUTION === "1";
process.env.WATCHER_PYTHON = "/usr/local/bin/python";
const root = mkdtempSync("/tmp/pi-namespace-");
const agentDir = join(root, "agent");
mkdirSync(agentDir);
const evidence = "/evidence";
const marker = join(root, "native-marker");
const command = `printf namespaced-native-write > ${marker}`;
const provider = "sdk50-fixture";
const model = {
  id: "fixture", name: "fixture", api: "openai-completions", provider,
  baseUrl: "http://127.0.0.1:1/v1", reasoning: false, input: ["text"],
  cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0},
  contextWindow: 100000, maxTokens: 4096,
};
writeFileSync(join(agentDir, "models.json"), JSON.stringify({
  providers: {[provider]: {
    api: model.api, baseUrl: model.baseUrl, apiKey: "fixture", models: [{id: model.id}],
  }},
}));
const record = (filename, value) => appendFileSync(join(evidence, filename), `${JSON.stringify(value)}\n`);
const settingsManager = SettingsManager.inMemory({compaction: {enabled: false}, retry: {enabled: false}});
const sessionManager = SessionManager.create(root, join(root, "sessions"));
const loader = new DefaultResourceLoader({
  cwd: root, agentDir, settingsManager,
  noExtensions: true, noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
  extensionFactories: [
    (pi) => pi.on("tool_call", (event, ctx) => {
      record("native-hook-events.jsonl", {event, branch: ctx.sessionManager.getBranch()});
    }),
    watcherExtension,
  ],
});
await loader.reload();
const {session, extensionsResult} = await createAgentSession({
  cwd: root, agentDir, model, tools: ["bash"], resourceLoader: loader, sessionManager, settingsManager,
});
assert.deepEqual(extensionsResult.errors, []);
await session.bindExtensions({mode: "print"});
session.subscribe((event) => record("native-events.jsonl", event));
let turns = 0;
session.agent.streamFunction = async (_model, context) => {
  record("stream-contexts.jsonl", context);
  assert.ok(turns < 2, "The fixture must stop after one native tool result");
  const first = turns++ === 0;
  const message = {
    role: "assistant",
    content: first ? [{
      type: "toolCall", id: "pi-namespaced-call", name: "bash", namespace: "provider_tools",
      arguments: {command},
    }] : [{type: "text", text: "namespaced native completed"}],
    api: model.api, provider, model: model.id,
    usage: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: {input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0}},
    stopReason: first ? "toolUse" : "stop", timestamp: Date.now(),
  };
  record("scripted-assistant-messages.jsonl", message);
  return {
    async *[Symbol.asyncIterator]() {
      yield {type: "start", partial: message};
      yield {type: "done", reason: message.stopReason, message};
    },
    result: async () => message,
  };
};

try {
  await session.prompt("Run the requested native Bash command once, then finish.");
  const branch = sessionManager.getBranch();
  writeFileSync(join(evidence, "native-branch.json"), JSON.stringify(branch, null, 2));
  const messages = branch.filter((entry) => entry.type === "message").map((entry) => entry.message);
  const calls = messages.flatMap((message) => Array.isArray(message.content) ? message.content : [])
    .filter((block) => block.type === "toolCall");
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], {
    type: "toolCall", id: "pi-namespaced-call", name: "bash", namespace: "provider_tools",
    arguments: {command},
  });
  const results = messages.filter((message) => message.role === "toolResult");
  assert.equal(results.length, 1);
  assert.equal(results[0].toolCallId, "pi-namespaced-call");
  assert.equal(results[0].toolName, "bash");
  assert.equal(results[0].isError, !expected);
  assert.equal(existsSync(marker), expected);
  if (expected) assert.equal(readFileSync(marker, "utf8"), "namespaced-native-write");
  assert.equal(turns, 2);
  writeFileSync(join(evidence, "namespace-summary.json"), JSON.stringify({
    session_id: sessionManager.getSessionId(), root, marker,
    tool_use_id: "pi-namespaced-call", name: "bash", namespace: "provider_tools",
    native_file_written: existsSync(marker), native_result_is_error: results[0].isError,
    scope: "Installed Pi AgentSession with scripted streamFunction and production Watcher extension",
  }, null, 2));
} finally {
  writeFileSync(join(evidence, "native-branch.json"), JSON.stringify(sessionManager.getBranch(), null, 2));
  session.dispose();
}
