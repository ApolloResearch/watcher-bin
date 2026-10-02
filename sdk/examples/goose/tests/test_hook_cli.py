"""Installed hook option parsing preserves neutral responses and private diagnostics."""

import io
import json
import sys

import pytest
from watcher_goose import integration


@pytest.mark.parametrize("arguments,expected", [([], False), (["--record-only"], True)])
def test_recording_option_reaches_native_callback(monkeypatch, capsys, arguments, expected):
    seen = []

    async def hook(payload, *, record_only=False):
        seen.append((payload, record_only))

    payload = {"native": "event"}
    monkeypatch.setattr(integration, "run_hook", hook)
    monkeypatch.setattr(sys, "argv", ["native-hook", *arguments])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    integration.main()
    captured = capsys.readouterr()
    assert seen == [(payload, expected)]
    assert json.loads(captured.out) == {}
    assert captured.err == ""


@pytest.mark.parametrize("arguments", [["PRIVATE_ARGUMENT"], ["--record-only=PRIVATE_ARGUMENT"]])
def test_invalid_options_do_not_run_callback_or_echo_arguments(monkeypatch, capsys, arguments):
    async def hook(*args, **kwargs):
        raise AssertionError("An invalid invocation cannot reach the callback")

    monkeypatch.setattr(integration, "run_hook", hook)
    monkeypatch.setattr(sys, "argv", ["native-hook", *arguments])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"native": "event"})))
    integration.main()
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {}
    assert "PRIVATE_ARGUMENT" not in captured.err
    assert "Watcher observation failed" in captured.err


@pytest.mark.parametrize("arguments", [["--help"], ["help"]])
def test_help_never_reads_native_stdin(monkeypatch, capsys, arguments):
    class Unreadable:
        def read(self, *args):
            raise AssertionError("Help must not wait for a native event")

    monkeypatch.setattr(sys, "argv", ["native-hook", *arguments])
    monkeypatch.setattr(sys, "stdin", Unreadable())
    integration.main()
    captured = capsys.readouterr()
    assert "record-only" in captured.out
    assert captured.err == ""
