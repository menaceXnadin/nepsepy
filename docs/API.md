# nepsepy API Reference

> Generated from `nepsepy/` (signatures, docstrings, request
> paths) — regenerate with `python3 gen_api_docs.py`. Discovery provenance
> (which site page fires what) lives in `nepse-api-catalog.md`
> (internal repo note, not published). Browse interactively
> with `python tui.py`.

Base URL: `https://nepalstock.com.np` (override via `NepseClient(base_url=…)`).

## Conventions

- **Auth** — `client.bootstrap()` once (prove → wasm-clean, same as the
  site). One automatic refresh+retry on 401/403, then `AuthExpiredError`.
  Token material is never printed (`describe_state()` redacts to lengths).
- **Paging** — every `page=` argument is **1-based like the UI**. Page 1
  sends no `page` param (like the site); page N sends `page=N-1`.
  `size=` defaults to 20. Responses are Spring pages:
  `{content, totalPages, totalElements, number, size, first, last, empty}`.
- **Dates** — `yyyy-MM-dd` strings (Nepal calendar days as the site uses).
- **Symbols vs ids** — most per-security methods take the numeric
  `security_id` (e.g. `2790` = ACLBSL). Resolve via `securities()` /
  `companies()`; the TUI accepts symbols directly.
- **Signed POSTs** — `today-price`, `floorsheet`, index/company graphs send
  `{"id": <checksum>}` derived from public values (see `checksum.py`);
  handled internally, never passed by callers.
- **Rate** — ≥0.4 s between requests, honors 429/`Retry-After` (max 30 s).
- **Errors** — `NepseError` base; `BootstrapError`, `WasmError`,
  `AuthExpiredError` (incl. still-403-after-refresh), `RateLimitedError`,
  `PublicEndpointError` (non-public path blocked).
- **Binary methods** — `captcha_image`, `fetch_*`, `export_stock_csv`,
  `security_image/file` return `bytes`, not parsed JSON.

## Known-bad backends

These mirror the site's own requests but the server refuses them (verified
against the genuine site, not just this client):

| Method | Symptom |
|---|---|
| `security_floorsheet()` | nginx 403 → `AuthExpiredError("access rejected with HTTP 403")` |
| `book_close()` | HTTP 404 for every id tried |
| `margin_trades()` without date | HTTP 500 on the site's own empty-query call; the method always sends `?businessDate=` (200, currently 0 rows) |

---


## brokers / dealers (reference data)

### `brokers`

```python
def brokers(self, page: int = 1, size: int = 20, criteria: Optional[dict] = None) -> dict:
```

**Request:** POST, GET `/api/nots/member`

Broker directory (Spring page; page 1-based like the UI).

criteria mirrors the Brokers search form: memberName,
contactPerson, contactNumber, memberCode, provinceId, districtId,
municipalityId. The site always sends the full object with
defaults, so missing keys are filled the same way.

### `dealers`

```python
def dealers(self, page: int = 1, size: int = 20, criteria: Optional[dict] = None) -> dict:
```

**Request:** POST, GET `/api/nots/member/dealer`

Dealer directory (same shape/conventions as brokers).

## captcha (suggestion-box flow; read-only steps only)

### `captcha_challenge`

```python
def captcha_challenge(self) -> dict:
```

**Request:** GET `/api/web/captcha/id`

Captcha challenge {id} (public; image/reload hang off the id).

### `captcha_image`

```python
def captcha_image(self, challenge_id: str) -> bytes:
```

**Request:** GET `/api/web/captcha/image/{challenge_id}`

Captcha image bytes (octet-stream). NOTE: the reload sibling
(web/captcha/reload/{id}) currently 500s server-side.

## file downloads (binary; verified live)

### `fetch_application_file`

```python
def fetch_application_file(self, encrypted_id: str) -> bytes:
```

**Request:** GET `/api/nots/application/fetchFiles`

Application/AGM report file (PDF bytes; id from e.g. disclosures).

### `fetch_notice_file`

```python
def fetch_notice_file(self, file_name: str) -> bytes:
```

**Request:** GET `/api/nots/news/notice/fetchFiles/{file_name}`

Notice attachment bytes (fileName from notices()).

### `export_stock_csv`

```python
def export_stock_csv(self, security_id: int, start: Optional[str] = None, end: Optional[str] = None) -> bytes:
```

**Request:** GET `/api/nots/market/export/{security_id}`

Stock Trading CSV export (site's export path; dates 'yyyy-MM-dd').

### `security_image`

```python
def security_image(self, file_location: str) -> bytes:
```

**Request:** GET `/api/nots/security/getImage`

Security image envelope (logos, board portraits) â€” raw body.

The response is JSON ``{"content": "<base64>"}``, NOT raw image
bytes. To process: parse the JSON, take ``["content"]``, strip
whitespace, pad to a multiple of 4 (``+= "=" * (-len(s) % 4)``),
then base64-decode â€” you get JPEG/PNG bytes (magic ``ffd8ff``).
For web display the site's own bundle prefixes the string as
``"data:image/PNG;base64," + content`` straight into an <img>.
``fileLocation`` from e.g. ``security_profile()["logoFilePath"]``
(verified: BARUN logo decodes to a 25 KB JPEG).
NOTE: returns the raw envelope; decoding is left to the caller.

### `security_file`

```python
def security_file(self, file_location: str) -> bytes:
```

**Request:** GET `/api/nots/security/fetchFiles`

Security file bytes (same fileLocation scheme) â€” raw bytes.

Unlike security_image(), this one returns the file directly
(verified: BARUN logo path yields ``image/jpeg`` + JFIF magic,
no envelope). Save the body as-is.

## market status / summary / ticker

### `market_status`

```python
def market_status(self) -> dict:
```

**Request:** GET `/api/nots/nepse-data/market-open`

Market open state (homepage + every page reads this).

### `market_summary`

```python
def market_summary(self) -> list:
```

**Request:** GET `/api/nots/market-summary/`

Homepage summary tiles [{detail, value}].

### `market_summary_history`

```python
def market_summary_history(self) -> list:
```

**Request:** GET `/api/nots/market-summary-history`

Daily history [{businessDate, totalTurnover, ...}].

### `ticker`

```python
def ticker(self, index_id: int = 58) -> list:
```

**Request:** GET `/api/nots/securityDailyTradeStat/{index_id}`

Live ticker strip [{symbol, ltp, ...}] (every page load).

### `live_market`

```python
def live_market(self) -> list:
```

**Request:** GET `/api/nots/lives-market`

Full live snapshot (356 rows: OHLC, volumes, per-security indexId).

The Live Market *page* redirects to `/` while the market is closed,
but the API itself answers 200 regardless â€” verified live.

### `nepse_indices`

```python
def nepse_indices(self) -> list:
```

**Request:** GET `/api/nots/nepse-index`

Index snapshot [{index, close, change, perChange, ...}].

### `sub_indices`

```python
def sub_indices(self) -> list:
```

**Request:** GET `/api/nots`

Sub-index snapshot [{id, index, change, currentValue}].

### `indices_list`

```python
def indices_list(self) -> list:
```

**Request:** GET `/api/nots/index`

Index directory [{id, indexCode, indexName, ...}].

### `index_history`

```python
def index_history(self, index_id: int = 58, page: int = 1, size: int = 20) -> dict:
```

**Request:** GET `/api/nots/index/history/{index_id}`

Datewise index OHLC (Indices page; page is 1-based like the UI).

### `sector_summary`

```python
def sector_summary(self, business_date: Optional[str] = None) -> list:
```

**Request:** GET `/api/nots/sectorwise`

Sector turnover (Sector Summary page; date 'yyyy-MM-dd').

## news / notices / calendar

### `notices`

```python
def notices(self, page: int = 1) -> dict:
```

**Request:** GET `/api/nots/news/notice/all`

Notices (Spring page; page 1-based like the UI).

### `disclosures`

```python
def disclosures(self) -> dict:
```

**Request:** GET `/api/nots/news/companies/disclosure`

Homepage disclosures {exchangeMessages, companyNews}.

### `company_news_list`

```python
def company_news_list(self) -> list:
```

**Request:** GET `/api/nots/news/media/company-news`

Corporate disclosures feed (8836 rows at capture time).

### `news_alerts`

```python
def news_alerts(self, page: int = 1) -> list:
```

**Request:** GET `/api/nots/news/media/news-and-alerts` `/api/nots/news/media/news-and-alerts/`

### `press_releases`

```python
def press_releases(self, page: int = 1) -> list:
```

**Request:** GET `/api/nots/news/press-release`

### `investor_awareness`

```python
def investor_awareness(self) -> list:
```

**Request:** GET `/api/nots/news/media/investor-awareness`

### `holiday_years`

```python
def holiday_years(self) -> list:
```

**Request:** GET `/api/nots/holiday/year`

### `holidays`

```python
def holidays(self, year: int) -> list:
```

**Request:** GET `/api/nots/holiday/list`

Market holidays [{holidayDate, holidayDescription}].

### `menu`

```python
def menu(self) -> list:
```

**Request:** GET `/api/web/menu/`

### `listing_info`

```python
def listing_info(self) -> dict:
```

**Request:** GET `/api/web/listing-info`

Listing Information page content {headline, body} (web CMS).

### `info_officer`

```python
def info_officer(self) -> dict:
```

**Request:** GET `/api/web/info-officer`

Information officer contact (web CMS).

### `about_introduction`

```python
def about_introduction(self, page: Optional[int] = None) -> dict:
```

**Request:** GET `/api/web/about-us/introduction`

About-Us introductions (Spring page; site passes ?page=0-based
only past the first page).

### `about_structure`

```python
def about_structure(self, page: Optional[int] = None) -> dict:
```

**Request:** GET `/api/web/about-us/structure`

About-Us org structure (same paging as introduction).

### `contact_info`

```python
def contact_info(self) -> dict:
```

**Request:** GET `/api/web/about-us/contact-info`

Contact-Us info {contact, id} (web CMS).

## per-security data (GET; mirrors company tabs)

### `security_detail`

```python
def security_detail(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/security/{security_id}`

{securityData, securityMcsData} (Market Depth page header).

### `security_profile`

```python
def security_profile(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/security/profile/{security_id}`

### `board_of_directors`

```python
def board_of_directors(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/security/boardOfDirectors/{security_id}`

### `corporate_actions`

```python
def corporate_actions(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/security/corporate-actions/{security_id}`

Bonus/cash/right [{fiscalYear, bonusPercentage, ...}].

### `financial_reports`

```python
def financial_reports(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/application/reports/{security_id}`

### `agm`

```python
def agm(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/application/agm/{security_id}`

### `security_company_news`

```python
def security_company_news(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/application/company-news/{security_id}`

### `market_security`

```python
def market_security(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/market/security/{security_id}`

Flat daily-trade snapshot + nested security (Listing Information).

### `security_market_picture`

```python
def security_market_picture(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/security-detail/{security_id}`

Compact quote {receivedDateTime, securityId, lastTradedPrice,
openPrice, highPrice, lowPrice} (site's getSecurityDetailsFromMarketPicture).

### `dividends`

```python
def dividends(self, security_id: int) -> list:
```

**Request:** GET `/api/nots/application/dividend/{security_id}`

Dividend applications/news for a security (site's getSecurityDividendNewsById).

### `book_close`

```python
def book_close(self, news_id: int) -> dict:
```

**Request:** GET `/api/nots/news/book-close/{news_id}`

Book-closure news by id (site's getSecurityBookCloseNewsById).

NOTE: currently HTTP 404 for every id tried (security ids and
company-news ids alike), so this is mapped-but-dead like
security_floorsheet() until the backend serves it again.

### `security_price_history`

```python
def security_price_history(self, security_id: int, page: int = 1, size: int = 20, business_date: Optional[str] = None) -> dict:
```

**Request:** GET `/api/nots/market/security/price/{security_id}{query}`

Price History tab (Spring page of OHLCV rows; page 1-based).

### `stock_trading_history`

```python
def stock_trading_history(self, security_id: int, page: int = 1, size: int = 20, start: Optional[str] = None, end: Optional[str] = None) -> dict:
```

**Request:** GET `/api/nots/market/history/security/{security_id}{query}`

Stock Trading page (page 1-based; dates 'yyyy-MM-dd').

### `trading_average`

```python
def trading_average(self, n_days: int = 120, business_date: Optional[str] = None, stock_id: Optional[int] = None) -> list:
```

**Request:** GET `/api/nots/nepse-data/trading-average`

N-day average price per security (Trading Average page).

### `market_cap_history`

```python
def market_cap_history(self, page: int = 1) -> list:
```

**Request:** GET `/api/nots/nepse-data/marcapbydate/`

Daily market caps [{businessDate, marCap, ...}] (filter client-side).

## securities directory

### `securities`

```python
def securities(self) -> list:
```

**Request:** GET `/api/nots/securities`

All securities [{securityId, securityName, securitySymbol}].

### `companies`

```python
def companies(self) -> list:
```

**Request:** GET `/api/nots/security`

Non-delisted companies (selectors site-wide).

### `companies_list`

```python
def companies_list(self) -> list:
```

**Request:** GET `/api/nots/company/list`

Listed companies directory.

### `companies_paged`

```python
def companies_paged(self, page: int = 1) -> dict:
```

**Request:** GET `/api/nots/company/`

Combined directory {companies: Spring page, securities: 938 flat}.

(Site's getListsOfCompanies(); page 1-based like the UI.)

### `margin_companies`

```python
def margin_companies(self) -> list:
```

**Request:** GET `/api/nots/company/margin-list`

Margin-tradable companies.

### `sectors`

```python
def sectors(self) -> dict:
```

**Request:** GET `/api/nots/sector`

Sector directory {sectors[{id, sectorDescription, regulatoryBody}]}.

### `debentures`

```python
def debentures(self, instrument_type: str = "govBonds") -> list:
```

**Request:** GET `/api/nots/company/debentureAndBond`

Listed debentures/bonds (Listing menu page; ``?type=`` required).

Verified against the live page dropdown: ``"govBonds"`` (default,
68 government bonds) and ``"debenture"`` (77 corporate debentures).
Unknown values fall back to the bond list server-side.

### `companies_non_promoter`

```python
def companies_non_promoter(self) -> list:
```

**Request:** GET `/api/nots/security`

Non-promoter securities [{id, symbol, securityName, ...}].

Filter source on the Listed Securities / Margin Securities pages
(``security?nonPromoter=true`` â€” 649 rows, flatter than companies()).

### `share_groups`

```python
def share_groups(self) -> list:
```

**Request:** GET `/api/nots/security/shareGroup/`

Share groups [{id, name}] â€” names A/Z/B/G drive classification().

### `classification`

```python
def classification(self, page: int = 1, size: int = 20, share_group: Optional[str] = None) -> dict:
```

**Request:** GET `/api/nots/security/classification{query}`

Company Classification page (Spring page; page 1-based like the UI;
share_group is the A/Z/B/G letter â€” verified exhaustive: 31/107/108/34).

### `promoters`

```python
def promoters(self, page: int = 1, size: int = 20) -> dict:
```

**Request:** GET `/api/nots/security/promoters`

Promoter Share page (Spring page, 289 rows; page 1-based).

### `report_types`

```python
def report_types(self) -> list:
```

**Request:** GET `/api/nots/report/report-types`

Report directory (Reports menu: Weekly/Monthly/Annual/AGM/Other).

### `reports_by_category`

```python
def reports_by_category(self, category_id: int, page: int = 1, size: int = 20) -> dict:
```

**Request:** GET `/api/web/report/reportByCategory/{category_id}`

Report files by category (Reports pages; category id = report
type id 1..5; page 1-based like the UI; category 5 is empty).

### `events`

```python
def events(self, page: int = 1, size: int = 20) -> dict:
```

**Request:** GET `/api/web/event`

Events page (Spring page; site grid uses size=6).

### `margin_trades`

```python
def margin_trades(self, business_date: Optional[str] = None) -> dict:
```

**Request:** GET `/api/margin/trades-report`

Margin Trades page ({content Spring page, totalAmountInvested}).

``business_date`` defaults to the market ``asOf`` day. NOTE: the
site itself calls this endpoint with an empty query and gets HTTP
500 back; ``?businessDate=`` answers 200 (empty as of 2026-09-24).

## signed POST: company data

### `company_info`

```python
def company_info(self, security_id: int) -> dict:
```

**Request:** POST (signed POST body variant raw) `/api/nots/security/{security_id}`

Company header {securityDailyTradeDto, security, ...} (detail page).

### `company_graph`

```python
def company_graph(self, security_id: int) -> list:
```

**Request:** POST (signed POST body variant raw) `/api/nots/market/graphdata/{security_id}`

Company OHLC history [{businessDate, openPrice, ...}] (chart tab).

### `company_graph_intraday`

```python
def company_graph_intraday(self, security_id: int) -> list:
```

**Request:** POST (signed POST body variant raw) `/api/nots/market/graphdata/daily/{security_id}`

Company intraday LTP (Charts Company tab, 1D range).

## signed POST: floorsheet

### `floorsheets`

```python
def floorsheets(self, page: int = 1, size: int = 20, contract_no: Optional[int] = None, stock_id: Optional[int] = None, buyer_broker: Optional[int] = None, seller_broker: Optional[int] = None, sort_by: str = "contractId", sort_order: str = "desc") -> dict:
```

**Request:** POST (signed POST body variant c) `/api/nots/nepse-data/floorsheet{query}`

Floor Sheet page ({totalAmount, totalQty, totalTrades, floorsheets};
page 1-based like the UI).

### `security_floorsheet`

```python
def security_floorsheet(self, security_id: int, business_date: Optional[str] = None, page: int = 1, size: int = 20, sort_by: str = "contractId", sort_order: str = "asc") -> dict:
```

**Request:** POST (signed POST body variant c) `/api/nots/security/floorsheet/{security_id}{query}`

Per-security Floor Sheet tab (company modal).

Mirrors the site's own tab request:
``POST /api/nots/security/floorsheet/{id}?[&businessDate=]...``.
``business_date`` defaults to the market ``asOf`` day like the UI.

NOTE: the server currently answers nginx ``403 Forbidden`` to this
request â€” including requests made by the genuine site itself â€”
so this method exists for the day they fix it server-side. Until
then it raises ``AuthExpiredError("access rejected with HTTP 403")``
after the normal single refresh + retry. The checksum variant is
likewise unverified; it follows the sibling floorsheet endpoint
(variant C).

## signed POST: index graphs

### `index_intraday`

```python
def index_intraday(self, index_id: int = 58) -> list:
```

**Request:** POST (signed POST body variant a) `/api/nots/graph/index/{index_id}`

Intraday index chart [[epochSeconds, value]] (homepage graph).

### `index_range`

```python
def index_range(self, index_code: int, start: str, end: str) -> list:
```

**Request:** POST (signed POST body variant a) `/api/nots/graph/index`

Index chart over a range (Charts 1W/1M/1Q/1Y; dates 'yyyy-MM-dd').

## signed POST: today price

### `today_price`

```python
def today_price(self, page: int = 1, size: int = 20, security_id: Optional[int] = None, business_date: Optional[str] = None, sort_by: str = "", sort_order: str = "") -> dict:
```

**Request:** POST (signed POST body variant b) `/api/nots/nepse-data/today-price{query}`

Today's Price table (Spring page; page 1-based like the UI).

### `today_price_all`

```python
def today_price_all(self, business_date: Optional[str] = None) -> list:
```

**Request:** POST (signed POST body variant b) `/api/nots/nepse-data/todays-price/`

Full Today's Price list behind the CSV export.

## supply / demand / depth

### `supply_demand`

```python
def supply_demand(self, full: bool = False) -> dict:
```

**Request:** GET `/api/nots/nepse-data/supplydemand`

Top supply/demand {supplyList, demandList}.

### `market_depth`

```python
def market_depth(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/nepse-data/marketdepth/{security_id}`

Order book {totalBuyQty, totalSellQty, marketDepth{...}}.

### `odd_lot_depth`

```python
def odd_lot_depth(self, security_id: int) -> dict:
```

**Request:** GET `/api/nots/nepse-data/marketdepth-ol/{security_id}`

Odd-lot order book (same shape as market_depth).

## top tens

### `top_gainers`

```python
def top_gainers(self, full: bool = False) -> list:
```

Top gainers [{symbol, ltp, pointChange, percentageChange, ...}].

### `top_losers`

```python
def top_losers(self, full: bool = False) -> list:
```

Top losers (same shape as gainers).

### `top_turnover`

```python
def top_turnover(self, full: bool = False) -> list:
```

Top by turnover.

### `top_traded_shares`

```python
def top_traded_shares(self, full: bool = False) -> list:
```

Top by shares traded.

### `top_transactions`

```python
def top_transactions(self, full: bool = False) -> list:
```

Top by transaction count.

### `top_active`

```python
def top_active(self, full: bool = False) -> list:
```

Most active scrips (trade quantity).
