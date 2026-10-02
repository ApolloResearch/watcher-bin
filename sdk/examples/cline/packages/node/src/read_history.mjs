#!/usr/bin/env node
import { ClineCore } from "@cline/core";

// Use the public SDK's history reader; the CLI owns its storage representation.
const core = await ClineCore.create({ clientName: "watcher-history-example", backendMode: "local" });
try {
  process.stdout.write(JSON.stringify(await core.readMessages(process.argv[2])));
} finally {
  await core.dispose();
}
