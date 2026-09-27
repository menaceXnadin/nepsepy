"""Async interface for the public NEPSE client.

The public endpoint implementation is shared with :class:`NepseClient`.
Calls run in a worker thread, so they do not block an asyncio event loop while
preserving the same public endpoint methods, token lifecycle, and pacing.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

import httpx

from .client import BASE_URL, MIN_INTERVAL_S, NepseClient


class AsyncNepseClient:
    """Awaitable counterpart to :class:`NepseClient`.

    Every public endpoint available on ``NepseClient`` is available here with
    the same name and arguments, but must be awaited. Requests for one client
    instance are serialized to protect its shared temporary token and retain
    the conservative request pacing.
    """

    def __init__(self, base_url: str = BASE_URL,
                 transport: Optional[httpx.BaseTransport] = None,
                 min_interval: float = MIN_INTERVAL_S) -> None:
        self._client = NepseClient(base_url=base_url, transport=transport,
                                   min_interval=min_interval)
        self._lock = asyncio.Lock()
        self._closed = False

    async def __aenter__(self) -> "AsyncNepseClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client and discard temporary tokens."""
        async with self._lock:
            if not self._closed:
                await asyncio.to_thread(self._client.close)
                self._closed = True

    def __getattr__(self, name: str) -> Any:
        """Expose each synchronous public method as an awaitable method."""
        if name.startswith("_"):
            raise AttributeError(name)
        method = getattr(self._client, name)
        if not callable(method):
            return method

        async def call(*args: Any, **kwargs: Any) -> Any:
            async with self._lock:
                if self._closed:
                    raise RuntimeError("AsyncNepseClient is closed")
                return await asyncio.to_thread(method, *args, **kwargs)

        return call
