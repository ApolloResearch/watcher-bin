"""Typed error hierarchy for the Watcher SDK.

Maps HTTP status codes to specific exception types so callers can handle
different failure modes (rate limits, auth, validation, etc.) independently.

Hierarchy::

    WatcherError (base)
    +-- WatcherConnectionError     (network unreachable)
    +-- WatcherTimeoutError        (request timed out)
    +-- WatcherAPIError            (HTTP error response)
        +-- WatcherValidationError     (400 / 422)
        +-- WatcherAuthenticationError (401)
        +-- WatcherNotFoundError       (404)
        +-- WatcherRateLimitError      (429, includes retry_after)
"""

from __future__ import annotations


class WatcherError(Exception):
    """Base exception for all Watcher SDK errors.

    All exceptions raised by the SDK inherit from this class, so callers
    can use ``except WatcherError`` as a catch-all.
    """


class WatcherConnectionError(WatcherError):
    """Raised when the SDK cannot establish a connection to the Watcher API.

    This typically indicates a network issue, DNS failure, or that the server
    is not running. This error is retryable by the built-in retry logic.
    """


class WatcherTimeoutError(WatcherError):
    """Raised when a request to the Watcher API exceeds the configured timeout.

    The timeout is set via the ``timeout`` parameter on the client constructor.
    This error is retryable by the built-in retry logic.
    """


class WatcherAPIError(WatcherError):
    """Raised when the Watcher API returns a non-2xx HTTP response.

    Attributes:
        status_code: The HTTP status code from the response.
        error: Short error description from the response body.
        message: Human-readable error message. For structured error bodies
            (``{"detail": {"code": ..., "message": ...}}``) this is the
            ``message``; for plain bodies it is the stringified detail.
        code: Stable machine-readable error code from a structured body,
            or None. Branch on this, not on message text.
        body: The raw parsed JSON response body, kept losslessly (e.g. for
            proxies forwarding the upstream error shape). None for
            SDK-synthesized errors (no HTTP response body).
        request_id: Optional server-assigned request ID for debugging.
    """

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str | None = None,
        request_id: str | None = None,
        *,
        code: str | None = None,
        body: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.request_id = request_id
        self.code = code
        self.body = body
        msg = f"[{status_code}] {error}"
        if code:
            msg += f" ({code})"
        if message:
            msg += f": {message}"
        super().__init__(msg)


class WatcherValidationError(WatcherAPIError):
    """Raised when the request fails server-side validation (HTTP 400 or 422).

    Check ``error`` and ``message`` for specifics about which fields or
    constraints were violated.
    """


class WatcherAuthenticationError(WatcherAPIError):
    """Raised when authentication fails (HTTP 401).

    This usually means the API key is missing, expired, or invalid.
    """


class WatcherNotFoundError(WatcherAPIError):
    """Raised when the requested resource does not exist (HTTP 404).

    For example, requesting a session or trajectory with an unknown ID.
    """


class WatcherRateLimitError(WatcherAPIError):
    """Raised when the API rate limit is exceeded (HTTP 429).

    This error is retryable by the built-in retry logic. The ``retry_after``
    attribute, when present, indicates how many seconds to wait before retrying.

    Attributes:
        retry_after: Seconds to wait before retrying, or None if the server
            did not specify.
    """

    def __init__(
        self,
        status_code: int,
        error: str,
        message: str | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
        *,
        code: str | None = None,
        body: dict[str, object] | None = None,
    ) -> None:
        super().__init__(status_code, error, message, request_id, code=code, body=body)
        self.retry_after = retry_after


# Mapping from HTTP status code to exception class
STATUS_CODE_MAP: dict[int, type[WatcherAPIError]] = {
    400: WatcherValidationError,
    401: WatcherAuthenticationError,
    404: WatcherNotFoundError,
    422: WatcherValidationError,
    429: WatcherRateLimitError,
}


def raise_for_status(status_code: int, response_body: dict[str, object], request_id: str | None = None) -> None:
    """Raise the appropriate WatcherAPIError subclass for a non-2xx HTTP response.

    Parses the standard ErrorResponse body format (``{error, detail, request_id}``)
    and maps the status code to a specific exception subclass via STATUS_CODE_MAP.
    Status codes not in the map fall back to the base WatcherAPIError.
    Structured details (``{"detail": {"code", "message"}}``) are flattened into
    the ``code``/``message`` fields.

    Args:
        status_code: The HTTP status code from the response (must be >= 400).
        response_body: Parsed JSON body of the error response, expected to
            contain ``error`` (str) and optionally ``detail`` (str or dict) and
            ``request_id`` (str); kept losslessly on the raised error's ``body``.
        request_id: Optional request ID from the response headers. If provided,
            takes precedence over any ``request_id`` in the body.

    Raises:
        WatcherValidationError: For 400 or 422 status codes.
        WatcherAuthenticationError: For 401 status codes.
        WatcherNotFoundError: For 404 status codes.
        WatcherRateLimitError: For 429 status codes (includes retry_after if present).
        WatcherAPIError: For all other non-2xx status codes.
    """
    error = str(response_body.get("error", "Unknown error"))
    detail_val = response_body.get("detail")
    code: str | None = None
    message: str | None = None
    if isinstance(detail_val, dict):
        # FastAPI-style structured detail: flatten {"code", "message"} into
        # typed fields; the raw shape stays available on .body.
        raw_code = detail_val.get("code")
        code = raw_code if isinstance(raw_code, str) else None
        raw_message = detail_val.get("message")
        message = raw_message if isinstance(raw_message, str) else None
    elif detail_val is not None:
        message = str(detail_val)
    req_id = request_id or (str(response_body["request_id"]) if "request_id" in response_body else None)

    exc_class = STATUS_CODE_MAP.get(status_code, WatcherAPIError)

    if exc_class is WatcherRateLimitError:
        retry_after_val = response_body.get("retry_after")
        retry_after = float(str(retry_after_val)) if retry_after_val is not None else None
        raise WatcherRateLimitError(status_code, error, message, req_id, retry_after, code=code, body=response_body)

    raise exc_class(status_code, error, message, req_id, code=code, body=response_body)
