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
and remaining limits.

| Label | Meaning |
| --- | --- |
| Static Tests | Adapter tests with simulated Watcher responses; some also exercise installed upstream software. |
| End-to-end testing | The integration path was tested against the Watcher API and database, locally or deployed. Model output or hosted services may use fixtures; see the example's README. |
| Not available | The example does not provide this feature. |

Read the example's limits before enabling tool blocking. A test result does not
mean every tool path is covered. Some hooks can stop a tool without recording a
decision; others cannot stop the tool if the host times out or fails to start them.

Local exporter tests do not establish that a hosted destination indexed the records
or generated an alert. Each README names the tested receiver
and the steps needed to verify your destination.

<!-- BEGIN INTEGRATIONS -->

### Coding agents

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [Aider](aider/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Amp](amp/README.md) | Static Tests | Not available | 2026-09-26 | Example |
| [Cline](cline/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Continue CLI](continue/README.md) | Static Tests | Not available | 2026-09-26 | Example |
| [Cursor](cursor/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Gemini CLI](gemini-cli/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Goose](goose/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Hermes Agent](hermes/README.md) | See README | See README | Not recorded | Example |
| [Kilo Code](kilocode/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Mistral Vibe](mistral-vibe/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [OpenCode](opencode/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [OpenHands](openhands/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Pi](pi/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Qwen Code](qwen-code/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Roo Code](roo-code/README.md) | Static Tests | Not available | 2026-09-26 | Example |
| [Windsurf](windsurf/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |

### General-purpose agents

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [OpenClaw](openclaw/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |

### Agent frameworks

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [Agno](agno/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [AutoGen](autogen/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [CAMEL](camel/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [CrewAI](crewai/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [DSPy](dspy/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Google ADK](google-adk/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Haystack](haystack/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [LangChain](langchain/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [LangChain4j](langchain4j/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [LangGraph](langgraph/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [LlamaIndex](llamaindex/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Mastra](mastra/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [OpenAI Agents](openai-agents/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Pydantic AI](pydantic-ai/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Semantic Kernel](semantic-kernel/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [smolagents](smolagents/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Strands Agents](strands/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Vercel AI SDK](vercel-ai/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |

### Gateways

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [Agent Router](agent-router/README.md) | End-to-end testing | End-to-end testing | 2026-10-06 | Example |
| [Bifrost](bifrost/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Cloudflare AI Gateway](cloudflare-ai/README.md) | Static Tests | Not available | 2026-09-26 | Example |
| [Helicone](helicone/README.md) | End-to-end testing | Not available | 2026-09-26 | Example |
| [Kong AI Proxy](kong-ai/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [LiteLLM proxy](litellm/README.md) | End-to-end testing | End-to-end testing | 2026-10-01 | Example |
| [OpenRouter](openrouter/README.md) | Static Tests | Not available | 2026-09-26 | Example |
| [Portkey](portkey/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |

### Model libraries

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [Anthropic Messages](anthropic/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Cohere V2](cohere/README.md) | End-to-end testing | End-to-end testing | 2026-09-26 | Example |
| [Google Gen AI](google-genai/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Groq](groq/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Hugging Face Inference](huggingface-inference/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Mistral AI](mistralai/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [Ollama](ollama/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |
| [OpenAI Responses and Chat Completions](openai/README.md) | Static Tests | Static Tests | 2026-09-26 | Example |

### Compliance APIs

| Integration | Observe | Block tools | Last tested | Support |
| --- | --- | --- | --- | --- |
| [Claude Compliance API](claude-compliance/README.md) | Static Tests | Not available | 2026-09-26 | Example |

### Observability and SIEM

| Integration | Export | Last tested | Support |
| --- | --- | --- | --- |
| [Google Security Operations](google-security-operations/README.md) | Static Tests | 2026-09-26 | Example |
| [Microsoft Sentinel](microsoft-sentinel/README.md) | Static Tests | 2026-09-26 | Example |
| [OpenTelemetry](opentelemetry/README.md) | Static Tests | 2026-09-26 | Example |
| [Splunk](splunk/README.md) | Static Tests | 2026-09-26 | Example |

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
