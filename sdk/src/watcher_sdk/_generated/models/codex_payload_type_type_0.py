from enum import Enum


class CodexPayloadTypeType0(str, Enum):
    COMPACTION = "compaction"
    COMPACTION_SUMMARY = "compaction_summary"
    CUSTOM_TOOL_CALL = "custom_tool_call"
    CUSTOM_TOOL_CALL_OUTPUT = "custom_tool_call_output"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
    LOCAL_SHELL_CALL = "local_shell_call"
    MESSAGE = "message"
    REASONING = "reasoning"

    def __str__(self) -> str:
        return str(self.value)
