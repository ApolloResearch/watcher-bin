#!/usr/bin/env node
// Native Vercel AI SDK lifecycle, including tool execution and responseMessages.
import { generateText, jsonSchema, stepCountIs, tool } from "ai";

let turn = 0;
const model = {
  specificationVersion: "v3",
  provider: "deterministic",
  modelId: "fixture",
  supportedUrls: {},
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
};
const prompt = "Double 2 and 3";
const result = await generateText({
  model,
  prompt,
  stopWhen: stepCountIs(3),
  tools: {
    double: tool({
      description: "Double an integer",
      inputSchema: jsonSchema({
        type: "object", properties: { value: { type: "integer" } }, required: ["value"],
      }),
      execute: async ({ value }) => String(value * 2),
    }),
  },
});
process.stdout.write(JSON.stringify([{ role: "user", content: prompt }, ...result.responseMessages]));
