# nepsepy

A clean Python interface for public Nepal Stock Exchange (NEPSE) market data.

`nepsepy` provides synchronous and async APIs for market status, prices, floor
sheets, indices, company information, notices, and other data used by the
NEPSE website. It is not affiliated with the Nepal Stock Exchange.

No account credentials are required. `NepseClient` performs the same public
session bootstrap used by NEPSE's frontend when it is first needed.

```{toctree}
:maxdepth: 2
:caption: Contents

usage
reference
API
```

- {doc}`usage` — install, quick start, async, pagination, errors.
- {doc}`reference` — autodoc API (`NepseClient`, `AsyncNepseClient`, exceptions).
- {doc}`API` — generated endpoint reference (`python gen_api_docs.py`).

## Links

- PyPI: <https://pypi.org/project/nepsepy/>
- Source: <https://github.com/menaceXnadin/nepsepy>
