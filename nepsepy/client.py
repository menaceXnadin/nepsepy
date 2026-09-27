"""NepseClient: public market-data flow only.

Bootstrap:
  GET /api/authenticate/prove (no auth) -> raw tokens + salts
  GET /assets/prod/css.wasm -> cut indexes -> cleaned tokens (memory only)

Requests:
  Authorization: Salter <cleaned-access-token>

Scope guardrails:
  - GETs limited to /api/nots/ and /api/web/ (the public market-data paths
    the normal website calls). Everything else raises PublicEndpointError.
  - No admin/CMS calls, no endpoint discovery, no token decryption.
  - Conservative rate limiting + 429 honoring, no evasion.
  - On access rejection (401/403) fail or do the single normal refresh;
    never probe further.
"""

from __future__ import annotations
from ._securities import SecuritiesMixin
from ._prices import PricesMixin
from ._news import NewsMixin
from ._market import MarketMixin
from ._company import CompanyMixin

import time
from typing import Optional

import httpx

from .auth import ProveResponse, TokenState
from .checksum import base as _ck_base
from .checksum import current_day as _ck_day
from .checksum import variant_a as _ck_a
from .checksum import variant_b as _ck_b
from .checksum import variant_c as _ck_c
from .exceptions import (AuthExpiredError, BootstrapError, PublicEndpointError,
                         RateLimitedError, WasmError)
from .wasm import WasmCleaner, redact

BASE_URL = "https://nepalstock.com.np"
PROVE_PATH = "/api/authenticate/prove"
REFRESH_PATH = "/api/authenticate/refresh-token"
WASM_PATH = "/assets/prod/css.wasm"

# Only these public prefixes may be fetched with the Salter header.
ALLOWED_GET_PREFIXES = ("/api/nots/", "/api/web/", "/api/margin/")
# Exact paths the UI calls that carry no trailing slash.
ALLOWED_GET_EXACT = ("/api/nots",)

CLIENT_UA = "nepsepy/1.0 (+public market-data observer)"
MIN_INTERVAL_S = 0.4  # at most ~2-3 requests/second
TIMEOUT_S = 15.0
MAX_RETRY_AFTER_S = 30.0


class NepseClient(MarketMixin, SecuritiesMixin, PricesMixin, CompanyMixin, NewsMixin):
    def __init__(self, base_url: str = BASE_URL,
                 transport: Optional[httpx.BaseTransport] = None,
                 min_interval: float = MIN_INTERVAL_S) -> None:
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base,
            timeout=TIMEOUT_S,
            headers={"User-Agent": CLIENT_UA,
                     "Accept": "application/json, text/plain, */*"},
            transport=transport,
        )
        self._cleaner: Optional[WasmCleaner] = None
        self._tokens: Optional[TokenState] = None
        self._wasm_bytes: Optional[bytes] = None
        self._market_id: Optional[int] = None
        self._min_interval = min_interval
        self._last_at = 0.0

    # -- context manager -------------------------------------------------
    def __enter__(self) -> "NepseClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._tokens = None  # drop in-memory credentials
        self._market_id = None
        self._http.close()

    # -- internal helpers ------------------------------------------------
    def _pace(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_at)
        if wait > 0:
            time.sleep(wait)
        self._last_at = time.monotonic()

    def _fail_429(self, response: httpx.Response) -> None:
        retry_after = 0.0
        try:
            retry_after = float(response.headers.get("Retry-After", "0"))
        except ValueError:
            retry_after = 0.0
        retry_after = max(0.0, min(retry_after, MAX_RETRY_AFTER_S))
        if retry_after:
            time.sleep(retry_after)
        raise RateLimitedError("server rate limit (429)",
                               retry_after=retry_after)

    @staticmethod
    def _check_public_path(path: str) -> None:
        if not path.startswith("/"):
            raise PublicEndpointError(f"path must be absolute: {path!r}")
        if path in (PROVE_PATH, REFRESH_PATH, WASM_PATH):
            raise PublicEndpointError(
                f"internal endpoint is not public market data: {path}")
        if path.startswith(("/api/cms", "/cms", "/admin", "/api/users",
                            "/api/authenticate/")):
            raise PublicEndpointError(f"non-public endpoint blocked: {path}")
        if not path.startswith(ALLOWED_GET_PREFIXES) \
                and path not in ALLOWED_GET_EXACT:
            raise PublicEndpointError(
                f"only {ALLOWED_GET_PREFIXES} may be fetched, got: {path}")

    def _ensure_cleaner(self) -> WasmCleaner:
        if self._cleaner is not None:
            return self._cleaner
        self._pace()
        resp = self._http.get(WASM_PATH)
        if resp.status_code == 429:
            self._fail_429(resp)
        resp.raise_for_status()
        self._wasm_bytes = resp.content
        self._cleaner = WasmCleaner.from_bytes(self._wasm_bytes)
        return self._cleaner

    # -- bootstrap --------------------------------------------------------
    def bootstrap(self) -> TokenState:
        """Run the normal public bootstrap: prove -> wasm clean."""
        self._pace()
        try:
            resp = self._http.get(PROVE_PATH)
        except httpx.HTTPError as exc:
            raise BootstrapError(
                f"prove request failed: {type(exc).__name__}") from exc
        if resp.status_code == 429:
            self._fail_429(resp)
        if resp.status_code != 200:
            raise BootstrapError(
                f"prove rejected with HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise BootstrapError("prove response is not JSON") from exc
        prove = ProveResponse.from_dict(payload)
        cleaner = self._ensure_cleaner()
        try:
            access = cleaner.clean_access(prove.raw_access, prove.salts)
            refresh = cleaner.clean_refresh(prove.raw_refresh, prove.salts)
        except WasmError:
            raise
        except Exception as exc:
            raise BootstrapError("token transform failed") from exc
        # Drop raw tokens: keep cleaned pair in memory only.
        self._tokens = TokenState(access=access, refresh=refresh,
                                  salts=prove.salts)
        return self._tokens

    def _refresh_once(self) -> TokenState:
        """Normal frontend refresh: POST cleaned refresh, transform new pair."""
        if self._tokens is None or not self._tokens.refresh:
            raise AuthExpiredError("no refresh token available")
        cleaner = self._ensure_cleaner()
        self._pace()
        try:
            resp = self._http.post(REFRESH_PATH,
                                   json={"refreshToken": self._tokens.refresh})
        except httpx.HTTPError as exc:
            raise AuthExpiredError("refresh request failed") from exc
        if resp.status_code == 429:
            self._fail_429(resp)
        if resp.status_code != 200:
            raise AuthExpiredError(
                f"refresh rejected with HTTP {resp.status_code}")
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AuthExpiredError("refresh response is not JSON") from exc
        prove = ProveResponse.from_dict(payload)
        access = cleaner.clean_access(prove.raw_access, prove.salts)
        refresh = cleaner.clean_refresh(prove.raw_refresh, prove.salts)
        self._tokens = TokenState(access=access, refresh=refresh,
                                  salts=prove.salts)
        return self._tokens

    # -- request plumbing ------------------------------------------------
    def _send(self, method: str, path: str,
              body: Optional[dict] = None) -> httpx.Response:
        """Send an authed request with at most one 401->refresh retry."""
        self._check_public_path(path)
        if self._tokens is None:
            self.bootstrap()
        assert self._tokens is not None
        self._pace()
        if method == "GET":
            resp = self._http.get(path, headers=self._tokens.auth_header())
        else:
            resp = self._http.post(path, json=body,
                                   headers=self._tokens.auth_header())
        if resp.status_code == 429:
            self._fail_429(resp)
        if resp.status_code == 401:
            # Single normal refresh + retry, mirroring handle401v1.
            self._refresh_once()
            assert self._tokens is not None
            self._pace()
            if method == "GET":
                resp = self._http.get(path,
                                      headers=self._tokens.auth_header())
            else:
                resp = self._http.post(path, json=body,
                                       headers=self._tokens.auth_header())
            if resp.status_code == 429:
                self._fail_429(resp)
            if resp.status_code == 401:
                raise AuthExpiredError(
                    "request still unauthorized after refresh")
        if resp.status_code in (401, 403):
            raise AuthExpiredError(
                f"access rejected with HTTP {resp.status_code}")
        return resp

    # -- public API ---------------------------------------------------------
    def get(self, path: str) -> httpx.Response:
        """GET a public market-data path, with at most one 401->refresh retry."""
        return self._send("GET", path)

    def post(self, path: str, body: Optional[dict] = None) -> httpx.Response:
        """POST a public market-data path (same guards/retry as GET)."""
        return self._send("POST", path, body)

    def get_json(self, path: str) -> object:
        resp = self.get(path)
        resp.raise_for_status()
        return resp.json()

    def post_json(self, path: str, body: Optional[dict] = None) -> object:
        resp = self.post(path, body)
        resp.raise_for_status()
        return resp.json()

    # -- request checksums (mirrors the site's own POST bodies) ------------
    def _market_status_id(self) -> int:
        """Cache the market-open id the site uses as checksum seed."""
        if self._market_id is None:
            payload = self.get_json("/api/nots/nepse-data/market-open")
            if not isinstance(payload, dict) or not isinstance(
                    payload.get("id"), int):
                raise BootstrapError("market-open id has unexpected shape")
            self._market_id = payload["id"]
        assert self._market_id is not None
        return self._market_id

    def _check_base(self) -> tuple[int, tuple[int, ...], int]:
        """(base, salts, day) triple every signed POST derives from."""
        if self._tokens is None:
            self.bootstrap()
        assert self._tokens is not None
        market_id = self._market_status_id()
        day = _ck_day()
        return _ck_base(market_id, day), self._tokens.salts, day

    def _signed(self, variant: str = "raw") -> int:
        """Body ``id`` for signed POSTs: 'raw', 'a', 'b' or 'c'."""
        value, salts, day = self._check_base()
        if variant == "a":
            return _ck_a(value, salts, day)
        if variant == "b":
            return _ck_b(value, salts, day)
        if variant == "c":
            return _ck_c(value, salts, day)
        return value

    # -- debugging ----------------------------------------------------------
    def describe_state(self) -> str:
        """Redacted one-line state for logs; never contains token material."""
        if self._tokens is None:
            return "NepseClient(bootstrapped=False)"
        return (f"NepseClient(bootstrapped=True "
                f"access={redact(self._tokens.access)} "
                f"refresh={redact(self._tokens.refresh)})")
