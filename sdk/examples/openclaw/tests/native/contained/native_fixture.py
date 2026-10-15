"""Exercise a native harness against local model and Watcher endpoints only."""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from native_evidence import expects_execution, forward, is_pending, retain_transcripts

SLUG = Path("slug.txt").read_text().strip()
SCENARIO = os.environ["WATCHER_EXAMPLE_SCENARIO"]
EVIDENCE = Path("/evidence")
ROOT = Path("/tmp/workspace")
ROOT.mkdir()
MARKER = ROOT / "executed.txt"
REWRITTEN = ROOT / "rewritten.txt"
watcher_requests = []
provider_requests = []
errors = []
pending = threading.Event()
release = threading.Event()
observed = threading.Event()
observation_graded = threading.Event()
delayed_approval = {}


class Handler(BaseHTTPRequestHandler):
    """Return deterministic judgments and one tool request followed by a final answer."""

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self):
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
        if "/hooks/pre-tool-use" in self.path:
            watcher_requests.append({"path": self.path, "body": body})
            inputs = body.get("input")
            is_gate = is_pending(body)
            if forward(self, body, raw, lambda: {"marker_exists": MARKER.exists()}):
                if not inputs and "The fixture task is complete." in json.dumps(body.get("messages", [])):
                    observed.set()
                if inputs and not is_gate:
                    observation_graded.set()
                return
            if is_gate:
                assert not MARKER.exists()
                if SCENARIO == "pending":
                    pending.set()
                    assert release.wait(40)
                if SCENARIO in {"timeout", "outer-timeout"}:
                    time.sleep(5)
                if SCENARIO == "delayed-allow":
                    started = time.monotonic()
                    time.sleep(25)
                    delayed_approval.update(
                        elapsed_seconds=time.monotonic() - started,
                        marker_before_approval=MARKER.exists(),
                    )
                    assert not MARKER.exists()
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
            if not inputs and "The fixture task is complete." in json.dumps(body.get("messages", [])):
                observed.set()
            if inputs and not is_gate:
                observation_graded.set()
            return
        provider_requests.append({"path": self.path, "body": body})
        if len(provider_requests) > 8:
            raise RuntimeError("Unexpected repeated model calls")
        has_result = any(m.get("role") == "tool" for m in body.get("messages", []))
        call_tool = not has_result
        name = "exec" if SLUG == "openclaw" else "bash"
        assert any(t.get("function", {}).get("name") == name for t in body.get("tools", [])), (
            "Native expected tool absent"
        )
        call = {
            "id": "fixture-native-call",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps({"command": f"printf 'executed' > {MARKER}"})},
        }
        message: dict[str, Any] = {
            "role": "assistant",
            "content": None if call_tool else "The fixture task is complete.",
        }
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
    "WATCHER_API_KEY": "fixture",
    "WATCHER_PYTHON": "/opt/fixture/bridge_entry.py",
    "WATCHER_TIMEOUT_SECONDS": "1" if SCENARIO == "timeout" else "60",
    "npm_config_offline": "true",
    "npm_config_update_notifier": "false",
}
state = Path("/tmp/openclaw-state")
state.mkdir()
config: dict[str, Any] = {
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
    "tools": {
        "profile": "coding",
        "exec": {"host": "gateway", "security": "full", "ask": "off"},
        "codeMode": {"enabled": False},
    },
}
config["gateway"] = {
    "mode": "local",
    "port": 19355,
    "auth": {"mode": "token", "token": "fixture-token-with-no-external-use"},
}
config_path = state / "openclaw.json"
config_path.write_text(json.dumps(config))
env.update(OPENCLAW_STATE_DIR=str(state), OPENCLAW_CONFIG_PATH=str(config_path))
archive = next(Path.cwd().glob("watcher-openclaw-example-*.tgz"))
install_command = ["openclaw", "plugins", "install", "npm-pack:" + str(archive), "--force", "--accept-capabilities"]
(EVIDENCE / "install-command.json").write_text(json.dumps(install_command, indent=2))
with (EVIDENCE / "install-stdout.txt").open("w") as stdout, (EVIDENCE / "install-stderr.txt").open("w") as stderr:
    installed = subprocess.run(
        install_command, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, text=True, timeout=120
    )
assert installed.returncode == 0, (EVIDENCE / "install-stderr.txt").read_text()
installed_root = state / "npm/projects/watcher-openclaw-example/node_modules/watcher-openclaw-example"
packaged_root = Path("packages/node")
installed_files = {}
retained_plugin = EVIDENCE / "installed-node-package"
retained_plugin.mkdir()
for packaged in sorted(packaged_root.rglob("*")):
    if not packaged.is_file():
        continue
    relative = packaged.relative_to(packaged_root)
    installed_file = installed_root / relative
    assert installed_file.read_bytes() == packaged.read_bytes(), str(relative)
    installed_files[str(relative)] = hashlib.sha256(installed_file.read_bytes()).hexdigest()
    retained = retained_plugin / relative
    retained.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(installed_file, retained)
assert "src/plugin.mjs" in installed_files
installed_source_files = {
    str(path.relative_to(installed_root)) for path in (installed_root / "src").rglob("*") if path.is_file()
}
assert installed_source_files == {name for name in installed_files if name.startswith("src/")}
(EVIDENCE / "installation.json").write_text(
    json.dumps(
        {
            "plugin_root": str(installed_root),
            "files_sha256": installed_files,
            "retained_installed_files": str(retained_plugin),
            "source_archive": str(archive),
            "source_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        },
        indent=2,
    )
)
config = json.loads(config_path.read_text())
config.setdefault("plugins", {}).update(
    allow=["watcher-openclaw-example"],
    entries={
        "watcher-openclaw-example": {
            "enabled": True,
            "config": {"mode": "observe" if SCENARIO == "observe" else "enforce"},
            "hooks": {"allowConversationAccess": SCENARIO != "no-context-access"},
        }
    },
)
assert not config["plugins"].get("load", {}).get("paths"), "Install proof must not load the source path"
(EVIDENCE / "installed-config.json").write_text(json.dumps(config, indent=2))
if SCENARIO == "outer-timeout":
    config["plugins"]["entries"]["watcher-openclaw-example"]["hooks"]["timeouts"] = {"before_tool_call": 1000}
if SCENARIO == "rewrite":
    rewrite_dir = Path.home() / "rewriter"
    rewrite_dir.mkdir(mode=0o700)
    rewrite = rewrite_dir / "index.mjs"
    (rewrite_dir / "package.json").write_text(
        json.dumps(
            {"name": "rewriter", "version": "0.1.0", "type": "module", "openclaw": {"extensions": ["./index.mjs"]}}
        )
    )
    (rewrite_dir / "openclaw.plugin.json").write_text(
        json.dumps(
            {
                "id": "rewriter",
                "activation": {"onStartup": True},
                "configSchema": {"type": "object", "additionalProperties": False},
            }
        )
    )
    rewrite.write_text(
        'export default function(api) { api.on("before_tool_call", e => ({params:{...e.params, command:"printf rewritten > /tmp/workspace/rewritten.txt"}}), {priority:-100}); }'
    )
    config["plugins"]["load"] = {"paths": [str(rewrite_dir)]}
    config["plugins"]["entries"]["rewriter"] = {"enabled": True}
    config["plugins"]["allow"].append("rewriter")
config_path.write_text(json.dumps(config))
if SCENARIO == "allow":
    with (
        (EVIDENCE / "plugin-inspect.json").open("w") as stdout,
        (EVIDENCE / "plugin-inspect-stderr.txt").open("w") as stderr,
    ):
        inspection = subprocess.run(
            ["openclaw", "plugins", "inspect", "watcher-openclaw-example", "--runtime", "--json"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            text=True,
            timeout=60,
        )
    assert inspection.returncode == 0, (EVIDENCE / "plugin-inspect-stderr.txt").read_text()
    inspected = json.loads((EVIDENCE / "plugin-inspect.json").read_text())
    assert inspected["plugin"]["status"] == "loaded"
    assert inspected["plugin"]["rootDir"] == str(installed_root)
    assert inspected["install"]["installPath"] == str(installed_root)
    assert inspected["install"]["artifactKind"] == "npm-pack"
    assert inspected["install"]["sourcePath"] == str(archive)
    assert {hook["name"] for hook in inspected["typedHooks"]} == {"agent_end", "before_tool_call"}
gateway_log = (EVIDENCE / "gateway.log").open("w")
gateway = subprocess.Popen(
    ["openclaw", "gateway", "run", "--port", "19355", "--bind", "loopback", "--allow-unconfigured"],
    env=env,
    stdout=gateway_log,
    stderr=subprocess.STDOUT,
)
(EVIDENCE / "gateway-pid.txt").write_text(str(gateway.pid))
for _attempt in range(120):
    try:
        with socket.create_connection(("127.0.0.1", 19355), timeout=0.1):
            break
    except OSError:
        if gateway.poll() is not None:
            raise RuntimeError("Gateway failed to start") from None
        time.sleep(0.25)
else:
    raise RuntimeError("Gateway did not become ready")
command = [
    "openclaw",
    "agent",
    "--agent",
    "main",
    "--message",
    "Run the fixture shell command, then finish.",
    "--json",
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
try:
    result = subprocess.run(
        command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180
    )
    if SCENARIO != "no-context-access":
        assert observed.wait(60), "Final transcript snapshot missing"
        if SCENARIO == "observe":
            assert observation_graded.wait(60), "Retrospective tool assessment missing"
        for _attempt in range(200):
            active_bridges = []
            for process in Path("/proc").glob("[0-9]*/cmdline"):
                try:
                    commandline = process.read_bytes().split(b"\0")
                except FileNotFoundError:
                    continue
                if b"watcher_openclaw_bridge.integration" in commandline:
                    active_bridges.append(int(process.parent.name))
            if not active_bridges:
                break
            time.sleep(0.05)
        assert not active_bridges, "Observation bridge did not exit after its responses"
        (EVIDENCE / "observation-complete.json").write_text(
            json.dumps(
                {
                    "final_snapshot": True,
                    "tool_assessment": observation_graded.is_set(),
                    "active_bridge_pids": active_bridges,
                }
            )
        )
        checkpoint_root = Path.home() / ".local/state/watcher-sdk-examples"
        if checkpoint_root.exists():
            shutil.copytree(checkpoint_root, EVIDENCE / "observation-state")
    (EVIDENCE / "stdout.txt").write_text(result.stdout)
    (EVIDENCE / "stderr.txt").write_text(result.stderr)
    summary = {
        "slug": SLUG,
        "scenario": SCENARIO,
        "returncode": result.returncode,
        "model_requests": len(provider_requests),
        "watcher_requests": len(watcher_requests),
        "marker": MARKER.exists(),
        "rewritten_marker": REWRITTEN.exists(),
        "fixture_errors": errors,
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2))
    assert not errors, errors
    if SCENARIO == "no-context-access":
        assert not watcher_requests, "Conversation access disabled but data was sent"
        # A failed plugin load is not a guaranteed host-wide veto.
        assert "allowConversationAccess" in (EVIDENCE / "gateway.log").read_text()
    else:
        assert result.returncode == 0, result.stderr
        assert len(provider_requests) >= 2, summary
        assert watcher_requests, summary
        expect_marker = SCENARIO in {"observe", "allow", "delayed-allow"}
        assert MARKER.exists() == expects_execution(expect_marker), summary
        if MARKER.exists():
            assert MARKER.read_text() == "executed"
            (EVIDENCE / "marker-content.txt").write_text(MARKER.read_text())
        if SCENARIO == "delayed-allow":
            assert delayed_approval["elapsed_seconds"] >= 25
            assert delayed_approval["marker_before_approval"] is False
            assert "timed out" not in (EVIDENCE / "gateway.log").read_text()
            (EVIDENCE / "delayed-approval.json").write_text(json.dumps(delayed_approval, indent=2))
        if SCENARIO == "rewrite":
            assert REWRITTEN.exists(), summary
            graded = [
                r["body"] for r in watcher_requests if r["body"].get("input") and "settings_overrides" not in r["body"]
            ]
            assert graded and graded[0]["input"][0]["tool_input"]["command"].endswith("/executed.txt")
        if SCENARIO == "pending":
            receipt = json.loads((EVIDENCE / "pending.json").read_text())
            assert not receipt["marker_before_release"] and receipt["model_requests_before_release"] == 1
        if SCENARIO != "outer-timeout":
            assert any(
                "The fixture task is complete." in json.dumps(r["body"].get("messages", [])) for r in watcher_requests
            ), "Final assistant text missing"
finally:
    (EVIDENCE / "sdk-requests.json").write_text(json.dumps([row["body"] for row in watcher_requests], indent=2))
    (EVIDENCE / "watcher-requests.json").write_text(json.dumps(watcher_requests, indent=2))
    (EVIDENCE / "provider-requests.json").write_text(json.dumps(provider_requests, indent=2))
    gateway.terminate()
    forced_shutdown = False
    try:
        gateway.wait(timeout=15)
    except subprocess.TimeoutExpired:
        forced_shutdown = True
        gateway.kill()
        gateway.wait()
    gateway_log.close()
    server.shutdown()
    (EVIDENCE / "gateway-shutdown.json").write_text(
        json.dumps({"returncode": gateway.returncode, "forced": forced_shutdown})
    )
    retain_transcripts([Path.home(), Path("/tmp/openclaw-state")])
    if SCENARIO != "no-context-access":
        assert "Watcher did not finish observing this turn." not in (EVIDENCE / "gateway.log").read_text()
