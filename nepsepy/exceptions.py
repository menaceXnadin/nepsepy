"""Public NEPSE market-data client exceptions.

All exceptions redact credential material: never include raw or cleaned
tokens in messages.
"""

from __future__ import annotations


def _redact(value: object) -> str:
    try:
        n = len(value)  # type: ignore[arg-type]
    except Exception:
        return "<redacted>"
    return f"<redacted len={n}>"


class NepseError(Exception):
    """Base error for the public client."""


class BootstrapError(NepseError):
    """Raised when /prove fails or returns a malformed payload."""


class WasmError(NepseError):
    """Raised when css.wasm cannot load or returns unusable indexes."""


class AuthExpiredError(NepseError):
    """Raised when refresh fails or a retried request is still 401."""


class RateLimitedError(NepseError):
    """Raised on HTTP 429. Honors Retry-After without evading limits."""

    def __init__(self, message: str = "rate limited", retry_after: float = 0.0):
        super().__init__(message)
        self.retry_after = retry_after


class PublicEndpointError(NepseError):
    """Raised when a caller requests a non-public path."""
