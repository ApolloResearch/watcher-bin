# Watcher Python SDK

A typed Python client for the Watcher API, with sync and async clients, retries,
pagination and structured errors. Requires Python 3.12 or later.

## Install

Follow the [SDK download instructions](https://watcher-docs.apolloresearch.ai/api/python-sdk/#installation)
to get the wheel matching your server version. For example:

```bash
pip install ./watcher_sdk-0.36.0-py3-none-any.whl
```

Wheels remain available with every release. If the release also provides
`watcher_sdk-<version>-source.tar.gz`, it contains the same runtime source under
`sdk/`. After extracting the archive, install it with:

```bash
pip install ./sdk
```

The generated API client and both runtime packages are included. Regenerating
the client is not required to install from source. Releases without a source
archive can be installed from their wheel. See the
[installation and authentication guide](https://watcher-docs.apolloresearch.ai/api/python-sdk/)
for server configuration.

## Quick start

```python
import os

from watcher_sdk import WatcherClient

with WatcherClient(
    os.environ["WATCHER_BASE_URL"],
    api_key=os.environ["WATCHER_API_KEY"],
) as client:
    for session in client.list_sessions_iter():
        print(session.session_id, session.trajectory_count)
```

Use the API base URL for your deployment, including its `/api` prefix when required.
`AsyncWatcherClient` provides the same methods for asyncio applications.

## Integrations and reference

The [integration examples](examples/README.md) under `sdk/examples/` cover
agents, frameworks, gateways, model libraries and exports. These are reference
samples to adapt and test in your environment, not complete production
integrations. They are included in the SDK source export. Keep the examples
beside the SDK source when
extracting the archive; their Python packages use the adjacent SDK.
Each example includes setup instructions, source, tests and the limits of its
tool blocking and test coverage. The [integration guide](https://watcher-docs.apolloresearch.ai/integrations/)
compares the available connections.

The [SDK reference](https://watcher-docs.apolloresearch.ai/api/python-sdk/) covers
authentication, ingestion, grading, sessions, error handling and pagination.

## License

The SDK is licensed under the [MIT License](LICENSE). Dependency licenses are
listed in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
