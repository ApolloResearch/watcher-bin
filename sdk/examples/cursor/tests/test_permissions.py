"""Native permission responses stay permissive even when observation fails."""

import json
import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("event", "expected"),
    [("preToolUse", {"permission": "allow"}), ("beforeSubmitPrompt", {"continue": True})],
)
@pytest.mark.parametrize("is_valid_session", [True, False])
def test_hook_permission_response_on_success_and_failure(tmp_path, event, expected, is_valid_session):
    payload = {"hook_event_name": event, "conversation_id": "session" if is_valid_session else ""}
    result = subprocess.run(
        [sys.executable, "-m", "watcher_cursor.integration"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={**os.environ, "WATCHER_STATE_DIR": str(tmp_path / "state")},
        check=False,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == expected
    assert ("not confirmed recorded" in result.stderr) != is_valid_session
