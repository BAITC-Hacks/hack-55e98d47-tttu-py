import pytest


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


def test_recommendation_schema(client, payload):
    response = client.post("/api/v1/recommendations", json=payload)
    assert response.status_code == 200
    body = response.json
    assert set(body) == {"status", "count", "message", "recommendations"}
    assert body["status"] == "matched"
    assert body["count"] == len(body["recommendations"]) == 1
    assert set(body["recommendations"][0]) == {
        "id",
        "anon_name",
        "category",
        "city",
        "price_from_kzt",
        "synthetic",
        "city_imputed",
        "price_imputed",
        "explanation",
    }


@pytest.mark.parametrize(
    "data,content_type",
    [
        ("{", "application/json"),
        ("null", "application/json"),
        ("[]", "application/json"),
        ("{}", "text/plain"),
        ("", "application/json"),
        ("x" * 17000, "application/json"),
    ],
)
def test_bad_body_uses_contract_error(client, data, content_type):
    response = client.post("/api/v1/recommendations", data=data, content_type=content_type)
    assert response.status_code == 422
    assert response.json["error"]["code"] == "VALIDATION_ERROR"
    assert response.json["error"]["details"]


def test_missing_fields_are_aggregated(client):
    response = client.post("/api/v1/recommendations", json={})
    assert response.status_code == 422
    assert set(response.json["error"]["details"]) == {
        "city",
        "event_date",
        "event_format",
        "category",
        "budget_kzt",
    }


def test_three_outcomes(client, payload):
    matched = client.post("/api/v1/recommendations", json=payload).json
    empty = client.post("/api/v1/recommendations", json={**payload, "budget_kzt": 0}).json
    absent = client.post("/api/v1/recommendations", json={**payload, "category": "Фотограф"}).json
    assert {matched["status"], empty["status"], absent["status"]} == {
        "matched",
        "category_not_found",
        "no_eligible_candidates",
    }
    assert empty["reasons"]["over_budget"] == 1
    assert all(response["message"] for response in (matched, empty, absent))
