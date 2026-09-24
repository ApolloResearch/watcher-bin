from enum import Enum


class ToolCallErrorType(str, Enum):
    APPROVAL = "approval"
    CANCELLED = "cancelled"
    FILE_NOT_FOUND = "file_not_found"
    IS_A_DIRECTORY = "is_a_directory"
    LIMIT = "limit"
    OUTPUT_LIMIT = "output_limit"
    PARSING = "parsing"
    PERMISSION = "permission"
    SANDBOX_UNAVAILABLE = "sandbox_unavailable"
    TIMEOUT = "timeout"
    UNICODE_DECODE = "unicode_decode"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
