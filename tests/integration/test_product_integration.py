"""Regressions at the Web/API product boundaries, using the production service."""

import csv
import io
import re
from dataclasses import replace

import pytest


def token(response, name="export_id"):
    match = re.search(rf'name="{name}" value="([^"]+)"', response.text)
    assert match, response.status_code
    return match[1]


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
def test_web_export_matches_api_and_generation_locale(client, payload, locale):
    payload = {**payload, "locale": locale, "language": "русский"}
    api = client.post("/api/v1/recommendations", json=payload).json
    shown = client.post("/", data=payload)
    exported = client.post("/recommendations/export/json", data={"export_id": token(shown)})
    assert exported.json["schema_version"] == "recommendation-export.v1"
    assert exported.json["locale"] == locale
    assert exported.json["result"] == api
    assert exported.json["request"]["language"] == "русский"
    assert f'class="mb-0 explanation-text" lang="{locale}"' in shown.text
    assert shown.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("surface", ["web", "api"])
def test_optional_capture_failure_preserves_recommendations(client, payload, monkeypatch, surface):
    from app.web.exports import ExportStore

    def fail(*args):
        raise ValueError("private-sentinel C:/private/file")

    if surface == "api":
        monkeypatch.setattr(client.application.extensions["export_snapshots"], "put", fail)
        response = client.post(
            "/api/v1/recommendations", json=payload, headers={"X-Enable-Export": "true"}
        )
        assert response.status_code == 200
        assert response.json["status"] == "matched"
        assert response.headers["X-Recommendation-Export-Status"] == "unavailable"
        assert "X-Recommendation-Export-Token" not in response.headers
    else:
        monkeypatch.setattr(ExportStore, "put", fail)
        response = client.post("/", data=payload)
        assert response.status_code == 200
        assert 'data-result-kind="matched"' in response.text
        assert 'name="export_id"' not in response.text
    assert "private-sentinel" not in response.text


@pytest.mark.parametrize("surface", ["/", "/api/v1/recommendations"])
@pytest.mark.parametrize("error", [ValueError, TypeError, RuntimeError])
def test_internal_errors_never_expose_or_log_details(
    client, payload, monkeypatch, caplog, surface, error
):
    def fail(*args):
        raise error("private-sentinel C:/private/file")

    monkeypatch.setattr(client.application.extensions["recommendation_service"], "recommend", fail)
    response = client.post(surface, **({"data": payload} if surface == "/" else {"json": payload}))
    assert response.status_code in (500, 503)
    assert "private-sentinel" not in response.text + caplog.text


def test_locale_switch_uses_saved_query_not_edited_draft(client, payload, monkeypatch):
    shown = client.post("/", data={**payload, "category": "Флорист"})
    view_id = token(shown, "view_id")

    def fail(*args):
        raise AssertionError("Locale switch must not recommend")

    monkeypatch.setattr(client.application.extensions["recommendation_service"], "recommend", fail)
    switched = client.post(
        "/", data={**payload, "locale": "en", "switch_locale": "1", "view_id": view_id}
    )
    assert "Florist" in switched.text
    assert '<option value="Ведущий" selected>Host</option>' in switched.text
    exported = client.post("/recommendations/export/json", data={"export_id": view_id})
    assert exported.json["request"]["category"] == "Флорист"
    assert exported.json["result"]["status"] == "category_not_found"


def test_expired_locale_switch_is_explicit(client, payload):
    response = client.post(
        "/", data={**payload, "switch_locale": "1", "view_id": "expired", "locale": "en"}
    )
    assert 'data-result-kind="snapshot_expired"' in response.text
    assert "expired" in response.text.lower()


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
@pytest.mark.parametrize(
    "changes,status,count",
    [
        ({}, "matched", 3),
        ({"category": "Флорист"}, "matched", 2),
        ({"category": "Флорист", "budget_kzt": 200000}, "matched", 1),
        ({"budget_kzt": 0}, "no_eligible_candidates", 0),
        ({"city": "Зарубежье", "category": "Флорист"}, "category_not_found", 0),
    ],
)
def test_real_dataset_web_export_outcome_matrix(real_app, locale, changes, status, count):
    client = real_app.test_client()
    query = {
        "city": "Алматы",
        "category": "Ведущий",
        "event_format": "свадьба",
        "event_date": "2026-10-15",
        "budget_kzt": 6000000,
        "locale": locale,
        **changes,
    }
    api = client.post("/api/v1/recommendations", json=query).json
    shown = client.post("/", data=query)
    assert f'data-result-kind="{status}"' in shown.text
    export_id = token(shown)
    document = client.post("/recommendations/export/json", data={"export_id": export_id}).json
    assert document["result"] == api
    assert api["count"] == count
    csv_response = client.post("/recommendations/export/csv", data={"export_id": export_id})
    assert csv_response.data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(csv_response.data.decode("utf-8-sig"))))
    assert len(rows) == max(count, 1)
    assert rows[0]["status"] == status
    assert rows[0]["generated_at"] == document["generated_at"]
    if count:
        assert [row["id"] for row in rows] == [card["id"] for card in api["recommendations"]]
    else:
        assert rows[0]["id"] == ""
    assert ("comparison-table" in shown.text) == (count >= 2)


def test_web_csv_uses_shared_formula_protection_and_html_escaping(
    client, payload, repository, profile
):
    name = ' \u200b=HYPERLINK("https://example.invalid")<script>alert(1)</script>'
    repository.initialize((replace(profile, anon_name=name),))
    shown = client.post("/", data=payload)
    assert "<script>alert(1)</script>" not in shown.text
    assert "&lt;script&gt;" in shown.text
    response = client.post("/recommendations/export/csv", data={"export_id": token(shown)})
    rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
    assert rows[0]["anon_name"] == "'" + name


def test_switch_keeps_generation_locale_and_exact_snapshot(client, payload, monkeypatch):
    shown = client.post("/", data={**payload, "locale": "en"})
    export_id = token(shown)
    original = client.post("/recommendations/export/json", data={"export_id": export_id})

    def fail(*args):
        raise AssertionError("Must not recompute")

    monkeypatch.setattr(client.application.extensions["recommendation_service"], "recommend", fail)
    switched = client.post(
        "/", data={**payload, "locale": "kk", "switch_locale": "1", "view_id": export_id}
    )
    assert 'lang="en"' in switched.text
    assert "Ағылшынша" in switched.text
    repeated = client.post("/recommendations/export/json", data={"export_id": token(switched)})
    assert repeated.data == original.data


def test_web_snapshot_is_immutable_bounded_and_size_limited(client, payload):
    from app.web.exports import ExportSnapshot, ExportStore

    result = client.post("/api/v1/recommendations", json=payload).json
    store = ExportStore(capacity=1)
    first = store.put(ExportSnapshot(payload, result))
    result["recommendations"][0]["anon_name"] = "changed"
    assert store.get(first).result["recommendations"][0]["anon_name"] != "changed"
    second = store.put(ExportSnapshot(payload, result))
    assert store.get(first) is None
    assert store.get(second) is not None
    result["recommendations"][0]["explanation"] = "x" * 262145
    with pytest.raises(ValueError):
        store.put(ExportSnapshot(payload, result))
    assert store.get(second) is not None
