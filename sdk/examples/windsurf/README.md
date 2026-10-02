# Windsurf: native lifecycle integration

Archive event-derived text only; no completed tool judgment or complete native call identities.

**What it does.** The post-response hook reads the JSONL file named by
`tool_info.transcript_path`. Its filename stem supplies the trajectory ID. The
adapter converts that text to Inspect messages and sends it with
`pre_tool_use_hook(input=[])`.

This saves the available history without grading or blocking tools. Capture and
submission are separate, so an SDK error cannot change the tool output. Add the
hook to `.windsurf/hooks.json` in a test project before using it elsewhere.

## Installation and configuration

Use Python 3.12+, `uv`, and an existing native harness installation with its normal credentials. From this directory:

```sh
uv sync --no-editable
```

The development environment uses the adjacent Watcher SDK source directory.
`pyproject.toml` lists the package version, dependencies and commands. `uv.lock`
records the tested environment. Once installed, the adapter uses installed
packages; it does not need the source checkout at runtime.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY` for intentional delivery.
`demo/.env.example` lists safe values; it is not loaded automatically. Keep normal
native permissions and existing monitoring configuration.

## Observation

Generate observation settings for the installed Python environment:

```sh
uv run --no-sync watcher-windsurf-observe-settings > /tmp/watcher-windsurf-observe.json
```

The command prints settings; it does not install hooks or change their deadlines.
Use the steps below to load the file. Keep the Python environment at its current
path. The command fills `__WATCHER_PYTHON__` in the templates under `demo/`;
do not install a template with that marker still in it.

Set `WATCHER_URL` and a session-write `WATCHER_API_KEY`. The library accepts
an `AsyncWatcherClient`; use it as an async context manager. Start in a test
workspace and keep your normal permissions and monitoring in place. After the
run, find `other=windsurf:<native-session-id>` in Watcher and check the final text
and available tool results. Delivery to a deployed Watcher server is unverified.

## Synchronous monitoring

Generate the pre-tool configuration. The hook follows the Watcher organization's
observe, enforce or paused setting.

```sh
uv run --no-sync watcher-windsurf-enforce-settings > /tmp/watcher-windsurf-enforce.json
```

**Scope of the pre-tool check.** Windsurf documents `pre_read_code`,
`pre_write_code`, `pre_run_command` and `pre_mcp_tool_use`. Exit code 2 blocks the
requested action. The adapter follows that contract, but native IDE dispatch
and veto behavior are unverified.

The hooks supply a conversation ID and turn ID, not a model tool-call ID. The full
transcript path arrives only after the response. These fields cannot safely link
repeated or parallel pending calls to recorded grades. This example therefore
checks each action without recording a decision or inventing a tool ID.

**Unrecorded checks.** The generated settings add `watcher_windsurf.pre_tool_ephemeral`
for reads, writes, commands and MCP calls, and keep the completion archive. The
request sends the exact `agent_action_name` and `tool_info`, plus `cwd` when
present. It uses full grading with `ephemeral=True` and empty messages.

Watcher sees the tool input, not prior conversation context or a model call ID.
The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch; deny and escalation
withhold the tool. This example does not provide a human approval interface.
Valid observe or paused responses leave native permissions in control. The hook
also honors an administrator's configured allow on grading failure. Malformed,
mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

A withheld action returns exit 2.

The check does not save its decision or link it to a later tool result. Keep the
completion observer if you need to save the final transcript. That saved transcript
does not reconstruct the earlier check.

The SDK deadline is 420 seconds; `WATCHER_TIMEOUT_SECONDS` can reduce it. Windsurf's
native hook deadline is unknown. Before enabling the hook, check that it allows
for the SDK wait plus process startup. Raising the SDK budget does not extend
the native deadline.

A timed-out grade may still run and incur cost on the server. The adapter does
not retry it. Native startup, crashes and timeouts are unverified; a killed hook
may never return its exit-2 veto. Tests check SDK requests and the exit-code adapter,
not actual IDE execution or deployed grading.

## Expected Watcher result

After a run, find `other=windsurf:<session-id>` in Watcher. Check the available
context, tool results and final text. Local fixtures do not verify deployed
server storage or grading. The unrecorded pre-tool check does not save
its early decision.

## Limitations

The archive lacks complete native tool-call IDs, so it cannot attach tool grades.
The converter rejects unknown content. Subagents and histories changed by
compaction or branch replay are outside the tested scope. Native dispatch and
delivery to a deployed Watcher server are unverified.

Failed observation can leave captured data unsent. Your application must decide
how to retry and how long to keep that data.

## Tests

Run the adapter tests from this directory:

```sh
../run-without-network.sh "$PWD/.venv/bin/python" -m pytest --noconftest -c pyproject.toml
```

The Linux wrapper needs `sudo`, `unshare`, `setpriv` and `ip`. It runs with only
loopback networking and a fresh home. These tests check the converter, bridge
process and SDK HTTP requests. They do not run the native hook dispatcher.

Native execution and delivery to a deployed Watcher server remain unverified.
`metadata.yaml` lists the tested versions and scope for each mode.

## References

- [Official SDK/hook reference](https://docs.windsurf.com/windsurf/cascade/hooks).
