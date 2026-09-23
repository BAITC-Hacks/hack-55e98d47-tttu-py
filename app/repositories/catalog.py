import csv
import io
import json
import sqlite3
from contextlib import closing
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from app.models import Contractor


class DatasetError(ValueError):
    """Catalog errors never include untrusted row contents."""


def load_csv(path: str | Path) -> tuple[Contractor, ...]:
    try:
        return _read_csv(Path(path).open(encoding="utf-8-sig", newline=""))
    except OSError:
        raise DatasetError("Unable to read contractor dataset.") from None


def load_csv_bytes(data: bytes) -> tuple[Contractor, ...]:
    """Same schema/model parser used by startup and local administrative staging."""
    try:
        decoded = data.decode("utf-8-sig", errors="strict")
    except UnicodeError:
        raise DatasetError("Catalog must be UTF-8.") from None
    if "\x00" in decoded or "\ufeff" in decoded:
        raise DatasetError("Invalid catalog encoding or control data.")
    return _read_csv(io.StringIO(decoded, newline=""))


def _read_csv(source) -> tuple[Contractor, ...]:
    required = {field.name for field in fields(Contractor)}
    result = []
    seen = set()
    try:
        with source:
            reader = csv.DictReader(source, strict=True)
            if not reader.fieldnames or set(reader.fieldnames) != required:
                raise DatasetError("CSV columns do not match the contractor schema.")
            if len(reader.fieldnames) != len(required):
                raise DatasetError("CSV has duplicate columns.")
            for number, row in enumerate(reader, start=2):
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError
                    values = dict(row)
                    for field in ("id", "anon_name", "city", "description"):
                        if not values[field].strip():
                            raise ValueError
                    if values["city"] not in ("Алматы", "Астана", "Зарубежье"):
                        raise ValueError
                    if values["id"] in seen:
                        raise ValueError
                    for field in (
                        "categories",
                        "event_formats",
                        "languages",
                        "busy_dates",
                    ):
                        raw = values[field]
                        items = tuple(raw.split("|")) if raw else ()
                        if any(not item.strip() or item != item.strip() for item in items):
                            raise ValueError
                        if field != "busy_dates" and not items:
                            raise ValueError
                        values[field] = items
                    for day in values["busy_dates"]:
                        if date.fromisoformat(day).isoformat() != day:
                            raise ValueError
                    for field in ("synthetic", "city_imputed", "price_imputed"):
                        if values[field] not in ("True", "False"):
                            raise ValueError
                        values[field] = values[field] == "True"
                    values["price_from_kzt"] = int(values["price_from_kzt"])
                    raw_hours = values["max_hours"]
                    values["max_hours"] = int(raw_hours) if raw_hours else None
                    if values["price_from_kzt"] < 0:
                        raise ValueError
                    if values["max_hours"] is not None and values["max_hours"] <= 0:
                        raise ValueError
                    result.append(Contractor(**values))
                    seen.add(values["id"])
                except (ValueError, TypeError, KeyError):
                    raise DatasetError(f"Invalid contractor data at CSV row {number}.") from None
    except (OSError, UnicodeError, csv.Error):
        raise DatasetError("Unable to read contractor dataset.") from None
    if not result:
        raise DatasetError("Contractor dataset is empty.")
    return tuple(result)


class CatalogRepository:
    """SQLite snapshot, atomically replaced from validated CSV on application startup.

    Each operation owns its connection; no Flask thread shares a connection.
    """

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)

    def initialize(self, contractors: tuple[Contractor, ...]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS contractors ("
                "id TEXT PRIMARY KEY, city TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS categories ("
                "contractor_id TEXT NOT NULL REFERENCES contractors(id) ON DELETE CASCADE, "
                "category TEXT NOT NULL, PRIMARY KEY (contractor_id, category))"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS catalog_city ON contractors(city)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS catalog_category ON categories(category)"
            )
            connection.execute("DELETE FROM contractors")
            for contractor in contractors:
                connection.execute(
                    "INSERT INTO contractors(id, city, payload) VALUES (?, ?, ?)",
                    (
                        contractor.id,
                        contractor.city,
                        json.dumps(asdict(contractor), ensure_ascii=False),
                    ),
                )
                connection.executemany(
                    "INSERT INTO categories(contractor_id, category) VALUES (?, ?)",
                    ((contractor.id, category) for category in set(contractor.categories)),
                )

    @staticmethod
    def _decode(payload: str) -> Contractor:
        values = json.loads(payload)
        for field in ("categories", "event_formats", "languages", "busy_dates"):
            values[field] = tuple(values[field])
        return Contractor(**values)

    def discover(self, city: str, category: str) -> tuple[Contractor, ...]:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute(
                "SELECT c.payload FROM contractors c JOIN categories k ON c.id = k.contractor_id "
                "WHERE c.city = ? AND k.category = ? ORDER BY c.id ASC",
                (city, category),
            ).fetchall()
        return tuple(self._decode(row[0]) for row in rows)

    def all(self) -> tuple[Contractor, ...]:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            rows = connection.execute("SELECT payload FROM contractors ORDER BY id ASC").fetchall()
        return tuple(self._decode(row[0]) for row in rows)
