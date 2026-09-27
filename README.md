# nepsepy

![nepsepy banner](https://res.cloudinary.com/dzbc5mlm9/image/upload/v1790524377/nepsepybanner_ucetgq.png)

[![PyPI](https://img.shields.io/pypi/v/nepsepy?logo=pypi&logoColor=white)](https://pypi.org/project/nepsepy/)
[![Python](https://img.shields.io/pypi/pyversions/nepsepy?logo=python&logoColor=white)](https://pypi.org/project/nepsepy/)
[![Tests](https://github.com/menaceXnadin/nepsepy/actions/workflows/tests.yml/badge.svg)](https://github.com/menaceXnadin/nepsepy/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-MIT-0b7f52)](LICENSE)

> A clean Python interface for public Nepal Stock Exchange (NEPSE) market data.

`nepsepy` provides a small, synchronous API for market status, prices, floor
sheets, indices, company information, notices, and other data used by the
NEPSE website.

It is not affiliated with the Nepal Stock Exchange.

## Why nepsepy?

- **Simple API** — use named methods such as `today_price()` and
  `security_profile()` instead of manually assembling HTTP requests.
- **Public session handling** — performs the same login-free bootstrap used by
  the NEPSE frontend; no user credentials are needed.
- **Careful by default** — requests are paced, token values are kept in memory,
  and rate limiting is surfaced clearly instead of retried aggressively.

## Installation

Requires Python 3.10 or later.

```bash
python -m pip install nepsepy
```

The PyPI distribution and Python import package are both named `nepsepy`.

## Quick start

```python
from nepsepy import NepseClient

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

| Area | Included data |
| --- | --- |
| Market | Status, summaries, live market data, ticker, and top-ten lists |
| Prices & trades | Today’s prices, floor sheets, depth, supply/demand, and trade history |
| Charts | NEPSE indices, index history, and market/company chart data |
| Companies | Profiles, corporate actions, financial reports, dividends, AGMs, and news |
| Directories | Companies, sectors, share groups, promoters, brokers, and dealers |
| News & files | Notices, disclosures, holidays, reports, events, CSV exports, and downloads |

## Authentication and rate limits

No account credentials are required. `NepseClient` performs the same public
session bootstrap used by NEPSE’s frontend when it is first needed. Session
tokens stay in memory and are redacted from package diagnostics.

Requests are paced conservatively. A `429 Too Many Requests` response raises
`RateLimitedError`; the client does not retry in a loop.

## Common examples

```python
from nepsepy import NepseClient

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
