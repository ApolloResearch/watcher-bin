from enum import StrEnum


class ToolCallSkipReason(StrEnum):
    AUTH_REJECTED = "auth_rejected"
    CREDENTIAL_HELPER_UNAVAILABLE = "credential_helper_unavailable"
    EMPTY_TRANSCRIPT = "empty_transcript"
    GRADING_BREAKER_HOLD = "grading_breaker_hold"
    HOOK_ERROR = "hook_error"
    SIGNED_OUT = "signed_out"
    TRANSCRIPT_UNAVAILABLE = "transcript_unavailable"
    UNKNOWN = "unknown"
    WATCHER_IGNORE = "watcher_ignore"
    WATCHER_OFFLINE = "watcher_offline"

    def __str__(self) -> str:
        return str(self.value)
