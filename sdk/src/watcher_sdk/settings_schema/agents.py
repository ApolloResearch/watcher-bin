"""Canonical identifiers for the agent clients Watcher integrates with.

Hooks import these names on every tool call. Keep this module free of client,
settings-model and logging imports so those processes start quickly.
"""

from __future__ import annotations

from typing import Literal

AgentName = Literal["claude_code", "codex", "copilot"]
ALL_AGENTS: frozenset[AgentName] = frozenset({"claude_code", "codex", "copilot"})
