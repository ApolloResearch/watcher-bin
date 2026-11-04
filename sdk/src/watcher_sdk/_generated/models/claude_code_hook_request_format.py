from enum import StrEnum


class ClaudeCodeHookRequestFormat(StrEnum):
    CLAUDE_CODE_JSONL = "claude-code-jsonl"
    CLAUDE_CODE_TRAJECTORY = "claude-code-trajectory"

    def __str__(self) -> str:
        return str(self.value)
