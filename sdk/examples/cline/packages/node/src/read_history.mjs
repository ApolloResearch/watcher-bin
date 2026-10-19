#!/usr/bin/env node
import { registerHooks } from "node:module";

// @cline/core pins simple-git 3, whose advisory is fixed only in 4; the override installs 4, which lacks
// the default export @cline/core imports, so its imports are routed through a re-export that adds it.
const simpleGitWithDefault = new URL("./simple_git_default.mjs", import.meta.url).href;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === "simple-git" && context.parentURL?.includes("/node_modules/@cline/core/")) {
      return { url: simpleGitWithDefault, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});
const { ClineCore } = await import("@cline/core");

// Use the public SDK's history reader; the CLI owns its storage representation.
const core = await ClineCore.create({ clientName: "watcher-history-example", backendMode: "local" });
try {
  process.stdout.write(JSON.stringify(await core.readMessages(process.argv[2])));
} finally {
  await core.dispose();
}
