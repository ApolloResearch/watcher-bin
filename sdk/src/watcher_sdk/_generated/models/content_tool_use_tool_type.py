from enum import StrEnum


class ContentToolUseToolType(StrEnum):
    CODE_EXECUTION = "code_execution"
    MCP_CALL = "mcp_call"
    WEB_SEARCH = "web_search"

    def __str__(self) -> str:
        return str(self.value)
