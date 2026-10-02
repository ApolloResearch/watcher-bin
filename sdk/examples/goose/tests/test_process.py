"""Interrupted native exports must leave no live or unreaped child process."""

import asyncio
import os
import sys

import pytest
from watcher_goose.integration import run_hook


@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
def test_interrupted_export_kills_and_reaps_its_child(monkeypatch, interruption):
    async def exercise():
        started = asyncio.Event()
        children = []
        create_process = asyncio.create_subprocess_exec

        async def start_sleeping_export(*args, **kwargs):
            child = await create_process(sys.executable, "-c", "import time; time.sleep(40)", **kwargs)
            children.append(child)
            started.set()
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", start_sleeping_export)
        hook = asyncio.create_task(run_hook({"session_id": "native-session"}))
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            child = children[0]
            os.kill(child.pid, 0)
            if interruption == "cancel":
                hook.cancel()
            error = asyncio.CancelledError if interruption == "cancel" else TimeoutError
            with pytest.raises(error):
                await asyncio.wait_for(hook, timeout=15)
            assert child.returncode is not None
            with pytest.raises(ProcessLookupError):
                os.kill(child.pid, 0)
        finally:
            if not hook.done():
                hook.cancel()
                await asyncio.gather(hook, return_exceptions=True)
            for child in children:
                if child.returncode is None:
                    child.kill()
                await child.communicate()

    asyncio.run(exercise())
