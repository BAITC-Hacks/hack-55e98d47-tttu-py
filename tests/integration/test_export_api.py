import json

import pytest

from app import create_app
from app.services.export import SnapshotStore


@pytest.mark.parametrize("format", ["csv", "json"])
def test_export_calls_same_service_once(client, payload, monkeypatch, format):
    service = client.application.extensions["recommendation_service"]
    original = service.recommend
    calls = []

    def spy(body):
        calls.append(body)
        return original(body)

    monkeypatch.setattr(service, "recommend", spy)
    response = client.post(
        "/api/v1/recommendations/export", json={"request": payload, "format": format}
    )
    assert response.status_code == 200
    assert calls == [payload]
    assert (
        response.headers["Content-Disposition"]
        == f'attachment; filename="recommendations.{format}"'
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    if format == "json":
        assert response.json["result"] == original(payload)
        assert response.json["schema_version"] == "recommendation-export.v1"


def test_exact_snapshot_export_does_not_call_service_or_ai(client, payload, monkeypatch):
    plain = client.post("/api/v1/recommendations", json=payload)
    assert "X-Recommendation-Export-Token" not in plain.headers
    captured = client.post(
        "/api/v1/recommendations", json=payload, headers={"X-Enable-Export": "true"}
    )
    assert captured.json == plain.json
    token = captured.headers["X-Recommendation-Export-Token"]

    def fail(_payload):
        raise AssertionError("Snapshot must not recompute")

    monkeypatch.setattr(client.application.extensions["recommendation_service"], "recommend", fail)
    body = {"export_token": token, "format": "json"}
    first = client.post("/api/v1/recommendations/export", json=body)
    second = client.post("/api/v1/recommendations/export", json=body)
    assert first.status_code == second.status_code == 200
    assert first.data == second.data
    assert first.json["result"] == captured.json


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"format": "xml", "request": {}},
        {"format": "csv"},
        {"format": "json", "request": {}, "export_token": "x"},
        {"format": "csv", "export_token": []},
        {"format": "csv", "request": {}, "path": "ignored"},
    ],
)
def test_bad_export_inputs(client, body):
    response = client.post(
        "/api/v1/recommendations/export", data=json.dumps(body), content_type="application/json"
    )
    assert response.status_code == 422
    assert response.json["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_and_expired_token(client, payload):
    now = [0]
    client.application.extensions["export_snapshots"] = SnapshotStore(ttl=1, clock=lambda: now[0])
    captured = client.post(
        "/api/v1/recommendations", json=payload, headers={"X-Enable-Export": "true"}
    )
    now[0] = 2
    for token in ("unknown", captured.headers["X-Recommendation-Export-Token"]):
        response = client.post(
            "/api/v1/recommendations/export", json={"export_token": token, "format": "json"}
        )
        assert response.status_code == 404
        assert response.json["error"]["code"] == "EXPORT_NOT_FOUND"


def test_internal_export_failure_is_private(client, payload, monkeypatch, caplog):
    def fail(_payload):
        raise RuntimeError("secret-value C:/private/catalog.sqlite3")

    monkeypatch.setattr(client.application.extensions["recommendation_service"], "recommend", fail)
    response = client.post(
        "/api/v1/recommendations/export", json={"request": payload, "format": "json"}
    )
    assert response.status_code == 500
    assert "secret-value" not in response.text + caplog.text
    assert "C:/private" not in response.text + caplog.text


def test_snapshot_keeps_actual_ai_explanation(repository, payload):
    class ChangingAI:
        calls = 0

        def select_reasons(self, evidence):
            self.calls += 1
            return {
                "items": [
                    {
                        "candidate_id": item.candidate_id,
                        "reason_id": item.semantic_reasons[
                            self.calls % len(item.semantic_reasons)
                        ].reason_id,
                    }
                    for item in evidence
                ]
            }

    ai = ChangingAI()
    app = create_app({"TESTING": True}, repository=repository, ai_client=ai)
    client = app.test_client()
    response = client.post(
        "/api/v1/recommendations", json=payload, headers={"X-Enable-Export": "true"}
    )
    export = client.post(
        "/api/v1/recommendations/export",
        json={"format": "json", "export_token": response.headers["X-Recommendation-Export-Token"]},
    )
    assert ai.calls == 1
    assert export.json["result"] == response.json
