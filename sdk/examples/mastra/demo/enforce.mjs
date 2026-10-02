/** Run the native Mastra processor with explicitly configured provider and Watcher credentials. */
import { runMonitored } from 'watcher-mastra-example/monitoring';

const result = await runMonitored(process.env.PROVIDER_MODEL, async ({city}) =>
  ({city, weather: 'demonstration value'}));
process.stdout.write(result.text + '\n');
