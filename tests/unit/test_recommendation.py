from dataclasses import replace

import pytest

from app.models import RecommendationRequest
from app.services import RecommendationService
from app.services.recommendation import REASONS, violations


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"busy_dates": ("2026-10-15",)}, "busy"),
        ({"price_from_kzt": 1000001}, "over_budget"),
        ({"event_formats": ("той",)}, "wrong_format"),
        ({"max_hours": 5}, "duration_too_long"),
        ({"languages": ("русский",)}, "language_mismatch"),
    ],
)
def test_each_hard_filter(profile, payload, repository, change, reason):
    repository.initialize((replace(profile, **change),))
    result = RecommendationService(repository).recommend(payload)
    assert result["status"] == "no_eligible_candidates"
    assert result["recommendations"] == []
    assert result["reasons"] == {key: int(key == reason) for key in REASONS}


@pytest.mark.parametrize("change", [{"city": "Алматы"}, {"categories": ("Фотограф",)}])
def test_city_category_discovery(profile, payload, repository, change):
    repository.initialize((replace(profile, **change),))
    result = RecommendationService(repository).recommend(payload)
    assert result["status"] == "category_not_found"
    assert result["message"]
    assert "reasons" not in result


def test_multiple_violations_are_all_counted(profile, payload, repository):
    bad = replace(
        profile,
        busy_dates=(payload["event_date"],),
        price_from_kzt=1000001,
        event_formats=("той",),
        max_hours=1,
        languages=("русский",),
    )
    repository.initialize((bad,))
    assert RecommendationService(repository).recommend(payload)["reasons"] == dict.fromkeys(
        REASONS, 1
    )


def test_inclusive_boundaries(profile, payload):
    candidate = replace(profile, price_from_kzt=payload["budget_kzt"], max_hours=6)
    assert violations(candidate, RecommendationRequest.from_payload(payload)) == ()


def test_null_max_hours_is_not_zero_or_unlimited_claim(profile, payload, repository):
    repository.initialize((replace(profile, max_hours=None),))
    payload["duration_hours"] = 1000
    result = RecommendationService(repository).recommend(payload)
    assert result["count"] == 1
    assert "не привязана к длительности" in result["recommendations"][0]["explanation"]
    assert "безлимит" not in result["recommendations"][0]["explanation"]


def test_omitted_optional_constraints(profile, payload, repository):
    repository.initialize((replace(profile, max_hours=1, languages=("английский",)),))
    payload.pop("duration_hours")
    payload.pop("language")
    assert RecommendationService(repository).recommend(payload)["count"] == 1


def test_multicategory_requested_category_and_flags(payload, repository):
    payload["category"] = "Ведущий церемонии"
    card = RecommendationService(repository).recommend(payload)["recommendations"][0]
    assert card["category"] == payload["category"]
    assert card["synthetic"] is True
    assert card["city_imputed"] is False
    assert card["price_imputed"] is True


@pytest.mark.parametrize("number", [1, 2, 3, 4, 6])
def test_cardinality(payload, repository, many_profiles, number):
    repository.initialize(many_profiles[:number])
    result = RecommendationService(repository).recommend(payload)
    assert result["count"] == len(result["recommendations"]) == min(3, number)
    if number < 3:
        assert "меньше трёх" in result["message"]


def test_repeated_and_reordered_catalog_is_deterministic(payload, repository, many_profiles):
    outputs = []
    for profiles in (
        many_profiles,
        many_profiles[::-1],
        many_profiles[2:] + many_profiles[:2],
    ):
        repository.initialize(profiles)
        service = RecommendationService(repository)
        outputs.extend(
            [
                [card["id"] for card in service.recommend(payload)["recommendations"]]
                for _ in range(4)
            ]
        )
    assert outputs == [["HK-00001", "HK-00002", "HK-00003"]] * 12


def test_busy_or_expensive_semantic_match_never_rescued(profile, payload, repository):
    repository.initialize(
        (
            replace(profile, id="busy", busy_dates=(payload["event_date"],)),
            replace(profile, id="costly", price_from_kzt=payload["budget_kzt"] + 1),
            replace(profile, id="eligible", description="Работает с гостями на мероприятиях"),
        )
    )
    assert [
        card["id"]
        for card in RecommendationService(repository).recommend(payload)["recommendations"]
    ] == ["eligible"]


def test_date_changes_availability(payload, repository):
    service = RecommendationService(repository)
    assert service.recommend(payload)["status"] == "matched"
    payload["event_date"] = "2026-10-16"
    assert service.recommend(payload)["reasons"]["busy"] == 1


def test_service_rechecks_discovery_boundary(profile, payload):
    class FaultyRepository:
        def discover(self, city, category):
            return (
                replace(profile, city="Алматы"),
                replace(profile, categories=("Фотограф",)),
            )

    assert (
        RecommendationService(FaultyRepository()).recommend(payload)["status"]
        == "category_not_found"
    )
