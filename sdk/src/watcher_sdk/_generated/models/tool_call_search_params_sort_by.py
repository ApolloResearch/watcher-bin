from enum import Enum


class ToolCallSearchParamsSortBy(str, Enum):
    DECISION = "decision"
    OCCURRED_AT = "occurred_at"
    SEVERITY = "severity"
    TOOL_NAME = "tool_name"

    def __str__(self) -> str:
        return str(self.value)
