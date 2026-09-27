# nepse-public-client

Unofficial Python client for the **public** market-data endpoints of the
Nepal Stock Exchange (https://nepalstock.com.np) — today's prices, floor
sheets, market depth, indices and charts, company filings, sector
summaries, brokers, notices, and more. It performs the same login-less
handshake the site's own frontend does; no credentials, no scraping of
private pages.

## Install

```bash
pip install nepse-public-client
```

Requires Python 3.10+ and `httpx` + `wasmtime` (installed automatically).

## Quick start

```python
from nepse_client import NepseClient

with NepseClient() as client:
    print(client.market_status())
    print(client.top_gainers())
    print(client.today_price(page=1, size=20))
    sheet = client.floorsheets(stock_id=686)   # BARUN
    print(sheet.get("totalTrades"), sheet.get("totalAmount"))
```

Every client bootstraps its own session on first use; tokens live in
memory only and are never logged. Requests are paced conservatively and
`429`/`Retry-After` responses are honored.

## What you can do

- **Market** — status, summary, live snapshot, ticker, top gainers /
  losers / turnover / traded shares / transactions / most active.
- **Prices & trades** — today-price table (14 sort columns), floor sheet
  with stock/broker/contract filters, market depth + odd lots,
  supply/demand, trading history, trading averages, market-cap history.
- **Indices & charts** — NEPSE/sub-indices, datewise history, intraday
  and range charts, per-company OHLC graphs.
- **Companies** — info, profile, price history, board, corporate actions,
  financials, AGM, dividends, news/filings with document attachments.
  Pass security ids (resolve symbols via `companies()`).
- **Directories** — sectors, share groups, classification, promoters,
  debentures/bonds, company lists, margin companies, brokers.
- **News & files** — notices, disclosures, company news feed, reports,
  events, holidays, file downloads, trading CSV export, captcha.

```python
with NepseClient() as client:
    news = client.security_company_news(686)
    print(news[0]["companyNews"]["newsHeadline"])
    prof = client.security_profile(686)
    print(prof["logoFilePath"])
```

Pages are 1-based (like the site); dates are `yyyy-MM-dd`. A few NEPSE
backends are broken server-side (their own site fails too) — those
methods raise with a note in the docstring.

## Interactive explorer

```bash
python tui.py
```

Browse everything from the terminal — no token material is ever printed.

## Scope & disclaimer

This is an unofficial, read-only client for publicly accessible data.
It does not touch login, admin/CMS, or any state-changing endpoints. Not
affiliated with the Nepal Stock Exchange. Data is delayed per exchange
rules; verify before trading.

## License

MIT — see `LICENSE`.
