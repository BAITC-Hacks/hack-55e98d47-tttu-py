"""Small deterministic catalog covering every mandatory case from the technical brief."""

from pathlib import Path

from app.repositories import CatalogRepository, load_csv
from app.services import RecommendationService


def payload(**overrides):
    return {
        "city": "Астана",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": 800000,
        "duration_hours": 6,
        "language": "казахский",
        **overrides,
    }


def service_from_contract_fixture(tmp_path):
    path = Path(__file__).parent.parent / "fixtures" / "contract_scenarios.csv"
    catalog = load_csv(path)
    repository = CatalogRepository(tmp_path / "contract-scenarios.sqlite3")
    repository.initialize(catalog)
    return RecommendationService(repository), catalog


def test_contract_fixture_is_valid_and_covers_catalog_shapes(tmp_path):
    service, catalog = service_from_contract_fixture(tmp_path)
    assert len(catalog) == 12
    assert any(item.synthetic for item in catalog)
    assert any(len(item.categories) > 1 for item in catalog)
    assert service.recommend(payload())["status"] == "matched"


def test_contract_fixture_exercises_constraints_and_date_sensitivity(tmp_path):
    service, _catalog = service_from_contract_fixture(tmp_path)
    first = service.recommend(payload())
    second = service.recommend(payload(event_date="2026-10-16"))
    rejected = service.recommend(payload(budget_kzt=0))

    assert [item["id"] for item in first["recommendations"]] == [
        "TST-003",
        "TST-001",
        "TST-008",
    ]
    assert [item["id"] for item in second["recommendations"]] == [
        "TST-003",
        "TST-002",
        "TST-008",
    ]
    assert "заняты 1 подрядчик" in first["message"]
    assert rejected["status"] == "no_eligible_candidates"
    assert rejected["reasons"] == {
        "busy": 1,
        "over_budget": 8,
        "wrong_format": 1,
        "duration_too_long": 1,
        "language_mismatch": 1,
    }


def test_contract_fixture_covers_rare_venue_and_category_absent_outcomes(tmp_path):
    service, _catalog = service_from_contract_fixture(tmp_path)
    rare = service.recommend(
        payload(city="Алматы", category="Флорист", duration_hours=None, language=None)
    )
    venue = service.recommend(payload(category="Банкетный зал", duration_hours=None, language=None))
    absent = service.recommend(payload(city="Зарубежье", category="Флорист"))

    assert rare["status"] == "matched"
    assert any(item["synthetic"] for item in rare["recommendations"])
    assert venue["status"] == "matched"
    assert venue["recommendations"][0]["category"] == "Банкетный зал"
    assert absent["status"] == "category_not_found"
