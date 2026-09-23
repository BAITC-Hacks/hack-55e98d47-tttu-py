"""Bounded in-process snapshots for exact server-side recommendation exports."""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExportSnapshot:
    query: dict[str, Any]
    result: dict[str, Any] | None
    state_kind: str = "result"

    @property
    def recommendations(self) -> tuple[dict[str, Any], ...]:
        if not self.result:
            return ()
        return tuple(
            dict(item)
            for item in list(self.result.get("recommendations") or [])[:3]
            if isinstance(item, dict)
        )


class ExportStore:
    def __init__(self, *, ttl_seconds: int = 900, capacity: int = 128):
        self.ttl_seconds = ttl_seconds
        self.capacity = capacity
        self._items: OrderedDict[str, tuple[float, ExportSnapshot]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, snapshot: ExportSnapshot) -> str:
        now = time.monotonic()
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._discard_expired(now)
            self._items[token] = (now + self.ttl_seconds, snapshot)
            while len(self._items) > self.capacity:
                self._items.popitem(last=False)
        return token

    def get(self, token: str) -> ExportSnapshot | None:
        now = time.monotonic()
        with self._lock:
            self._discard_expired(now)
            item = self._items.get(token)
            if item is None:
                return None
            self._items.move_to_end(token)
            return item[1]

    def _discard_expired(self, now: float) -> None:
        expired = [token for token, (deadline, _) in self._items.items() if deadline <= now]
        for token in expired:
            self._items.pop(token, None)
