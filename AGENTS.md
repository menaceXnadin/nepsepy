# Repository Guidelines

## Project Structure & Module Organization

- `nepse_client/` contains the public client package. Keep transport and endpoint methods in `client.py`, token/bootstrap logic in `auth.py`, wasm token cleanup in `wasm.py`, checksum logic in `checksum.py`, and domain errors in `exceptions.py`.
- `tests/test_client.py` is the pytest suite; it uses `httpx.MockTransport` and fake token data only.
- `tui.py` provides the interactive browser, and `example.py` is a minimal library example.
- `docs/API.md` is generated from client method signatures and docstrings. `docs/METHOD.md` and `docs/nepse-api-catalog.md` record research and endpoint provenance.

## Build, Test, and Development Commands

```powershell
pip install -r requirements.txt  # Install httpx, wasmtime, and pytest
pytest -q                        # Run the complete unit suite
python example.py                # Exercise the documented client example
python tui.py                    # Start the interactive terminal UI
python gen_api_docs.py           # Regenerate docs/API.md after API changes
```

Run `pytest -q` before submitting changes. Regenerate and review `docs/API.md` whenever public method signatures, docstrings, or endpoint paths change.

## Coding Style & Naming Conventions

Use four-space indentation, standard-library-first imports, `snake_case` for functions and variables, `PascalCase` for classes, and descriptive type annotations where they clarify public APIs. Follow the existing compact formatting in the package; no formatter or linter is configured. Keep endpoint methods small, add a concise docstring describing response shape and UI behavior, and preserve the UI-facing convention that public `page` arguments are 1-based.

## Testing Guidelines

Name tests `test_<behavior>()` and add focused cases beside related tests in `tests/test_client.py`. Mock every network interaction; tests must never call NEPSE or use real credentials. Cover successful requests plus guardrails such as malformed bootstrap data, 401 refresh limits, 429 handling, public-path restrictions, signed POST bodies, and token redaction.

## Security & API Boundaries

This project supports public, read-only NEPSE flows only. Do not add login, CMS/admin, credential, feedback/mail, or other state-changing endpoints. Tokens must stay in memory and must not appear in logs, exceptions, fixtures, docs, or test assertions. Retain conservative pacing and the existing single-refresh behavior; never implement bypass or retry loops for rejected requests.

## Commit & Pull Request Guidelines

The current repository has no Git commits, so no established commit convention exists. Use short imperative subjects such as `Add broker directory filters` or `Fix 429 retry handling`. In pull requests, summarize behavior and boundary implications, list tests run, update generated documentation when needed, and include terminal screenshots only for TUI changes.
