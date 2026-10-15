# Hermes Agent: shell-hook integration

Native `pre_tool_call` gate with full stored history; per-turn session recording.

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is Nous Research's open-source agent harness. This example connects it to Watcher through Hermes's own shell hooks and the public Watcher SDK. It is an example integration, not an officially supported connector. It was tested with Hermes v0.21.7 on Linux.

| Install | What it does | Main limit |
|---|---|---|
| Blocking review (default) | Sends each tool call to Watcher, with the session history up to that call, before it runs. In enforce mode Watcher's allow lets the call continue, deny refuses it, and escalate opens Hermes's own approval prompt. In observe or paused mode Hermes's own permissions decide. Also records the session after every turn. | Adds an export of the session (about 2 seconds in tests) plus Watcher's decision to every tool call. |
| Record only (`--record-only`) | Records the session after every turn. | Watcher cannot stop a call. |

Watcher's trailing review runs on the server over recorded sessions, so it needs nothing from this example; see [Blocking and trailing review](https://watcher-docs.apolloresearch.ai/concepts/blocking-and-trailing-review/).

## How it works

Hermes runs each hook in its profile's `config.yaml` as a subprocess, with a JSON payload on stdin, and reads a JSON answer from stdout. This example installs two:

- **`pre_tool_call` runs `watcher_hermes gate`.** Hermes stores the assistant message that proposes a tool call before it fires this hook. The gate reads the session with `hermes sessions export`, converts it to Inspect chat messages, and asks Watcher to judge the pending call under your organization's policy. It answers `{}` to continue, `{"action": "block"}` to refuse, or `{"action": "approve"}` to ask a person in Hermes's approval prompt. The prompt shows Watcher's explanation. If the gate cannot get a trustworthy answer from Watcher, it refuses the call, and `fail_closed: true` makes Hermes refuse it too if the gate crashes or times out.
- **`on_session_end` runs `watcher_hermes record`.** Hermes fires this after every turn, including interrupted ones. The recorder reads the session the same way and sends it to Watcher. Watcher stores only messages it has not seen, so recording after every turn never duplicates history. Recording failures never affect the agent.

Both commands name the session in Watcher as `hermes:<Hermes session ID>`. Hermes subagents have their own session IDs, so each appears as its own Watcher session. A deferred or MCP tool called through Hermes's `tool_call` bridge is recorded and judged as the underlying tool, which is what runs. Diagnostics on stderr are fixed text: transcripts, tool arguments, paths, credentials and server error bodies are never printed.

## Install

Use Python 3.12 or later, [uv](https://docs.astral.sh/uv/getting-started/installation/) and a working Hermes installation. From this directory:

```sh
uv sync --no-editable
```

The environment installs the adjacent Watcher SDK source and this example as packages. Keep the virtual environment at its current path while the hooks are installed: they run its interpreter by absolute path.

### Credentials

The hooks authenticate one of two ways:

- **Saved sign-in (recommended).** Sign in to the Watcher app for your server on this machine, then add `--watcher-auth` when you generate the hooks. Tokens stay in Watcher's credential store and are refreshed as needed. If your Watcher app uses `APOLLO_MONITOR_HOME`, also pass `--watcher-state-dir` with that folder.
- **API key.** Set `WATCHER_API_KEY` to a key that can write sessions, where Hermes's hook processes can read it. Hermes passes its own environment to hooks, so the agent's terminal tool can read the key too.

A Watcher running on this machine (`localhost`, `127.0.0.1` or `::1`) can be reached without either, which is how a local development stack accepts requests.

### Wire the hooks

Print the hooks block for this interpreter and merge it into your Hermes profile's `config.yaml` (`~/.hermes/config.yaml` for the default profile, or `$HERMES_HOME/config.yaml`):

```sh
uv run --no-sync watcher-hermes hooks --watcher-url https://watcher.example.com/api --watcher-auth
```

Add `--record-only` to record without gating, `--escalate-as-block` to refuse escalated calls instead of asking (see [Limits](#limits)), and `--hermes-bin /path/to/hermes` when the `hermes` command is not on the hooks' `PATH`. The command prints configuration and changes no file. `demo/hooks.enforce.yaml` and `demo/hooks.record.yaml` show the shape of its output.

The printed block raises `plugins.hook_callback_timeout` to 300 seconds. Keep that line: without it Hermes abandons a `pre_tool_call` hook after 30 seconds and refuses the call, even though the hook's own `timeout` is longer.

Hermes asks you to approve each new hook command the first time it sees it. For unattended runs (gateway, cron, CI), approve them with `hermes --accept-hooks chat` once, set `HERMES_ACCEPT_HOOKS=1`, or set `hooks_auto_accept: true`; otherwise Hermes skips the hooks and logs a warning. Check them with `hermes hooks list`, and run `hermes hooks doctor` after updating this example, since Hermes approves the command text, not the script behind it.

`WATCHER_TIMEOUT_SECONDS` sets how long the gate waits for Watcher's decision: 240 seconds by default and at most 270, which leaves room for the export inside Hermes's 300-second hook limit.

### Check it works

Start a new Hermes session, ask it to run a harmless command, and find `hermes:<session ID>` among Watcher's sessions; Hermes prints the session ID when it exits. The session should hold the turn and Watcher's decision for the call.

## Limits

- **Escalations can be approved without a person.** Hermes approves an escalation without asking anyone under `--yolo`, `approvals.mode: off`, or an unattended approval mode set to `approve` (`approvals.single_query_mode`, `approvals.cron_mode`). Where no person can answer and none of those is set, Hermes refuses the call. Generate the hooks with `--escalate-as-block` where escalated calls must never run without a person.
- **People's answers are not stored, and apply to one call.** Your answer in Hermes's approval prompt decides the call, but Watcher does not store it as a human decision. "Allow for this session" and "Add to permanent allowlist" behave like "Allow once" for Watcher's escalations: each escalation asks again, so one answer can never approve a later, different call.
- **Policy keyed to Claude Code tool names does not match.** Watcher's built-in command rules and per-tool thresholds name Claude Code tools such as `Bash` and `Read`. Hermes calls its tools `terminal`, `read_file`, `write_file`, `patch` and so on, so its calls go to grading unless your administrator writes rules for those names.
- **Rewinds and compaction start a new branch.** The integration sends the conversation the model currently sees. After a rewind or context compaction that no longer extends what Watcher stored, so Watcher records a new branch of the session.
- **Some calls are refused without being judged.** The gate refuses, rather than lets through, calls it cannot judge in their real context: tools called from inside `execute_code` (Hermes gives these no session or call ID), calls from agents that keep their history only in memory, such as Hermes's background review agents (they share their parent's session ID but their conversation is not in the store), and connector tools (`connectors__…`) called through the `tool_call` bridge, which Hermes judges per entry under the bridge's call ID. Call such tools directly instead. Hermes splits bridge batches of local and MCP tools into single calls, and those are judged normally.
- **Other hooks that rewrite arguments defeat the gate.** Hermes applies every `pre_tool_call` hook's `modify` answer after all hooks have run, so another hook that rewrites a call's arguments can run something other than what Watcher judged. Do not combine this gate with hooks or plugins that modify tool arguments.
- **Grading time is bounded by Hermes.** Hermes caps a shell hook at 300 seconds. Grading that takes longer than `WATCHER_TIMEOUT_SECONDS` refuses the call.

## Tests

```sh
uv run --no-sync pytest
```

The tests use sessions captured from Hermes v0.21.7 and a mocked SDK transport. Gating, escalation through Hermes's approval prompt and recording were also exercised by hand against Hermes v0.21.7 and a local Watcher.
