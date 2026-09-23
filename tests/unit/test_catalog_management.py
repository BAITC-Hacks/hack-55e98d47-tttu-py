import hashlib

import pytest

from app.repositories import CatalogRepository, load_csv
from app.services.catalog_management import CatalogManager, CatalogOperationError


def _manager(tmp_path):
    source = tmp_path / "fallback.csv"
    source.write_bytes(
        (
            "id,anon_name,categories,city,price_from_kzt,event_formats,languages,max_hours,busy_dates,description,synthetic,city_imputed,price_imputed\n"
            "old,Old,Host,Алматы,1,Wedding,Russian,1,,old,False,False,False\n"
        ).encode()
    )
    active = tmp_path / "active.csv"
    active.write_bytes(source.read_bytes())
    repository = CatalogRepository(tmp_path / "catalog.sqlite3")
    repository.initialize(load_csv(source))
    return CatalogManager(active, source, repository), repository


def test_stage_is_bounded_and_returns_safe_preview(tmp_path):
    manager, _ = _manager(tmp_path)
    data = (tmp_path / "active.csv").read_bytes()
    result = manager.stage(data, "admin")
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["count"] == 1
    assert result["sample"][0]["id"] == "old"
    assert "description" not in result["sample"][0]


def test_owner_and_expiry_are_enforced(tmp_path):
    now = [100.0]
    manager, _ = _manager(tmp_path)
    manager._clock = lambda: now[0]
    preview = manager.stage((tmp_path / "active.csv").read_bytes(), "admin")
    with pytest.raises(CatalogOperationError) as error:
        manager.commit(preview["preview_id"], "other")
    assert error.value.code == "invalid"
    now[0] += 901
    with pytest.raises(CatalogOperationError) as error:
        manager.commit(preview["preview_id"], "admin")
    assert error.value.code == "expired"


def test_commit_updates_csv_and_repository_atomically(tmp_path):
    manager, repository = _manager(tmp_path)
    data = (tmp_path / "active.csv").read_bytes().replace(b"old,Old", b"new,New")
    preview = manager.stage(data, "admin")
    result = manager.commit(preview["preview_id"], "admin")
    assert result["count"] == 1
    assert manager.active_path.read_bytes() == data
    assert repository.all()[0].id == "old"
    assert manager.all()[0].id == "new"


def test_stale_preview_is_rejected(tmp_path):
    manager, _ = _manager(tmp_path)
    data = (tmp_path / "active.csv").read_bytes()
    first = manager.stage(data, "admin")
    manager.commit(first["preview_id"], "admin")
    second = manager.stage(data, "admin")
    manager.active_path.write_bytes(data + b"\n")
    with pytest.raises(CatalogOperationError) as error:
        manager.commit(second["preview_id"], "admin")
    assert error.value.code == "conflict"


def test_replace_failure_restores_repository(tmp_path, monkeypatch):
    manager, repository = _manager(tmp_path)
    original = repository.all()
    preview = manager.stage((tmp_path / "active.csv").read_bytes(), "admin")
    monkeypatch.setattr(
        "app.services.catalog_management.os.replace", lambda *_: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(CatalogOperationError) as error:
        manager.commit(preview["preview_id"], "admin")
    assert error.value.code == "failure"
    assert repository.all() == original
