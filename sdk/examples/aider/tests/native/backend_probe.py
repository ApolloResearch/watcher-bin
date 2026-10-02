"""Run the installed Aider whole-file editor against the real Watcher test relay.

The parent supplies /evidence/input.json and WATCHER_URL inside a network-disabled
container. A deterministic model response replaces only external model inference;
Coder parsing, EnforcedIO, the native file write and public SDK calls are real.
Retain the complete Capture separately from the normalized Watcher transcript.
"""

import asyncio
import json
import os
import traceback
from pathlib import Path

from _test_support.readback import wait_for_conversation
from aider.coders import Coder
from watcher_aider.observation import (
    Capture,
    ObservedModel,
    archive_messages,
    run_prompt,
    send_capture,
)
from watcher_aider.synchronous import EnforcedIO

from watcher_sdk import AsyncWatcherClient

ROOT = Path("/evidence")


def watcher_client() -> AsyncWatcherClient:
    """Give each synchronous IO callback its own public SDK client and event loop."""
    return AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key", max_retries=0)


async def record_and_read(capture: Capture, config: dict, pending: list[dict]) -> None:
    """Record the actual completed journal without replacing pre-write judgments."""
    transcript = archive_messages(capture)
    (ROOT / "native-transcript.json").write_text(json.dumps(transcript, indent=2))
    async with watcher_client() as client:
        await send_capture(client, config["conversation_id"], capture, record_only=True)
        await wait_for_conversation(
            client,
            external_ids={"other": ["aider:" + config["conversation_id"]]},
            final_text=config["final_text"],
            expected_messages=transcript,
            decision_ids={item["call_id"] for item in pending},
            evidence=ROOT,
            timeout=30,
        )


def main() -> None:
    """Keep filesystem evidence independent of Watcher's returned policy decision."""
    config = json.loads((ROOT / "input.json").read_text())
    workspace = ROOT / "workspace"
    workspace.mkdir()
    os.chdir(workspace)
    target = workspace / "greeting.txt"
    target.write_text(config["before_text"])
    (ROOT / "file-before.json").write_text(json.dumps({"path": str(target), "content": target.read_text()}))
    capture = Capture()
    model = ObservedModel("gpt-4o", capture)
    model.extra_params = {"mock_response": "greeting.txt\n```text\n" + config["written_text"] + "```"}
    coder = Coder.create(
        main_model=model,
        edit_format="whole",
        io=EnforcedIO(capture, config["conversation_id"], watcher_client, yes=False, pretty=False),
        fnames=[str(target)],
        use_git=False,
        stream=False,
        map_tokens=0,
        auto_lint=False,
        auto_test=False,
    )
    failure = None
    try:
        run_prompt(
            coder,
            capture,
            "Replace greeting.txt with the requested text: " + config["token"],
        )
    except Exception as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        (ROOT / "file-after.json").write_text(json.dumps({"path": str(target), "content": target.read_text()}))
        (ROOT / "native-source.json").write_text(capture.model_dump_json(indent=2))
        (ROOT / "native-error.json").write_text(json.dumps(failure, indent=2))
    expected = config["written_text"] if config["executes"] else config["before_text"]
    assert target.read_text() == expected, "Native Aider edit disagrees with the independent policy case"
    if config["executes"]:
        assert failure is None, failure
    writes = [operation for exchange in capture.exchanges for operation in exchange["writes"]]
    assert len(writes) == 1, "The native editor must attempt exactly one file operation"
    assert writes[0]["arguments"] == {
        "path": str(target),
        "content": config["written_text"],
    }
    assert writes[0]["status"] == ("completed" if config["executes"] else "withheld")
    if not config["executes"]:
        assert writes[0]["error"] == "Watcher did not confirm approval; write was withheld"
    pending = [
        {
            "call_id": writes[0]["id"],
            "name": "aider_write_file",
            "arguments": writes[0]["arguments"],
        }
    ]
    (ROOT / "native-pending.json").write_text(json.dumps(pending, indent=2))
    model.extra_params = {"mock_response": config["final_text"]}
    run_prompt(coder, capture, "Report completion without editing any files.")
    assert target.read_text() == expected
    (ROOT / "native-source.json").write_text(capture.model_dump_json(indent=2))
    asyncio.run(record_and_read(capture, config, pending))


if __name__ == "__main__":
    main()
