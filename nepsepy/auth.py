"""Bootstrap token state: validate /prove, hold cleaned tokens in memory only."""

from __future__ import annotations

from dataclasses import dataclass, field

from .exceptions import BootstrapError
from .wasm import redact

REQUIRED_KEYS = ("accessToken", "refreshToken",
                 "salt1", "salt2", "salt3", "salt4", "salt5")


@dataclass
class ProveResponse:
    server_time: object = None
    salts: tuple[int, ...] = (0, 0, 0, 0, 0)
    raw_access: str = field(default="", repr=False)
    raw_refresh: str = field(default="", repr=False)

    def __repr__(self) -> str:  # never echo token material
        return (f"ProveResponse(salts={self.salts}, "
                f"access={redact(self.raw_access)}, "
                f"refresh={redact(self.raw_refresh)})")

    @classmethod
    def from_dict(cls, payload: object) -> "ProveResponse":
        if not isinstance(payload, dict):
            raise BootstrapError("prove response is not a JSON object")
        missing = [k for k in REQUIRED_KEYS if k not in payload]
        if missing:
            raise BootstrapError(
                f"prove response missing keys: {sorted(missing)}")
        salts: list[int] = []
        for key in ("salt1", "salt2", "salt3", "salt4", "salt5"):
            val = payload[key]
            if not isinstance(val, int) or isinstance(val, bool):
                raise BootstrapError(f"prove salt not an int: {key}")
            salts.append(val)
        raw_access = payload["accessToken"]
        raw_refresh = payload["refreshToken"]
        for name, tok in (("accessToken", raw_access),
                          ("refreshToken", raw_refresh)):
            if not isinstance(tok, str) or len(tok) < 32:
                raise BootstrapError(
                    f"prove {name} has unexpected shape "
                    f"({redact(tok)})")
        return cls(server_time=payload.get("serverTime"),
                    salts=tuple(salts),
                    raw_access=raw_access,
                    raw_refresh=raw_refresh)


@dataclass
class TokenState:
    """Cleaned tokens kept in memory only. Repr is always redacted."""

    access: str = field(default="", repr=False)
    refresh: str = field(default="", repr=False)
    salts: tuple[int, ...] = (0, 0, 0, 0, 0)

    def __repr__(self) -> str:
        return (f"TokenState(access={redact(self.access)}, "
                f"refresh={redact(self.refresh)})")

    def auth_header(self) -> dict[str, str]:
        if not self.access:
            raise BootstrapError("no cleaned access token available")
        return {"Authorization": f"Salter {self.access}"}
