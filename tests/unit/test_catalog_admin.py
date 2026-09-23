from pathlib import Path

import pytest

from app.admin import MAX_CATALOG_BYTES, create_admin_app
from app.config import ROOT
from app.repositories import CatalogRepository


@pytest.fixture
def admin_app(real_app, tmp_path):
    real_app.config.update(
        CATALOG_ADMIN_ENABLED=True, CATALOG_STAGING_PATH=str(tmp_path / "staged.sqlite3")
    )
    admin = create_admin_app(dict(real_app.config))
    admin.extensions["catalog_repository"] = real_app.extensions["catalog_repository"]
    return admin


def test_admin_disabled_by_default(real_app):
    real_app.config["CATALOG_ADMIN_ENABLED"] = False
    outcome = (
        create_admin_app(dict(real_app.config))
        .test_cli_runner()
        .invoke(args=["catalog-admin", "validate", str(ROOT / "data/hackathon_dataset.csv")])
    )
    assert outcome.exit_code != 0
    assert "disabled" in outcome.output
    assert str(ROOT) not in outcome.output


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"])
def test_validate_and_stage_leave_active_catalog_unchanged(admin_app, tmp_path, bom):
    source = tmp_path / "source.csv"
    source.write_bytes(
        bom + (ROOT / "data/hackathon_dataset.csv").read_bytes().removeprefix(b"\xef\xbb\xbf")
    )
    before = admin_app.extensions["catalog_repository"].all()
    runner = admin_app.test_cli_runner()
    for action in ("validate", "stage"):
        outcome = runner.invoke(args=["catalog-admin", action, str(source)])
        assert outcome.exit_code == 0, outcome.output
        assert "66" in outcome.output
        assert str(source) not in outcome.output
    assert CatalogRepository(admin_app.config["CATALOG_STAGING_PATH"]).all() == before
    assert admin_app.extensions["catalog_repository"].all() == before


@pytest.mark.parametrize(
    "kind",
    ["invalid-utf8", "utf16", "nul", "bom-twice", "oversized", "empty", "malformed", "directory"],
)
def test_admin_rejects_bad_import_preserving_staging(admin_app, tmp_path, kind):
    runner = admin_app.test_cli_runner()
    assert (
        runner.invoke(
            args=["catalog-admin", "stage", str(ROOT / "data/hackathon_dataset.csv")]
        ).exit_code
        == 0
    )
    staged = Path(admin_app.config["CATALOG_STAGING_PATH"])
    before = staged.read_bytes()
    cases = {
        "invalid-utf8": b"\xff",
        "utf16": "id,name".encode("utf-16"),
        "nul": b"\x00",
        "bom-twice": b"\xef\xbb\xbf" * 2,
        "oversized": b"a" * (MAX_CATALOG_BYTES + 1),
        "empty": b"",
        "malformed": b'id,"unterminated',
    }
    source = tmp_path / "private-name.csv"
    if kind == "directory":
        source.mkdir()
    else:
        source.write_bytes(cases[kind])
    outcome = runner.invoke(args=["catalog-admin", "stage", str(source)])
    assert outcome.exit_code != 0
    assert "private-name" not in outcome.output
    assert "Traceback" not in outcome.output
    assert staged.read_bytes() == before


@pytest.mark.parametrize("target", ["DATASET_PATH", "DATABASE_PATH"])
def test_staging_cannot_replace_active_files(admin_app, target):
    path = Path(admin_app.config[target])
    before = path.read_bytes()
    admin_app.config["CATALOG_STAGING_PATH"] = str(path)
    result = admin_app.test_cli_runner().invoke(
        args=["catalog-admin", "stage", str(ROOT / "data/hackathon_dataset.csv")]
    )
    assert result.exit_code != 0
    assert path.read_bytes() == before


def test_staging_atomic_failure_preserves_previous_snapshot(admin_app, monkeypatch):
    runner = admin_app.test_cli_runner()
    arguments = ["catalog-admin", "stage", str(ROOT / "data/hackathon_dataset.csv")]
    assert runner.invoke(args=arguments).exit_code == 0
    staged = Path(admin_app.config["CATALOG_STAGING_PATH"])
    before = staged.read_bytes()

    def fail(*_args):
        raise OSError("secret internal path")

    monkeypatch.setattr("app.admin.os.replace", fail)
    result = runner.invoke(args=arguments)
    assert result.exit_code != 0
    assert "secret internal path" not in result.output
    assert staged.read_bytes() == before
    assert list(staged.parent.glob("catalog-stage-*")) == []


def test_no_public_admin_upload(admin_app, real_app):
    for app in (admin_app, real_app):
        client = app.test_client()
        for route in ("/api/v1/catalog/import", "/api/v1/admin/catalog", "/catalog-admin"):
            assert client.post(route, data=b"csv").status_code == 404


def test_admin_factory_does_not_open_or_seed_active_catalog(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Admin factory must not initialize the active catalog")

    monkeypatch.setattr(CatalogRepository, "initialize", forbidden)
    active = tmp_path / "must-not-be-created.sqlite3"
    app = create_admin_app({"CATALOG_ADMIN_ENABLED": True, "DATABASE_PATH": str(active)})
    result = app.test_cli_runner().invoke(
        args=["catalog-admin", "validate", str(ROOT / "data/hackathon_dataset.csv")]
    )
    assert result.exit_code == 0
    assert not active.exists()
    assert list(app.url_map.iter_rules()) == []


def test_admin_input_symlink_is_rejected(admin_app, monkeypatch):
    monkeypatch.setattr(Path, "is_symlink", lambda _path: True)
    outcome = admin_app.test_cli_runner().invoke(
        args=["catalog-admin", "validate", str(ROOT / "data/hackathon_dataset.csv")]
    )
    assert outcome.exit_code != 0


def test_staging_input_itself_is_protected(admin_app, tmp_path):
    source = tmp_path / "source.csv"
    source.write_bytes((ROOT / "data/hackathon_dataset.csv").read_bytes())
    original = source.read_bytes()
    admin_app.config["CATALOG_STAGING_PATH"] = str(source)
    result = admin_app.test_cli_runner().invoke(args=["catalog-admin", "stage", str(source)])
    assert result.exit_code != 0
    assert source.read_bytes() == original
