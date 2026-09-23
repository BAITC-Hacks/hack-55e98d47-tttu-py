"""Serialize service results, never discover/filter/rank candidates here."""

import csv
import io
import json
import secrets
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import asdict
from datetime import datetime, timezone

from app.localization import locale_from_payload
from app.models import RecommendationRequest

CARD_FIELDS = (
    "id",
    "anon_name",
    "category",
    "city",
    "price_from_kzt",
    "synthetic",
    "city_imputed",
    "price_imputed",
    "explanation",
)
REQUEST_FIELDS = (
    "city",
    "event_date",
    "event_format",
    "category",
    "budget_kzt",
    "duration_hours",
    "language",
)
RESULT_FIELDS = ("status", "count", "message", "reasons", "recommendations")
CSV_COLUMNS = (
    "schema_version",
    "generated_at",
    "locale",
    *(f"request_{field}" for field in REQUEST_FIELDS),
    "status",
    "count",
    "message",
    "reasons",
    *CARD_FIELDS,
)


def snapshot(payload: object, result: dict, *, generated_at: datetime | None = None) -> dict:
    """Only call with the server-produced result of this request, never client result data."""
    request = RecommendationRequest.from_payload(payload)
    safe_result = {key: result[key] for key in RESULT_FIELDS if key in result}
    safe_result["recommendations"] = [
        {key: card[key] for key in CARD_FIELDS} for card in result["recommendations"]
    ]
    instant = generated_at or datetime.now(timezone.utc)
    return {
        "schema_version": "recommendation-export.v1",
        "generated_at": instant.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "locale": locale_from_payload(payload),
        "request": asdict(request),
        "result": safe_result,
    }


def json_bytes(document: dict) -> bytes:
    return json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def safe_csv_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, str):
        return value
    # Spreadsheet programs can ignore leading whitespace/control/format characters.
    significant = value.lstrip()
    while significant and unicodedata.category(significant[0])[0] in ("C", "Z"):
        significant = significant[1:]
    if (significant and significant[0] in "=+-@＝＋－＠") or any(
        character in value for character in "\t\r\n\x00"
    ):
        return "'" + value
    return value


def csv_bytes(document: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    result = document["result"]
    metadata = {key: document[key] for key in ("schema_version", "generated_at", "locale")}
    metadata.update({f"request_{key}": document["request"][key] for key in REQUEST_FIELDS})
    metadata.update({key: result[key] for key in ("status", "count", "message")})
    metadata["reasons"] = json.dumps(result.get("reasons", {}), ensure_ascii=False, sort_keys=True)
    for card in result["recommendations"] or [{}]:
        row = {**metadata, **card}
        writer.writerow({key: safe_csv_cell(row.get(key)) for key in CSV_COLUMNS})
    return stream.getvalue().encode("utf-8-sig")


class SnapshotStore:
    """Bounded immutable serialized snapshots; tokens are short-lived bearer capabilities."""

    def __init__(self, *, ttl: float = 900, capacity: int = 128, clock=time.monotonic):
        self.ttl = ttl
        self.capacity = capacity
        self.clock = clock
        self._entries = OrderedDict()
        self._lock = threading.Lock()

    def _expire(self):
        now = self.clock()
        for token, (expires, _) in list(self._entries.items()):
            if expires <= now:
                del self._entries[token]

    def put(self, document: dict) -> str:
        data = json_bytes(document)
        if len(data) > 262144:
            raise ValueError("Export snapshot is too large")
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._expire()
            while len(self._entries) >= self.capacity:
                self._entries.popitem(last=False)
            self._entries[token] = (self.clock() + self.ttl, data)
        return token

    def get(self, token: str) -> dict | None:
        with self._lock:
            self._expire()
            entry = self._entries.get(token)
            return json.loads(entry[1]) if entry else None
