/** Gate Mastra's public createTool.execute callback before the application tool runs. */
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { transcript } from './integration.mjs';

/** Compare JSON values without treating object key order as tool semantics. */
function canonicalJson(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalJson(value[key])).join(',') + '}';
  }
  throw new Error('Tool inputs must contain only JSON values');
}

/** Submit only ordinary Inspect messages to a private Python SDK subprocess.
 * Exit zero permits native dispatch. Process, SDK or invalid-result failures reject.
 * Optional approve(request) must await an authorized human and return a boolean;
 * the Python side records and verifies that choice before its successful exit.
 * The SDK owns the configurable grading deadline; this function adds no retries.
 */
export function submit(messages, callId, approve) {
  return new Promise((resolve, reject) => {
    const python = process.env.WATCHER_PYTHON;
    if (!python) return reject(new Error('WATCHER_PYTHON is required'));
    if (approve !== undefined && typeof approve !== 'function') return reject(new Error('approve must be a function'));
    const human = callId !== undefined && approve !== undefined;
    const child = spawn(python, ['-m', 'watcher_mastra_bridge.gate',
      ...(human ? ['--human-approval'] : []),
      ...(callId === undefined ? [] : ['--', callId])], {stdio: ['pipe', 'pipe', 'pipe']});
    child.stderr.resume();
    const output = createInterface({input: child.stdout});
    let requested = false;
    const fail = error => { child.kill(); reject(error); };
    output.on('line', line => {
      let pending;
      try {
        pending = JSON.parse(line);
        if (!human || requested || pending.type !== 'approval' || pending.tool_use_id !== callId) {
          throw new Error('Unexpected approval request');
        }
        requested = true;
      } catch (error) { fail(error); return; }
      Promise.resolve().then(() => approve(structuredClone(pending))).then(approved => {
        if (typeof approved !== 'boolean') throw new Error('Human approval must be an explicit boolean');
        child.stdin.end(JSON.stringify({tool_use_id: callId, approved}) + '\n');
      }).catch(fail);
    });
    child.on('error', fail);
    child.stdin.on('error', fail);
    child.on('close', code => {
      output.close();
      if (code === 0) resolve();
      else reject(new Error('Watcher withheld execution'));
    });
    const input = JSON.stringify(messages) + '\n';
    if (human) child.stdin.write(input);
    else child.stdin.end(input);
  });
}

/** Use the native output processor before Mastra invokes any client tool.
 * Each full response is authorized before tool callbacks receive permission to run.
 * A rejection aborts the step; native schema checks and permissions remain active.
 * Provider-hosted tools and callbacks outside this agent are not controlled.
 */
export async function runMonitored(model, executeWeather, sink = async () => {}, inputSchema = z.object({city: z.string()}), {approve} = {}) {
  const instructions = 'Call weather once for Paris and once for Tokyo, then summarize.';
  const prompt = 'Paris and Tokyo?';
  const attempted = new Set();
  const approved = new Map();
  let messagesAfterStep;
  const processor = {id: 'watcher-before-tools', processOutputStep: async ({messageList, systemMessages, toolCalls}) => {
    const system = structuredClone(systemMessages);
    messagesAfterStep = () => transcript([...system, ...messageList.get.all.aiV5.model()]);
    const messages = messagesAfterStep();
    for (const call of toolCalls ?? []) {
      if (!call.toolCallId || attempted.has(call.toolCallId)) throw new Error('Missing or repeated native tool ID');
      attempted.add(call.toolCallId);
      if (call.toolName !== 'weather' || canonicalJson(inputSchema.parse(call.args)) !== canonicalJson(call.args)) {
        await submit(messages);
        throw new Error('Unregistered tool or schema changes model arguments; supply explicit tool inputs');
      }
      await submit(messages, call.toolCallId, approve);
      approved.set(call.toolCallId, {name: call.toolName, input: structuredClone(call.args)});
    }
    return messageList;
  }};
  const agent = new Agent({id: 'watcher-enforcement-example', name: 'Watcher enforcement example',
    instructions, model, outputProcessors: [processor],
    tools: {weather: createTool({id: 'weather', description: 'Return city weather',
      inputSchema, execute: async (input, context) => {
        const id = context.agent?.toolCallId;
        const approval = approved.get(id);
        approved.delete(id);
        if (!approval || approval.name !== 'weather' || canonicalJson(approval.input) !== canonicalJson(input)) {
          throw new Error('No matching native execution approval');
        }
        return await executeWeather(input);
      }})}});
  const result = await agent.generate(prompt, {maxSteps: 3, onStepFinish: async () => {
    if (!messagesAfterStep) throw new Error('Native step history is unavailable');
    const messages = messagesAfterStep();
    await submit(messages);
    await sink(messages);
  }});
  if (result.error) throw result.error;
  if (result.tripwire) throw new Error('Native processing blocked the run');
  return result;
}
