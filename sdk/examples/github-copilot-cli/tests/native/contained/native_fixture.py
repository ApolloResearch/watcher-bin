"""Exercise a native harness against local model and Watcher endpoints only."""

import fcntl
import json
import os
import pty
import select
import shutil
import struct
import subprocess
import sys
import termios
import threading
import time
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from backend_forward import expects_execution, forward, forward_get
from readback_fixture import login_configuration

SLUG = Path("slug.txt").read_text().strip()
SCENARIO = os.environ["WATCHER_EXAMPLE_SCENARIO"]
EVIDENCE = Path("/evidence")
ROOT = Path("/tmp/workspace")
ROOT.mkdir()
MARKER = ROOT / "executed.txt"
REWRITTEN = ROOT / "rewritten.txt"
SECOND_MARKER = ROOT / "second-turn.txt"
watcher_requests = []
readback_requests = []
provider_requests = []
FIXTURE_SESSION = "65dc89f8-e94d-4f54-8503-cb218d015a18"
errors = []
pending = threading.Event()
release = threading.Event()


class Handler(BaseHTTPRequestHandler):
    """Return deterministic judgments and one tool request followed by a final answer."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def reply(self, payload: object) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def stored_messages(self) -> list:
        """The latest recording snapshot, which is what Watcher would return on readback."""
        snapshots = [r["body"]["messages"] for r in watcher_requests if r["body"].get("input") == []]
        return snapshots[-1] if snapshots else []

    def do_GET(self):
        if "/trajectories/" in self.path:
            readback_requests.append(self.path)
            if os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
                forward_get(self)
                return
            self.reply(
                {
                    "trajectory_id": "fixture-trajectory",
                    "session_id": FIXTURE_SESSION,
                    "source": "watcher-hook",
                    "messages": self.stored_messages(),
                    "grades": [],
                    "metadata": {},
                    "created_at": "2026-09-29T12:00:00Z",
                }
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(
            json.dumps(
                {"object": "list", "data": [{"id": "fixture", "object": "model", "owned_by": "fixture"}]}
            ).encode()
        )

    def do_POST(self):
        try:
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            self.respond(json.loads(raw), raw)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
            self.send_error(500)

    def respond(self, body, raw):
        if "/sessions/search" in self.path:
            # The recorders confirm storage by reading the session back.
            readback_requests.append(self.path)
            if os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
                forward(self, body, raw, MARKER)
                return
            stored = self.stored_messages()
            sessions = (
                [
                    {
                        "session_id": FIXTURE_SESSION,
                        "agent_platform": "other",
                        "trajectory_count": 1,
                        "message_count": len(stored),
                        "started_at": "2026-09-29T12:00:00Z",
                        "ended_at": "2026-09-29T12:00:01Z",
                        "latest_trajectory_id": "fixture-trajectory",
                    }
                ]
                if stored
                else []
            )
            self.reply({"sessions": sessions, "total": len(sessions), "limit": 2, "offset": 0})
            return
        if "/hooks/pre-tool-use" in self.path:
            watcher_requests.append({"path": self.path, "body": body})
            if os.environ.get("WATCHER_EXAMPLE_FORWARD_URL"):
                forward(self, body, raw, MARKER)
                return
            inputs = body.get("input")
            # The gate sends one input object; recording snapshots send input=[].
            is_gate = isinstance(inputs, dict)
            if is_gate:
                target = SECOND_MARKER if "second-turn.txt" in json.dumps(inputs) else MARKER
                # The deliberately short native timeout can expire during hook
                # startup, before this request arrives, as well as while waiting.
                if SCENARIO != "outer-timeout":
                    assert not target.exists()
                if SCENARIO == "pending":
                    pending.set()
                    assert release.wait(40)
                if SCENARIO in {"timeout", "outer-timeout"}:
                    time.sleep(5)
            if is_gate and SCENARIO == "http-error":
                self.send_response(503)
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"unavailable"}}')
                return
            decision = SCENARIO if SCENARIO in {"deny", "escalate", "deferred"} else "allow"
            if SCENARIO == "pending":
                decision = "deny"
            mode = "paused" if SCENARIO == "paused" else "enforce"
            if not is_gate:
                decision = "deferred"
                mode = "observe"
            values = inputs if isinstance(inputs, list) else [inputs] if inputs else []
            outcomes = [
                {
                    "tool_use_id": "incorrect" if is_gate and SCENARIO == "identity-error" else call.get("tool_use_id"),
                    "decision": decision,
                    "judged_decision": "allow" if decision == "deferred" else decision,
                    "enforcement_mode": mode,
                    "decision_source": "rule",
                    "verdict": {},
                    "latency_ms": 1,
                }
                for call in values
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    []
                    if is_gate and SCENARIO == "missing-outcome"
                    else outcomes
                    if isinstance(inputs, list) or inputs is None
                    else outcomes[0]
                ).encode()
            )
            return
        provider_requests.append({"path": self.path, "body": body})
        if len(provider_requests) > 8:
            raise RuntimeError("Unexpected repeated model calls")
        messages = body.get("messages", [])
        second_turn = any("Run the second fixture command" in str(m.get("content", "")) for m in messages)
        target = SECOND_MARKER if second_turn else MARKER
        current_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
        has_result = any(m.get("role") == "tool" for m in messages[current_user + 1 :])
        call_tool = not has_result
        name = "exec" if SLUG == "openclaw" else "bash"
        assert any(t.get("function", {}).get("name") == name for t in body.get("tools", [])), (
            "Native expected tool absent"
        )
        call = {
            "id": "fixture-native-second-call" if second_turn else "fixture-native-call",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps({"command": f"printf 'executed' > {target}"})},
        }
        answer = "The second fixture task is complete." if second_turn else "The fixture task is complete."
        message: dict[str, Any] = {"role": "assistant", "content": None if call_tool else answer}
        if call_tool:
            message["tool_calls"] = [call]
        finish = "tool_calls" if call_tool else "stop"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
        self.end_headers()
        if body.get("stream"):
            delta = dict(message)
            if call_tool:
                delta["tool_calls"] = [{"index": 0, **call}]
            chunks = [
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                },
                {
                    "id": "chatcmpl-fixture",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "fixture",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            ]
            self.wfile.write(
                ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n").encode()
            )
        else:
            self.wfile.write(
                json.dumps(
                    {
                        "id": "chatcmpl-fixture",
                        "object": "chat.completion",
                        "created": 1,
                        "model": "fixture",
                        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    }
                ).encode()
            )


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{server.server_port}"
env = {
    **os.environ,
    "WATCHER_URL": url,
    "WATCHER_PYTHON": sys.executable,
    "WATCHER_TIMEOUT_SECONDS": "1" if SCENARIO == "timeout" else "60",
}
if SLUG == "github-copilot-cli":
    home = Path.home() / ".copilot"
    home.mkdir(parents=True)
    subprocess.run(["git", "init", str(ROOT)], capture_output=True, check=True)
    repository_hooks = ROOT / ".github/hooks"
    repository_hooks.mkdir(parents=True)
    # The interactive scenario grades two turns retrospectively; the enforce demo only records.
    demo = "hooks.observe.json" if SCENARIO in {"observe", "interactive"} else "hooks.enforce.json"
    configuration = json.loads((Path("demo") / demo).read_text())
    # Hooks authenticate only with the sign-in their configuration names; the demos
    # leave a placeholder for the path setup would print.
    hook_config = login_configuration(Path.home() / "watcher-config" / "config.json", ROOT, url)
    for kind, hooks in configuration["hooks"].items():
        words = hooks[0]["bash"].split()
        assert words[:2] == ["watcher-github-copilot-cli", "enforce" if kind == "preToolUse" else "observe"]
        assert words[2:4] == ["--config", "/path/printed/by/setup/config.json"], words
        words[3] = str(hook_config)
        hooks[0]["bash"] = " ".join([sys.executable, "/opt/fixture/capture_hook.py", *words[1:]])
        if kind == "preToolUse" and SCENARIO == "outer-timeout":
            hooks[0]["timeoutSec"] = 1
    (repository_hooks / "watcher.json").write_text(json.dumps(configuration))
    shutil.copyfile(repository_hooks / "watcher.json", EVIDENCE / "repository-hooks.json")
    assert not (home / "hooks").exists()
    env.update(
        COPILOT_HOME=str(home),
        COPILOT_OFFLINE="true",
        COPILOT_PROVIDER_BASE_URL=url + "/v1",
        COPILOT_PROVIDER_TYPE="openai",
        COPILOT_PROVIDER_API_KEY="fixture",
        COPILOT_MODEL="fixture",
        GITHUB_COPILOT_PROMPT_MODE_REPO_HOOKS="true",
    )
    command = [
        "copilot",
        "-i" if SCENARIO == "interactive" else "-p",
        "Run the fixture shell command, then finish.",
        "--model",
        "fixture",
        "--allow-all-tools",
        "--allow-all-paths",
        "--disable-builtin-mcps",
        "--no-auto-update",
        "--log-level",
        "debug",
        "--log-dir",
        str(EVIDENCE / "copilot-logs"),
    ]
    if SCENARIO == "interactive":
        env.update(COPILOT_ALLOW_ALL="true", TERM="xterm-256color")
        command.extend(["--screen-reader", "--no-color"])
else:
    state = Path("/tmp/openclaw-state")
    state.mkdir()
    config = {
        "agents": {"defaults": {"workspace": str(ROOT), "model": {"primary": "fixture/fixture"}}},
        "models": {
            "providers": {
                "fixture": {
                    "baseUrl": url + "/v1",
                    "api": "openai-completions",
                    "apiKey": "fixture",
                    "models": [
                        {
                            "id": "fixture",
                            "name": "Fixture",
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": 128000,
                            "maxTokens": 4096,
                        }
                    ],
                }
            }
        },
        "plugins": {
            "allow": ["watcher-openclaw-example"],
            "load": {"paths": ["/opt/fixture/adapter"]},
            "entries": {
                "watcher-openclaw-example": {
                    "enabled": True,
                    "config": {"mode": "observe" if SCENARIO == "observe" else "enforce"},
                    "hooks": {"allowConversationAccess": SCENARIO != "no-context-access"},
                }
            },
        },
        "tools": {
            "profile": "coding",
            "exec": {"host": "gateway", "security": "full", "ask": "off"},
            "codeMode": {"enabled": False},
        },
    }
    if SCENARIO == "rewrite":
        rewrite = Path("/tmp/rewriter.mjs")
        rewrite.write_text(
            'export default function(api) { api.on("before_tool_call", e => ({params:{...e.params, command:"printf rewritten > /tmp/workspace/rewritten.txt"}}), {priority:-100}); }'
        )
        config["plugins"]["load"]["paths"].append(str(rewrite))
        config["plugins"]["allow"].append("rewriter")
    config_path = Path("/tmp/openclaw.json")
    config_path.write_text(json.dumps(config))
    env.update(OPENCLAW_STATE_DIR=str(state), OPENCLAW_CONFIG_PATH=str(config_path))
    command = [
        "openclaw",
        "agent",
        "exec",
        "Run the fixture shell command, then finish.",
        "--config",
        str(config_path),
        "--cwd",
        str(ROOT),
        "--state-dir",
        str(state),
        "--json",
        "--model",
        "fixture/fixture",
        "--code-mode",
        "direct",
    ]
(EVIDENCE / "command.json").write_text(json.dumps(command, indent=2))
if SCENARIO == "pending":

    def hold():
        if not pending.wait(120):
            return
        receipt = {"marker_before_release": MARKER.exists(), "model_requests_before_release": len(provider_requests)}
        (EVIDENCE / "pending.json").write_text(json.dumps(receipt))
        release.set()

    threading.Thread(target=hold, daemon=True).start()


def run_interactive():
    """Drive two real TTY turns, waiting for completed native observation each time."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    output = bytearray()
    deadline = time.monotonic() + 160

    def drain():
        if select.select([master], [], [], 0.05)[0]:
            with suppress(OSError):
                output.extend(os.read(master, 65536))
                (EVIDENCE / "interactive-terminal.txt").write_bytes(output)

    def wait_turn(count):
        while time.monotonic() < deadline:
            drain()
            receipts = list((EVIDENCE / "hook-inputs").glob("observe-*.receipt"))
            if len(receipts) >= count:
                assert all(json.loads(path.read_text())["returncode"] == 0 for path in receipts)
                time.sleep(0.3)
                return
            assert process.poll() is None, "Interactive Copilot exited before observation"
        raise TimeoutError("Interactive agentStop did not complete")

    try:
        wait_turn(1)
        os.write(master, b"Run the second fixture command, then finish.")
        time.sleep(0.3)
        os.write(master, b"\r")
        wait_turn(2)
        os.write(master, b"/exit")
        time.sleep(0.3)
        os.write(master, b"\r")
        while process.poll() is None and time.monotonic() < deadline:
            drain()
        assert process.poll() is not None, "Interactive Copilot did not exit"
        return subprocess.CompletedProcess(command, process.returncode, output.decode(errors="replace"), "")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        (EVIDENCE / "interactive-terminal.txt").write_bytes(output)
        os.close(master)


try:
    result = (
        run_interactive()
        if SCENARIO == "interactive"
        else subprocess.run(
            command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180
        )
    )
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    summary = {
        "slug": SLUG,
        "scenario": SCENARIO,
        "returncode": result.returncode,
        "model_requests": len(provider_requests),
        "watcher_requests": len(watcher_requests),
        "marker": MARKER.exists(),
        "marker_content": MARKER.read_text() if MARKER.exists() else None,
        "actual_backend": bool(os.environ.get("WATCHER_EXAMPLE_FORWARD_URL")),
        "rewritten_marker": REWRITTEN.exists(),
        "fixture_errors": errors,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    if SLUG == "github-copilot-cli":
        for path in (Path.home() / ".copilot/session-state").glob("*/events.jsonl"):
            shutil.copyfile(path, EVIDENCE / (path.parent.name + "-events.jsonl"))
    assert not errors, errors
    if SCENARIO == "no-context-access":
        assert not watcher_requests, "Conversation access disabled but data was sent"
        # A failed plugin load is not a guaranteed host-wide veto.
        assert "allowConversationAccess" in result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert len(provider_requests) >= 2, summary
        assert watcher_requests, summary
        expect_marker = (
            expects_execution()
            if os.environ.get("WATCHER_EXAMPLE_FORWARD_URL")
            else SCENARIO in {"observe", "allow", "outer-timeout", "interactive"}
        )
        assert MARKER.exists() == expect_marker, summary
        if SCENARIO == "rewrite":
            assert REWRITTEN.exists(), summary
        if SCENARIO == "pending":
            receipt = json.loads((EVIDENCE / "pending.json").read_text())
            assert not receipt["marker_before_release"] and receipt["model_requests_before_release"] == 1
        if SCENARIO != "outer-timeout":
            assert any(
                "The fixture task is complete." in json.dumps(r["body"].get("messages", [])) for r in watcher_requests
            ), "Final assistant text missing"
        if SCENARIO == "interactive":
            assert SECOND_MARKER.exists(), summary
            # Copilot stops sessionEnd hooks soon after an interactive exit, so the
            # final snapshot comes from a detached process that can outlive Copilot.
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and sum(r["body"].get("input") == [] for r in watcher_requests) < 3:
                time.sleep(0.2)
            snapshots = [r["body"] for r in watcher_requests if r["body"].get("input") == []]
            # One snapshot per turn, then the sessionEnd callback resends the same final history.
            assert len(snapshots) == 3, snapshots
            assert snapshots[-1]["messages"] == snapshots[-2]["messages"], snapshots
            assert "The second fixture task is complete." in json.dumps(snapshots[-1]["messages"])
            assert "The fixture task is complete." in json.dumps(snapshots[-1]["messages"])
            observations = [
                r["body"] for r in watcher_requests if isinstance(r["body"].get("input"), list) and r["body"]["input"]
            ]
            ids = [call["tool_use_id"] for request in observations for call in request["input"]]
            assert len(ids) == 2 and len(set(ids)) == 2, "Prior tool observation replayed"
            assert "The fixture task is complete." in json.dumps(observations[-1]["messages"])
            assert "The second fixture task is complete." not in json.dumps(observations[-1]["messages"])
        # A gate decision is stored on the named native call; only a call the log
        # cannot name is judged ephemerally, and the two never mix.
        gates = [r["body"] for r in watcher_requests if isinstance(r["body"].get("input"), dict)]
        for gate in gates:
            named = bool(gate["input"].get("tool_use_id"))
            assert named == (gate.get("ephemeral") is not True), gate.get("ephemeral")
            assert not named or gate.get("external_ids", {}).get("other", "").startswith("github-copilot-cli:")
        if SCENARIO == "allow" and gates:
            assert any(gate["input"].get("tool_use_id") for gate in gates), "No gate decision named its native call"
        for path in (EVIDENCE / "hook-inputs").glob("enforce-*.json"):
            payload = json.loads(path.read_text())
            assert {"toolName", "toolArgs", "cwd"} <= payload.keys(), payload.keys()
            assert not ({"toolCallId", "tool_call_id", "tool_use_id", "toolCalls", "transcriptPath"} & payload.keys())
finally:
    (EVIDENCE / "watcher-requests.json").write_text(json.dumps(watcher_requests, indent=2))
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps([row["body"] for row in watcher_requests], indent=2))
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    server.shutdown()
