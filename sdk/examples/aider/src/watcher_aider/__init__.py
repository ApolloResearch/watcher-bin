"""Experimental aider integration using only the public Watcher SDK."""

from aider.exceptions import ExInfo, LiteLLMExceptions

# aider-chat 0.86.2 raises on unlisted litellm errors; litellm 1.83 added PermissionDeniedError (HTTP 403), not retryable.
LiteLLMExceptions.exception_info.setdefault(
    "PermissionDeniedError", ExInfo("PermissionDeniedError", False, "The API provider refused the request.")
)
