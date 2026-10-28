# Watcher integration examples

Examples for connecting agents, model libraries, gateways, compliance data and
observability tools to Watcher. They show how to send conversations for review,
check tool calls before they run, and export decisions, session summaries and
optional transcripts to other tools.

Each example has its own README, source, tests and package files. Choose one below,
then follow its README for setup and use. These are reference examples to adapt and
test in your own environment. They are separate from the
[built-in Watcher client integrations](https://watcher-docs.apolloresearch.ai/supported-agents/).

## Choose where to connect

| Integration type | Where the example runs | What the connection can cover |
| --- | --- | --- |
| Coding agents | Native harness hooks or approval interfaces | Tool proposals before execution and the transcript visible to the harness. Native timeout and hook-loading behavior matter. |
| General-purpose agents | The agent's tool lifecycle | Tool checks and transcript ingestion. Unattended runs need an explicit policy for calls that require human approval. |
| Agent frameworks | The framework's native scheduler or callbacks | Tool checks before dispatch, with a human approval callback where implemented. Read the example's unattended and human-choice behavior. |
| Model libraries | Application code using a provider SDK | The application's model exchanges and the tools dispatched through its monitor. Other clients are outside this boundary. |
| Gateways | A server-side plugin, callback or export connection | Clients using the configured gateway route inherit monitoring. A synchronous callback can withhold tool proposals; completed-request exports provide observation only. |
| Compliance APIs | An importer | Completed activity for later review. Imported calls have already happened. |
| Observability and SIEM | An SDK-based exporter | Stored Watcher decisions, selected sessions and optional transcripts sent to another system. |

## Choose an integration

The table summarizes the tests recorded in each example's metadata. Dates
identify those runs; they do not establish compatibility with changes made since
the test. Read the example's README for the tested environment, covered paths
and remaining limits. **Last tested** shows Not recorded when no test run is
recorded.

| Label | Meaning |
| --- | --- |
| Static tests | Adapter tests with simulated Watcher responses; some also exercise installed upstream software. |
| End-to-end testing | The integration path was tested against the Watcher API and database, locally or deployed. Model output or hosted services may use fixtures; see the example's README. |
| Not verified | The example provides this feature, but no passing test is recorded for it. Read its README before relying on it. |
| Not available | The example does not provide this feature. |

Read the example's limits before enabling tool blocking. A test result does not
mean every tool path is covered. Some hooks can stop a tool without recording a
decision; others cannot stop the tool if the host times out or fails to start them.

Local exporter tests do not establish that a hosted destination indexed the records
or generated an alert. Each README names the tested receiver
and the steps needed to verify your destination.

<!-- BEGIN INTEGRATIONS -->

### Coding agents

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [Aider](aider/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Amp](amp/README.md) | Static tests | Not available | 2026-09-26 |
| [Cline](cline/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Continue CLI](continue/README.md) | Static tests | Not available | 2026-09-26 |
| [Cursor](cursor/README.md) | Static tests | Static tests | 2026-09-26 |
| [Gemini CLI](gemini-cli/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Goose](goose/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Hermes Agent](hermes/README.md) | Not verified | Not verified | Not recorded |
| [Kilo Code](kilocode/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Mistral Vibe](mistral-vibe/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [OpenCode](opencode/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [OpenHands](openhands/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Pi](pi/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Qwen Code](qwen-code/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Roo Code](roo-code/README.md) | Static tests | Not available | 2026-09-26 |
| [Windsurf](windsurf/README.md) | Static tests | Static tests | 2026-09-26 |

### General-purpose agents

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [OpenClaw](openclaw/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |

### Agent frameworks

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [Agno](agno/README.md) | Static tests | Static tests | 2026-09-26 |
| [AutoGen](autogen/README.md) | Static tests | Static tests | 2026-09-26 |
| [CAMEL](camel/README.md) | Static tests | Static tests | 2026-09-26 |
| [CrewAI](crewai/README.md) | Static tests | Static tests | 2026-09-26 |
| [DSPy](dspy/README.md) | Static tests | Static tests | 2026-09-26 |
| [Google ADK](google-adk/README.md) | Static tests | Static tests | 2026-09-26 |
| [Haystack](haystack/README.md) | Static tests | Static tests | 2026-09-26 |
| [LangChain](langchain/README.md) | Static tests | Static tests | 2026-09-26 |
| [LangChain4j](langchain4j/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [LangGraph](langgraph/README.md) | Static tests | Static tests | 2026-09-26 |
| [LlamaIndex](llamaindex/README.md) | Static tests | Static tests | 2026-09-26 |
| [Mastra](mastra/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [OpenAI Agents](openai-agents/README.md) | Static tests | Static tests | 2026-09-26 |
| [Pydantic AI](pydantic-ai/README.md) | Static tests | Static tests | 2026-09-26 |
| [Semantic Kernel](semantic-kernel/README.md) | Static tests | Static tests | 2026-09-26 |
| [smolagents](smolagents/README.md) | Static tests | Static tests | 2026-09-26 |
| [Strands Agents](strands/README.md) | Static tests | Static tests | 2026-09-26 |
| [Vercel AI SDK](vercel-ai/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |

### Gateways

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [Agent Router](agent-router/README.md) | End-to-end testing | End-to-end testing | 2026-10-06 |
| [Bifrost](bifrost/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Cloudflare AI Gateway](cloudflare-ai/README.md) | Static tests | Not available | 2026-09-26 |
| [Helicone](helicone/README.md) | End-to-end testing | Not available | 2026-09-26 |
| [Kong AI Proxy](kong-ai/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [LiteLLM proxy](litellm/README.md) | End-to-end testing | End-to-end testing | 2026-10-01 |
| [OpenRouter](openrouter/README.md) | Static tests | Not available | 2026-09-26 |
| [Portkey](portkey/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |

### Model libraries

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [Anthropic Messages](anthropic/README.md) | Static tests | Static tests | 2026-09-26 |
| [Cohere V2](cohere/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 |
| [Google Gen AI](google-genai/README.md) | Static tests | Static tests | 2026-09-26 |
| [Groq](groq/README.md) | Static tests | Static tests | 2026-09-26 |
| [Hugging Face Inference](huggingface-inference/README.md) | Static tests | Static tests | 2026-09-26 |
| [Mistral AI](mistralai/README.md) | Static tests | Static tests | 2026-09-26 |
| [Ollama](ollama/README.md) | Static tests | Static tests | 2026-09-26 |
| [OpenAI Responses and Chat Completions](openai/README.md) | Static tests | Static tests | 2026-09-26 |

### Compliance APIs

| Integration | Observe | Block tools | Last tested |
| --- | --- | --- | --- |
| [Claude Compliance API](claude-compliance/README.md) | Static tests | Not available | 2026-09-26 |

### Observability and SIEM

| Integration | Export | Last tested |
| --- | --- | --- |
| [Google Security Operations](google-security-operations/README.md) | Static tests | 2026-09-26 |
| [Microsoft Sentinel](microsoft-sentinel/README.md) | Static tests | 2026-09-26 |
| [OpenTelemetry](opentelemetry/README.md) | Static tests | 2026-09-26 |
| [Splunk](splunk/README.md) | Static tests | 2026-09-26 |

<!-- END INTEGRATIONS -->

## Export destinations

These examples send stored decisions, session summaries and optional transcripts
to observability and SIEM tools. They do
not add synchronous tool blocking. Destination setup, authentication, indexing
and detection rules are separate from exporting a request.

| Destination | Example | Transport |
| --- | --- | --- |
| Grafana / Loki | [Setup](opentelemetry/README.md#grafana-and-loki) | OTLP logs through a Collector |
| Datadog | [Setup](opentelemetry/README.md#datadog) | OTLP logs through a Collector |
| Splunk | [Setup](splunk/README.md) | HTTP Event Collector |
| Microsoft Sentinel | [Setup](microsoft-sentinel/README.md) | Azure Monitor Logs Ingestion into a custom table |
| Elastic Cloud | [Setup](opentelemetry/README.md#elastic-cloud) | Managed OTLP endpoint through a Collector |
| New Relic | [Setup](opentelemetry/README.md#new-relic) | OTLP logs through a Collector |
| Dynatrace | [Setup](opentelemetry/README.md#dynatrace) | OTLP logs through a Collector |
| AWS CloudWatch Logs | [Setup](opentelemetry/README.md#cloudwatch-logs) | OTLP logs signed by the Collector |
| OpenSearch | [Setup](opentelemetry/README.md#opensearch) | OTLP through OpenSearch Ingestion or Data Prepper |
| Google Security Operations | [Setup](google-security-operations/README.md) | Chronicle v1 structured-event import |

An accepted request does not prove searchable records or an alert. The README
provides a destination check and states which local tests were run. Reconcile
late-arriving records and later decision changes before relying on scheduled
exports; occurrence-time windows do not provide a complete change feed.

## Install and configure

The examples are included in the SDK source export under `sdk/examples/`.
Download `watcher_sdk-<version>-source.tar.gz` for your server version,
following the [SDK installation instructions](../README.md#install),
and extract it, keeping the whole `sdk/` directory together. Older source
releases may not contain examples. The SDK wheel installs only the client library.

Python examples use the SDK source next to this directory. `uv sync` resolves that
local package and the example's own dependencies. Mixed-language examples have
separate Python and Node.js or Java packages; their READMEs give the install order.

To use an example with a released SDK wheel, install the wheel that matches your
Watcher server before installing the example package. See the
[SDK installation guide](https://watcher-docs.apolloresearch.ai/api/python-sdk/).
The package files define dependencies. The [metadata](METADATA.md) lists the
versions and environments used in tests.

Keep credentials in environment variables or your normal secret store. Each README
names the values its example needs. Demo credentials and local fixtures are for
tests, not a deployed service.

## What each mode does

**Observation** sends conversations or tool activity to Watcher. It cannot stop a
tool that has already run. Some examples send a full conversation only when the
agent finishes.

**Tool blocking** waits for Watcher before allowing a covered tool to run. Coverage
depends on the agent's hooks or the application's tool dispatcher. The README
states which tools it covers, what context Watcher receives, and what happens on
errors and timeouts.

**Export** sends recorded Watcher results to another system. Transcript content
is excluded unless explicitly enabled. An export does not
add a pre-tool check or prove that all future updates will be delivered.

## Tests and metadata

Each README explains how to run its tests. Network-isolated fixtures keep test
model calls and Watcher requests local. Native test recipes require the tools and
container runtime listed in that example.

`metadata.yaml` records the example's capabilities, known limits and latest tested
environment. An empty verification list means no run is recorded. The test date is
separate from the date the example was last updated. See the
[metadata and directory reference](METADATA.md) for the full format.
