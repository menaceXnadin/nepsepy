"""Public NEPSE market-data client (normal public-site flow only)."""

from importlib.metadata import PackageNotFoundError, version as _version

from .auth import ProveResponse, TokenState
from .checksum import base as checksum_base
from .checksum import current_day as checksum_day
from .checksum import variant_a as checksum_a
from .checksum import variant_b as checksum_b
from .checksum import variant_c as checksum_c
from .client import NepseClient
from .async_client import AsyncNepseClient
from .exceptions import (AuthExpiredError, BootstrapError, NepseError,
                         PublicEndpointError, RateLimitedError, WasmError)
from .wasm import WasmCleaner, redact, strip_at_indexes

try:
    __version__ = _version("nepsepy")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0+unknown"

__all__ = ["__version__", "NepseClient", "AsyncNepseClient", "ProveResponse", "TokenState", "WasmCleaner",
           "redact", "strip_at_indexes", "NepseError", "BootstrapError",
           "WasmError", "AuthExpiredError", "RateLimitedError",
           "PublicEndpointError", "checksum_base", "checksum_day",
           "checksum_a", "checksum_b", "checksum_c"]
