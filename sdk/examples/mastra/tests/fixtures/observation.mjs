/** Save native Mastra snapshots for the cross-component observation contract. */
import { mkdir, writeFile } from 'node:fs/promises';
import { MockLanguageModelV3 } from 'ai/test';
import { run } from 'watcher-mastra-example/observation';

const responses = [
  {content: [
    {type: 'tool-call', toolCallId: 'call-a', toolName: 'weather', input: '{"city":"Paris"}'},
    {type: 'tool-call', toolCallId: 'call-b', toolName: 'weather', input: '{"city":"Tokyo"}'},
  ], finishReason: {unified: 'tool-calls', raw: 'tool_calls'}},
  {content: [{type: 'text', text: 'Finished.'}], finishReason: {unified: 'stop', raw: 'stop'}},
];
const model = new MockLanguageModelV3({doGenerate: async () => ({...responses.shift(),
  usage: {inputTokens: {total: 5}, outputTokens: {total: 2}}, warnings: []})});
await mkdir(process.env.SNAPSHOT_DIR, {recursive: true});
let index = 0;
await run(model, async snapshot => {
  await writeFile(`${process.env.SNAPSHOT_DIR}/${index++}.json`, JSON.stringify(snapshot));
});
