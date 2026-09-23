"""Web view snapshots backed by the shared bounded, immutable snapshot store."""

from dataclasses import dataclass
from typing import Any

from app.services.export import SnapshotStore, snapshot


@dataclass(frozen=True, slots=True)
class ExportSnapshot:
    query: dict[str, Any]
    result: dict[str, Any] | None
    state_kind: str = "result"
    document: dict[str, Any] | None = None


class ExportStore:
    def __init__(self, *, ttl_seconds: int = 900, capacity: int = 128):
        self._store = SnapshotStore(ttl=ttl_seconds, capacity=capacity)

    def put(self, item: ExportSnapshot) -> str:
        document = snapshot(item.query, item.result) if item.result is not None else None
        return self._store.put({"document": document, "state_kind": item.state_kind})

    def get(self, token: str) -> ExportSnapshot | None:
        stored = self._store.get(token)
        if stored is None:
            return None
        document = stored["document"]
        return ExportSnapshot(
            {**document["request"], "locale": document["locale"]} if document else {},
            document["result"] if document else None,
            stored["state_kind"],
            document,
        )
