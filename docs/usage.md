# Usage

## Installation

Requires Python 3.10 or later.

```bash
python -m pip install nepsepy
```

For local development:

```bash
python -m pip install -e ".[dev]"
pytest -q
```

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

## Async use

For async applications such as FastAPI, use `AsyncNepseClient`. It has the
same endpoint methods and automatically manages the temporary NEPSE token.

```python
from nepsepy import AsyncNepseClient

async def load_market():
    async with AsyncNepseClient() as client:
        status = await client.market_status()
        gainers = await client.top_gainers()
        return status, gainers
```

## Conventions

- **Auth** — `client.bootstrap()` once. One automatic refresh + retry on
  401/403, then `AuthExpiredError`. Tokens stay in memory and are redacted
  from diagnostics.
- **Paging** — every `page=` argument is 1-based like the UI. Page 1 sends no
  `page` param; page N sends `page=N-1`. `size=` defaults to 20.
- **Symbols vs ids** — most per-security methods take the numeric
  `security_id`. Resolve via `securities()` / `companies()`.
- **Rate limits** — requests are paced conservatively. A `429 Too Many
  Requests` response raises `RateLimitedError`; the client does not retry
  in a loop.

## Common example

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

## Scope

This package is for public, read-only market-data workflows. It does not
handle user login, trading, portfolio actions, or other state-changing
operations.
