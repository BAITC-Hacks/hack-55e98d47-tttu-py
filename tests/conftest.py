from dataclasses import replace

import pytest

from app import create_app
from app.config import ROOT
from app.models import Contractor
from app.repositories import CatalogRepository, load_csv


@pytest.fixture
def profile():
    return Contractor(
        id="HK-00001",
        anon_name="Тестовый ведущий",
        categories=("Ведущий", "Ведущий церемонии"),
        city="Астана",
        price_from_kzt=600000,
        event_formats=("свадьба", "корпоратив"),
        languages=("русский", "казахский"),
        max_hours=8,
        busy_dates=("2026-10-16",),
        description="Ведёт свадебные церемонии с живой импровизацией. Проводит интерактивные игры с гостями.",
        synthetic=True,
        city_imputed=False,
        price_imputed=True,
    )


@pytest.fixture
def payload():
    return {
        "city": "Астана",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": 1000000,
        "duration_hours": 6,
        "language": "казахский",
    }


@pytest.fixture
def repository(tmp_path, profile):
    result = CatalogRepository(tmp_path / "catalog.sqlite3")
    result.initialize((profile,))
    return result


@pytest.fixture
def client(repository):
    return create_app({"TESTING": True, "LLM_API_KEY": ""}, repository=repository).test_client()


@pytest.fixture
def real_catalog():
    return load_csv(ROOT / "data/hackathon_dataset.csv")


@pytest.fixture
def real_app(tmp_path):
    return create_app(
        {"TESTING": True, "LLM_API_KEY": "", "DATABASE_PATH": tmp_path / "real.sqlite3"}
    )


@pytest.fixture
def many_profiles(profile):
    return tuple(
        replace(
            profile,
            id=f"HK-{index:05}",
            description=f"Проводит свадебные церемонии: программа номер {index}",
        )
        for index in range(1, 7)
    )
