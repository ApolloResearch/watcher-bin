# LangChain4j with Watcher

Connect LangChain4j's native AI Services tool loop to Watcher through a small
Python SDK bridge. Register `Guard` with `AiServices.beforeToolExecution` to
apply the server's enforce, observe or paused policy before each native tool.
An optional application callback can obtain and record a human approval.

## Install

Use Java 17 or later, Maven, and Python 3.12. From this directory:

```bash
uv sync --project packages/python --frozen --python 3.12
mvn -f packages/java/pom.xml package dependency:copy-dependencies
export WATCHER_PYTHON="$PWD/packages/python/.venv/bin/python"
export WATCHER_JAVA_CLASSPATH="packages/java/target/*:packages/java/target/dependency/*"
export WATCHER_BASE_URL="https://your-watcher-server/api"
export WATCHER_API_KEY="your-watcher-key"
export WATCHER_SESSION_ID="your-unique-conversation-id"
```

Use a Watcher key with `sessions:ingest` to store transcripts. Human-decision
reporting also needs session-read access and authority to update the session as
its owner or with `sessions:write:any`.
For a service API key, configure `sessions:ingest`, `sessions:findings:read:any`,
`sessions:content:read:any` and `sessions:write:any` for transcript recording and human-decision reporting.

## Connect an application

Create a `ChatMemory` and `Guard` for each conversation, then register them with
the same native AI Service:

```java
import com.example.watcher.examples.langchain4j.WatcherMonitoredExample;

var memory = MessageWindowChatMemory.withMaxMessages(1000);
var guard = new WatcherMonitoredExample.Guard(watcherPython, memory, null);
var assistant = AiServices.builder(Assistant.class)
    .chatModel(yourChatModel)
    .chatMemory(memory)
    .tools(yourToolExecutors)
    .beforeToolExecution(guard)
    .build();

assistant.chat(userMessage);
guard.record();
```

Use `dev.langchain4j.service.AiServices` and
`dev.langchain4j.memory.chat.MessageWindowChatMemory`. `Assistant` is your
AI Service interface; `WatcherMonitoredExample.Assistant` is the minimal example.
`yourToolExecutors` is a map from `ToolSpecification` to `ToolExecutor`.
The complete runnable configuration is in `WatcherMonitoredExample.java`.

The native runner supplies the original `ToolExecutionRequest`. Its ID, name and
JSON arguments must match retained memory before the SDK gate can allow it. The
guard waits for the gate process; it never matches calls by argument equality or
invocation order. LangChain4j retains actual results and the final model answer.
Call `guard.record()` after each successful turn to submit that history.

The example runs synchronous, non-streaming AI Services. Previous tools can
already have completed when a later tool is refused; they are not rolled back.
Do not retry a tool to repair a failed transcript submission.

## Policy and human approval

The default inherits Watcher's settings. Applied allow resumes native execution;
deny stops it. Deferred responses in observe or paused mode preserve normal host
permissions. A Watcher network failure or invalid response stops execution. The
server's configured grading-failure policy can produce an applied allow.

With no `HumanApproval` callback, escalation stops unattended execution. To
connect an approval UI, provide `HumanApproval` as the third `Guard` constructor
argument. It receives the original native request and retained history and must
return an authorized human choice. The SDK bridge uploads that choice and confirms
the stored human choice and tool status before releasing an approval, preserving
the original evaluation and grades. Reporting failure blocks
execution. The example includes no approval UI or durable pending-call storage.

## Run a conversation

Configure a provider key and invoke the native example with its provider URL,
tool effect file and transcript output directory:

```bash
export PROVIDER_API_KEY="your-provider-key"
export PROVIDER_MODEL="your-model-name"
demo/enforce.sh https://your-provider/v1 ./effects.txt ./snapshots
```

The native weather tool writes the requested cities to `effects.txt`. The final
history goes to `snapshots/final.json` and Watcher under
`other=$WATCHER_SESSION_ID`. The same command observes without blocking when the
server is configured for observe mode.

For completed-history ingestion, `demo/observe.sh PROVIDER_URL SNAPSHOT_DIRECTORY`
runs a native conversation and writes response snapshots. Submit those snapshots
with `SNAPSHOT_DIR=SNAPSHOT_DIRECTORY "$WATCHER_PYTHON" -m watcher_langchain4j_bridge.bridge`. The observer inherits server policy. Its decisions are advisory because the
operations already happened; it cannot prevent tool side effects. Paused bypasses
and grading-failure fallbacks are not reported as completed judgments.

In Enforce mode, Watcher can store a retrospective assessment as an applied
denial and count it in automatic-denial totals after the tool has run. Those
records describe the assessment; they do not show that execution was prevented.

Hook success acknowledges the request, not durable storage. Confirm stored
sessions, trajectories and decisions through the public SDK when needed.

## Tests and package layout

```bash
tests/native/run.sh
```

The recipe builds the Java JAR and Python wheel, installs them outside the source
tree, and runs the actual JVM against local provider and Watcher HTTP fixtures
with external networking disabled. Its Linux isolation helper requires `sudo`.
It verifies native tool effects, pending decisions, refusal paths, policy
inheritance, human approval/refusal and human-report failure. It does not prove
hosted-provider or deployed Watcher behavior. Verified environments and versions
are recorded separately in `metadata.yaml`.

Prepare the installed image for Watcher API/database verification with:

```sh
bash tests/native/build.sh
```

This recipe requires Linux x86_64, Python 3.12+, uv, Docker and package-registry
access. It accepts `WATCHER_SDK_WHEEL` and `WATCHER_EXAMPLE_RUN_DIR`, creates a fresh
output directory, and writes `image.id`, package checksums and source-comparison
receipts there. It prepares artifacts without starting an agent; the Watcher
backend runner launches the image separately with networking disabled.

The build uses checksum-verified JDK 17.0.20.1 and Maven 3.9.11 archives.
`tests/native/java-dependencies.json` pins the fixture runtime JAR checksums.

`packages/java/` contains the native integration and its Maven manifest;
`packages/python/` contains the SDK bridge and Python manifest; `tests/` holds
conversion and native-runtime checks. The Java JAR and Python wheel are separate
artifacts suitable for packaging in your application.

Only finalized text and function tools are supported. Retain complete history
and unique original tool IDs; context truncation can make a transcript invalid.
Provider-hosted tools, streaming AI Services and durable approval resume are
outside this example. Its in-memory ID checks do not provide exactly-once tool
execution across application restarts.
