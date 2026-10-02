/** Drive the installed Mastra Agent and tool scheduler; only model inference is deterministic. */
import { appendFile, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { setTimeout } from 'node:timers/promises';
import { MockLanguageModelV3 } from 'ai/test';
import { runMonitored } from 'watcher-mastra-example/monitoring';

const root = '/evidence';
const config = JSON.parse(await readFile(`${root}/input.json`, 'utf8'));
const require = createRequire(import.meta.url);
await writeFile(`${root}/native-node-installation.json`, JSON.stringify({
  node: process.version,
  mastra: JSON.parse(await readFile(require.resolve('@mastra/core/package.json'), 'utf8')).version,
  ai: JSON.parse(await readFile(require.resolve('ai/package.json'), 'utf8')).version,
  module: import.meta.resolve('watcher-mastra-example/monitoring'),
}, null, 2));
const responses = [
  {content: config.call_ids.map((id, index) => ({type: 'tool-call', toolCallId: id,
    toolName: 'weather', input: JSON.stringify({city: ['Paris', 'Tokyo'][index]})})),
    finishReason: {unified: 'tool-calls', raw: 'tool_calls'}},
  {content: [{type: 'text', text: config.final_text}], finishReason: {unified: 'stop', raw: 'stop'}},
];
const model = new MockLanguageModelV3({doGenerate: async options => {
  const next = responses.shift();
  if (!next) throw new Error('Unexpected extra native model turn');
  const response = {...next, usage: {inputTokens: {total: 5}, outputTokens: {total: 2}}, warnings: []};
  await appendFile(`${root}/native-model.jsonl`, JSON.stringify({request: options, response}) + '\n');
  return response;
}});
const snapshots = [];
const approve = config.manual ? async request => {
  await appendFile(`${root}/approval-entered.jsonl`, JSON.stringify(request) + '\n');
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    try {
      const choice = JSON.parse(await readFile(`${root}/approval-release.json`, 'utf8'));
      if (typeof choice.approved !== 'boolean') throw new Error('Expected an explicit human choice');
      return choice.approved;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    await setTimeout(20);
  }
  throw new Error('Human fixture choice was not supplied');
} : undefined;
let failure;
try {
  await runMonitored(model, async input => {
    await appendFile(`${root}/side-effects.jsonl`, JSON.stringify(input) + '\n');
    return {...input, weather: config.token};
  }, async messages => {
    snapshots.push(messages);
    await writeFile(`${root}/native-snapshots.json`, JSON.stringify(snapshots, null, 2));
  }, undefined, {approve});
} catch (error) {
  failure = {name: error.name, message: error.message, stack: error.stack};
} finally {
  await writeFile(`${root}/native-result.json`, JSON.stringify({returned: !failure, failure: failure ?? null}, null, 2));
}
if (failure) process.exitCode = 1;
