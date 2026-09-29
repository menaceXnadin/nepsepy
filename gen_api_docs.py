"""Generate docs/API.md from nepsepy/client.py (signatures, docstrings,
HTTP paths). Run: python3 gen_api_docs.py (then delete or keep in tools)."""

import ast
from pathlib import Path

SRCS = [Path(__file__).parent / "nepsepy" / f for f in
        ("client.py", "_market.py", "_securities.py", "_prices.py",
         "_company.py", "_news.py")]
OUT = Path(__file__).parent / "docs" / "API.md"

HEADER = """# nepsepy API Reference

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

"""

trees_lines = [(ast.parse(p.read_text()), p.read_text().splitlines())
               for p in SRCS]


def _is_get(src: str) -> bool:
    return "self.get(" in src and "post_json" not in src


entries: list[tuple[str, int, str, str, str, list[str], str]] = []
for tree, lines in trees_lines:
    file_sections: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# --"):
            file_sections.append((i + 1, s.strip("# ").strip("- ")))

    def section_for(lineno: int) -> str:
        cur = "Session & low-level"
        for start, name in file_sections:
            if start < lineno:
                cur = name
        return cur

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("_") or node.name in (
                "bootstrap", "close", "get", "post", "get_json", "post_json",
                "describe_state"):
            continue
        # full signature: source lines until parentheses balance
        import re as _re

        sig_lines = []
        depth = 0
        started = False
        for ln in lines[node.lineno - 1: node.end_lineno]:
            sig_lines.append(ln.strip())
            depth += ln.count("(") - ln.count(")")
            if "(" in ln:
                started = True
            if started and depth <= 0:
                break
        sig = " ".join(sig_lines)
        doc = (ast.get_docstring(node) or "").strip()
        # request paths (incl. f-string templates) + verbs + signed variant
        # (code only — docstring mentions would duplicate the paths)
        code_from = node.lineno
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            code_from = node.body[0].end_lineno + 1
        body_src = "\n".join(lines[code_from - 1: node.end_lineno])
        paths = []
        for m in _re.finditer(r"(/api/[\w\-/.?=&{}]+)", body_src):
            p = m.group(1).rstrip("?&")
            base = p.split("?")[0]
            if base not in paths:
                paths.append(base)
        src = body_src
        verbs = []
        if "post_json" in src or "self.post(" in src:
            verbs.append("POST")
        if "get_json" in src or _is_get(src):
            verbs.append("GET")
        signed = ""
        m = _re.search(r'_signed\("(\w+)"\)', src)
        if m:
            signed = m.group(1)
        how = ", ".join(verbs) + (f" (signed POST body variant {signed})" if signed else "")
        entries.append((section_for(node.lineno), node.lineno, node.name, sig, doc, paths, how))


entries.sort(key=lambda e: (e[0], e[1]))

out = [HEADER]
current = None
for section, _, name, sig, doc, paths, how in entries:
    if section != current:
        out.append(f"## {section}\n")
        current = section
    out.append(f"### `{name}`\n")
    out.append(f"```python\n{sig}\n```\n")
    if paths:
        out.append(f"**Request:** {how} " +
                   " ".join(f"`{p}`" for p in paths) + "\n")
    if doc:
        out.append(f"{doc}\n")

OUT.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {OUT} ({len(entries)} methods)")
