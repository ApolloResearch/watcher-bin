from enum import Enum


class ContentToolUseToolType(str, Enum):
    CODE_EXECUTION = "code_execution"
    MCP_CALL = "mcp_call"
    WEB_SEARCH = "web_search"

    def __str__(self) -> str:
        return str(self.value)
