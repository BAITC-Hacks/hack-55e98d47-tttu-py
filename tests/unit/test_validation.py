import pytest

from app.models import RecommendationRequest, ValidationError


@pytest.mark.parametrize("field", ["city", "event_date", "event_format", "category", "budget_kzt"])
def test_required_fields(payload, field):
    del payload[field]
    with pytest.raises(ValidationError) as error:
        RecommendationRequest.from_payload(payload)
    assert field in error.value.details


@pytest.mark.parametrize("value", [None, [], "", 1, True])
def test_body_must_be_object(value):
    with pytest.raises(ValidationError):
        RecommendationRequest.from_payload(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("city", " "),
        ("category", []),
        ("event_format", "a" * 121),
        ("event_date", "2026-02-30"),
        ("event_date", "20261015"),
        ("event_date", "2026-1-01"),
        ("event_date", "2026-10-15T00:00:00"),
        ("event_date", True),
        ("budget_kzt", -1),
        ("budget_kzt", True),
        ("budget_kzt", "600000"),
        ("budget_kzt", 600000.0),
        ("budget_kzt", float("nan")),
        ("budget_kzt", 10**16),
        ("duration_hours", 0),
        ("duration_hours", -1),
        ("duration_hours", True),
        ("duration_hours", "6"),
        ("duration_hours", float("inf")),
        ("duration_hours", float("nan")),
        ("language", []),
        ("language", ""),
        ("language", "a" * 121),
    ],
)
def test_invalid_fields(payload, field, value):
    payload[field] = value
    with pytest.raises(ValidationError) as error:
        RecommendationRequest.from_payload(payload)
    assert field in error.value.details


def test_optional_null_and_missing(payload):
    payload.pop("duration_hours")
    payload["language"] = None
    request = RecommendationRequest.from_payload(payload)
    assert request.duration_hours is None
    assert request.language is None


def test_fractional_duration_and_zero_budget(payload):
    payload.update(duration_hours=0.5, budget_kzt=0)
    assert RecommendationRequest.from_payload(payload).duration_hours == 0.5


def test_whitespace_and_unknown_values_are_discovered_not_enumerated(payload):
    payload.update(city=" Несуществующий город ", category="Неизвестная категория")
    request = RecommendationRequest.from_payload(payload)
    assert request.city == "Несуществующий город"
