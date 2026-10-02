/** Capture actual Kilo events and completed native tools without changing their outputs. */
import { appendFile, writeFile } from "node:fs/promises";

export default {
  id: "kilo-contained-native-evidence",
  server: async () => {
    await writeFile("/evidence/capture-plugin-loaded.json", JSON.stringify({ loaded: true }));
    return {
      event: async ({ event }) => {
        await appendFile("/evidence/native-events.jsonl", JSON.stringify(event) + "\n");
      },
      "tool.execute.after": async (input, output) => {
        await appendFile("/evidence/native-tool-events.jsonl", JSON.stringify({ input, output }) + "\n");
      },
    };
  },
};
