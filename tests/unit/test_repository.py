import csv
import json
import sqlite3
from dataclasses import replace

import pytest

from app.repositories import DatasetError, load_csv


def test_full_catalog_preserved(real_catalog, repository):
    assert len(real_catalog) == 66
    assert len({profile.id for profile in real_catalog}) == 66
    assert sum(profile.synthetic for profile in real_catalog) == 13
    assert sum(profile.city_imputed for profile in real_catalog) == 8
    assert sum(profile.price_imputed for profile in real_catalog) == 18
    assert sum(profile.max_hours is None for profile in real_catalog) == 9
    repository.initialize(real_catalog)
    assert repository.all() == tuple(sorted(real_catalog, key=lambda profile: profile.id))


def test_atomic_replacement_and_duplicate_failure(profile, repository):
    original = repository.all()
    with pytest.raises(sqlite3.IntegrityError):
        repository.initialize((profile, profile))
    assert repository.all() == original
    repository.initialize((replace(profile, id="new", categories=("Фотограф",)),))
    assert repository.discover(profile.city, "Ведущий") == ()
    assert len(repository.all()) == 1


def test_discovery_is_parameterized(repository):
    assert repository.discover("Астана' OR 1=1 --", "Ведущий") == ()
    assert repository.discover("Астана", "Ведущий' OR 1=1 --") == ()
    assert len(repository.all()) == 1


def write_csv(tmp_path, rows, fieldnames):
    path = tmp_path / "input.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def raw_row():
    from app.config import ROOT

    with (ROOT / "data/hackathon_dataset.csv").open(encoding="utf-8-sig", newline="") as source:
        return next(csv.DictReader(source))


@pytest.mark.parametrize(
    "field,value",
    [
        ("synthetic", "yes"),
        ("city_imputed", ""),
        ("price_imputed", "0"),
        ("max_hours", "0"),
        ("max_hours", "nan"),
        ("price_from_kzt", "-1"),
        ("price_from_kzt", ""),
        ("busy_dates", "2026-02-30"),
        ("busy_dates", "20261015"),
        ("categories", ""),
        ("categories", "Ведущий||Фотограф"),
        ("languages", "русский|"),
        ("city", ""),
        ("city", "Mars"),
        ("id", ""),
        ("description", ""),
    ],
)
def test_malformed_catalog_fails_closed(tmp_path, raw_row, field, value):
    raw_row[field] = value
    path = write_csv(tmp_path, [raw_row], raw_row.keys())
    with pytest.raises(DatasetError):
        load_csv(path)


def test_duplicate_ids_rejected(tmp_path, raw_row):
    with pytest.raises(DatasetError):
        load_csv(write_csv(tmp_path, [raw_row, raw_row], raw_row.keys()))


def test_missing_columns_and_empty_catalog(tmp_path, raw_row):
    with pytest.raises(DatasetError):
        load_csv(write_csv(tmp_path, [], ["id"]))
    with pytest.raises(DatasetError):
        load_csv(write_csv(tmp_path, [], raw_row.keys()))


def test_missing_file_is_explicit(tmp_path):
    with pytest.raises(DatasetError, match="Unable to read"):
        load_csv(tmp_path / "missing.csv")


@pytest.mark.parametrize(
    "changes",
    [
        {"city": "Mars"},
        {"price_from_kzt": -1},
        {"price_from_kzt": True},
        {"max_hours": 0},
        {"synthetic": "False"},
        {"categories": []},
        {"languages": ()},
        {"busy_dates": ("2026-02-30",)},
    ],
)
def test_models_cannot_bypass_import_validation(profile, changes):
    with pytest.raises(ValueError):
        replace(profile, **changes)


def test_corrupted_sqlite_payload_fails_closed(repository):
    with sqlite3.connect(repository.path) as connection:
        raw = connection.execute("SELECT payload FROM contractors").fetchone()[0]
        payload = json.loads(raw)
        payload["price_from_kzt"] = -1
        connection.execute("UPDATE contractors SET payload = ?", (json.dumps(payload),))
    with pytest.raises(ValueError, match="price"):
        repository.discover("Астана", "Ведущий")
