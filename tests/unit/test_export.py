import csv
import io
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services import RecommendationService
from app.services.export import (
    CSV_COLUMNS,
    SnapshotStore,
    csv_bytes,
    json_bytes,
    safe_csv_cell,
    snapshot,
)


@pytest.mark.parametrize(
    "value",
    [
        "=1+1",
        "+cmd",
        "-cmd",
        "@SUM(A1)",
        "  =SUM(A1)",
        "\t=1",
        "\r=1",
        "\n+1",
        "\ufeff=1",
        "\u200b@cmd",
        "\x00-1",
        "＝1+1",
        "line\n=1",
    ],
)
def test_csv_formula_injection(value):
    assert safe_csv_cell(value) == "'" + value


def test_csv_utf8_bom_stable_columns_and_escaping(repository, profile, payload):
    name = '=HYPERLINK("https://example.invalid","Казахский, русский")\nстрока'
    repository.initialize((replace(profile, anon_name=name),))
    result = RecommendationService(repository).recommend(payload)
    fixed = datetime(2026, 9, 23, 9, tzinfo=timezone.utc)
    document = snapshot(payload, result, generated_at=fixed)
    exported = csv_bytes(document)
    assert exported.startswith(b"\xef\xbb\xbf")
    reader = csv.DictReader(io.StringIO(exported.decode("utf-8-sig"), newline=""))
    assert reader.fieldnames == list(CSV_COLUMNS)
    row = next(reader)
    assert row["anon_name"] == "'" + name
    assert row["synthetic"] == "true"
    assert row["city_imputed"] == "false"
    assert row["generated_at"] == "2026-09-23T09:00:00.000000Z"
    assert json.loads(json_bytes(document))["result"] == result
    assert document["result"]["recommendations"][0]["anon_name"] == name


@pytest.mark.parametrize(
    "changes,status",
    [
        ({"category": "Нет категории"}, "category_not_found"),
        ({"budget_kzt": 0}, "no_eligible_candidates"),
    ],
)
def test_zero_result_metadata_is_exported(repository, payload, changes, status):
    payload.update(changes)
    result = RecommendationService(repository).recommend(payload)
    document = snapshot(payload, result)
    rows = list(csv.DictReader(io.StringIO(csv_bytes(document).decode("utf-8-sig"))))
    assert len(rows) == 1
    assert rows[0]["status"] == status
    assert rows[0]["count"] == "0"
    assert rows[0]["id"] == ""
    assert json.loads(rows[0]["reasons"]) == result.get("reasons", {})


def test_snapshot_store_immutable_expiring_and_bounded(repository, payload):
    now = [0]
    store = SnapshotStore(ttl=2, capacity=2, clock=lambda: now[0])
    result = RecommendationService(repository).recommend(payload)
    document = snapshot(payload, result)
    first = store.put(document)
    document["result"]["message"] = "changed"
    assert store.get(first)["result"]["message"] != "changed"
    returned = store.get(first)
    returned["result"]["recommendations"].clear()
    assert store.get(first)["result"]["recommendations"]
    second = store.put(document)
    third = store.put(document)
    assert first != second != third
    assert store.get(first) is None
    now[0] = 2
    assert store.get(second) is None
    assert store.get(third) is None


def test_snapshot_allowlists_unknown_fields(repository, payload):
    result = RecommendationService(repository).recommend(payload)
    payload["LLM_API_KEY"] = "never-export-this"
    payload["path"] = "C:/private/catalog.csv"
    result["internal_error"] = "never-export-this"
    result["recommendations"][0]["description"] = "not-for-export"
    encoded = json_bytes(snapshot(payload, result)).decode()
    assert "never-export-this" not in encoded
    assert "C:/private" not in encoded
    assert "not-for-export" not in encoded
