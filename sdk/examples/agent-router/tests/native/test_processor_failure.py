"""Stop the processor while a response is held and require Envoy not to release it.

Set ``AIGW_BIN`` to run. Runs in its own module because the test ends the
processor, and only one ``aigw`` gateway can run at a time.
"""

import sys
import threading
from collections.abc import Iterator

import openai
import pytest
from aigw_support import AIGW, Fixture, Provider, SimulatedWatcher, ask, running_gateway

pytestmark = pytest.mark.skipif(not AIGW, reason="Set AIGW_BIN to an aigw binary to run native gateway tests")


@pytest.fixture
def gateway(tmp_path) -> Iterator[dict]:
    provider, watcher = Fixture(Provider), Fixture(SimulatedWatcher)
    serve = [sys.executable, "-m", "watcher_agent_router.processor", "serve", "--address"]
    try:
        with running_gateway(tmp_path, provider, f"http://127.0.0.1:{watcher.server_port}", "key", serve) as urls:
            yield urls
    finally:
        provider.shutdown()
        watcher.shutdown()


def test_processor_failure_during_grading_withholds_the_response(gateway: dict) -> None:
    outcome: dict = {}

    def call() -> None:
        try:
            outcome["response"] = ask(gateway, "hold tool request")
        except openai.APIStatusError as error:
            outcome["error"] = error

    SimulatedWatcher.held.clear()
    caller = threading.Thread(target=call)
    caller.start()
    assert SimulatedWatcher.held.wait(30), "the exchange never reached Watcher"
    gateway["processor"].kill()
    caller.join(30)
    assert not caller.is_alive() and "response" not in outcome
    error = outcome["error"]
    assert error.status_code >= 500
    assert "call-hold" not in error.response.text
