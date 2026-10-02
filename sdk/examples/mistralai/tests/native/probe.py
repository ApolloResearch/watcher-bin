"""Drive an installed provider client through a loopback model and a real Watcher API.

Run in a network-isolated fixture with WATCHER_URL pointing to its local relay.
Native provider requests, stored transcripts and actual callback effects are
retained separately. The model is scripted; this measures integration behavior.
"""

import argparse
import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import os
import threading
import zipfile
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from watcher_sdk import AsyncWatcherClient, TrajectoryView


def visible_text(content):
    """Read text from Inspect's public string or content-block representation."""
    if isinstance(content, str):
        return content
    return "".join(part["text"] for part in content or [] if isinstance(part, dict) and part.get("type") == "text")


def verify_installation(evidence):
    """Match installed runtime files to pinned wheels before either endpoint is called."""
    receipt_path = Path("/opt/provider-provenance.json")
    receipt = json.loads(receipt_path.read_text())
    for item in receipt["wheels"]:
        wheel = Path(item["path"])
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == item["sha256"]
        installed = importlib.metadata.distribution(item["distribution"])
        origin = json.loads(installed.read_text("direct_url.json") or "{}")
        assert not origin.get("dir_info", {}).get("editable", False)
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if name.endswith(".py"):
                    assert Path(str(installed.locate_file(name))).read_bytes() == archive.read(name), name
    versions = {name: importlib.metadata.version(name) for name in receipt["upstream_versions"]}
    assert versions == receipt["upstream_versions"]
    (evidence / "installed-artifacts.json").write_text(
        json.dumps(
            {
                **receipt,
                "measured_upstream_versions": versions,
                "provenance_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )
    return receipt


async def readback(watcher, session_id, case, evidence):
    """Require the exact generated identity, both tool decisions and final native turn."""
    async with asyncio.timeout(20):
        while True:
            response = await watcher.search_sessions(external_ids={"other": [session_id]}, limit=2)
            sessions = response.to_dict()
            (evidence / "sessions.json").write_text(json.dumps(sessions, indent=2))
            assert sessions["total"] <= 1
            if sessions["total"] == 1 and len(sessions["sessions"]) == 1:
                row = sessions["sessions"][0]
                if row["latest_trajectory_id"]:
                    view = await watcher.get_trajectory(
                        row["session_id"], row["latest_trajectory_id"], view=TrajectoryView.EXTENDED
                    )
                    stored = view.to_dict()
                    (evidence / "trajectory.json").write_text(json.dumps(stored, indent=2))
                    ids = set(case["tool_ids"]) if case["mode"] != "paused" else set()
                    texts = [
                        visible_text(item.get("content")) for item in stored["messages"] if item["role"] == "assistant"
                    ]
                    target = case["final_text"] if case["executes"] else "Pending provider " + case["token"]
                    results = {item["tool_call_id"] for item in stored["messages"] if item["role"] == "tool"}
                    if (
                        target in texts
                        and ids <= stored["tool_call_decisions"].keys()
                        and (not case["executes"] or results == set(case["tool_ids"]))
                    ):
                        return
            await asyncio.sleep(0.05)


async def run(args):
    evidence = args.evidence
    evidence.mkdir(parents=True, exist_ok=True)
    case = json.loads(args.case.read_text())
    receipt = verify_installation(evidence)
    slug = receipt["slug"]
    assert slug == case["slug"]
    assert sorted(os.listdir("/sys/class/net")) == ["lo"]
    package = "watcher_" + slug.replace("-", "_")
    integration = importlib.import_module(package + ".integration")
    assert integration.__file__ is not None
    assert Path(integration.__file__).is_relative_to("/usr/local/lib")
    requests, responses = [], []
    session_id = slug + ":" + str(uuid4())
    native_calls: list[dict] = [
        {"id": identifier, "type": "function", "function": {"name": "weather", "arguments": json.dumps({"city": city})}}
        for identifier, city in zip(case["tool_ids"], ["Paris", "Tokyo"], strict=True)
    ]
    pending = "Pending provider " + case["token"]

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append({"url": self.path, "body": body, "user_agent": self.headers.get("user-agent")})
            if slug == "openai":
                assert self.path == "/v1/responses"
                final = any(item.get("type") == "function_call_output" for item in body["input"])
                output = (
                    [
                        {
                            "type": "message",
                            "id": "msg-final",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": case["final_text"], "annotations": []}],
                        }
                    ]
                    if final
                    else [
                        {
                            "type": "message",
                            "id": "msg-pending",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": pending, "annotations": []}],
                        },
                        *[
                            {
                                "type": "function_call",
                                "id": "item-" + call["id"],
                                "call_id": call["id"],
                                "name": "weather",
                                "arguments": call["function"]["arguments"],
                                "status": "completed",
                            }
                            for call in native_calls
                        ],
                    ]
                )
                response = {
                    "id": "response-fixture",
                    "object": "response",
                    "created_at": 1,
                    "model": "fixture-model",
                    "status": "completed",
                    "output": output,
                    "parallel_tool_calls": True,
                }
            elif slug == "anthropic":
                assert self.path == "/v1/messages"
                final = any(
                    any(
                        isinstance(block, dict) and block.get("type") == "tool_result"
                        for block in item.get("content", [])
                        if isinstance(item.get("content"), list)
                    )
                    for item in body["messages"]
                )
                content = [{"type": "text", "text": case["final_text"] if final else pending}]
                if not final:
                    content.extend(
                        {
                            "type": "tool_use",
                            "id": call["id"],
                            "name": "weather",
                            "input": json.loads(call["function"]["arguments"]),
                        }
                        for call in native_calls
                    )
                response = {
                    "id": "message-fixture",
                    "type": "message",
                    "role": "assistant",
                    "model": "fixture-model",
                    "content": content,
                    "stop_reason": "end_turn" if final else "tool_use",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 3, "output_tokens": 2},
                }
            else:
                assert self.path == "/v1/chat/completions"
                final = any(item["role"] == "tool" for item in body["messages"])
                message = {
                    "role": "assistant",
                    "content": [{"type": "text", "text": case["final_text"] if final else pending}],
                }
                if not final:
                    message["tool_calls"] = deepcopy(native_calls)
                response = {
                    "id": "chat-fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "fixture-model",
                    "system_fingerprint": "fixture",
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
                    "choices": [{"index": 0, "message": message, "finish_reason": "stop" if final else "tool_calls"}],
                }
            responses.append(response)
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    async def weather(*, city):
        value = {"city": city, "token": case["token"]}
        with (evidence / "side-effects.jsonl").open("a") as stream:
            stream.write(json.dumps(value) + "\n")
        return value

    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "description": "Local fixture",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
            },
        }
    ]
    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    history = [{"role": "user", "content": "Read two cities " + case["token"]}]
    if slug == "openai":
        provider_context = importlib.import_module("openai").AsyncOpenAI(
            api_key="fixture-key", base_url=base + "/v1", max_retries=0
        )
    elif slug == "anthropic":
        provider_context = importlib.import_module("anthropic").AsyncAnthropic(
            api_key="fixture-key", base_url=base, max_retries=0
        )
    else:
        if slug == "huggingface-inference":
            integration.configure_http_client_factory(
                lambda: importlib.import_module("httpx").AsyncClient(trust_env=False)
            )
        provider_context = integration.make_client("fixture-key", base if slug == "mistralai" else base + "/v1")
    error = None
    try:
        async with (
            provider_context as provider,
            AsyncWatcherClient(os.environ["WATCHER_URL"], api_key="fixture-key") as watcher,
        ):
            try:
                if slug == "openai":
                    request = {
                        "model": "fixture-model",
                        "input": history,
                        "tools": [{"type": "function", **tools[0]["function"]}],
                    }
                    first = await integration.complete(provider, watcher, request, session_id)
                    history.extend(item.model_dump(mode="json", exclude_none=True) for item in first.output)
                    for item in first.output:
                        if item.type == "function_call":
                            history.append(
                                {
                                    "type": "function_call_output",
                                    "call_id": item.call_id,
                                    "output": json.dumps(await weather(**json.loads(item.arguments))),
                                }
                            )
                    await integration.complete(provider, watcher, request, session_id)
                elif slug == "anthropic":
                    request = {
                        "model": "fixture-model",
                        "max_tokens": 256,
                        "messages": history,
                        "tools": [
                            {
                                "name": "weather",
                                "description": "Local fixture",
                                "input_schema": tools[0]["function"]["parameters"],
                            }
                        ],
                    }
                    first = await integration.complete(provider, watcher, request, session_id)
                    blocks = [item.model_dump(mode="json", exclude_none=True) for item in first.content]
                    history.append({"role": "assistant", "content": blocks})
                    results = []
                    for item in blocks:
                        if item["type"] == "tool_use":
                            results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": item["id"],
                                    "content": json.dumps(await weather(**item["input"])),
                                }
                            )
                    history.append({"role": "user", "content": results})
                    await integration.complete(provider, watcher, request, session_id)
                else:
                    monitoring = importlib.import_module(package + ".monitoring")
                    monitor = monitoring.Monitor(watcher, session_id, timeout=90)
                    history = await monitoring.run_turn(
                        provider,
                        monitor,
                        model="fixture-model",
                        messages=history,
                        tools=tools,
                        functions={"weather": weather},
                    )
                    history = await monitoring.run_turn(
                        provider,
                        monitor,
                        model="fixture-model",
                        messages=history,
                        tools=tools,
                        functions={"weather": weather},
                    )
                assert case["executes"], "A blocked response reached application dispatch"
            except PermissionError as failure:
                error = type(failure).__name__
                assert not case["executes"], repr(failure)
            await readback(watcher, session_id, case, evidence)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        (evidence / "provider-requests.json").write_text(json.dumps(requests, indent=2))
        (evidence / "provider-responses.json").write_text(json.dumps(responses, indent=2))
        (evidence / "native-history.json").write_text(json.dumps(history, indent=2))
        (evidence / "native-result.json").write_text(
            json.dumps({"session_id": session_id, "error": error, "slug": slug}, indent=2)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
