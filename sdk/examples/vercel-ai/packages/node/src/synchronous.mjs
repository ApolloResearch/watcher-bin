#!/usr/bin/env node
// Native tool.execute waits for the Python public-SDK sidecar before its body.
import { generateText, jsonSchema, stepCountIs, tool, wrapLanguageModel } from "ai";
import { createInterface } from "node:readline";

let sequence = 0;
const waiting = new Map();
const input = createInterface({ input: process.stdin });
input.on("line", (line) => {
  const reply = JSON.parse(line);
  const pending = waiting.get(reply.id);
  if (!pending) throw new Error("Unexpected sidecar response");
  waiting.delete(reply.id);
  if (reply.ok) pending.resolve(reply.result);
  else pending.reject(new Error(`Tool withheld by Watcher (${reply.error ?? "UnapprovedCall"})`));
});
input.on("close", () => {
  for (const pending of waiting.values()) pending.reject(new Error("Sidecar disconnected"));
});
function request(event) {
  const id = String(++sequence);
  return new Promise((resolve, reject) => {
    waiting.set(id, { resolve, reject });
    process.stdout.write(JSON.stringify({ id, ...event }) + "\n");
  });
}

// Wrap a public provider model to preserve the current response, which execute's
// messages option does not yet include. Hosted provider-executed tools are outside this boundary.
export function capturePendingModel(model) {
  let pending;
  return {
    model: wrapLanguageModel({ model, middleware: {
      wrapGenerate: async ({ doGenerate }) => {
        const response = await doGenerate();
        pending = { role: "assistant", content: response.content.map((part) => {
          if (part.type === "text") return { type: "text", text: part.text };
          if (part.type === "tool-call" && !part.providerExecuted) return {
            type: "tool-call", toolCallId: part.toolCallId, toolName: part.toolName, input: JSON.parse(part.input),
          };
          throw new Error("Only local function calls and text are supported");
        }) };
        return response;
      },
    } }),
    pending: () => structuredClone(pending),
  };
}
let turn = 0;
const captured = capturePendingModel({
  specificationVersion: "v3", provider: "deterministic", modelId: "fixture", supportedUrls: {},
  doGenerate: async () => {
    turn += 1;
    return {
      content: turn === 1 ? [
        { type: "tool-call", toolCallId: "double-2", toolName: "double", input: '{"value":2}' },
        { type: "tool-call", toolCallId: "double-3", toolName: "double", input: '{"value":3}' },
      ] : [{ type: "text", text: "4 and 6" }],
      finishReason: { unified: turn === 1 ? "tool-calls" : "stop", raw: undefined },
      usage: {
        inputTokens: { total: 1, noCache: 1, cacheRead: 0, cacheWrite: 0 },
        outputTokens: { total: 1, text: 1, reasoning: 0 },
      },
      warnings: [],
    };
  },
});
const prompt = "Double 2 and 3";
try {
  const result = await generateText({ model: captured.model, prompt, stopWhen: stepCountIs(3), tools: {
    double: tool({ description: "Double an integer", inputSchema: jsonSchema({ type: "object",
      properties: { value: { type: "integer" } }, required: ["value"] }),
      execute: async (args, options) => {
        await request({ type: "authorize", toolCallId: options.toolCallId, toolName: "double", input: args,
          messages: [...options.messages, captured.pending()] });
        return await request({ type: "execute", toolCallId: options.toolCallId, input: args });
      },
    }),
  } });
  process.stdout.write(JSON.stringify({ id: "complete", type: "complete",
    messages: [{ role: "user", content: prompt }, ...result.responseMessages] }) + "\n");
} finally {
  input.close();
}
