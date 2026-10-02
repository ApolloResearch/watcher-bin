"""Run installed OpenHands LocalConversation through the real Watcher test relay.

Only external model inference is replaced. Native ActionEvent scheduling,
EnforcementRecorder callbacks, blocked-action handling and the file executor run
unchanged. Keep raw events, native messages, normalized history and physical file
evidence separately; the parent's policy case determines expected execution.
"""

import asyncio
import json
import os
import traceback
from pathlib import Path

from _test_support.readback import wait_for_conversation
from litellm.types.utils import ModelResponse
from openhands.sdk import Action, Agent, Observation, ToolDefinition
from openhands.sdk.conversation import LocalConversation
from openhands.sdk.event import ActionEvent
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
from openhands.sdk.tool import Tool, ToolExecutor, register_tool
from watcher_openhands.integration import convert, send
from watcher_openhands.synchronous import EnforcementRecorder

from watcher_sdk import AsyncWatcherClient

ROOT = Path("/evidence")


class WriteAction(Action):
    """Native fixture action with explicit path and content for policy comparison."""

    path: str
    content: str


class WriteObservation(Observation):
    """Native tool result created only after the executor writes the file."""

    @property
    def to_llm_content(self):
        return [TextContent(text="File written")]


class WriteExecutor(ToolExecutor[WriteAction, WriteObservation]):
    """Perform the physical side effect that the parent inspects independently."""

    def __call__(self, action, conversation=None):
        Path(action.path).write_text(action.content)
        with (ROOT / "file-effects.jsonl").open("a") as output:
            output.write(json.dumps({"path": action.path, "content": action.content}) + "\n")
        return WriteObservation()


class WriteTool(ToolDefinition[WriteAction, WriteObservation]):
    """Register the real executor with OpenHands's native tool dispatcher."""

    @classmethod
    def create(cls, conv_state):
        return [
            cls(
                description="Write a local fixture marker",
                action_type=WriteAction,
                observation_type=WriteObservation,
                executor=WriteExecutor(),
            )
        ]


class FixtureLLM(LLM):
    """Propose native writes, then acknowledge their actual results or refusals."""

    target: str = ""
    written_text: str = ""
    final_text: str = ""
    call_id: str = ""
    second_target: str = ""
    second_call_id: str = ""
    second_written_text: str = ""

    def completion(
        self,
        messages,
        tools=None,
        add_security_risk_prediction=False,
        on_token=None,
        call_context=None,
        **kwargs,
    ):
        message = Message(role="assistant", content=[TextContent(text=self.final_text)])
        if not any(item.role == "tool" for item in messages):
            calls = [
                MessageToolCall(
                    id=self.call_id,
                    name=WriteTool.name,
                    arguments=json.dumps({"path": self.target, "content": self.written_text}),
                    origin="completion",
                )
            ]
            if self.second_target:
                calls.append(
                    MessageToolCall(
                        id=self.second_call_id,
                        name=WriteTool.name,
                        arguments=json.dumps({"path": self.second_target, "content": self.second_written_text}),
                        origin="completion",
                    )
                )
            message = Message(role="assistant", content=[], tool_calls=calls)
        return LLMResponse(
            message=message,
            metrics=MetricsSnapshot(
                model_name="fixture",
                accumulated_cost=0,
                max_budget_per_task=0,
                accumulated_token_usage=TokenUsage(model="fixture"),
            ),
            raw_response=ModelResponse(id="fixture", choices=[]),
        )


def watcher_client() -> AsyncWatcherClient:
    """Use a fresh public SDK client for each synchronous native action callback."""
    return AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0)


async def record_and_read(session_id: str, transcript: list[dict], pending: list[dict]) -> None:
    """Store native completion history without regrading already applied decisions."""
    async with watcher_client() as client:
        await send(client, session_id, transcript, record_only=True)
        await wait_for_conversation(
            client,
            external_ids={"other": ["openhands:" + session_id]},
            final_text=None,
            expected_messages=transcript,
            decision_ids={item["call_id"] for item in pending},
            evidence=ROOT,
            timeout=30,
        )


def main() -> None:
    """Require native action events and actual file contents before checking storage."""
    config = json.loads((ROOT / "input.json").read_text())
    workspace = ROOT / "workspace"
    workspace.mkdir()
    mixed = config.get("mixed_decisions", False)
    marker = workspace / ("denied-marker.txt" if mixed else "marker.txt")
    second = workspace / "allowed-marker.txt"
    assert not second.exists()
    assert not marker.exists()
    (ROOT / "file-before.json").write_text(json.dumps({"path": str(marker), "content": None}))
    register_tool(WriteTool.name, WriteTool)
    assert WriteTool.name == config["tool_name"]
    recorder = EnforcementRecorder(watcher_client)
    pending = []

    def capture_event(event):
        with (ROOT / "native-events.jsonl").open("a") as output:
            output.write(event.model_dump_json() + "\n")
        if isinstance(event, ActionEvent) and event.action is not None:
            pending.append(
                {
                    "call_id": event.tool_call_id,
                    "name": event.tool_call.name,
                    "arguments": json.loads(event.tool_call.arguments),
                }
            )
            (ROOT / "native-pending.json").write_text(json.dumps(pending, indent=2))

    conversation = LocalConversation(
        agent=Agent(
            llm=FixtureLLM(
                model="openai/gpt-4o",
                usage_id="fixture",
                target=str(marker),
                written_text=config["written_text"],
                final_text=config["final_text"],
                call_id=config["call_id"],
                second_target=str(second) if mixed else "",
                second_call_id=config["second_call_id"] if mixed else "",
                second_written_text=config["second_written_text"] if mixed else "",
            ),
            tools=[Tool(name=WriteTool.name)],
        ),
        workspace=str(workspace),
        callbacks=[capture_event, recorder],
        visualizer=None,
        profile_store_dir=workspace / "profiles",
    )
    recorder.bind(conversation)
    session_id = str(conversation.id)
    (ROOT / "native-conversation.json").write_text(json.dumps({"id": session_id}))
    failure = None
    try:
        conversation.send_message("Write a fixture marker and finish: " + config["token"])
        conversation.run()
    except Exception as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        (ROOT / "file-after.json").write_text(
            json.dumps(
                {
                    "path": str(marker),
                    "content": marker.read_text() if marker.exists() else None,
                }
            )
        )
        if mixed:
            (ROOT / "mixed-files-after.json").write_text(
                json.dumps(
                    {str(path): path.read_text() if path.exists() else None for path in (marker, second)}, indent=2
                )
            )
        (ROOT / "native-source.json").write_text(json.dumps(recorder.messages, indent=2))
        (ROOT / "native-error.json").write_text(json.dumps(failure, indent=2))
    assert failure is None, failure
    assert marker.exists() is config["executes"]
    if config["executes"]:
        assert marker.read_text() == config["written_text"]
    expected_pending = [
        {
            "call_id": config["call_id"],
            "name": config["tool_name"],
            "arguments": {"path": str(marker), "content": config["written_text"]},
        }
    ]
    if mixed:
        assert not marker.exists() and second.read_text() == config["second_written_text"]
        expected_pending.append(
            {
                "call_id": config["second_call_id"],
                "name": config["tool_name"],
                "arguments": {"path": str(second), "content": config["second_written_text"]},
            }
        )
        effects = [json.loads(line) for line in (ROOT / "file-effects.jsonl").read_text().splitlines()]
        assert effects == [{"path": str(second), "content": config["second_written_text"]}]
    assert pending == expected_pending
    transcript = convert(recorder.messages)
    assert all(any(item.get("tool_call_id") == call["call_id"] for item in transcript) for call in pending)
    expected_final = [{"type": "text", "text": config["final_text"]}]
    assert recorder.messages[-1]["content"] == expected_final
    assert transcript[-1] == {"role": "assistant", "content": expected_final}
    (ROOT / "native-transcript.json").write_text(json.dumps(transcript, indent=2))
    asyncio.run(record_and_read(session_id, transcript, pending))


if __name__ == "__main__":
    main()
