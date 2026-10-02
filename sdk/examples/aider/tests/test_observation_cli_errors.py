"""Observation CLI failures stay private without suppressing process interrupts."""

import asyncio
import io
import sys

import httpx
import pytest
from watcher_aider import integration

from watcher_sdk import AsyncWatcherClient


@pytest.mark.parametrize("error_type", [httpx.ReadError, httpx.RemoteProtocolError, httpx.ProxyError, RuntimeError])
def test_sdk_transport_errors_keep_observation_failure_contract(monkeypatch, capsys, error_type):
    requests = []

    def respond(request):
        requests.append(request)
        raise error_type("PRIVATE transport detail")

    async def hook(payload, **kwargs):
        async with AsyncWatcherClient(
            httpx_client=httpx.AsyncClient(base_url="http://watcher.test", transport=httpx.MockTransport(respond))
        ) as client:
            await client.pre_tool_use_hook(
                input=[], messages=[{"role": "user", "content": "fixture"}], external_ids={"other": "observation:test"}
            )

    monkeypatch.setattr(integration, "run_hook", hook)
    monkeypatch.setattr(sys, "argv", ["watcher-observe"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    assert integration.main() is None
    captured = capsys.readouterr()
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/hooks/pre-tool-use"
    assert captured.out == "{}\n"
    assert captured.err == "Watcher observation failed; transcript was not confirmed recorded.\n"


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt])
def test_observation_does_not_suppress_cancellation_or_interrupt(monkeypatch, capsys, error_type):
    async def hook(payload, **kwargs):
        raise error_type()

    monkeypatch.setattr(integration, "run_hook", hook)
    monkeypatch.setattr(sys, "argv", ["watcher-observe"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(error_type):
        integration.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
