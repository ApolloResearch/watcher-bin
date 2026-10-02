/** Save native Mastra snapshots; run watcher-mastra-observe afterward to monitor them. */
import { mkdir, writeFile } from 'node:fs/promises';
import { run } from 'watcher-mastra-example/observation';

if (!process.env.SNAPSHOT_DIR || !process.env.PROVIDER_MODEL) throw new Error('Set SNAPSHOT_DIR and PROVIDER_MODEL');
await mkdir(process.env.SNAPSHOT_DIR, {recursive: true});
let index = 0;
await run(process.env.PROVIDER_MODEL, async snapshot => {
  await writeFile(`${process.env.SNAPSHOT_DIR}/${index++}.json`, JSON.stringify(snapshot), {flag: 'wx'});
});
