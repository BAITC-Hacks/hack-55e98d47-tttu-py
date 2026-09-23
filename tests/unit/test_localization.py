from dataclasses import asdict

import pytest

from app.models import RecommendationRequest
from app.services import RecommendationService
from app.services.explanation import ExplanationService
from app.services.ranking import score


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
def test_locale_does_not_change_model_score_ids_or_evidence(real_app, locale):
    payload = {
        "city": "Алматы",
        "category": "Ведущий",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "budget_kzt": 6000000,
        "language": "казахский",
        "duration_hours": 6,
    }
    localized = {**payload, "locale": locale}
    request = RecommendationRequest.from_payload(payload)
    translated_request = RecommendationRequest.from_payload(localized)
    assert asdict(request) == asdict(translated_request)
    for profile in real_app.extensions["catalog_repository"].all():
        assert score(profile, request) == score(profile, translated_request)
    service = real_app.extensions["recommendation_service"]
    before = service.recommend(payload)
    after = service.recommend(localized)
    assert [
        {key: value for key, value in card.items() if key != "explanation"}
        for card in before["recommendations"]
    ] == [
        {key: value for key, value in card.items() if key != "explanation"}
        for card in after["recommendations"]
    ]
    if locale == "ru":
        assert before == after
    else:
        assert before["message"] != after["message"]


def test_ai_evidence_identical_across_locales(repository, payload):
    class AI:
        received = []

        def select_reasons(self, evidence):
            self.received.append(evidence)
            raise TimeoutError

    ai = AI()
    service = RecommendationService(repository, ExplanationService(ai))
    for locale in ("ru", "kk", "en"):
        result = service.recommend({**payload, "locale": locale})
        source = ai.received[-1][0].semantic_reasons[0].source_text
        assert source in result["recommendations"][0]["explanation"]
    assert ai.received[0] == ai.received[1] == ai.received[2]


@pytest.mark.parametrize("locale", ["ru", "kk", "en"])
def test_language_alias_is_independent_of_locale(client, payload, locale):
    original = client.post("/api/v1/recommendations", json={**payload, "locale": locale})
    alias = {**payload, "locale": locale, "communication_language": payload["language"]}
    del alias["language"]
    response = client.post("/api/v1/recommendations", json=alias)
    assert response.json == original.json
    alias["communication_language"] = "английский"
    assert (
        client.post("/api/v1/recommendations", json=alias).json["status"]
        == "no_eligible_candidates"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"locale": "fr"},
        {"locale": None},
        {"locale": []},
        {"communication_language": "английский"},
        {"communication_language": None},
    ],
)
def test_invalid_locale_and_alias_conflict(client, payload, change):
    assert client.post("/api/v1/recommendations", json={**payload, **change}).status_code == 422


def test_localized_error_details_and_zero_states(client, payload):
    error = client.post(
        "/api/v1/recommendations", json={**payload, "locale": "en", "budget_kzt": -1}
    )
    assert error.json["error"]["message"] == "Invalid request parameters."
    assert "integer" in error.json["error"]["details"]["budget_kzt"]
    for locale in ("kk", "en"):
        empty = client.post(
            "/api/v1/recommendations", json={**payload, "locale": locale, "budget_kzt": 0}
        ).json
        absent = client.post(
            "/api/v1/recommendations",
            json={**payload, "locale": locale, "category": "Нет категории"},
        ).json
        assert empty["status"] == "no_eligible_candidates"
        assert empty["reasons"]["over_budget"] == 1
        assert absent["status"] == "category_not_found"


def test_export_locale_and_language_normalization(client, payload):
    payload = {**payload, "locale": "en", "communication_language": payload["language"]}
    del payload["language"]
    response = client.post(
        "/api/v1/recommendations/export", json={"request": payload, "format": "json"}
    )
    assert response.json["locale"] == "en"
    assert response.json["request"]["language"] == "казахский"
    assert "locale" not in response.json["request"]
    assert (
        "Original description (untranslated)"
        in response.json["result"]["recommendations"][0]["explanation"]
    )
