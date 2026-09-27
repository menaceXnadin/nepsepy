# nepse-public-client

Small Python client for the **public** market-data flow of
https://nepalstock.com.np, mirroring exactly what the site's own Angular
frontend does. Scope is deliberately narrow:

- Public endpoints only (`/api/nots/*`, `/api/web/*`, `/api/margin/*`,
  plus the internal bootstrap/refresh/wasm URLs the frontend itself uses).
- No admin/CMS calls, no JWE decryption, no forgery. No credential or
  state-changing endpoints (login, password flows, feedback/mail POSTs).
- Tokens live in memory only and are never logged.
- Conservative pacing (~2-3 req/s max) + `429`/`Retry-After` honoring.
- On rejection, fail (or do the single normal refresh) — never bypass.

## How the bootstrap works

1. `GET /api/authenticate/prove` (no auth) returns raw `accessToken` /
   `refreshToken` plus `salt1..salt5`. The raw tokens contain 5 decoy chars.
2. `GET /assets/prod/css.wasm` provides `cdx/rdx/bdx/ndx/mdx`, which map the
   salts to 5 cut positions. Access order: `cdx(s1..s5)`,
   `rdx/bdx/ndx/mdx(s1,s2,s4,s3,s5)`. Refresh order: `cdx(s2,s1,s3,s5,s4)`,
   `rdx(s2,s1,s3,s4,s5)`, `bdx/ndx/mdx(s2,s1,s4,s3,s5)` — taken from the
   shipped frontend, never guessed.
3. The client deletes one char at each position (JS `slice()` equivalent),
   stores the cleaned pair in memory, and sends
   `Authorization: Salter <cleaned-access-token>`.
4. On a single 401 it does the frontend's normal
   `POST /api/authenticate/refresh-token {refreshToken}` + transform + one
   retry. A second 401 raises `AuthExpiredError`.

## Install

```bash
pip install -r requirements.txt
```

## Example

```bash
python example.py
```

## Terminal UI

Browse every discovered endpoint interactively (market, top tens,
today-price with all 14 sort columns, floorsheet with filters, depth,
indices/charts, company tabs incl. book-close, company lists, share
groups, sector/classification/promoter/margin/debenture directories,
reports, events, about/contact, file downloads, CSV export, captcha):

```bash
python tui.py
```

Symbols are accepted anywhere an id is needed (resolved via the site's own
company list). Token material is never printed.

```python
with NepseClient() as client:
    data = client.get("/api/nots/securityDailyTradeStat/58")
    gainers = client.top_gainers(full=True)
    table = client.today_price(page=2, size=20)
    sheet = client.floorsheets(contract_no=2026092405016843)
    depth = client.market_depth(2790)
    history = client.security_price_history(2790)
    chart = client.index_range(58, "2026-09-20", "2026-09-27")
```

Named methods cover the homepage, Today's Price, Floor Sheet, Market Depth,
Indices/Charts, company detail tabs, top tens, sector/marcap/average
summaries, trading history, notices and disclosures, directories
(sectors, classification, promoters, debentures), reports, events,
margin trades, about-us CMS, captcha steps, and file downloads.

## Signed POST bodies

Some POSTs take `{"id": <checksum>}` computed from public values
(`market-open` id, day of month, prove salts, and a 100-entry table from the
shipped frontend) — see `nepse_client/checksum.py` and the catalog doc.
The server validates the value; wrong ones are rejected.

## Tests

```bash
pytest -q
```

Tests use fake tokens/indexes only — no live credentials anywhere.
