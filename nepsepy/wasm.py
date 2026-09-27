"""Load the publicly served css.wasm exactly as the frontend does and strip
decoy characters from bootstrap tokens.

No JWE decryption happens here: the WASM exports only return small integer
cut positions which the frontend's slice() logic uses to drop 5 characters.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exceptions import WasmError

EXPECTED_EXPORTS = ("cdx", "rdx", "bdx", "ndx", "mdx")


def redact(value: object) -> str:
    """Return a length-only placeholder; never echo token material."""
    try:
        n = len(value)  # type: ignore[arg-type]
    except Exception:
        return "<redacted>"
    return f"<redacted len={n}>"


def strip_at_indexes(token: str, indexes: tuple[int, ...]) -> str:
    """Mirror the frontend's slice() concatenation.

    token[0:p0] + token[p0+1:p1] + ... + token[p4+1:]
    """
    if len(indexes) != 5:
        raise WasmError(f"expected 5 cut indexes, got {len(indexes)}")
    if any(not isinstance(p, int) or p < 0 or p >= len(token) for p in indexes):
        raise WasmError("cut index out of range for token of "
                        f"length {len(token)}")
    p0, p1, p2, p3, p4 = indexes
    if not (p0 < p1 < p2 < p3 < p4):
        raise WasmError("cut indexes are not strictly ascending")
    return (token[0:p0] + token[p0 + 1:p1] + token[p1 + 1:p2]
            + token[p2 + 1:p3] + token[p3 + 1:p4] + token[p4 + 1:])


@dataclass
class WasmCleaner:
    """Thin wrapper around the instantiated css.wasm exports."""

    _exports: object = None  # mapping name -> callable

    @classmethod
    def from_bytes(cls, wasm_bytes: bytes) -> "WasmCleaner":
        try:
            from wasmtime import Func, FuncType, Linker, Module, Store
        except ImportError as exc:
            raise WasmError("wasmtime is required") from exc
        if not wasm_bytes:
            raise WasmError("empty wasm payload")
        try:
            store = Store()
            module = Module(store.engine, wasm_bytes)
            linker = Linker(store.engine)
            # Stub every function import the module declares (the frontend
            # passes {imports: {imported_func: console.log}}). Stubs ignore
            # args and return zeros so exports stay pure index functions.
            for imp in module.imports:
                try:
                    if not isinstance(imp.type, FuncType):
                        continue
                    ftype = imp.type
                    n_results = len(list(ftype.results))

                    def make_stub(n_results):
                        def stub(*_args):
                            if n_results == 0:
                                return None
                            return [0] * n_results
                        return stub

                    linker.define(store, imp.module, imp.name,
                                  Func(store, ftype, make_stub(n_results)))
                except Exception:
                    continue
            instance = linker.instantiate(store, module)
            exports = {}
            for name in EXPECTED_EXPORTS:
                try:
                    fn = instance.exports(store)[name]
                except Exception as exc:
                    raise WasmError(f"wasm export missing: {name}") from exc
                exports[name] = (store, fn)

            def call(name: str, *args: int) -> int:
                store_, fn = exports[name]
                try:
                    out = fn(store_, *args)
                except Exception as exc:
                    raise WasmError(f"wasm call failed: {name}") from exc
                if not isinstance(out, int):
                    raise WasmError(f"wasm export did not return int: {name}")
                return out

            cleaner = cls()
            cleaner._call = call  # type: ignore[attr-defined]
            return cleaner
        except WasmError:
            raise
        except Exception as exc:
            raise WasmError(f"wasm instantiate failed: {exc}") from exc

    def _call(self, _name: str, *_args: int) -> int:  # replaced by from_bytes
        raise WasmError("cleaner not initialised")

    def access_indexes(self, s1: int, s2: int, s3: int, s4: int, s5: int) -> tuple[int, ...]:
        """Cut positions for accessToken, in call order cdx,rdx,bdx,ndx,mdx."""
        return (
            self._call("cdx", s1, s2, s3, s4, s5),
            self._call("rdx", s1, s2, s4, s3, s5),
            self._call("bdx", s1, s2, s4, s3, s5),
            self._call("ndx", s1, s2, s4, s3, s5),
            self._call("mdx", s1, s2, s4, s3, s5),
        )

    def refresh_indexes(self, s1: int, s2: int, s3: int, s4: int, s5: int) -> tuple[int, ...]:
        """Cut positions for refreshToken (observed differing arg order)."""
        return (
            self._call("cdx", s2, s1, s3, s5, s4),
            self._call("rdx", s2, s1, s3, s4, s5),
            self._call("bdx", s2, s1, s4, s3, s5),
            self._call("ndx", s2, s1, s4, s3, s5),
            self._call("mdx", s2, s1, s4, s3, s5),
        )

    def clean_access(self, raw: str, salts: tuple[int, ...]) -> str:
        return strip_at_indexes(raw, self.access_indexes(*salts))

    def clean_refresh(self, raw: str, salts: tuple[int, ...]) -> str:
        return strip_at_indexes(raw, self.refresh_indexes(*salts))
