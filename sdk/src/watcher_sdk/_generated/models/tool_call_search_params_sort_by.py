from enum import StrEnum


class ToolCallSearchParamsSortBy(StrEnum):
    DECISION = "decision"
    OCCURRED_AT = "occurred_at"
    SEVERITY = "severity"
    TOOL_NAME = "tool_name"

    def __str__(self) -> str:
        return str(self.value)
