# Watcher Python SDK

Typed Python client for the Watcher API. Provides sync and async clients with
automatic retry, pagination, and structured error handling.

## Installation

Requires Python 3.12+.

Download the SDK wheel for your Watcher release from
[Watcher releases](https://github.com/ApolloResearch/watcher-bin/releases). For example:

```bash
pip install ./watcher_sdk-0.34.0-py3-none-any.whl
```

Wheels remain available with every release. If the release also provides
`watcher_sdk-<version>-source.tar.gz`, it contains the same runtime source under
`sdk/`. After extracting the archive, install it with:

```bash
pip install ./sdk
```

The generated API client and both runtime packages are included. Regenerating
the client is not required to install from source. Releases without a source
archive can be installed from their wheel.

## Quick start

```python
from watcher_sdk import WatcherClient

with WatcherClient("http://localhost:8000") as client:
    sessions = client.list_sessions()
    print(f"Total sessions: {sessions.total}")

    for session in client.list_sessions_iter():
        print(session.session_id, session.trajectory_count)
```

An `AsyncWatcherClient` with the same surface is available for asyncio code.

## Documentation

See the [Watcher documentation](https://watcher-docs.apolloresearch.ai) for configuration
and authentication, ingestion and grading, pagination, and error handling.

## License

The SDK is licensed under the [MIT License](LICENSE). Dependency licenses are
listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
