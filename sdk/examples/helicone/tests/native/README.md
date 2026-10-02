# Receiver verification against Watcher

This fixture starts the installed receiver CLI on local HTTPS, sends signed
completion-webhook fixtures and checks stored sessions through the public SDK.
It verifies invalid-signature rejection, inline ingestion, redelivery and
credential-free retrieval of a referenced body. The source events are synthetic;
this test does not run Helicone or establish its delivery behavior.

From the example directory, build the image with Docker, uv and access to package
registries:

```sh
bash tests/native/build.sh
```

Set `WATCHER_SDK_WHEEL` to an absolute wheel path to select an already-built SDK.
The printed artifact directory contains `image.id`, the build log, exported
dependency constraints and image inspection. The image contains the receiver
and SDK installed from retained wheels, the contract tests, and
`/opt/observer/probe.py`. The build runs the contract tests without networking.
The probe creates a fresh local certificate for every run.

The Watcher repository's `tests/integration/sdk_examples/test_helicone.py` runs
this probe through its shared backend fixture. Select it with
`WATCHER_SDK_EXAMPLES_OBSERVER=helicone` and set
`WATCHER_SDK_EXAMPLES_OBSERVER_IMAGE` to the immutable image ID. The test owns an
isolated container and PostgreSQL database; no hosted Helicone or model-provider
credential is needed.

The retained evidence includes exact posted event bytes and headers, receiver
responses, storage fetches, Watcher requests, and SDK readback of every accepted
history. Its verification level is `contract-local-api`: a synthetic source event
through the real installed receiver, Watcher API and database.
