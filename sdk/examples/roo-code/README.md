# Roo Code: observation and synchronous monitoring

This example saves part of the text from Roo's `message` and `taskCompleted`
events. Those events do not provide complete tool-call IDs, so it does not grade
tools. It calls the public Watcher SDK through a Python bridge. Native permissions
and validation remain in place. This example is not officially supported.

## Installation

Use Python 3.12, `uv` and Node 24.11.1. The manifests under `packages/` list
versions and dependencies for each component. Their lockfiles record the tested
environment. The Python component uses the adjacent Watcher SDK source directory.

Roo must be installed in the VS Code Extension Development Host before using
this example. Native runtime capture remains unverified; the tests cover the
adapter's public event contract only.

From this directory:

```sh
uv sync --project packages/python
mkdir -p dist
npm pack ./packages/node --pack-destination dist --ignore-scripts
npm install --no-save --package-lock=false --ignore-scripts dist/watcher-roo-example-0.0.1.tgz
export PATH="$PWD/node_modules/.bin:$PATH"
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
```

Install both components. The Node package does not install Python. Set
`WATCHER_PYTHON` to an absolute path to an interpreter with `watcher_roo_code_bridge`
and the Watcher SDK installed. The bridge calls installed modules or commands,
so it does not need sibling source files at runtime.

Set the variables in `demo/.env.example`; the demos do not load the file.
Set `WATCHER_URL`, a session-write `WATCHER_API_KEY`, and the provider settings
your native tool needs. Keep existing permission and monitoring hooks. Store
transcripts in a private directory and decide how long to keep them.

## Observation

The companion extension in `packages/node` listens to public `message` and
`taskCompleted` events. To inspect it, unpack the Node tarball and open that package
as a VS Code Extension Development Host. Roo must already be installed there,
and `WATCHER_PYTHON` must be set.

This recipe does not install an IDE extension. Native execution in that host
remains unverified. To exercise the installed Python bridge alone, feed a
native-shaped snapshot on stdin to
`packages/python/.venv/bin/python demo/observe.py`.

This saves a partial text archive. UI events lack complete model tool-call IDs,
so the example does not claim tool grades.

## Synchronous monitoring

This public interface has no awaited per-tool permission callback with a complete
call ID. Roo's notifications, task cancellation and button controls do not supply
that check. The standalone CLI does not add it either.

A manual confirmation or cancellation after an event does not prove that Watcher
can stop the tool before it runs. This example has no synchronous SDK workaround.

## Expected Watcher result

Find the conversation in Analyzer using `roo-code:<native-session-id>` as its external ID.
Check the visible context and final assistant text. This partial archive does not
include complete tool IDs or tool grades.

Local fixtures exercise native ordering and public SDK serialization. Their fixture replies do not establish deployed Watcher persistence, real grading quality or provider behavior.

## Limitations

- Native dispatcher and deployed Watcher persistence not yet verified
- No complete native tool identities available on this public integration seam
- No awaited per-tool decision callback with complete pending call identity found on the pinned public interface; archive remains partial.

## Tests

Run the complete test suite from this directory:

```sh
bash tests/native/run.sh
```

The runner builds the SDK and adapter packages, installs them in a fresh
environment, and tests them outside the source checkout. Package downloads finish
before the tests start. `WATCHER_SDK_WHEEL` can select a prebuilt SDK wheel.
`WATCHER_EXAMPLE_RUN_DIR` selects a parent for a fresh output directory.

The Linux wrapper needs noninteractive `sudo`, `unshare`, `setpriv` and `ip`.
It permits only loopback traffic. Provider and Watcher replies come from local
fixtures. The tests do not use your service credentials.

Roo tests cover Python conversion, SDK requests and the bridge process. The Node
extension is syntax-checked. No native IDE dispatcher is exercised, so native
capture and synchronous prevention remain unverified.

The printed output directory holds logs, installed versions and JUnit results.
`metadata.yaml` describes each mode's current test scope and versions.
