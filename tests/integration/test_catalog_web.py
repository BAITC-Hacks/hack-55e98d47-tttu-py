import hashlib
import io
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.config import ROOT

PASSWORD = "test administrator password"
CSRF_RE = re.compile(r'name="csrf_token" value="([^"]+)"')
PREVIEW_RE = re.compile(r'name="preview_id" value="([^"]+)"')


@pytest.fixture
def admin_app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "CATALOG_WEB_ADMIN_ENABLED": True,
            "CATALOG_ADMIN_PASSWORD_HASH": generate_password_hash(PASSWORD),
            "SECRET_KEY": "catalog-test-secret-key-with-at-least-32-bytes",
            "CATALOG_ACTIVE_PATH": str(tmp_path / "active.csv"),
            "DATABASE_PATH": str(tmp_path / "catalog.sqlite3"),
            "DATASET_PATH": str(ROOT / "data" / "hackathon_dataset.csv"),
            "LLM_API_KEY": "",
        }
    )


@pytest.fixture
def admin_client(admin_app):
    return admin_app.test_client()


def csrf(client, locale="en"):
    response = client.get(f"/admin/catalog?locale={locale}")
    match = CSRF_RE.search(response.text)
    assert match is not None, response.text
    return match.group(1)


def login(client, password=PASSWORD, locale="en"):
    token = csrf(client, locale)
    return client.post(
        "/admin/catalog/login",
        data={"csrf_token": token, "locale": locale, "password": password},
    )


def changed_catalog():
    original = (ROOT / "data" / "hackathon_dataset.csv").read_bytes()
    return original.replace(b"HK-39372", b"HK-TEST01", 1)


def upload(client, data, filename="catalog.csv"):
    token = csrf(client)
    return client.post(
        "/admin/catalog/upload",
        data={
            "csrf_token": token,
            "locale": "en",
            "catalog_file": (io.BytesIO(data), filename),
        },
        content_type="multipart/form-data",
    )


def test_unauthenticated_mutations_and_sample_are_blocked(admin_client):
    token = csrf(admin_client)
    for endpoint, data in (
        ("/admin/catalog/upload", {"csrf_token": token, "locale": "en"}),
        ("/admin/catalog/activate", {"csrf_token": token, "locale": "en", "preview_id": "x"}),
        ("/admin/catalog/logout", {"csrf_token": token, "locale": "en"}),
    ):
        response = admin_client.post(endpoint, data=data)
        assert response.status_code == 401
    assert admin_client.get("/admin/catalog/sample").status_code == 401
    assert admin_client.get("/admin/catalog/activate").status_code == 405


def test_disabled_or_misconfigured_admin_fails_closed(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "CATALOG_WEB_ADMIN_ENABLED": True,
            "CATALOG_ADMIN_PASSWORD_HASH": "not-a-password-hash",
            "SECRET_KEY": "too-short",
            "CATALOG_ACTIVE_PATH": str(tmp_path / "active.csv"),
            "DATABASE_PATH": str(tmp_path / "catalog.sqlite3"),
            "DATASET_PATH": str(ROOT / "data" / "hackathon_dataset.csv"),
        }
    )
    response = app.test_client().get("/admin/catalog")
    assert response.status_code == 503
    assert "not-a-password-hash" not in response.text
    assert "too-short" not in response.text


def test_login_wrong_password_csrf_and_rate_limit(admin_client):
    token = csrf(admin_client)
    assert admin_client.post("/admin/catalog/login", data={"password": PASSWORD}).status_code == 403
    for _ in range(5):
        response = admin_client.post(
            "/admin/catalog/login",
            data={"csrf_token": token, "locale": "en", "password": "wrong"},
        )
        assert response.status_code == 401
    assert (
        admin_client.post(
            "/admin/catalog/login",
            data={"csrf_token": token, "locale": "en", "password": "wrong"},
        ).status_code
        == 429
    )


def test_login_success_localizes_and_requires_csrf(admin_client):
    response = login(admin_client, locale="en")
    assert response.status_code == 303
    page = admin_client.get("/admin/catalog?locale=en")
    assert page.status_code == 200
    assert '<html lang="en"' in page.text
    assert "Upload a new catalog" in page.text
    assert admin_client.post("/admin/catalog/logout", data={"locale": "en"}).status_code == 403


def test_session_expiry_and_credential_rotation(admin_client, admin_app):
    assert login(admin_client).status_code == 303
    with admin_client.session_transaction() as session:
        session["catalog_until"] = 0
    assert admin_client.get("/admin/catalog?locale=en").status_code == 200
    assert "Administrator sign in" in admin_client.get("/admin/catalog?locale=en").text
    assert login(admin_client).status_code == 303
    admin_app.config["CATALOG_ADMIN_PASSWORD_HASH"] = generate_password_hash("rotated")
    page = admin_client.get("/admin/catalog?locale=en")
    assert page.status_code == 200
    assert "Administrator sign in" in page.text


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("private-name.txt", b"not a csv"),
        ("private-name.csv", b"\xff\xfe"),
        ("private-name.csv", b"id,unexpected\n1,x\n"),
    ],
)
def test_invalid_uploads_preserve_active_catalog(admin_client, filename, payload):
    assert login(admin_client).status_code == 303
    response = upload(admin_client, payload, filename)
    assert response.status_code == 422
    assert filename not in response.text
    assert "private-name" not in response.text
    assert not Path(admin_client.application.config["CATALOG_ACTIVE_PATH"]).exists()


def test_oversized_upload_is_rejected_without_activation(admin_client):
    assert login(admin_client).status_code == 303
    response = upload(admin_client, b"a" * (1024 * 1024 + 1))
    assert response.status_code == 413
    assert "1 MiB" in response.text
    assert not Path(admin_client.application.config["CATALOG_ACTIVE_PATH"]).exists()


def test_preview_activation_restart_and_source_is_untouched(admin_client, admin_app, tmp_path):
    source = (ROOT / "data" / "hackathon_dataset.csv").read_bytes()
    updated = changed_catalog()
    assert login(admin_client).status_code == 303
    preview = upload(admin_client, updated)
    assert preview.status_code == 200
    assert "Catalog preview" in preview.text
    assert hashlib.sha256(updated).hexdigest() in preview.text
    preview_id = PREVIEW_RE.search(preview.text).group(1)
    token = csrf(admin_client)
    activated = admin_client.post(
        "/admin/catalog/activate",
        data={"csrf_token": token, "locale": "en", "preview_id": preview_id},
    )
    assert activated.status_code == 200
    assert "Catalog activated successfully" in activated.text
    active_path = Path(admin_app.config["CATALOG_ACTIVE_PATH"])
    assert active_path.read_bytes() == updated
    assert (ROOT / "data" / "hackathon_dataset.csv").read_bytes() == source
    assert "HK-TEST01" in {item.id for item in admin_app.extensions["catalog_manager"].all()}

    restarted = create_app(dict(admin_app.config))
    assert "HK-TEST01" in {item.id for item in restarted.extensions["catalog_manager"].all()}
    assert (ROOT / "data" / "hackathon_dataset.csv").read_bytes() == source


def test_preview_is_owned_by_session_and_activation_conflict_is_safe(admin_app):
    first = admin_app.test_client()
    second = admin_app.test_client()
    assert login(first).status_code == 303
    preview = upload(first, changed_catalog())
    preview_id = PREVIEW_RE.search(preview.text).group(1)
    assert login(second).status_code == 303
    token = csrf(second)
    response = second.post(
        "/admin/catalog/activate",
        data={"csrf_token": token, "locale": "en", "preview_id": preview_id},
    )
    assert response.status_code == 422
    assert "HK-TEST01" not in {item.id for item in admin_app.extensions["catalog_manager"].all()}


def test_export_snapshot_survives_catalog_activation(admin_client, admin_app, payload):
    captured = admin_client.post(
        "/api/v1/recommendations", json=payload, headers={"X-Enable-Export": "true"}
    )
    assert captured.status_code == 200
    token = captured.headers["X-Recommendation-Export-Token"]
    before = admin_client.post(
        "/api/v1/recommendations/export", json={"format": "json", "export_token": token}
    )
    assert before.status_code == 200
    assert login(admin_client).status_code == 303
    preview = upload(admin_client, changed_catalog())
    preview_id = PREVIEW_RE.search(preview.text).group(1)
    admin_client.post(
        "/admin/catalog/activate",
        data={"csrf_token": csrf(admin_client), "locale": "en", "preview_id": preview_id},
    )
    exported = admin_client.post(
        "/api/v1/recommendations/export", json={"format": "json", "export_token": token}
    )
    assert exported.status_code == 200
    assert exported.data == before.data


def test_cancel_revokes_preview_and_prevents_old_apply(admin_client, admin_app):
    assert login(admin_client).status_code == 303
    preview = upload(admin_client, changed_catalog())
    preview_id = PREVIEW_RE.search(preview.text).group(1)
    token = csrf(admin_client)
    canceled = admin_client.post(
        "/admin/catalog/cancel", data={"csrf_token": token, "locale": "en"}
    )
    assert canceled.status_code == 303
    assert "Upload a new catalog" in admin_client.get(canceled.headers["Location"]).text
    replayed = admin_client.post(
        "/admin/catalog/activate",
        data={"csrf_token": token, "locale": "en", "preview_id": preview_id},
    )
    assert replayed.status_code == 422
    assert not Path(admin_app.config["CATALOG_ACTIVE_PATH"]).exists()
    assert "HK-TEST01" not in {item.id for item in admin_app.extensions["catalog_manager"].all()}
