"""Live checks with real coding-agent CLIs pointed at the proxy.

Claude Code uses the proxy's Anthropic Messages route, Codex its Responses
route, and OpenCode, Qwen Code and Mistral Vibe its Chat Completions route;
all reach real models through the provider gateway. Each agent is
asked to read a file (allowed, and it must answer from the file's contents)
and to run a harmless command containing the policy's deny marker, which
would create ``proof.txt``. The file must never appear. Watcher's records are
then read back, including the agent's own session identity.

The CLIs run isolated from this machine's settings and hooks: Claude Code with
``--setting-sources project`` in an empty directory, Codex with a fresh
``CODEX_HOME`` and OpenCode with a fresh ``HOME``. Claude Code still writes its
transcripts under ``~/.claude/projects``. Tests skip when a CLI is not
installed; OpenCode and Qwen Code run through ``npx`` and Mistral Vibe
through ``uvx``, at the pinned versions below. Qwen Code and Vibe cannot send
the session header, so their records are found by a unique file name.
"""

import datetime
import json
import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from common import DENY_MARKER, GATEWAY, GATEWAY_KEY, WATCHER_URL, recorded_calls, recorded_calls_mentioning
from harness import litellm_proxy
from watcher_litellm.callback import SESSION_PREFIX

CLAUDE_MODEL = os.environ.get("WATCHER_LIVE_CLAUDE_MODEL", "claude-haiku-4-5")
CODEX_MODEL = os.environ.get("WATCHER_LIVE_CODEX_MODEL", "gpt-5.4-mini")
OPENCODE_VERSION = os.environ.get("WATCHER_LIVE_OPENCODE_VERSION", "1.18.30")
QWEN_VERSION = os.environ.get("WATCHER_LIVE_QWEN_VERSION", "0.23.4")
VIBE_VERSION = os.environ.get("WATCHER_LIVE_VIBE_VERSION", "2.25.4")
NOTES = "Shopping list. The first word is pineapple.\n"
TIMEOUT = 300


@pytest.fixture(scope="module")
def cli_proxy(live_policy: None, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    model_list = [
        {
            "model_name": CLAUDE_MODEL,
            "litellm_params": {"model": f"anthropic/{CLAUDE_MODEL}", "api_base": GATEWAY, "api_key": GATEWAY_KEY},
        },
        {
            "model_name": CODEX_MODEL,
            "litellm_params": {"model": f"openai/{CODEX_MODEL}", "api_base": f"{GATEWAY}/v1", "api_key": GATEWAY_KEY},
        },
    ]
    env = {"WATCHER_API_URL": str(WATCHER_URL), "WATCHER_API_KEY": os.environ.get("WATCHER_LIVE_API_KEY", "")}
    with litellm_proxy(model_list, env, tmp_path_factory.mktemp("cli-proxy")) as url:
        yield url


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    (work / "notes.txt").write_text(NOTES)
    return work


def _base_env() -> dict[str, str]:
    return {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG", "TERM") if key in os.environ}


def _claude(proxy: str, work: Path, prompt: str, tools: str) -> tuple[str, str]:
    session_id = str(uuid.uuid4())
    env = {
        **_base_env(),
        "ANTHROPIC_BASE_URL": proxy,
        "ANTHROPIC_API_KEY": "sk-proxy",
        # Background requests use the small model; keep them on a configured route.
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": CLAUDE_MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": CLAUDE_MODEL,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    result = subprocess.run(
        [
            shutil.which("claude") or "claude",
            "-p",
            prompt,
            "--model",
            CLAUDE_MODEL,
            "--session-id",
            session_id,
            "--setting-sources",
            "project",
            "--allowedTools",
            tools,
            "--output-format",
            "json",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout)["result"], session_id


def _codex(proxy: str, work: Path, home: Path, prompt: str) -> tuple[str, str]:
    session_id = f"codex-live-{uuid.uuid4()}"
    home.mkdir()
    (home / "config.toml").write_text(
        f'model = "{CODEX_MODEL}"\n'
        'model_provider = "litellm"\n'
        'approval_policy = "never"\n'
        'sandbox_mode = "workspace-write"\n'
        "[model_providers.litellm]\n"
        'name = "LiteLLM proxy"\n'
        f'base_url = "{proxy}/v1"\n'
        'wire_api = "responses"\n'
        'env_key = "OPENAI_API_KEY"\n'
        f'http_headers = {{ "x-watcher-session-id" = "{session_id}" }}\n'
    )
    env = {**_base_env(), "CODEX_HOME": str(home), "OPENAI_API_KEY": "sk-proxy"}
    last_message = home / "last.txt"
    result = subprocess.run(
        [
            shutil.which("codex") or "codex",
            "exec",
            "--skip-git-repo-check",
            "--output-last-message",
            str(last_message),
            prompt,
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return last_message.read_text(), session_id


def _opencode(proxy: str, work: Path, home: Path, prompt: str) -> tuple[str, str]:
    session_id = f"opencode-live-{uuid.uuid4()}"
    home.mkdir()
    config = {
        "model": f"litellm/{CODEX_MODEL}",
        "small_model": f"litellm/{CODEX_MODEL}",
        "enabled_providers": ["litellm"],
        "provider": {
            "litellm": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "LiteLLM proxy",
                "options": {
                    "baseURL": f"{proxy}/v1",
                    "apiKey": "sk-proxy",
                    "headers": {"x-watcher-session-id": session_id},
                },
                "models": {
                    CODEX_MODEL: {"name": CODEX_MODEL, "tool_call": True, "limit": {"context": 65536, "output": 4096}}
                },
            }
        },
        "permission": {"*": "deny", "read": "allow", "bash": "allow"},
        "plugin": [],
    }
    (home / "opencode.json").write_text(json.dumps(config))
    env = {
        **_base_env(),
        "HOME": str(home),
        "OPENCODE_CONFIG": str(home / "opencode.json"),
        "OPENCODE_DISABLE_AUTOUPDATE": "true",
        "OPENCODE_DISABLE_MODELS_FETCH": "true",
        "npm_config_cache": str(Path(os.environ.get("HOME", str(home))) / ".npm"),
    }
    result = subprocess.run(
        [
            shutil.which("npx") or "npx",
            "-y",
            f"opencode-ai@{OPENCODE_VERSION}",
            "run",
            "--pure",
            "--dir",
            str(work),
            "--model",
            f"litellm/{CODEX_MODEL}",
            "--format",
            "json",
            prompt,
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    texts = []
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        part = event.get("part") or {}
        if part.get("type") == "text":
            texts.append(part.get("text", ""))
    return "".join(texts), session_id


def _run_cli(command: list[str], work: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, timeout=TIMEOUT, check=False)
    assert result.returncode == 0, (result.stdout[-1000:], result.stderr[-2000:])
    return result.stdout


def _qwen(proxy: str, work: Path, home: Path, prompt: str) -> str:
    (home / ".qwen").mkdir(parents=True)
    (home / ".qwen" / "settings.json").write_text(json.dumps({"security": {"auth": {"selectedType": "openai"}}}))
    env = {**_base_env(), "HOME": str(home), "OPENAI_API_KEY": "sk-proxy", "OPENAI_BASE_URL": f"{proxy}/v1"}
    env["npm_config_cache"] = str(Path(os.environ["HOME"]) / ".npm")
    return _run_cli(
        [
            shutil.which("npx") or "npx",
            "-y",
            f"@qwen-code/qwen-code@{QWEN_VERSION}",
            "--auth-type",
            "openai",
            "--approval-mode",
            "yolo",
            "--model",
            CODEX_MODEL,
            "--openai-base-url",
            f"{proxy}/v1",
            "--openai-api-key",
            "sk-proxy",
            prompt,
        ],
        work,
        env,
    )


def _vibe(proxy: str, work: Path, home: Path, prompt: str) -> str:
    vibe_home = home / ".vibe"
    vibe_home.mkdir(parents=True)
    (vibe_home / "config.toml").write_text(
        'active_model = "proxy"\n'
        f'[[models]]\nname = "{CODEX_MODEL}"\nprovider = "litellm"\nalias = "proxy"\n'
        '[[providers]]\nname = "litellm"\n'
        f'api_base = "{proxy}/v1"\n'
        'api_key_env_var = "LITELLM_PROXY_KEY"\nbackend = "generic"\napi_style = "openai"\n'
    )
    env = {**_base_env(), "HOME": str(home), "VIBE_HOME": str(vibe_home), "LITELLM_PROXY_KEY": "sk-proxy"}
    env["UV_CACHE_DIR"] = os.environ.get("UV_CACHE_DIR", str(Path(os.environ["HOME"]) / ".cache" / "uv"))
    return _run_cli(
        [
            shutil.which("uvx") or "uvx",
            "--from",
            f"mistral-vibe=={VIBE_VERSION}",
            "vibe",
            "--trust",
            "--auto-approve",
            "--max-turns",
            "6",
            "--output",
            "text",
            "--prompt",
            prompt,
        ],
        work,
        env,
    )


needs_claude = pytest.mark.skipif(shutil.which("claude") is None, reason="Claude Code is not installed")
needs_codex = pytest.mark.skipif(shutil.which("codex") is None, reason="Codex CLI is not installed")


@needs_claude
def test_claude_code_reads_through_the_proxy(cli_proxy: str, workspace: Path) -> None:
    answer, session_id = _claude(
        cli_proxy,
        workspace,
        "Use the Read tool on notes.txt, then reply with only the word that follows 'The first word is'.",
        "Read",
    )

    assert "pineapple" in answer.lower()
    session, calls = recorded_calls({"anthropic-claude-code": [session_id]})
    assert session["agent_platform"] == "claude_code"
    assert [(c["tool_name"], c["applied_decision"]) for c in calls] == [("Read", "allow")]


@needs_claude
def test_claude_code_denied_command_never_runs(cli_proxy: str, workspace: Path) -> None:
    _, session_id = _claude(
        cli_proxy,
        workspace,
        f"Run exactly this command with the Bash tool and nothing else: echo {DENY_MARKER} > proof.txt",
        "Bash",
    )

    assert not (workspace / "proof.txt").exists()
    _, calls = recorded_calls({"anthropic-claude-code": [session_id]})
    assert ("Bash", "deny") in [(c["tool_name"], c["applied_decision"]) for c in calls]


@needs_codex
def test_codex_reads_through_the_proxy(cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    answer, session_id = _codex(
        cli_proxy,
        workspace,
        tmp_path / "codex",
        "Run `cat notes.txt` and reply with only the word that follows 'The first word is'.",
    )

    assert "pineapple" in answer.lower()
    session, calls = recorded_calls({"other": [SESSION_PREFIX + session_id]})
    assert session["agent_platform"] == "codex"
    assert calls and all(c["applied_decision"] == "allow" for c in calls)


@needs_codex
def test_codex_denied_command_never_runs(cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    _, session_id = _codex(
        cli_proxy,
        workspace,
        tmp_path / "codex",
        f"Run exactly this shell command and nothing else: echo {DENY_MARKER} > proof.txt",
    )

    assert not (workspace / "proof.txt").exists()
    _, calls = recorded_calls({"other": [SESSION_PREFIX + session_id]})
    assert "deny" in [c["applied_decision"] for c in calls]


needs_npx = pytest.mark.skipif(shutil.which("npx") is None, reason="npx is needed to run OpenCode")


@needs_npx
def test_opencode_reads_through_the_proxy(cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    answer, session_id = _opencode(
        cli_proxy,
        workspace,
        tmp_path / "home",
        "Read notes.txt and reply with only the word that follows 'The first word is'.",
    )

    assert "pineapple" in answer.lower()
    session, calls = recorded_calls({"other": [SESSION_PREFIX + session_id]}, min_messages=4)
    assert calls and all(c["applied_decision"] == "allow" for c in calls)
    assert session["message_count"] >= 4


@needs_npx
def test_opencode_denied_command_never_runs(cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    _, session_id = _opencode(
        cli_proxy,
        workspace,
        tmp_path / "home",
        f"Run exactly this shell command with the bash tool and nothing else: echo {DENY_MARKER} > proof.txt",
    )

    assert not (workspace / "proof.txt").exists()
    _, calls = recorded_calls({"other": [SESSION_PREFIX + session_id]})
    assert "deny" in [c["applied_decision"] for c in calls]


needs_uvx = pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx is needed to run Mistral Vibe")
CHAT_CLIS = [
    pytest.param(_qwen, marks=needs_npx, id="qwen-code"),
    pytest.param(_vibe, marks=needs_uvx, id="mistral-vibe"),
]


@pytest.mark.parametrize("cli", CHAT_CLIS)
def test_chat_cli_reads_through_the_proxy(cli: Any, cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    since = datetime.datetime.now(datetime.UTC)
    name = f"notes-{uuid.uuid4().hex[:8]}.txt"
    (workspace / name).write_text(NOTES)

    output = cli(
        cli_proxy,
        workspace,
        tmp_path / "home",
        f"Read {name} and reply with only the word that follows 'The first word is'.",
    )

    assert "pineapple" in output.lower()
    calls = recorded_calls_mentioning(name, since)
    assert calls and all(c["applied_decision"] == "allow" for c in calls)


@pytest.mark.parametrize("cli", CHAT_CLIS)
def test_chat_cli_denied_command_is_withheld(cli: Any, cli_proxy: str, workspace: Path, tmp_path: Path) -> None:
    """A read-only marker command: Qwen Code declines any file-writing command, so no proof file is used."""
    since = datetime.datetime.now(datetime.UTC)
    target = f"{DENY_MARKER}-{uuid.uuid4().hex[:8]}"

    output = cli(cli_proxy, workspace, tmp_path / "home", f"Run `ls {target}` in the shell and tell me what it prints.")

    decisions = [c["applied_decision"] for c in recorded_calls_mentioning(target, since)]
    assert decisions and set(decisions) == {"deny"}, output[-1500:]
