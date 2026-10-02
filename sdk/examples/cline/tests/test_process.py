"""History-reader interruption must kill, drain and reap real Node children."""

import asyncio
import json
import os
import signal
from contextlib import suppress
from pathlib import Path

import pytest
from watcher_cline_bridge import integration as integration


@pytest.mark.parametrize(
    ("phase", "interruption"),
    [("startup", "timeout"), ("buffered", "timeout"), ("buffered", "cancel")],
)
def test_history_reader_is_killed_and_reaped(tmp_path, monkeypatch, phase, interruption):
    """Separate startup timeout from interruption with a deliberately unread pipe.

    The startup gate never opens, so the parent must use its captured OS PID.
    Buffered cases finish fixture setup before the adapter's one-second timeout
    starts. Holding the first read makes cleanup drain a real paused pipe; only
    the adapter's cleanup call performs the actual communicate operation.
    """
    pid_path = tmp_path / "reader-pid.json"
    temporary_pid = tmp_path / "reader-pid.tmp"
    startup_gate = tmp_path / "release-startup"
    reader = tmp_path / "read_history.mjs"
    reader.write_text(
        '#!/usr/bin/env node\nimport { writeFileSync, renameSync, existsSync } from "node:fs";\n'
        f"while ({json.dumps(phase == 'startup')} && !existsSync({json.dumps(str(startup_gate))})) "
        "await new Promise(resolve => setTimeout(resolve, 10));\n"
        'const backpressured = !process.stdout.write("x".repeat(256000));\n'
        f"writeFileSync({json.dumps(str(temporary_pid))}, JSON.stringify({{pid: process.pid, backpressured}}));\n"
        f"renameSync({json.dumps(str(temporary_pid))}, {json.dumps(str(pid_path))});\n"
        "setInterval(() => {}, 1000);\n"
    )
    reader.chmod(0o755)
    monkeypatch.setenv("WATCHER_HISTORY_READER", str(reader))
    monkeypatch.setattr(integration, "HISTORY_READ_TIMEOUT_SECONDS", 1 if interruption == "timeout" else 20)
    original_create = asyncio.create_subprocess_exec
    children = []
    cleanup_callbacks = []
    buffered_bytes = 0

    async def exercise():
        nonlocal buffered_bytes
        communicate_started = asyncio.Event()

        async def capture_child(*args, **kwargs):
            """Capture ownership immediately, then stage the buffered fixture before returning."""
            nonlocal buffered_bytes
            buffer_limit = 1024
            process = await original_create(*args, **kwargs, limit=buffer_limit)
            original_communicate = process.communicate
            original_kill = process.kill
            children.append(process)

            async def cleanup_child():
                """Use original methods even when the test replaced process methods."""
                if process.returncode is None:
                    with suppress(ProcessLookupError):
                        original_kill()
                await original_communicate()

            cleanup_callbacks.append(cleanup_child)
            if phase == "buffered":
                assert process.stdout is not None
                async with asyncio.timeout(10):
                    while not pid_path.exists():
                        await asyncio.sleep(0.01)
                    identity = json.loads(pid_path.read_text())
                    assert identity == {"pid": process.pid, "backpressured": True}
                    # StreamReader pauses its OS pipe above twice its configured limit.
                    while len(process.stdout._buffer) <= 2 * buffer_limit:
                        await asyncio.sleep(0.01)
                buffered_bytes = len(process.stdout._buffer)
                first_read = True

                async def communicate():
                    """Keep real data unread until production cleanup follows interruption."""
                    nonlocal first_read
                    if first_read:
                        first_read = False
                        communicate_started.set()
                        await asyncio.Future()
                    return await original_communicate()

                monkeypatch.setattr(process, "communicate", communicate)
            return process

        monkeypatch.setattr(integration.asyncio, "create_subprocess_exec", capture_child)
        task = asyncio.create_task(
            integration.run_hook({"sessionContext": {"rootSessionId": "test-session"}, "hookName": "agent_end"})
        )
        try:
            if phase == "buffered":
                # This event is set inside run_hook's protected communicate call,
                # after create_subprocess_exec has returned ownership to it.
                async with asyncio.timeout(10):
                    await communicate_started.wait()
                if interruption == "cancel":
                    task.cancel()
            done, _ = await asyncio.wait({task}, timeout=5)
            assert task in done, "History-reader interruption did not finish cleanup"
            expected = TimeoutError if interruption == "timeout" else asyncio.CancelledError
            with pytest.raises(expected):
                task.result()
            assert len(children) == 1
            process = children[0]
            pid = process.pid
            assert process.returncode == -signal.SIGKILL
            assert process.stdout is not None and process.stdout.at_eof()
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
            if phase == "startup":
                assert not pid_path.exists()
            else:
                assert buffered_bytes > 2048
            if destination := os.environ.get("SDK50_PROCESS_TEST_EVIDENCE"):
                with Path(destination).open("a") as log:
                    log.write(
                        json.dumps(
                            {
                                "case": interruption,
                                "phase": phase,
                                "pid": pid,
                                "returncode": process.returncode,
                                "pid_file_exists": pid_path.exists(),
                                "buffered_bytes_before_read": buffered_bytes,
                                "stdout_drained": process.stdout.at_eof(),
                                "pid_exists_after_reap": False,
                            }
                        )
                        + "\n"
                    )
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            for cleanup_child in cleanup_callbacks:
                await cleanup_child()

    asyncio.run(exercise())
