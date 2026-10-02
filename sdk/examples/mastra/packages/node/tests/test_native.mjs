import assert from 'node:assert/strict';
import { writeFile, mkdir } from 'node:fs/promises';
import { test } from 'node:test';
import { MockLanguageModelV3 } from 'ai/test';
import { run, transcript } from 'watcher-mastra-example/observation';

function model() {
  const results = [
    {content: [{type: 'tool-call', toolCallId: 'call-a', toolName: 'weather', input: '{"city":"Paris"}'},
               {type: 'tool-call', toolCallId: 'call-b', toolName: 'weather', input: '{"city":"Tokyo"}'}],
      finishReason: {unified: 'tool-calls', raw: 'tool_calls'}},
    {content: [{type: 'text', text: 'Finished.'}], finishReason: {unified: 'stop', raw: 'stop'}},
  ];
  return new MockLanguageModelV3({doGenerate: async () => ({...results.shift(),
    usage: {inputTokens: {total: 5}, outputTokens: {total: 2}}, warnings: []})});
}

test('native agent executes two tools and publishes complete final history', async () => {
  const snapshots = [];
  const calls = [];
  const result = await run(model(), async value => snapshots.push(value), async ({city}) => {
    calls.push(city); return {city, weather: 'fixture'};
  });
  assert.deepEqual(calls.sort(), ['Paris', 'Tokyo']);
  assert.equal(snapshots.length, 2);
  assert.deepEqual(snapshots[0][2].tool_calls.map(call => call.id), ['call-a', 'call-b']);
  assert.deepEqual(snapshots[1].map(message => message.role), ['system', 'user', 'assistant', 'tool', 'tool', 'assistant']);
  assert.equal(snapshots[1][3].tool_call_id, 'call-a');
  assert.equal(snapshots[1][4].tool_call_id, 'call-b');
  assert.equal(snapshots[1][5].content[0].text, 'Finished.');
  assert.equal(result.text, 'Finished.');
  if (process.env.SNAPSHOT_DIR) {
    await mkdir(process.env.SNAPSHOT_DIR, {recursive: true});
    for (let i = 0; i < snapshots.length; i++) await writeFile(`${process.env.SNAPSHOT_DIR}/${i}.json`, JSON.stringify(snapshots[i]));
  }
});

test('unsupported content fails visibly without changing source messages', () => {
  const native = [{role: 'user', content: [{type: 'image', image: 'fixture'}]}];
  const before = structuredClone(native);
  assert.throws(() => transcript(native), /Unsupported content/);
  assert.deepEqual(native, before);
});

test('duplicate identities and unmatched results fail visibly', () => {
  const call = {type: 'tool-call', toolCallId: 'duplicate', toolName: 'weather', input: {}};
  assert.throws(() => transcript([{role: 'assistant', content: [call, call]}]), /Malformed tool call/);
  assert.throws(() => transcript([{role: 'tool', content: [{type: 'tool-result', toolCallId: 'unknown',
    output: {type: 'text', value: 'result'}}]}]), /Unmatched tool result/);
});

test('provider failure does not create a successful snapshot', async () => {
  const snapshots = [];
  const failing = new MockLanguageModelV3({doGenerate: async () => {throw new Error('provider unavailable');}});
  await assert.rejects(run(failing, async value => snapshots.push(value)), /provider unavailable/);
  assert.deepEqual(snapshots, []);
});

test('native tool execution failure retains an error marker and the final tail', async () => {
  const snapshots = [];
  const result = await run(model(), async value => snapshots.push(value), async ({city}) => {
    if (city === 'Paris') throw new Error('weather unavailable');
    return {city, weather: 'fixture'};
  });
  const failed = snapshots[1].find(message => message.role === 'tool' && message.tool_call_id === 'call-a');
  const succeeded = snapshots[1].find(message => message.role === 'tool' && message.tool_call_id === 'call-b');
  assert.deepEqual(failed.error, {type: 'unknown', message: 'Tool reported an error'});
  assert.match(failed.content, /weather unavailable/);
  assert.equal(succeeded.error, undefined);
  assert.equal(result.text, 'Finished.');
  assert.equal(snapshots[1].at(-1).content[0].text, 'Finished.');
});

for (const output of [{type: 'error-text', value: 'failed'}, {type: 'error-json', value: {code: 'failed'}}]) {
  test(`${output.type} keeps its error flag without mutating native messages`, () => {
    const native = [
      {role: 'assistant', content: [{type: 'tool-call', toolCallId: 'call', toolName: 'weather', input: {}}]},
      {role: 'tool', content: [{type: 'tool-result', toolCallId: 'call', toolName: 'weather', output}]},
    ];
    const original = structuredClone(native);
    const mapped = transcript(native);
    assert.deepEqual(mapped[1].error, {type: 'unknown', message: 'Tool reported an error'});
    assert.equal(mapped[1].content, output.type === 'error-text' ? 'failed' : '{"code":"failed"}');
    assert.deepEqual(native, original);
  });
}

for (const content of ['unlinked text', [{type: 'text', text: 'unlinked text'}]]) {
  test(`unlinked tool-role ${typeof content === 'string' ? 'string' : 'text part'} is rejected`, () => {
    assert.throws(() => transcript([{role: 'tool', content}]), /Tool messages require linked tool results/);
  });
}

test('null tool arguments are rejected', () => {
  assert.throws(() => transcript([{role: 'assistant', content: [{type: 'tool-call',
    toolCallId: 'call', toolName: 'weather', input: null}]}]), /Malformed tool call/);
});

test('a second result cannot reuse a completed tool identity', () => {
  const result = {type: 'tool-result', toolCallId: 'call', toolName: 'weather', output: {type: 'text', value: 'done'}};
  assert.throws(() => transcript([
    {role: 'assistant', content: [{type: 'tool-call', toolCallId: 'call', toolName: 'weather', input: {}}]},
    {role: 'tool', content: [result, result]},
  ]), /Unmatched tool result/);
});
