"""Canonical identifiers for the agent clients Watcher integrates with."""

from __future__ import annotations

from typing import Literal

AgentName = Literal["claude_code", "codex"]
ALL_AGENTS: frozenset[AgentName] = frozenset({"claude_code", "codex"})
