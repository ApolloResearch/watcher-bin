# Watcher

Monitor your AI coding agents. 

Watcher observes agents (Claude Code and Codex) as they work. It hooks into agent sessions on your machine, sends activity to your Watcher backend for analysis, and gives you visibility into, and policy controls over, what agents are doing. For more, see [watcher.apolloresearch.ai](https://watcher.apolloresearch.ai).

## Install

Watcher runs on macOS (Apple Silicon) and x86_64 Linux.

```bash
curl -fsSL https://github.com/ApolloResearch/watcher-bin/releases/latest/download/install.sh | bash -s -- --cloud
```

Open a new terminal, then start Watcher one of two ways.

Run it in the current terminal (stops when you close it):

```bash
watcher
```

Watcher starts in the background and automatically starts on future logins.

To run Watcher only in the current terminal, without enabling start-on-login:

```bash
watcher --foreground
```

Watcher stops when that terminal closes.

## Uninstall

```bash
watcher uninstall
```

### Self-hosted

If your organization runs its own Watcher backend, pass its URL with `--watcher-api-url`:

```bash
curl -fsSL https://github.com/ApolloResearch/watcher-bin/releases/latest/download/install.sh | bash -s -- --watcher-api-url https://watcher.veidt.enterprises
```

The installer downloads the latest release, verifies its checksum, installs the binary to `~/.local/bin/watcher`, records your chosen backend, and registers agent hooks (with a consent prompt where config changes are needed). If `~/.local/bin` isn't on your `PATH`, the installer prints the command to add it.

The first time you run `watcher`, it opens a sign-in page in your browser; monitoring starts once you've signed in with your organization's credentials.

### Installing a specific version

```bash
curl -fsSL https://github.com/ApolloResearch/watcher-bin/releases/download/v0.11.3/install.sh | bash -s -- --watcher-api-url https://watcher.veidt.enterprises
```

This is useful for self-hosted instances, where you'll want a client version that matches your server. The client is compatible with server versions within ±1 minor versions (while `v0.x.x`) of its own version.

## Updating

Re-run the same install command you used above. The installer safely replaces the existing installation; your sign-in and settings are kept.

## Uninstall

```bash
watcher uninstall
```

## CLI reference

Running `watcher` with no arguments starts the Watcher services. Other commands:

| Command | Description |
| --- | --- |
| `watcher --version` | Show the installed Watcher client version. |
| `watcher target set --cloud` / `--url <url>` | Change the backend this install talks to. |
| `watcher hooks install` / `remove` | Install or remove the agent hooks, always for both Claude Code and Codex. `install --yes` skips the consent prompt (for unattended installs). |
| `watcher autostart install --launcher <script>` / `uninstall` | Install or remove the login agent that runs Watcher on login. |
| `watcher autostart enable` / `disable` | Turn autostart-on-login on or off. |
| `watcher autostart start` / `stop` | Start or stop the login agent now, without waiting for login. |
| `watcher profile list` / `current` / `set` | List, show, or switch Watcher settings profiles. |
| `watcher build-info` | Show build details and the backend target a launch would resolve. |
| `watcher uninstall` | Remove hooks, autostart, and the Watcher binary. |

Run `watcher <command> --help` for full details on any command.

## Licenses

Third-party license attributions are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
