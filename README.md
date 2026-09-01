# Watcher

Monitor your AI coding agents.

Watcher observes coding agents (Claude Code and Codex) as they work. It hooks into agent sessions on your machine, sends activity to your Watcher backend for analysis, and gives you visibility into, and policy controls over, what agents are doing. For more, see [watcher.apolloresearch.ai](https://watcher.apolloresearch.ai), or [read the docs](https://watcher-docs.apolloresearch.ai).

## Install

Watcher runs on macOS (Apple Silicon) and x86_64 Linux.

```bash
# Apollo's hosted cloud
curl -fsSL https://github.com/ApolloResearch/watcher-bin/releases/latest/download/install.sh | bash -s -- --cloud
```

```bash
# A backend your organization hosts
API_URL="https://watcher.example.com"
curl -fsSL https://github.com/ApolloResearch/watcher-bin/releases/latest/download/install.sh | bash -s -- --watcher-api-url $API_URL
```

Then start Watcher:

```bash
watcher
```

For sign-in, containers, and everything else, see the [client guide](https://watcher-docs.apolloresearch.ai/client/).

## Other commands

```bash
# Check the health of your Watcher installation
watcher doctor
# Update the Watcher client
watcher update
# Uninstall Watcher
watcher uninstall
```

See the full command reference [here](https://watcher-docs.apolloresearch.ai/client/#command-reference).

## Python SDK

Every release also ships the Watcher Python SDK as a wheel. Download `watcher_sdk-<version>-py3-none-any.whl` from the [latest release](https://github.com/ApolloResearch/watcher-bin/releases/latest), then:

```bash
pip install ./watcher_sdk-<version>-py3-none-any.whl
```

See the [SDK docs](https://watcher-docs.apolloresearch.ai/api/python-sdk/) for usage.

## Licenses

Third-party license attributions are listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
