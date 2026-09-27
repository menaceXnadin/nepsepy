# nepsepy

`nepsepy` is an unofficial Python client for publicly available Nepal Stock
Exchange (NEPSE) market data. It provides a small, synchronous API for market
status, prices, floor sheets, indices, company information, notices, and other
data used by the NEPSE website.

It is not affiliated with the Nepal Stock Exchange.

## Installation

Requires Python 3.10 or later.

```bash
python -m pip install nepsepy
```

The PyPI distribution is named `nepsepy`; the Python import package is
`nepse_client`.

## Quick start

```python
from nepse_client import NepseClient

with NepseClient() as client:
    status = client.market_status()
    gainers = client.top_gainers()
    prices = client.today_price(page=1, size=20)

    print(status["isOpen"])
    print(gainers[:3])
    print(prices["content"][:3])
```

Most methods return the JSON object or list supplied by NEPSE. Pagination uses
1-based page numbers, matching the website UI. Dates use `yyyy-MM-dd`.

## Features

- Market status, summaries, live market data, ticker, and top-ten lists.
- Today’s prices, floor sheets, market depth, supply/demand, and trade history.
- NEPSE indices, index history, and market/company chart data.
- Security profiles, company information, corporate actions, financial reports,
  dividends, AGMs, and company news.
- Listed-company, sector, share-group, promoter, broker, and dealer directories.
- Notices, disclosures, holidays, reports, events, CSV exports, and file
  downloads.

## Authentication and rate limits

No account credentials are required. `NepseClient` performs the same public
session bootstrap used by NEPSE’s frontend when it is first needed. Session
tokens stay in memory and are redacted from package diagnostics.

Requests are paced conservatively. A `429 Too Many Requests` response raises
`RateLimitedError`; the client does not retry in a loop.

## Common examples

```python
from nepse_client import NepseClient

with NepseClient() as client:
    # Use numeric security IDs; resolve them from companies() or securities().
    companies = client.companies()
    barun = next(row for row in companies if row["symbol"] == "BARUN")

    profile = client.security_profile(barun["id"])
    floorsheet = client.floorsheets(stock_id=barun["id"])

    print(profile)
    print(floorsheet["totalTrades"])
```

## Interactive explorer

The repository includes a terminal explorer for local use:

```bash
python tui.py
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Scope and disclaimer

This package is for public, read-only market-data workflows. It does not handle
user login, trading, portfolio actions, or other state-changing operations.
NEPSE data may be delayed or corrected by the exchange; verify information
independently before making financial decisions.

## License

Distributed under the [MIT License](LICENSE).
