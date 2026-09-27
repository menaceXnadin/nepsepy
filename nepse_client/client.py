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

CLIENT_UA = "nepse-public-client/1.0 (+public market-data observer)"
MIN_INTERVAL_S = 0.4  # at most ~2-3 requests/second
TIMEOUT_S = 15.0
MAX_RETRY_AFTER_S = 30.0


class NepseClient:
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
            raise BootstrapError(f"prove request failed: {type(exc).__name__}") from exc
        if resp.status_code == 429:
            self._fail_429(resp)
        if resp.status_code != 200:
            raise BootstrapError(f"prove rejected with HTTP {resp.status_code}")
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

    # -- market status / summary / ticker --------------------------------
    def market_status(self) -> dict:
        """Market open state (homepage + every page reads this)."""
        return self.get_json("/api/nots/nepse-data/market-open")  # type: ignore[return-value]

    def market_summary(self) -> list:
        """Homepage summary tiles [{detail, value}]."""
        return self.get_json("/api/nots/market-summary/")  # type: ignore[return-value]

    def market_summary_history(self) -> list:
        """Daily history [{businessDate, totalTurnover, ...}]."""
        return self.get_json("/api/nots/market-summary-history")  # type: ignore[return-value]

    def ticker(self, index_id: int = 58) -> list:
        """Live ticker strip [{symbol, ltp, ...}] (every page load)."""
        return self.get_json(f"/api/nots/securityDailyTradeStat/{index_id}")  # type: ignore[return-value]

    def live_market(self) -> list:
        """Full live snapshot (356 rows: OHLC, volumes, per-security indexId).

        The Live Market *page* redirects to `/` while the market is closed,
        but the API itself answers 200 regardless — verified live.
        """
        return self.get_json("/api/nots/lives-market")  # type: ignore[return-value]

    def nepse_indices(self) -> list:
        """Index snapshot [{index, close, change, perChange, ...}]."""
        return self.get_json("/api/nots/nepse-index")  # type: ignore[return-value]

    def sub_indices(self) -> list:
        """Sub-index snapshot [{id, index, change, currentValue}]."""
        return self.get_json("/api/nots")  # type: ignore[return-value]

    def indices_list(self) -> list:
        """Index directory [{id, indexCode, indexName, ...}]."""
        return self.get_json("/api/nots/index")  # type: ignore[return-value]

    def index_history(self, index_id: int = 58, page: int = 1,
                      size: int = 20) -> dict:
        """Datewise index OHLC (Indices page; page is 1-based like the UI)."""
        path = f"/api/nots/index/history/{index_id}?&size={size}"
        if page > 1:
            path = f"/api/nots/index/history/{index_id}?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def sector_summary(self, business_date: Optional[str] = None) -> list:
        """Sector turnover (Sector Summary page; date 'yyyy-MM-dd')."""
        path = "/api/nots/sectorwise"
        if business_date:
            path += f"?businessDate={business_date}"
        return self.get_json(path)  # type: ignore[return-value]

    # -- securities directory ----------------------------------------------
    def securities(self) -> list:
        """All securities [{securityId, securityName, securitySymbol}]."""
        return self.get_json("/api/nots/securities")  # type: ignore[return-value]

    def companies(self) -> list:
        """Non-delisted companies (selectors site-wide)."""
        return self.get_json("/api/nots/security?nonDelisted=true")  # type: ignore[return-value]

    def companies_list(self) -> list:
        """Listed companies directory."""
        return self.get_json("/api/nots/company/list")  # type: ignore[return-value]

    def companies_paged(self, page: int = 1) -> dict:
        """Combined directory {companies: Spring page, securities: 938 flat}.

        (Site's getListsOfCompanies(); page 1-based like the UI.)"""
        path = "/api/nots/company/"
        if page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def margin_companies(self) -> list:
        """Margin-tradable companies."""
        return self.get_json("/api/nots/company/margin-list")  # type: ignore[return-value]

    def sectors(self) -> dict:
        """Sector directory {sectors[{id, sectorDescription, regulatoryBody}]}."""
        return self.get_json("/api/nots/sector")  # type: ignore[return-value]

    def debentures(self, instrument_type: str = "govBonds") -> list:
        """Listed debentures/bonds (Listing menu page; ``?type=`` required).

        Verified against the live page dropdown: ``"govBonds"`` (default,
        68 government bonds) and ``"debenture"`` (77 corporate debentures).
        Unknown values fall back to the bond list server-side.
        """
        return self.get_json(  # type: ignore[return-value]
            f"/api/nots/company/debentureAndBond?type={instrument_type}")

    def companies_non_promoter(self) -> list:
        """Non-promoter securities [{id, symbol, securityName, ...}].

        Filter source on the Listed Securities / Margin Securities pages
        (``security?nonPromoter=true`` — 649 rows, flatter than companies()).
        """
        return self.get_json("/api/nots/security?nonPromoter=true")  # type: ignore[return-value]

    def share_groups(self) -> list:
        """Share groups [{id, name}] — names A/Z/B/G drive classification()."""
        return self.get_json("/api/nots/security/shareGroup/")  # type: ignore[return-value]

    def classification(self, page: int = 1, size: int = 20,
                       share_group: Optional[str] = None) -> dict:
        """Company Classification page (Spring page; page 1-based like the UI;
        share_group is the A/Z/B/G letter — verified exhaustive: 31/107/108/34)."""
        query = f"?&size={size}"
        if share_group is not None:
            query += f"&shareGroup={share_group}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.get_json(f"/api/nots/security/classification{query}")  # type: ignore[return-value]

    def promoters(self, page: int = 1, size: int = 20) -> dict:
        """Promoter Share page (Spring page, 289 rows; page 1-based)."""
        path = "/api/nots/security/promoters?&size=" + str(size)
        if page > 1:
            path = f"/api/nots/security/promoters?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def report_types(self) -> list:
        """Report directory (Reports menu: Weekly/Monthly/Annual/AGM/Other)."""
        return self.get_json("/api/nots/report/report-types")  # type: ignore[return-value]

    def reports_by_category(self, category_id: int, page: int = 1,
                            size: int = 20) -> dict:
        """Report files by category (Reports pages; category id = report
        type id 1..5; page 1-based like the UI; category 5 is empty)."""
        path = f"/api/web/report/reportByCategory/{category_id}?"
        if page > 1 or size != 20:
            path = (f"/api/web/report/reportByCategory/{category_id}?"
                    f"page={page - 1}&size={size}")
        return self.get_json(path)  # type: ignore[return-value]

    def events(self, page: int = 1, size: int = 20) -> dict:
        """Events page (Spring page; site grid uses size=6)."""
        path = "/api/web/event?&size=" + str(size)
        if page > 1:
            path = f"/api/web/event?page={page - 1}&size={size}"
        return self.get_json(path)  # type: ignore[return-value]

    def margin_trades(self, business_date: Optional[str] = None) -> dict:
        """Margin Trades page ({content Spring page, totalAmountInvested}).

        ``business_date`` defaults to the market ``asOf`` day. NOTE: the
        site itself calls this endpoint with an empty query and gets HTTP
        500 back; ``?businessDate=`` answers 200 (empty as of 2026-09-24).
        """
        if business_date is None:
            business_date = str(self.market_status().get("asOf", ""))[:10]
        return self.get_json(  # type: ignore[return-value]
            f"/api/margin/trades-report?businessDate={business_date}")

    # -- top tens ------------------------------------------------------------
    def _top_ten(self, kind: str, full: bool = False) -> list:
        return self.get_json(f"/api/nots/top-ten/{kind}?all={str(full).lower()}")  # type: ignore[return-value]

    def top_gainers(self, full: bool = False) -> list:
        """Top gainers [{symbol, ltp, pointChange, percentageChange, ...}]."""
        return self._top_ten("top-gainer", full)

    def top_losers(self, full: bool = False) -> list:
        """Top losers (same shape as gainers)."""
        return self._top_ten("top-loser", full)

    def top_turnover(self, full: bool = False) -> list:
        """Top by turnover."""
        return self._top_ten("turnover", full)

    def top_traded_shares(self, full: bool = False) -> list:
        """Top by shares traded."""
        return self._top_ten("trade", full)

    def top_transactions(self, full: bool = False) -> list:
        """Top by transaction count."""
        return self._top_ten("transaction", full)

    def top_active(self, full: bool = False) -> list:
        """Most active scrips (trade quantity)."""
        return self._top_ten("trade-qty", full)

    # -- supply / demand / depth ----------------------------------------------
    def supply_demand(self, full: bool = False) -> dict:
        """Top supply/demand {supplyList, demandList}."""
        return self.get_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/supplydemand?all={str(full).lower()}")

    def market_depth(self, security_id: int) -> dict:
        """Order book {totalBuyQty, totalSellQty, marketDepth{...}}."""
        return self.get_json(f"/api/nots/nepse-data/marketdepth/{security_id}")  # type: ignore[return-value]

    def odd_lot_depth(self, security_id: int) -> dict:
        """Odd-lot order book (same shape as market_depth)."""
        return self.get_json(f"/api/nots/nepse-data/marketdepth-ol/{security_id}")  # type: ignore[return-value]

    # -- per-security data (GET; mirrors company tabs) --------------------------
    def security_detail(self, security_id: int) -> dict:
        """{securityData, securityMcsData} (Market Depth page header)."""
        return self.get_json(f"/api/nots/security/{security_id}")  # type: ignore[return-value]

    def security_profile(self, security_id: int) -> dict:
        return self.get_json(f"/api/nots/security/profile/{security_id}")  # type: ignore[return-value]

    def board_of_directors(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/security/boardOfDirectors/{security_id}")  # type: ignore[return-value]

    def corporate_actions(self, security_id: int) -> list:
        """Bonus/cash/right [{fiscalYear, bonusPercentage, ...}]."""
        return self.get_json(f"/api/nots/security/corporate-actions/{security_id}")  # type: ignore[return-value]

    def financial_reports(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/reports/{security_id}")  # type: ignore[return-value]

    def agm(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/agm/{security_id}")  # type: ignore[return-value]

    def security_company_news(self, security_id: int) -> list:
        return self.get_json(f"/api/nots/application/company-news/{security_id}")  # type: ignore[return-value]

    def market_security(self, security_id: int) -> dict:
        """Flat daily-trade snapshot + nested security (Listing Information)."""
        return self.get_json(f"/api/nots/market/security/{security_id}")  # type: ignore[return-value]

    def security_market_picture(self, security_id: int) -> dict:
        """Compact quote {receivedDateTime, securityId, lastTradedPrice,
        openPrice, highPrice, lowPrice} (site's getSecurityDetailsFromMarketPicture)."""
        return self.get_json(f"/api/nots/security-detail/{security_id}")  # type: ignore[return-value]

    def dividends(self, security_id: int) -> list:
        """Dividend applications/news for a security (site's getSecurityDividendNewsById)."""
        return self.get_json(f"/api/nots/application/dividend/{security_id}")  # type: ignore[return-value]

    def book_close(self, news_id: int) -> dict:
        """Book-closure news by id (site's getSecurityBookCloseNewsById).

        NOTE: currently HTTP 404 for every id tried (security ids and
        company-news ids alike), so this is mapped-but-dead like
        security_floorsheet() until the backend serves it again.
        """
        return self.get_json(f"/api/nots/news/book-close/{news_id}")  # type: ignore[return-value]

    def security_price_history(self, security_id: int, page: int = 1,
                               size: int = 20,
                               business_date: Optional[str] = None) -> dict:
        """Price History tab (Spring page of OHLCV rows; page 1-based)."""
        query = f"?&size={size}"
        if business_date:
            query += f"&businessDate={business_date}"
        if page > 1:
            query = f"?page={page - 1}&size={size}" + (
                f"&businessDate={business_date}" if business_date else "")
        return self.get_json(f"/api/nots/market/security/price/{security_id}{query}")  # type: ignore[return-value]

    def stock_trading_history(self, security_id: int, page: int = 1,
                              size: int = 20,
                              start: Optional[str] = None,
                              end: Optional[str] = None) -> dict:
        """Stock Trading page (page 1-based; dates 'yyyy-MM-dd')."""
        query = f"?&size={size}"
        if start:
            query += f"&startDate={start}"
        if end:
            query += f"&endDate={end}"
        if page > 1:
            query = f"?page={page - 1}&size={size}" + (
                f"&startDate={start}" if start else "") + (
                    f"&endDate={end}" if end else "")
        return self.get_json(f"/api/nots/market/history/security/{security_id}{query}")  # type: ignore[return-value]

    def trading_average(self, n_days: int = 120,
                        business_date: Optional[str] = None,
                        stock_id: Optional[int] = None) -> list:
        """N-day average price per security (Trading Average page)."""
        path = f"/api/nots/nepse-data/trading-average?nDays={n_days}"
        if business_date:
            path += f"&businessDate={business_date}"
        if stock_id is not None:
            path += f"&stockId={stock_id}"
        return self.get_json(path)  # type: ignore[return-value]

    def market_cap_history(self, page: int = 1) -> list:
        """Daily market caps [{businessDate, marCap, ...}] (filter client-side)."""
        path = "/api/nots/nepse-data/marcapbydate/?"
        if page > 1:
            path = f"/api/nots/nepse-data/marcapbydate/?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    # -- signed POST: today price ----------------------------------------------
    def today_price(self, page: int = 1, size: int = 20,
                    security_id: Optional[int] = None,
                    business_date: Optional[str] = None,
                    sort_by: str = "", sort_order: str = "") -> dict:
        """Today's Price table (Spring page; page 1-based like the UI)."""
        query = f"?&size={size}"
        if security_id is not None:
            query += f"&securityId={security_id}"
        if business_date:
            query += f"&businessDate={business_date}"
        if sort_by:
            query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/today-price{query}",
            {"id": self._signed("b")})

    def today_price_all(self, business_date: Optional[str] = None) -> list:
        """Full Today's Price list behind the CSV export."""
        path = "/api/nots/nepse-data/todays-price/"
        if business_date:
            path += f"?businessDate={business_date}"
        return self.post_json(path, {"id": self._signed("b")})  # type: ignore[return-value]

    # -- signed POST: floorsheet -------------------------------------------------
    def floorsheets(self, page: int = 1, size: int = 20,
                    contract_no: Optional[int] = None,
                    stock_id: Optional[int] = None,
                    buyer_broker: Optional[int] = None,
                    seller_broker: Optional[int] = None,
                    sort_by: str = "contractId",
                    sort_order: str = "desc") -> dict:
        """Floor Sheet page ({totalAmount, totalQty, totalTrades, floorsheets};
        page 1-based like the UI)."""
        query = f"?&size={size}"
        if stock_id is not None:
            query += f"&stockId={stock_id}"
        if contract_no is not None:
            query += f"&contractNo={contract_no}"
        if buyer_broker is not None:
            query += f"&buyerBroker={buyer_broker}"
        if seller_broker is not None:
            query += f"&sellerBroker={seller_broker}"
        query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/nepse-data/floorsheet{query}",
            {"id": self._signed("c")})

    def security_floorsheet(self, security_id: int,
                            business_date: Optional[str] = None,
                            page: int = 1, size: int = 20,
                            sort_by: str = "contractId",
                            sort_order: str = "asc") -> dict:
        """Per-security Floor Sheet tab (company modal).

        Mirrors the site's own tab request:
        ``POST /api/nots/security/floorsheet/{id}?[&businessDate=]...``.
        ``business_date`` defaults to the market ``asOf`` day like the UI.

        NOTE: the server currently answers nginx ``403 Forbidden`` to this
        request — including requests made by the genuine site itself —
        so this method exists for the day they fix it server-side. Until
        then it raises ``AuthExpiredError("access rejected with HTTP 403")``
        after the normal single refresh + retry. The checksum variant is
        likewise unverified; it follows the sibling floorsheet endpoint
        (variant C).
        """
        if business_date is None:
            business_date = str(self.market_status().get("asOf", ""))[:10]
        query = f"?businessDate={business_date}&size={size}"
        query += f"&sort={sort_by},{sort_order}"
        if page > 1:
            query = query.replace("?", f"?page={page - 1}", 1)
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/security/floorsheet/{security_id}{query}",
            {"id": self._signed("c")})

    # -- signed POST: index graphs -----------------------------------------------
    def index_intraday(self, index_id: int = 58) -> list:
        """Intraday index chart [[epochSeconds, value]] (homepage graph)."""
        return self.post_json(f"/api/nots/graph/index/{index_id}",  # type: ignore[return-value]
                              {"id": self._signed("a")})

    def index_range(self, index_code: int, start: str, end: str) -> list:
        """Index chart over a range (Charts 1W/1M/1Q/1Y; dates 'yyyy-MM-dd')."""
        return self.post_json(  # type: ignore[return-value]
            f"/api/nots/graph/index?indexCode={index_code}"
            f"&startDate={start}&endDate={end}",
            {"id": self._signed("a")})

    # -- signed POST: company data --------------------------------------------------
    def company_info(self, security_id: int) -> dict:
        """Company header {securityDailyTradeDto, security, ...} (detail page)."""
        return self.post_json(f"/api/nots/security/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

    def company_graph(self, security_id: int) -> list:
        """Company OHLC history [{businessDate, openPrice, ...}] (chart tab)."""
        return self.post_json(f"/api/nots/market/graphdata/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

    def company_graph_intraday(self, security_id: int) -> list:
        """Company intraday LTP (Charts Company tab, 1D range)."""
        return self.post_json(f"/api/nots/market/graphdata/daily/{security_id}",  # type: ignore[return-value]
                              {"id": self._signed("raw")})

    # -- news / notices / calendar -----------------------------------------------------
    def notices(self, page: int = 1) -> dict:
        """Notices (Spring page; page 1-based like the UI)."""
        return self.get_json(f"/api/nots/news/notice/all?page={page - 1}")  # type: ignore[return-value]

    def disclosures(self) -> dict:
        """Homepage disclosures {exchangeMessages, companyNews}."""
        return self.get_json("/api/nots/news/companies/disclosure")  # type: ignore[return-value]

    def company_news_list(self) -> list:
        """Corporate disclosures feed (8836 rows at capture time)."""
        return self.get_json("/api/nots/news/media/company-news")  # type: ignore[return-value]

    def news_alerts(self, page: int = 1) -> list:
        if page <= 1:
            return self.get_json("/api/nots/news/media/news-and-alerts")  # type: ignore[return-value]
        return self.get_json(f"/api/nots/news/media/news-and-alerts/?page={page - 1}")  # type: ignore[return-value]

    def press_releases(self, page: int = 1) -> list:
        if page <= 1:
            return self.get_json("/api/nots/news/press-release")  # type: ignore[return-value]
        return self.get_json(f"/api/nots/news/press-release?page={page - 1}")  # type: ignore[return-value]

    def investor_awareness(self) -> list:
        return self.get_json("/api/nots/news/media/investor-awareness")  # type: ignore[return-value]

    def holiday_years(self) -> list:
        return self.get_json("/api/nots/holiday/year")  # type: ignore[return-value]

    def holidays(self, year: int) -> list:
        """Market holidays [{holidayDate, holidayDescription}]."""
        return self.get_json(f"/api/nots/holiday/list?year={year}")  # type: ignore[return-value]

    def menu(self) -> list:
        return self.get_json("/api/web/menu/")  # type: ignore[return-value]

    def listing_info(self) -> dict:
        """Listing Information page content {headline, body} (web CMS)."""
        return self.get_json("/api/web/listing-info")  # type: ignore[return-value]

    def info_officer(self) -> dict:
        """Information officer contact (web CMS)."""
        return self.get_json("/api/web/info-officer")  # type: ignore[return-value]

    def about_introduction(self, page: Optional[int] = None) -> dict:
        """About-Us introductions (Spring page; site passes ?page=0-based
        only past the first page)."""
        path = "/api/web/about-us/introduction"
        if page is not None and page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def about_structure(self, page: Optional[int] = None) -> dict:
        """About-Us org structure (same paging as introduction)."""
        path = "/api/web/about-us/structure"
        if page is not None and page > 1:
            path += f"?page={page - 1}"
        return self.get_json(path)  # type: ignore[return-value]

    def contact_info(self) -> dict:
        """Contact-Us info {contact, id} (web CMS)."""
        return self.get_json("/api/web/about-us/contact-info")  # type: ignore[return-value]

    # -- captcha (suggestion-box flow; read-only steps only) -------------------
    def captcha_challenge(self) -> dict:
        """Captcha challenge {id} (public; image/reload hang off the id)."""
        return self.get_json("/api/web/captcha/id")  # type: ignore[return-value]

    def captcha_image(self, challenge_id: str) -> bytes:
        """Captcha image bytes (octet-stream). NOTE: the reload sibling
        (web/captcha/reload/{id}) currently 500s server-side."""
        return self.get(
            f"/api/web/captcha/image/{challenge_id}").content

    # -- file downloads (binary; verified live) --------------------------------
    def fetch_application_file(self, encrypted_id: str) -> bytes:
        """Application/AGM report file (PDF bytes; id from e.g. disclosures)."""
        return self.get(  # type: ignore[return-value]
            f"/api/nots/application/fetchFiles?encryptedId={encrypted_id}").content

    def fetch_notice_file(self, file_name: str) -> bytes:
        """Notice attachment bytes (fileName from notices())."""
        return self.get(  # type: ignore[return-value]
            f"/api/nots/news/notice/fetchFiles/{file_name}").content

    def export_stock_csv(self, security_id: int,
                         start: Optional[str] = None,
                         end: Optional[str] = None) -> bytes:
        """Stock Trading CSV export (site's export path; dates 'yyyy-MM-dd')."""
        path = f"/api/nots/market/export/{security_id}"
        query = "&".join(
            [f"startDate={start}" for _ in [0] if start] +
            [f"endDate={end}" for _ in [0] if end])
        if query:
            path += "?" + query
        return self.get(path).content

    def security_image(self, file_location: str) -> bytes:
        """Security image envelope (logos, board portraits) — raw body.

        The response is JSON ``{"content": "<base64>"}``, NOT raw image
        bytes. To process: parse the JSON, take ``["content"]``, strip
        whitespace, pad to a multiple of 4 (``+= "=" * (-len(s) % 4)``),
        then base64-decode — you get JPEG/PNG bytes (magic ``ffd8ff``).
        For web display the site's own bundle prefixes the string as
        ``"data:image/PNG;base64," + content`` straight into an <img>.
        ``fileLocation`` from e.g. ``security_profile()["logoFilePath"]``
        (verified: BARUN logo decodes to a 25 KB JPEG).
        NOTE: returns the raw envelope; decoding is left to the caller.
        """
        return self.get(  # type: ignore[return-value]
            f"/api/nots/security/getImage?fileLocation={file_location}").content

    def security_file(self, file_location: str) -> bytes:
        """Security file bytes (same fileLocation scheme) — raw bytes.

        Unlike security_image(), this one returns the file directly
        (verified: BARUN logo path yields ``image/jpeg`` + JFIF magic,
        no envelope). Save the body as-is.
        """
        return self.get(  # type: ignore[return-value]
            f"/api/nots/security/fetchFiles?fileLocation={file_location}").content

    # -- brokers / dealers (reference data) --------------------------------------
    def brokers(self, page: int = 1, size: int = 20,
                criteria: Optional[dict] = None) -> dict:
        """Broker directory (Spring page; page 1-based like the UI).

        criteria mirrors the Brokers search form: memberName,
        contactPerson, contactNumber, memberCode, provinceId, districtId,
        municipalityId. The site always sends the full object with
        defaults, so missing keys are filled the same way.
        """
        if page > 1:
            path = f"/api/nots/member?page={page - 1}&size={size}"
        else:
            path = f"/api/nots/member?&size={size}"
        if criteria:
            body = {"memberName": "", "contactPerson": "",
                    "contactNumber": "", "memberCode": "", "provinceId": 0,
                    "districtId": 0, "municipalityId": 0}
            body.update(criteria)
            return self.post_json(path, body)  # type: ignore[return-value]
        return self.get_json(path)  # type: ignore[return-value]

    def dealers(self, page: int = 1, size: int = 20,
                criteria: Optional[dict] = None) -> dict:
        """Dealer directory (same shape/conventions as brokers)."""
        if page > 1:
            path = f"/api/nots/member/dealer?page={page - 1}&size={size}"
        else:
            path = f"/api/nots/member/dealer?&size={size}"
        if criteria:
            body = {"memberName": "", "contactPerson": "",
                    "contactNumber": "", "memberCode": "", "provinceId": 0,
                    "districtId": 0, "municipalityId": 0}
            body.update(criteria)
            return self.post_json(path, body)  # type: ignore[return-value]
        return self.get_json(path)  # type: ignore[return-value]

    # -- debugging ----------------------------------------------------------
    def describe_state(self) -> str:
        """Redacted one-line state for logs; never contains token material."""
        if self._tokens is None:
            return "NepseClient(bootstrapped=False)"
        return (f"NepseClient(bootstrapped=True "
                f"access={redact(self._tokens.access)} "
                f"refresh={redact(self._tokens.refresh)})")
