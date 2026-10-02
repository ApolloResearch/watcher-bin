/** Native deterministic Mastra driver used by the network-isolated Python tests. */
import { appendFile, writeFile, readFile } from 'node:fs/promises';
import { setTimeout } from 'node:timers/promises';
import { MockLanguageModelV3 } from 'ai/test';
import { z } from 'zod';
import { runMonitored } from 'watcher-mastra-example/monitoring';

const schemaCase = process.env.FIXTURE_SCHEMA_CASE;
const toolInput = city => JSON.stringify(schemaCase === 'reverse' ? {units: 'c', city} : {city});
const inputSchema = schemaCase === 'reverse' ? z.object({city: z.string(), units: z.string()}) :
  schemaCase === 'default' ? z.object({city: z.string(), units: z.string().default('c')}) :
  schemaCase === 'transform' ? z.object({city: z.string().transform(value => value.toUpperCase())}) : undefined;
const tools = ids => ({content: [
  {type: 'tool-call', toolCallId: ids[0],
    toolName: schemaCase === 'unknown' ? 'unregistered_tool' : 'weather', input: toolInput('Paris')},
  {type: 'tool-call', toolCallId: ids[1], toolName: 'weather', input: toolInput('Tokyo')}],
  finishReason: {unified: 'tool-calls', raw: 'tool_calls'}});
const responses = [tools([process.env.FIXTURE_FIRST_TOOL_ID || 'call-a', 'call-b'])];
if (process.env.REPEATED_CALLS === 'fresh') responses.push(tools(['call-c', 'call-d']));
if (process.env.REPEATED_CALLS === 'same') responses.push(tools(['call-a', 'call-b']));
if (process.env.REPEATED_CALLS === 'budget') responses.push(tools(['call-c', 'call-d']), tools(['call-e', 'call-f']));
responses.push({content: [{type: 'text', text: 'Finished.'}], finishReason: {unified: 'stop', raw: 'stop'}});
const model = new MockLanguageModelV3({doGenerate: async () => ({...responses.shift(),
  usage: {inputTokens: {total: 5}, outputTokens: {total: 2}}, warnings: []})});
const approve = process.env.FIXTURE_HUMAN_APPROVAL ? async request => {
  await appendFile(process.env.APPROVAL_ENTERED_FILE, JSON.stringify(request) + '\n');
  request.tool_input.city = 'mutated';
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try { return JSON.parse(await readFile(process.env.APPROVAL_RELEASE_FILE, 'utf8')).approved; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    await setTimeout(20);
  }
  throw new Error('Fixture human approval was never released');
} : undefined;
const snapshots = [];
await runMonitored(model, async input => {
  await appendFile(process.env.EFFECT_FILE, input.city + '\n');
  return {...input, weather: 'fixture'};
}, async messages => snapshots.push(messages), inputSchema, {approve});
await writeFile(process.env.FINAL_FILE, JSON.stringify(snapshots.at(-1)));
