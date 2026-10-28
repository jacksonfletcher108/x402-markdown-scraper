from __future__ import annotations

import threading
import time
from typing import Any


class TtlCache:
    """Process-local TTL cache. Used after x402 settlement to skip repeat fetches."""

    def __init__(self, ttl_seconds: float = 900.0, max_items: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_items = max_items
        self._lock = threading.Lock()
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires <= now:
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        expires = time.monotonic() + self.ttl_seconds
        with self._lock:
            if len(self._items) >= self.max_items:
                oldest = min(self._items.items(), key=lambda item: item[1][0])[0]
                self._items.pop(oldest, None)
            self._items[key] = (expires, value)


cache = TtlCache()
