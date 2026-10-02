# GitHub Copilot CLI

Record Copilot CLI conversations through the public Watcher SDK and find them in the Analyzer. This is an example integration, not an officially supported connector. Setup installs callbacks in Copilot's personal hooks folder, so they run for every Copilot session of your user on this machine, or in one project with `--project`. They send the native transcript directly to the Watcher API. It requires no Watcher Live daemon or native hook installer.

| Install | What it does | Main limit |
|---|---|---|
| Record only (`setup --record-only`) | Records each turn, including reasoning, compaction, subagents and attachments, and the final state when the session ends, then confirms the stored history. | Requires the user's own Watcher login. |
| [Blocking review](https://watcher-docs.apolloresearch.ai/concepts/blocking-and-trailing-review/#blocking-review) (`setup`, the default) | Also sends each tool call to Watcher before it runs. In enforce mode, it withholds each call until Watcher approves it, asking you when Watcher escalates. In observe or paused mode, Copilot's own permissions decide. | Adds a Watcher decision to every tool call. In enforce mode, a Watcher approval skips Copilot's own prompt and overrides your Copilot deny rules. Copilot runs the tool if its 480-second hook timeout expires. |
| Grade completed tool calls after each turn (`demo/hooks.observe.json`) | Records the history and grades each turn's completed tool calls. | It cannot stop a tool that has run. |

Setup installs Record only or Blocking review, the default for new installs. The demo hook files are alternatives to setup for wiring hooks by hand: `demo/hooks.enforce.json` runs the same Blocking review gate, and `demo/hooks.observe.json` grades completed tool calls after each turn instead; see [Optional demo hooks](#optional-demo-hooks). Your administrator sets Watcher's enforcement mode: enforce, observe or paused mode. Watcher's trailing review runs on the server over recorded sessions, so it needs nothing from this sample; see [Blocking and trailing review](https://watcher-docs.apolloresearch.ai/concepts/blocking-and-trailing-review/).

## Managed installation

Use the [Copilot quickstart](https://watcher-docs.apolloresearch.ai/integrations/copilot)
for a one-command cloud or self-hosted installation. The SDK release installer
provides the adapter, Python and uv in a permanent managed environment. It needs
no source checkout or local Watcher app. Setup verifies server access before
installing recording and tool review. Like `setup` below, it installs the
personal hooks for every Copilot session by default, or one project's with
`--project`. Browser login belongs to the shared SDK; reuse of a saved Watcher
login is optional.

Use `watcher-sdk integrations status copilot` to check confirmed delivery and the
read-back of stored judgments, `doctor copilot` to check access and read the
judgments back again without grading anything, `logs copilot` to inspect
sanitized failures, `update copilot` to update and `remove copilot` to remove the
hooks. `opt-out copilot --project PATH` and `opt-in copilot --project PATH` manage
the opt-outs and, like this sample's own `opt-out` and `opt-in`, need you at an
interactive terminal to type the project folder. Prefix each subcommand with
`watcher-sdk integrations`; each acts on
the personal install unless you add `--project`. Status and install warn when both
installs cover a project. Reinstall and update preserve the saved mode and
credential source, and repair a configuration that names another server than its
hooks only when you name the server with `--cloud` or `--url`. SDK logout keeps the
Watcher app's saved login file, though the server may sign out a browser or
Watcher app that shared the SDK login's session.

The source-based commands below remain available for custom deployments and
adapter development. Their low-level `setup` checks local configuration only;
it does not replace the managed installer's authenticated preflight.

## Prerequisites

Use Python 3.12 or later, [uv](https://docs.astral.sh/uv/getting-started/installation/) and the [standalone GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/cli-getting-started). Setup's recording hooks and the container fixture are tested with Copilot CLI 1.0.89 on Linux. Use `copilot --no-auto-update` to keep the installed version stable during verification.

Copilot model access and Watcher API access are separate:

- For GitHub-hosted inference, use `copilot login` with an account that has Copilot access. Verify a real prompt before installing this sample; `gh auth status` alone does not prove inference access.
- Copilot also supports a custom provider, documented by `copilot help providers`. Supply `COPILOT_PROVIDER_BASE_URL`, `COPILOT_PROVIDER_TYPE`, `COPILOT_PROVIDER_WIRE_API` and `COPILOT_MODEL` only to the Copilot command. Supply `COPILOT_PROVIDER_API_KEY` securely if that provider requires it. This example was tested with Claude Sonnet 4.6 through an Anthropic-compatible endpoint and GPT-6 Luna through an OpenAI-compatible Responses endpoint, both with `--reasoning-effort high`. Copilot only enables reasoning for model IDs it recognizes; when your provider's model name differs, set `COPILOT_PROVIDER_MODEL_ID` to the matching Copilot model ID, such as `claude-sonnet-4.6`, and `COPILOT_PROVIDER_WIRE_MODEL` to the provider's name.
- Get your Watcher API URL and sign in to the installed Watcher app for that server. Saved-login authentication supports macOS and Linux and runs as the same OS user as Watcher. The integration authenticates only with a user's own login; it does not accept API keys. The URL must use HTTPS unless Watcher runs on this machine (`localhost`, `127.0.0.1` or `::1`); setup and the hooks refuse plain HTTP to any other host.

An installation from an earlier version that used an API key stops recording and withholds tools with a message asking you to run setup again with a login. Confirming delivery reads the session back; with a user's login, Watcher limits those reads to that user's own sessions, so no organization-wide read permission is needed.

Recording also stores your answers to Watcher's prompts as human decisions, and the decision for a multi-file patch that recording stores after the turn (see [Tool names](#tool-names)). Your login may change your own sessions, so this needs no further permission. If that upload fails, transcripts and the gate's other decisions are still stored, and the recording adds an `unsynced_decisions` event to `events.jsonl`; the next callback tries again.

After setup, restart Copilot and complete a test turn. Use the status command below to confirm that `last_delivery` has a timestamp from that turn and `last_error` is `null`. If the turn ran a tool, `last_review_check` should also count its stored decision as confirmed.

## Install and configure

Download `watcher_sdk-<version>-source.tar.gz` from the Watcher release matching your server, linked from the SDK README, then extract it with `tar -xzf watcher_sdk-<version>-source.tar.gz`. Replace `<version>` with the release number without its leading `v`. Enter the extracted `sdk/` directory and keep it together: the example installs the matching SDK from the adjacent source. The SDK wheel installs the client library and optional CLI; the source archive contains adapters. Older source releases may not contain examples.

From that extracted `sdk/` directory, one command installs the sample and its matching SDK as packages, then installs the callbacks for every Copilot session of your user:

```sh
uv run --project ./examples/github-copilot-cli --locked --no-dev --no-editable \
  watcher-github-copilot-cli setup \
  --watcher-url https://watcher.example.com/api \
  --watcher-auth
```

Setup writes `watcher-sdk-copilot.json` to Copilot's personal hooks folder and prints its path and the private configuration path. The folder is `$COPILOT_HOME/hooks/`, or `~/.copilot/hooks/` when `COPILOT_HOME` is unset or empty. Copilot runs personal hooks in every folder, so the callbacks cover each session you start on this machine. Setup reads `COPILOT_HOME` as Copilot does, using a set value exactly as given, so run setup with the value Copilot uses. It refuses a value that is not an absolute path, because Copilot would resolve it from whichever folder it starts in. To install in one project instead, add `--project /path/to/project`; see [Personal and project installs](#personal-and-project-installs).

The file registers one callback for `agentStop`, which fires after each turn, and for `sessionEnd`, which records the session as it stands, including subagents that finish after the last turn. In prompt mode Copilot fires `sessionEnd` after every invocation. Recording is idempotent, so repeated callbacks never duplicate messages; `sessionEnd` can add a background compaction's summary that finished after the turn. It checks that the credential is available locally; API access is checked when a turn is recorded. Keep the extracted SDK directory and its sample virtual environment at the same path while the hook is installed.

Repeating the command updates only this integration and does not add a second callback. Run it again after updating this sample, since the commands it installs can change between versions; until then, a gate installed by an earlier version keeps its shorter deadline. Other hook files and entries remain in place. Keep your own hooks in files of their own: Copilot ignores a whole hook file over one entry it rejects, so status reports this file as changed when it holds any other entry. Setup refuses an existing file it does not own, and refuses to replace an entry of this integration that was edited by hand. The callback uses an absolute executable path, so no shell PATH changes are needed. It does not change Copilot's tool permissions.

Configuration defaults to `~/.config/watcher-copilot/`, or `$XDG_CONFIG_HOME/watcher-copilot/`. The personal install keeps one machine-level configuration in its `personal/` folder there. Each project install keeps its own, in a folder named by a hash of the project's path. Use `--config-dir /private/configuration` to choose another root outside any project. Use the same option for later setup, status, opt-outs and removal, and for every install on the machine.

Each hook command also names the server with `--watcher-url`, the same URL the private configuration holds. If the configuration later names a different server, the hooks refuse to run: the gate denies the tool call, and recording fails with a warning. Run setup again to change servers or to repair such a configuration; it rewrites both files. Hooks installed by an earlier version of this sample do not name the server, so they skip this check and follow whatever server the configuration names. The status command warns when any hook in the installation's hook file or the private configuration names no server, including hooks left behind by an upgrade that stopped partway. Run setup again to add the check.

Keep saved login stores outside the project too. For a project install, setup rejects a store or credential file inside the project, including symlink targets, before replacing any hooks.

The `--watcher-auth` option uses the SDK's shared saved-login helper. It works with the packaged Watcher app; no Watcher Python package is needed. Setup refuses a missing login or one saved for a different server URL, including another localhost port. Hooks and replay read current credentials and refresh expired tokens using Watcher's lock. Tokens stay in Watcher's credential store; setup saves the source, server URL and store location. If you use `APOLLO_MONITOR_HOME` for Watcher, set it during setup; hooks and replay use the saved location.

API keys are not supported: the key would sit in a file or variable the Copilot agent's own shell can read, and confirming delivery with a key needs permission to read every session in the organization. A missing or rejected saved login never falls back to another credential or another server's login.

New installs use Blocking review, a `preToolUse` gate that follows Watcher's policy; see [Blocking review](#blocking-review). Use `--record-only` for Record only, or `--enforce` to turn Blocking review back on. Repeating setup without either flag keeps the current choice.

From the SDK source directory, run `./examples/github-copilot-cli/.venv/bin/watcher-github-copilot-cli status` to check the personal install. Add `--project /path/to/project` for a project install, or pass `--config <configuration-path>`. Status prints the installation's `scope`, its `hook_file`, whether that file holds exactly the installed entries and nothing else (`hooks_installed`), the opted-out projects, the last hook callback and confirmed delivery. It warns when the hook file is missing, changed, disabled or holds other entries. Private `status.json` and bounded `events.jsonl` files beside the configuration also record detached session-end failures. They contain event types, times, Watcher and Copilot session IDs, Copilot tool-call IDs, hashes of judged calls and Watcher's decision values, never transcripts, tool arguments or credentials. A callback without confirmed delivery does not prove that the session reached Watcher. `last_delivery` confirms the transcript only: `last_review_check` is the last check of the gate's stored decisions, and `last_review_gap` the last call the gate judged without storing (see [Blocking review](#blocking-review)).

Copilot reads hook files, folder trust and its settings when a session starts. A running session keeps only the hooks it loaded then, so restart Copilot after setup, removal or any change to either install. For a project install, start or restart Copilot from the configured project and trust the folder when Copilot asks. Copilot runs no repository hooks in an untrusted folder, and gives no warning. In prompt mode, `GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS=true` also enables them in an untrusted folder; use it only for a project whose hook code you trust. GitHub documents this setting in the [CLI environment reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference#environment-variables). Outside a Git repository, Copilot finds the hooks only when started in the project folder itself. An organization policy that allows only managed hooks also stops them silently. So does a `disableAllHooks` setting in any of the project's `.github/copilot/settings.json`, `.github/copilot/settings.local.json`, `.claude/settings.json` or `.claude/settings.local.json`, which stops the personal hooks as well; see [Trust and enforcement](#trust-and-enforcement). For a project install, setup warns about an untrusted folder, a missing repository and `disableAllHooks` in any of those four files. For either install, it warns about `disableAllHooks` or `disabledHooks` in your user settings (`settings.json` or `config.json` under `COPILOT_HOME`). It also warns when Copilot's managed settings file on Linux, `/etc/github-copilot/managed-settings.json`, allows only managed hooks. A policy your organization delivers through GitHub or a device management profile is not visible to setup. A settings file setup cannot parse, for example one with inline comments, is reported rather than checked.

Copilot also runs hooks from the project's `.claude/settings.json` and `.claude/settings.local.json`, sending Claude-style input, but not from your user-level `~/.claude/settings.json`. Watcher Live's own Claude Code hooks, which are user-level, therefore do not fire for Copilot sessions. Setup for a project install warns when the project has Claude Code hooks.

### Personal and project installs

`--project /path/to/project` installs the callbacks in that project's `.github/hooks/watcher-sdk-copilot.json`, with the project's own configuration. In a Git repository, including a linked worktree or a folder below the repository root, setup also lists that file in the repository's local `info/exclude`, so it is not committed. Its commands name this machine's interpreter and configuration, and on another machine a gate command that cannot start makes Copilot deny every tool. Removal leaves that line in place. If Git is unavailable or the exclude file cannot be updated, setup warns instead; do not commit the hook file. A personal install writes nothing into any project.

Both kinds of install can exist on one machine. Copilot then runs both, personal hooks before project hooks, as the [hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference) documents, and neither install stands aside for the other. In a project with its own install, both installs record each turn, and each call the first gate allows is judged by both gates; when it denies, or escalates in prompt mode, Copilot does not run the project gate, so that call is judged once. A call the personal gate leaves to Copilot's own permissions in observe or paused mode also reaches the project gate. Copilot withholds a call that either gate denies. Each install keeps its own diagnostics. Recording is idempotent, so the second recording adds no messages.

When both installs send to the same Watcher organization with credentials for the same user, both gates name the same native call in the same Watcher session, and Watcher stores one decision per call. An install with another user's credential, or one that sends to another Watcher, records its own session and decision.

- If the first gate's decision is already stored as a completed judgment, from a rule, a tool threshold or grading, Watcher answers the second gate with it under the current enforcement mode. It evaluates nothing again and adds no grades, usage or alerts. Other stored decisions are not reused, so the second gate's call is graded again: grading failures, bypasses, calls that were not evaluated and judgments whose deciding grade failed. A grading failure is not reused even when an administrator's configured allow on grading failure let the call run. In paused mode Watcher neither reuses nor grades.
- Watcher stores a decision just after it answers, so a second request that arrives before then is evaluated again too. Watcher still keeps one decision for the call. In enforce mode it keeps the one whose request arrived last, so when the project gate denies a call the personal gate allowed, the stored decision is that deny. In observe mode it keeps the first completed judgment stored, which also replaces a deferred grading failure stored before it. The install whose decision was not kept can then count it as unconfirmed in `last_review_check`.
- A call the gate judges without storing (see [Blocking review](#blocking-review)) is graded by each gate.

In tests with Copilot 1.0.91 and both installs in a trusted repository, in prompt mode and in an interactive session, each tool call ran both gates one after the other, personal first. Both named the same call, the tool ran once after both allowed it, and both installs recorded the session. In prompt mode, when the personal gate denied or escalated a call, Copilot withheld it without running the project gate, and when the personal gate allowed and the project gate denied or escalated, Copilot withheld the call. Denial and escalation in an interactive session were not measured.

`setup --project` warns when the personal install already covers that project, and `status` warns in either scope when both installs cover one project. Personal setup lists the project installs that overlap it, with the command that removes each. Nothing is removed automatically. To judge each call once, remove one of the two installs. Opting the project out turns off both.

To keep this sample's hooks out of a project, opt it out:

```sh
./examples/github-copilot-cli/.venv/bin/watcher-github-copilot-cli opt-out --project /path/to/project
```

`opt-out` and `opt-in` need a person at an interactive terminal: they ask you to type the project folder, and refuse when stdin or stdout is not a terminal. In tests with Copilot 1.0.91, a command its bash tool ran had no terminal on stdin, stdout or stderr, in prompt and interactive mode, so an agent's ordinary command cannot opt its project out.

Opting out turns off all of this sample's hooks in that project, a project install included, from the next callback on, including in sessions already running. Every callback, personal or project, reads the opt-out list. In an opted-out project it records nothing and gives no decision, so tool calls there follow Copilot's own permissions. With Copilot 1.0.91 and both installs, neither sent anything to Watcher in an opted-out project, in prompt or interactive mode. The same applies to any other hook command whose `--config` names a configuration in that configuration root, such as a copied demo hook. `opt-in --project /path/to/project` reverses it.

The choice is stored only in the personal install's private configuration, never in the project, so nothing committed to a repository can opt it out. Opting out therefore needs the personal install. A project install sees the opt-out only when both installs use the same configuration root, and only when its hooks run this version of the sample. `opt-out` and `status` warn when a project install's hooks run another Python than the one running the command, such as an older checkout's virtual environment, since that code may ignore opt-outs; run `setup --project` again with this version. Repeating setup keeps the opt-outs. Removing the personal install deletes them, which turns a project install in a formerly opted-out project back on. A callback that cannot read its opt-out list, or cannot resolve its folder, records and judges the call as usual.

Each callback finds its project from the folder Copilot reports for the session, the way Copilot finds a project, and an opt-out applies when that project is opted out. Symlinks are followed first. Inside a Git repository, including a linked worktree or a nested repository, the project is the innermost repository's root, so opting out any folder of a repository opts out all of it. Elsewhere the project is the folder itself: opting out a folder outside Git does not cover its subfolders, because Copilot started in a subfolder treats that subfolder as the project. `opt-out` prints the folder it stored, and status lists them. A callback that an opt-out leaves alone adds a `skipped` event with the reason `opted_out` to its install's `events.jsonl`. A `.git` marker that exists but cannot be inspected safely, such as an unreadable or oversized file, a symlink or a FIFO, or that names no valid repository, such as a `.git` folder without `HEAD` or a `.git` file pointing nowhere, leaves the project unknown, so the callback is recorded and judged rather than matched to a parent folder's project. The project is found again on every callback, from Git markers and symlinks a process running as you can change, so creating repository markers above a running session's folder, or retargeting a symlink in its path, can change which project the session resolves to, and so whether an opt-out applies to it.

### Trust and enforcement

These behaviors of personal hooks were measured with personal hooks only, in fresh untrusted folders outside Git:

- In prompt mode, with Copilot 1.0.89 on Linux, personal hooks ran without a trust prompt; `sessionStart`, `preToolUse` and `agentStop` fired.
- In interactive mode, on macOS, with a Copilot version that was not recorded, Copilot asked whether to trust the folder. Answering No exited Copilot and fired only `sessionEnd`. Answering Yes for this session fired the hooks for the session's prompts, turns and tool calls, and each tool ran after the gate answered. Choosing to remember the folder was not measured.

Personal hooks are per user and removable. They live in your own Copilot folder, which you, and an agent running as you, can edit or delete; `remove` uninstalls them. A `disableAllHooks` setting in any of a repository's `.github/copilot/settings.json`, `.github/copilot/settings.local.json`, `.claude/settings.json` or `.claude/settings.local.json` stops them for sessions in that repository, once Copilot loads its repository hooks. It does so in a trusted folder, or when `COPILOT_ALLOW_ALL` or `GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS` is `true`. Copilot then runs no hook at all and gives no warning. A file committed to a repository can therefore switch the personal hooks off in it, and setup cannot check every repository. With Copilot 1.0.91 on Linux, the same setting in your user `settings.json` under `COPILOT_HOME` did not stop them in prompt or interactive mode, and one in `config.json` did not stop them in prompt mode. Setup still warns about either. An organization policy that allows only managed hooks blocks them. An agent running as you can still edit this sample's private configuration directly, for example to opt its project out, or run `opt-out` under a program that fakes a terminal, and Watcher sees no record of either. An opt-out is therefore a convenience, not a control. The only hooks Copilot enforces are managed policy hooks in `/etc/github-copilot/policy.d/`, which must be owned by root and which an administrator deploys, for example through MDM. This example does not install them.

## Record and verify a conversation

In a disposable configured project, create `status.txt` containing `Status: pending`. Ask Copilot to read it, change `pending` to `complete`, read the result and explain the change. Then continue the same session and ask it to change `complete` to `resumed`. Check the file after each turn. Use `--session-id <UUID>` on repeated prompt-mode invocations to keep the same session, or continue interactively.

The `agentStop` callback reads the complete native event log, including the final answer. It sends generic messages with native session and tool identities through the public SDK, then polls the public API until the stored history matches. The credential needs both session read and write access for this confirmation. A continued session keeps its earlier history; submitting the same snapshot again does not duplicate messages.

Find the session in the Analyzer by external ID `github-copilot-cli:<session-id>`. Copilot's native history is at `~/.copilot/session-state/<session-id>/events.jsonl`, or under `$COPILOT_HOME` when set. Compare the user messages, assistant responses, tool arguments, linked results and final answer with the Analyzer transcript. Translated tools appear there under their Claude Code names and arguments; see [Tool names](#tool-names). The recording callback does not request tool grading; the default pre-tool hook handles review.

For public SDK readback, call `client.search_sessions(external_ids={"other": ["github-copilot-cli:<session-id>"]})` on an authenticated Watcher client. The response contains the Watcher session UUID and its latest trajectory ID. Replay also prints that UUID; open `<Analyzer URL>/sessions/<Watcher session UUID>` to inspect the same conversation.

The callback waits up to five seconds for Copilot to flush the completed turn and the current callback marker to its transcript. It then allows 25 seconds for submission and readback, and up to five more to check the gate's stored decisions, inside Copilot's 50-second outer hook timeout. In an interactive session Copilot waits for the `agentStop` callback before accepting the next prompt; in local testing it took about one second. When an interactive session exits or is interrupted, Copilot stops `sessionEnd` hooks after 1.5 seconds, so the callback passes the final recording to a detached process and returns. Starting Python and the sample takes about half a second on the test machine, so a much slower machine can miss that window; replay recovers the final state then. The detached process saves failures to private diagnostics; replay also recovers a final recording that failed. Missing or rejected credentials, connection errors and unsupported transcripts produce a warning. They do not change Copilot's native tool permissions. A warning means recording was not confirmed, even if part of the request reached Watcher.

After restoring connectivity or credentials, replay the same complete session from the SDK source directory:

```sh
./examples/github-copilot-cli/.venv/bin/watcher-github-copilot-cli replay \
  --config /path/printed/by/setup/config.json \
  --session-id <native-session-uuid>
```

If you set `COPILOT_HOME` for Copilot, pass the same value to replay. The command prints the Watcher session UUID, and one line per recorded subagent session, only after readback confirms each history, and exits nonzero on failure. It then prints how many of the gate's stored decisions for the session it confirmed. An unconfirmed decision leaves the exit status at zero, because the transcript was confirmed. A later completed turn also retries the full history. There is no background queue.

To remove the personal install, run:

```sh
./examples/github-copilot-cli/.venv/bin/watcher-github-copilot-cli remove
```

Add `--project /path/to/project` to remove a project install instead. Removal deletes the installed callback and its configuration, including the personal install's opt-outs. It keeps the saved login, recorded sessions and other hooks. The personal hook file is removed from the Copilot folder it was installed into, even if `COPILOT_HOME` has changed since. Until you remove it, setup refuses a different `COPILOT_HOME`. If an installed entry was edited by hand, restore it before removing the integration.

## Optional demo hooks

The `observe` and `enforce` commands also serve the separate demo hooks. Each demo command takes `--config` with a placeholder path; replace it with the configuration path printed by setup, whose saved login the hooks use. The demo commands leave out `--watcher-url`; add it with the server URL you gave setup to get the same check as setup's hooks. There is no environment-variable fallback. These files are for wiring hooks by hand instead of running setup. Copy `demo/hooks.observe.json` to a new file under the project's `.github/hooks/` to grade completed tool calls after each turn, or use `demo/hooks.enforce.json` for the same Blocking review gate that setup installs. `hooks.observe.json` runs `observe` at `agentStop` and at `sessionEnd`; `hooks.enforce.json` runs `observe --record-only` there, because its gate already judges each call. `sessionEnd` records the final state, including subagents that finish after the last turn, without assessing it again. Configure one set of recording hooks per project to avoid redundant callbacks. A demo hook runs beside the personal install, which records and judges the same calls. Opting the project out does not separate them when the demo hook's `--config` names a configuration in the same configuration root, because the opt-out turns that hook off too. The `observe` command confirms storage by reading it back, so the login needs session read and write access; when it fails, it exits with status 2 so Copilot shows its warning.

In every copied demo command, replace `watcher-github-copilot-cli` with the
quoted absolute path to its executable in the permanent SDK source directory.
Add `--config` with the private configuration path printed by setup. For example:

```json
"bash": "'/path/to/sdk/examples/github-copilot-cli/.venv/bin/watcher-github-copilot-cli' observe --config '/private/path/config.json'"
```

Keep each command's existing subcommand and flags, including `--record-only`
where present. Then start Copilot in the configured project. Setup-generated
hooks already use absolute executable paths.

With `hooks.observe.json`, the `agentStop` hook reads Copilot's native event log after each turn. It first records the complete supported transcript, including the final answer, and its subagents. It then assesses the tool calls made since the previous final answer, which covers calls before a steering prompt and calls of an earlier turn that was aborted or failed, each against its earlier history, before its result. Initial system instructions precede the first user message; later instruction changes remain in chronological order.

After waiting up to five seconds for the native transcript to flush and 25 seconds for recording, assessment has a 40-second budget, which each request may use in full. A recording failure stops that callback before grading. If grading runs out of time, the snapshot is already recorded while some judgments remain unfinished, and later callbacks do not return to that turn. Watcher reuses a completed judgment for the same call, so a retried callback usually does not grade it again. Failures print a short error and do not block Copilot.

Assessment after each turn follows the organization's Watcher policy without a
settings override, including when the mode is locked. In observe or enforce
mode, it runs rules and triage with `mode="triage_only"`; the full grading stage
does not run. Paused mode records the transcript without grading. Decisions are
advisory to actions that already finished: a returned deny cannot undo a tool,
and the adapter does not report that the action was blocked. Use Blocking review
where available to withhold execution. Assessment sends the recorded
calls, which carry Claude Code tool names (see [Tool names](#tool-names)),
so rules written for Claude Code tool names apply to it as they do at the gate.

In enforce mode, Watcher can store one of these assessments as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Find the conversation in Watcher by its external ID, `github-copilot-cli:<session-id>`.

## Blocking review

New setup installs this gate with the same private configuration as the
recording hooks. The `preToolUse` hook sends the current tool call and working
directory, with the session's conversation so far, read from Copilot's own log.
That is what Copilot has written when the hook runs, normally everything before
the pending call. It waits up to 420 seconds in total, reading the log included, for
Watcher's decision. `WATCHER_TIMEOUT_SECONDS` can shorten
that deadline; valid values are greater than zero and at most 420.

Copilot's hook input has no tool-call ID. Before it runs the hook, Copilot writes
a record of the hook run to its log, naming the session or subagent, the working
directory, the time and the pending calls with their IDs. The gate names a call by
that ID only when exactly one call matches. A match is an open hook record within
a second of the hook input, for the same session or subagent and the same
directory. It names the same tool with the same arguments, and the log's
conversation holds that call without a result. Tool names and arguments are
compared as Copilot sent them, before translation (see [Tool names](#tool-names)),
so a `bash` call and a `local_shell` call never match each other. Order never
decides. Identical parallel calls match each other, so none of them is named, and a decision or your
answer to an escalation is never stored on the wrong call. The log is
agent-writable, so a matching record within that second that has already ended
also leaves the call unnamed: the gate's own record cannot end while it runs. The gate waits up to
five seconds for the record to reach the log. A subagent's calls are in its
parent's log, and their decisions are stored on the subagent's own Watcher
session, `github-copilot-cli:<session-id>:agent:<agent-id>`.

Watcher then stores the conversation and its decision on that call, and the
Analyzer shows the decision beside it. The conversation the gate sends is the
same conversion that recording stores after the turn, so recording extends the
stored history rather than starting a second one.

The gate does not store the decision in five cases; it then judges the call
without storing anything, and saves the reason, without content, as an
`unrecorded_review` event in `events.jsonl`:

- `subagent_no_log`: no recently written log names the call's subagent, or the
  Copilot release names no session. It is judged without earlier conversation.
- `transcript_unsupported`: a log that could hold the call could not be read or
  converted, or has a broken line or malformed hook record written around the time
  of the call. A matching call could be in the damaged part, so none is named.
  Damage from earlier in the session does not count: Copilot writes its log in
  time order, so a broken line followed by an event from more than two seconds
  before the call was written before the call's hook record could have been.
  Only events up to the first one dated earlier than an event before it count
  for this, since such an event was not written in order. The
  call is judged with the recent conversation when the session's log can still be
  converted, otherwise without it.
- `tool_call_id_not_found`: no open hook record and call without a result match the
  pending call, or the hook input lacks the time or directory needed to match.
- `tool_call_ambiguous`: more than one call matches, such as identical parallel
  calls, or a matching hook record has already ended.
- `conversation_too_large`: the conversation and pending call exceed 7 MiB, inside
  Watcher's default 8 MiB request limit. Storing a trimmed copy would fork the
  stored history, so the gate judges the call with the most recent part of the
  conversation that fits.

These checks read Copilot's log, which the agent, or any process running as you,
can append to. Copilot gives parallel calls the same timestamp, so an event dated
the same as the one before it still counts as written in order. An appended
event with an old date can therefore make a broken line written around the call
look old, and the gate can then match another pending call with the same tool
and arguments. Under such tampering, Watcher judges the pending call with that
other call's conversation, which can change its decision, and the decision is
stored on the other call.

The hook accepts raw log events up to 16 MiB before converting the conversation.
If an event exceeds that limit, Watcher judges the pending call without earlier
conversation or session attribution.

When the decision is stored, the gate saves a receipt in `events.jsonl`: the
Copilot session and tool-call IDs, a hash of the judged call, Watcher's decision
values and the IDs of any grades. The gate also saves one for a multi-file patch
decision that recording stores (see [Tool names](#tool-names)). After
recording confirms a turn's transcript, it reads that session's stored decisions
back from Watcher, for up to five seconds and without grading anything again.
Each receipt must match the stored call, decision and grades. The result is
`last_review_check` in the status. It counts confirmed and unconfirmed
decisions, decisions made in paused mode, which stores none, and calls judged
without storing. A confirmed transcript does not confirm its decisions, and a
decision that cannot be confirmed never changes a tool's permission. The counts
cover only the records the rotating diagnostics log still holds, not every call
Copilot made.

The gate sends each call under the same tool name and arguments as the recorded
history: Claude Code's name where Copilot's tool has a counterpart, otherwise
Copilot's own. See [Tool names](#tool-names).

The hook inherits the organization's Watcher policy without settings overrides.
In enforce mode, a matching allow permits native dispatch and a deny withholds
the tool. An escalation asks you: interactive Copilot shows its hook permission
dialog, even with all tools allowed, while prompt mode cannot ask and denies the
call. A host that approves permission requests automatically, such as an
application built on the Copilot SDK with an approve-all handler, approves an
escalation without asking anyone. Your answer to that dialog is recorded too:
after each turn, recording reads Copilot's log for approvals and denials of the
gate's prompts and stores them as the human decision on the recorded call, which
the Analyzer shows beside Watcher's decision. A prompt cancelled without an answer
records none. Only answers about the parent conversation's own calls are stored.
Answers to prompts for a subagent's calls are not, so the Analyzer shows such a
call's escalation without a human decision. Answers come from Copilot's log,
which the agent, or any process running as you, can append to. So only answers
for calls this gate escalated count: the gate lists those calls in a private
`escalations.json` beside the configuration. Only an answer Copilot marks as a
person's, with `decisionSource` set to `human_response`, counts. In tests with
Copilot 1.0.91, an approval of the gate's prompt in an interactive session was
marked that way, and the denial Copilot gives in prompt mode was marked
`unattended_fallback`. A call whose prompts or answers in the log disagree, such
as an approval beside a denial, gets no human decision.
This narrows forged answers without ruling them out: an approval appended for an
escalated call that has no other answer in the log, for example because Copilot
stopped before you answered, is stored as yours.
Hook commands run without `--config` keep no such list and store no answers, nor
the multi-file patch decisions recording stores.
Valid responses in observe or paused mode leave native permissions in control.
The hook also honors an administrator's configured allow on grading failure.
Malformed, mismatched or unavailable decisions withhold execution.

`mode="full"` selects grading depth; it does not select auto mode or override
the organization's enforcement settings.

The gate answers the way Watcher's Claude Code hook does. A call Watcher
approves gets an explicit allow, and that allow replaces Copilot's own permission
check for the call:

- Copilot runs the call without its own permission prompt, even when the tool is
  not pre-approved with `--allow-tool` or `--allow-all-tools`.
- Copilot also runs a call that your own Copilot deny rules would refuse. In native
  testing with Copilot 1.0.89, an allowed `touch` command ran despite
  `--deny-tool='shell(touch)'`, and despite `--deny-tool=shell`, which denies every
  shell command.

This includes an administrator's configured allow on grading failure. While
Blocking review is installed and your organization uses enforce mode, put the
restrictions you rely on in Watcher's policy, such as a `deny` rule, rather than
in Copilot's deny rules. Only observe and paused mode answer with no decision,
which leaves the call to Copilot's own permissions, deny rules included. Withheld calls return a native denial whose
reason says whether Watcher withheld the call, rejected the credential, could not
be reached in time or could not evaluate it.

What the gate blocks is decided by the organization's Watcher policy. In local
testing with the default policy, the built-in Git read-only allow and the
`.watcher-ignore` escalation applied to Copilot's calls, while Watcher's grading
allowed `rm -rf` on a project directory. Add rules where you need a stricter
decision, such as a `deny` rule for `Bash` commands matching recursive deletes.

The gate is not tamper-resistant. It lives in your personal hooks folder, or
in the project's `.github/hooks/` directory, and the agent runs as you and can
edit either. Copilot only runs repository hooks in a trusted folder, or in
prompt mode with `GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS=true`. When the hooks do
not run, tools are allowed without a warning.

The agent runs as your user, so it can change every file your user can write.
That includes the hook file, the private configuration and the saved logins.
An agent that rewrites both files can point the hooks at a server it runs
itself, such as one on this machine that approves every call. Approved calls
then skip Copilot's own permission prompt. `status` cannot detect this, because
the server the hooks use is the one that confirms each delivery. Check that the
hook file names the server you set up. Only hooks your user cannot edit resist
tampering. Copilot documents organization policy hooks in
`/etc/github-copilot/policy.d`, which can be owned by root and which projects
cannot disable. This example does not install them. See
[Trust and enforcement](#trust-and-enforcement).

Recording stores native tool history after the turn, including a denied
call's denial and the result of every permitted call.

The hook file gives Copilot a 480-second outer deadline. If that deadline
expires, Copilot runs the tool through its normal permission flow. If the hook
command cannot start or exits nonzero, Copilot denies the tool. This example is
not a guarantee that every tool waits for Watcher.

## Tool names

Watcher's built-in rules and thresholds name Claude Code's tools. Watcher
translates the tools of harnesses it can identify, but it cannot tell that an SDK
request comes from Copilot, so this sample translates Copilot's tools itself.

Blocking review, the recorded history and assessment after each turn use the same
translation. Watcher refuses to store a gate decision whose tool name or
arguments differ from the same call in the stored transcript. So the Analyzer
shows a translated tool under its Claude Code name, with the translated
arguments, and rules written for Claude Code's tools apply to it. Rules keyed to
Copilot's own name for a translated tool do not apply.

| Copilot tool | Recorded and judged as | Arguments |
|---|---|---|
| `bash`, `local_shell` | `Bash` | Unchanged |
| `powershell` | `PowerShell` | Unchanged |
| `write_bash`, `write_powershell` | `Bash`, `PowerShell` | Typed `input` becomes `command` |
| `view` | `Read` | `path` becomes `file_path` |
| `create` | `Write` | `path` becomes `file_path` |
| `edit` | `Edit` | `path` becomes `file_path` |
| `str_replace_editor` | `Read` for `view`, `Write` for `create`, `Edit` for `str_replace` and `insert` | `path` becomes `file_path` |
| `apply_patch` | `Write` or `Edit`, by its first file | See below |
| `grep`, `rg` | `Grep` | Unchanged |
| `glob` | `Glob` | Unchanged |
| `web_fetch` | `WebFetch` | Unchanged |
| `web_search` | `WebSearch` | Unchanged |
| `task` | `Agent` | Unchanged |
| `skill` | `Skill` | Unchanged |
| `lsp` with `goToDefinition`, `findReferences`, `hover`, `documentSymbol`, `workspaceSymbol`, `goToImplementation`, `incomingCalls` or `outgoingCalls` | `LSP` | `file` becomes `filePath` |

A key the translation sets, such as `command` or `file_path`, replaces any key of
the same name the model sent. Other arguments pass through, so a translated
`str_replace_editor` call keeps its `command`, and `create` keeps `file_text`. A
file tool whose path is not text keeps its arguments under the Claude Code name.

PowerShell calls get Claude Code's `PowerShell` tool rather than `Bash`, because
Watcher's Bash allow rules assume POSIX shell syntax and never allow a PowerShell
command. Write rules for `PowerShell` where you need them. Text typed into a
running shell with `write_bash` or `write_powershell` is judged as a command for
that shell. Copilot 1.0.62 and later no longer offer these two tools, but Copilot
still runs the gate when a model calls one.

GPT's `apply_patch` becomes `Write` when its first file is an added file and
`Edit` otherwise, with that first path as `file_path`, every path under
`file_paths` and the raw patch under `input`. The sample reads file headers the
way Copilot's own patch parser does in 1.0.89 and 1.0.91: it starts a line at
LF, CR or CRLF, and trims each line and path as JavaScript's `trim` does, so an
indented, CR-separated or byte-order-mark-led header still names its file.
Text that contains `*** Begin Patch` but names no file this sample can read
becomes `Edit` without a `file_path`, so Edit thresholds still apply to it. Because Edit and Write rules
match `file_path` alone, the gate first judges each further path of a multi-file
patch, as `Write` for an added file or a `Move to` target and `Edit` otherwise,
without storing those extra decisions, and applies the strictest result. A further path judged deny withholds
the call without judging the first path. Watcher stores a gate decision only for
the call as recorded, judged on its first file, so when a further path is judged
deny or escalate, the gate stores nothing itself. It saves a receipt of the
strictest judgment across the patch's files instead. After recording confirms
the turn's transcript, it stores that judgment on the call. When the gate
escalated a call of the parent conversation, your answer is stored with it; for a
subagent's call it is not. The Analyzer then shows the decision that
governed the patch, without grades, because those judgments keep none. Until the
turn is recorded, the call shows no decision.

Every other tool keeps Copilot's name and arguments, in the gate and in the
Analyzer. Only thresholds and rules written for that name, or for any tool, apply
to it. A tool with no threshold of its own gets Watcher's `unknown` threshold,
which by default leaves each call to rules and grading. These tools have no
Claude Code counterpart:

- `lsp` with `rename`, which edits files across the project, while Claude Code's
  `LSP` only reads, and with any operation not listed in the table.
- `str_replace_editor` with a command other than the four in the table.
- `sql` and `session_store_sql`, which query Copilot's own session databases.
- `list_bash`, `list_powershell` and `list_agents`.
- `manage_schedule`, `extensions_manage`, `extensions_reload` and the canvas tools.
- `store_memory`, `vote_memory`, `task_complete` and
  `fetch_copilot_cli_documentation`.
- MCP tools, named `<server>-<tool>`.
- Freeform text that does not contain `*** Begin Patch`, judged as
  `{"input": <raw text>}`.

Some tools also keep Copilot's names although a Claude Code tool does similar work:

- `read_bash`, `read_powershell`, `stop_bash` and `stop_powershell`, which read or
  stop shells Copilot started.
- `read_agent` and `write_agent`, which read or message agents Copilot started.
- `update_todo` and `tool_search_tool`.
- `ask_user` and `exit_plan_mode`. Watcher's default policy would escalate every
  call to these under Claude Code's names.

## Scope and testing

The converter records model-facing text, readable reasoning, function and freeform tool calls with their results, and these other events:

- **Reasoning.** Readable reasoning appears in the Analyzer as internal reasoning before the assistant's reply. Encrypted reasoning and provider signatures contain no readable text and are not recorded.
- **Compaction.** A successful compaction appends Copilot's summary and Watcher's compaction notice, which the Analyzer shows as a context-compacted marker. Earlier messages stay in place, so each snapshot extends the previous one. Copilot wraps the summary in its own template before sending it to the model; the transcript records the summary text. A background compaction's summary appears where the compaction finished; when a prompt-mode session ends mid-compaction, recording waits up to 15 seconds for it, and a slower compaction is recorded by the next turn or by replay. Failed compactions change nothing. A `/compact` command fires none of the hooks this sample installs, so its summary is recorded with the next turn, at the end of the session or by replay.
- **Truncation.** When Copilot drops earlier messages from the model's context without compacting, a truncation notice records how many.
- **Subagents.** The parent conversation keeps the delegation call and its result, whose metadata names the subagent. Each subagent that has replied is recorded as its own Watcher session with the ID `github-copilot-cli:<session-id>:agent:<agent-id>`, once it completes or fails, or with the session as it stands when the session ends or is replayed. With `hooks.observe.json`, subagents are recorded the same way but not assessed.
- **Interruptions.** A tool call still running when Copilot aborts the turn gets the result Copilot later gives the model: `The execution of this tool, or a previous tool was interrupted.` When a session resumes, calls and subagents left open by the process that ended, for example after a crash, get the same result, unless the resume joined a session another client is still running. A result that arrives after an interruption is not recorded, since the model was given the interrupted result.
- **Rewinds and cleared sessions.** `/rewind` rewrites Copilot's log from the chosen turn; the next turn is recorded as a new branch of the same Watcher session, which becomes its latest trajectory. `/clear` starts a new Copilot session, recorded separately.
- **User shell commands.** A `!command` is recorded as the user message the model receives, with the command, its output and whether it exited with code 0; a failed or cancelled command reads "non-zero exit code".
- **Model errors.** A model request that fails, for example with HTTP 500, 429 or an authentication error, is recorded as an error notice, so a failed first turn is recorded too.
- **Attachments and binary results.** Each is recorded as a data block with Copilot's descriptor: path or name, MIME type, size and content hash. The bytes are not recorded, because the Analyzer and graders cannot use them and they would count against Watcher's request size limit.
- **Injected context.** Skill context, mode notices and system notifications, such as a background agent finishing, are recorded as the user messages the model received. A session handed over from another Copilot session, such as a cloud agent, records the handoff summary and context as a user message.
- **Unanswered calls.** A tool call whose result has not appeared yet stays unanswered. If its result appears later, the next snapshot adds it.

Tool results use native `content`; UI-only `detailedContent` and display metadata are not recorded. Each later system prompt is recorded where it appeared, although the model only receives the latest one. When Copilot discovers nested instructions mid-session, the transcript records Copilot's notification but not the instruction text, which Copilot does not log.

An event type this sample does not recognize is recorded where it first appears as a notice naming the type, without its content, and recording continues. An event it cannot read, such as a broken line, an event with malformed fields, or a tool call or result that repeats an earlier tool-call ID, is left out: a skipped-event notice marks the place, without the event's content, recording continues, and the recording adds a `skipped_events` event to `events.jsonl`. The sample refuses provider-hosted tools and provider content blocks, which remain in the session log, so every later recording in that session also fails; start a new session to restore recording. Histories larger than 256 MiB and inconsistent system content are also refused instead of sending a partial transcript. NUL characters are removed, as Watcher's database cannot store them.

Every turn sends the whole history, and Watcher's server rejects hook requests above its request size limit, 8 MiB by default. Tool results longer than 131,072 characters, such as a large file read with `view`, are cut at that length with a note giving the full length; tool-call arguments and user messages are not cut. In prompt mode, Copilot logs its full system prompt of roughly 37 KB with every invocation, so a session still reaches the limit after about 200 prompt-mode turns, or sooner with many large results; recording then fails with a warning on every later turn. Start a new session, or, on a self-hosted server, raise `hooks_max_request_bytes`.

This example was tested live on Linux with Copilot CLI 1.0.89 in custom-provider, prompt mode (`--prompt`, one invocation per turn), recording into a local Watcher. These tests used OpenAI-, Anthropic- and Gemini-compatible model endpoints with high reasoning effort. The scenarios were manual, repeated and automatic compaction, truncation, synchronous and background subagents, image attachments, interruptions, denials, skills, parallel calls, a mid-session model switch, project custom instructions, concurrent replays, an upgrade from the previous version of this sample, invalid keys, and enforcement: default-policy rule decisions, a model-graded decision, escalations, native permissions without allow-all, subagent and MCP calls, organizations in observe and paused mode. NUL output, large file views, provider errors and a killed-then-resumed session were recorded. Interactive sessions, with the same Copilot version, were tested with rewind, `/clear`, `!command`, `/exit` with a background subagent, and the escalation dialog with all tools allowed. GitHub-hosted Copilot models and authentication, `@` file mentions (interactive only), failed or cancelled subagents and sessions long enough to reach the request size limit were not tested live. In custom-provider mode Copilot marks models as unable to view images, so image tool results carry no descriptor to record.

Other hooks that change arguments can make execution differ from the arguments Watcher assessed. Use Blocking review only where other hooks leave tool arguments unchanged. Manual shell commands and tools outside Copilot's hook path are outside its scope.

The tests include installed-package conversion and SDK checks. Native verification covers Linux. The native recipe uses the real Copilot CLI with local model and Watcher fixtures in a container with no external network. It checks actual file effects for approval, refusal and timeout cases. Fixture results do not establish deployed Watcher recording, grading quality or provider compatibility. See `metadata.yaml` for the recorded verification status.

```sh
bash tests/native/run.sh
```

Docker, Node and uv are needed to build the test environment. Dependency downloads happen before isolated execution. The command prints a directory containing logs, test results and the installed SDK version. `WATCHER_SDK_WHEEL` can select a local SDK wheel, and `WATCHER_EXAMPLE_RUN_DIR` selects the parent directory for test output.

## Directory layout

```text
github-copilot-cli/
├── metadata.yaml
├── README.md
├── pyproject.toml
├── uv.lock
├── src/watcher_github_copilot_cli/
├── demo/
└── tests/
    └── native/
```

Upstream reference: [Copilot hook contracts](https://docs.github.com/en/copilot/reference/hooks-reference).
