# Example metadata and layout

Each example contains a `metadata.yaml` file. It describes what the example does,
what its tests cover, and which versions were tested. Package files such as
`pyproject.toml`, `package.json` and `pom.xml` define dependencies and build settings.

## Metadata

The [JSON Schema](metadata.schema.json) defines the fields and accepted values.
Schema version 2 requires these groups:

| Group | Fields and purpose |
| --- | --- |
| Identity | `slug`, `name`, `summary`, `category` and `upstream_url` identify the integration. `direction` states whether data goes to or from Watcher. |
| Maintenance | `support_status` is `experimental` or `archived`. `updated_at` is the date of the latest change. `maintainer` is optional. |
| Capabilities | `capabilities.observe` and `capabilities.enforce` state whether each mode exists and where to run it. Exporters also have `capabilities.export`. |
| Verification | `verification` contains the latest recorded test environment, or is empty when no run is recorded. |
| Limitations | `limitations` describes gaps in behavior or testing. The list may be empty. |
| Packages | `manifests` lists the native package files by relative path. |

An implemented capability needs a `scope` and an `example` path. Tool blocking also
needs its execution boundary, available context, recording behavior and error
policy. State native hook limits as well as errors the adapter handles. A host
timeout can have a different outcome from an SDK timeout caught by the adapter.

Each limit has a descriptive `id`, an affected `mode`, a `cause`, a `kind` and a
plain-language `description`. Use `blocker` for a feature that cannot work,
`verification-gap` for behavior that has not been tested, and `constraint` for a
limit on the feature's scope. Missing tests alone do not prove an SDK defect.

### Tested versions and scope

A verification entry records:

- `checked_at`: the date the tests ran.
- `watcher_sdk` and `watcher_server`: observed versions. The server is null for
  fixture-only tests.
- `upstream_versions`, `runtimes` and `platform`: the upstream packages and test
  environment. A null upstream version means it was not observed.
- `watcher_test_target`: a local SDK transport fixture, a local HTTP fixture, a
  local API, or a deployed service.
- `results`: separate outcomes and coverage for observation, tool blocking and,
  where present, export.

Keep the SDK version, upstream version and example package version distinct.
Dependency ranges state what installation permits; they are not a list of tested
versions. Local fixture tests do not establish deployed behavior.

Coverage distinguishes the upstream tool from Watcher itself:

| Value | Tested boundary |
| --- | --- |
| `contract` | Adapter logic and SDK request contracts. |
| `native-fixture` | Installed upstream software with fabricated Watcher replies. |
| `native-local-api` | Installed upstream software through the actual local Watcher API and database. |
| `contract-local-api` | Installed receiver or exporter through actual local Watcher, with a protocol fixture for the hosted source or destination. |
| `deployed-end-to-end` | The documented path through a deployed Watcher service. |

A server version of `dev` is the value reported by an unstamped local build, not
a tested release. Read the capability scope and limitations alongside the version.


`verification_plan` names the test suites for each mode. A plan is not a passing
result. Set `checked_at` only from a real run. Editing a README must not make an old
test date current.

## Directory layout

Most Python examples use this layout:

```text
integration/
├── metadata.yaml
├── README.md
├── pyproject.toml
├── uv.lock
├── src/watcher_integration/
├── demo/
└── tests/
    ├── fixtures/          # when needed
    └── native/            # when a real agent or container is needed
```

Reusable code and runtime assets belong in `src/`. Demos and tests import the
installed package. Keep fixtures separate from code that runs in a customer's
application. Python examples use distinct import names so they can share an
environment without replacing one another.

Node.js examples use `package.json` and a lockfile. Java examples keep their Maven
or Gradle layout. Mixed-language examples use separate folders such as
`packages/python/` and `packages/node/`. List each package in `manifests`; installing
one language component does not install the other.

The README gives installation, configuration, usage, limits and test commands.
Include only the folders an example needs. A Python `requirements.txt` file is not
needed when `pyproject.toml` and `uv.lock` define the environment.
