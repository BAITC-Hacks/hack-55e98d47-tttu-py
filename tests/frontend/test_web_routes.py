import csv
import io
import json
import re

import pytest
from flask import Flask

from app.models import ValidationError
from app.web import web
from app.web.exports import ExportStore


class StubService:
    def __init__(self, result=None, error=None):
        if isinstance(result, dict) and result.get("status") in {
            "matched",
            "category_not_found",
            "no_eligible_candidates",
        }:
            result = {
                "count": len(result.get("recommendations", [])),
                "message": "",
                "recommendations": [],
                **result,
            }
        self.result = result
        self.error = error
        self.payload = None
        self.calls = 0

    def recommend(self, payload):
        self.calls += 1
        self.payload = payload
        if self.error:
            raise self.error
        return self.result


def make_client(service, export_store=None):
    app = Flask(__name__, template_folder="../../app/templates", static_folder="../../app/static")
    app.config.update(TESTING=True, RECOMMENDATION_SERVICE=service)
    if export_store is not None:
        app.extensions["web_export_store"] = export_store
    app.register_blueprint(web)
    return app.test_client()


def valid_form(**overrides):
    values = {
        "city": "Астана",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": "1000000",
        "duration_hours": "6",
        "language": "казахский",
    }
    values.update(overrides)
    return values


def recommendation(number=1, **flags):
    return {
        "id": f"HK-{number:05d}",
        "anon_name": f"Подрядчик {number}",
        "category": "Ведущий",
        "city": "Астана",
        "price_from_kzt": flags.get("price_from_kzt", 700000),
        "explanation": f"Конкретное объяснение для подрядчика {number}.",
        "synthetic": flags.get("synthetic", False),
        "city_imputed": flags.get("city_imputed", False),
        "price_imputed": flags.get("price_imputed", False),
    }


def test_get_shows_form_and_non_blank_initial_state():
    response = make_client(StubService()).get("/")
    assert response.status_code == 200
    assert "Здесь появятся рекомендации" in response.text
    assert 'name="budget_kzt"' in response.text


def test_form_maps_all_fields_to_service():
    service = StubService({"status": "matched", "recommendations": [recommendation()]})
    response = make_client(service).post("/", data=valid_form())
    assert response.status_code == 200
    assert service.payload == {
        "city": "Астана",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": 1000000,
        "duration_hours": 6.0,
        "language": "казахский",
        "locale": "ru",
    }


def test_matched_renders_at_most_three_cards_and_markers():
    items = [recommendation(i, synthetic=i == 1, price_imputed=i == 2) for i in range(1, 5)]
    response = make_client(StubService({"status": "matched", "recommendations": items})).post(
        "/", data=valid_form()
    )
    assert response.status_code == 200
    assert response.text.count("recommendation-card") == 3
    assert "Подрядчик 4" not in response.text
    assert "ID профиля: HK-00001" in response.text
    assert "Показано лучших вариантов: 3" in response.text
    assert "Синтетический профиль" in response.text
    assert "Цена заполнена автоматически" in response.text
    assert "Показаны три лучших варианта" in response.text


def test_one_and_two_result_copy():
    for count, copy in ((1, "единственный найденный"), (2, "оба найденных")):
        result = {"status": "matched", "recommendations": [recommendation(i) for i in range(count)]}
        response = make_client(StubService(result)).post("/", data=valid_form())
        assert copy in response.text


def test_category_not_found_is_distinct():
    result = {
        "status": "category_not_found",
        "message": "В Астане нет подрядчиков категории «Флорист».",
    }
    response = make_client(StubService(result)).post("/", data=valid_form())
    assert "Категория не найдена" in response.text
    assert "нет подрядчиков категории" in response.text


def test_no_eligible_candidates_lists_nonzero_reasons():
    result = {
        "status": "no_eligible_candidates",
        "message": "Никто не прошёл условия.",
        "reasons": {"busy": 2, "over_budget": 1, "wrong_format": 0},
    }
    response = make_client(StubService(result)).post("/", data=valid_form())
    assert "Нет подходящих вариантов" in response.text
    assert "заняты на выбранную дату — 2" in response.text
    assert "превышают указанный бюджет — 1" in response.text
    assert "не работают с выбранным форматом" not in response.text


def test_empty_matched_response_never_leaves_blank_area():
    response = make_client(StubService({"status": "matched", "recommendations": []})).post(
        "/", data=valid_form()
    )
    assert "Рекомендации не получены" in response.text


def test_validation_and_backend_errors_are_visible_and_preserve_form():
    validation = make_client(
        StubService(error=ValidationError({"budget_kzt": "Бюджет некорректен"}))
    ).post("/", data=valid_form())
    assert validation.status_code == 422
    assert "Проверьте" in validation.text
    assert 'value="1000000"' in validation.text

    backend = make_client(StubService(error=RuntimeError("secret backend detail"))).post(
        "/", data=valid_form()
    )
    assert backend.status_code == 503
    assert "Сервис временно недоступен" in backend.text
    assert "secret backend detail" not in backend.text


def test_malformed_number_has_localized_validation_error():
    response = make_client(StubService()).post("/", data=valid_form(budget_kzt="not-a-number"))
    assert response.status_code == 422
    assert "нужны числовые значения" in response.text
    assert "invalid literal" not in response.text


@pytest.mark.parametrize(
    ("locale", "lang", "heading", "submit"),
    (
        ("ru", "ru", "Найдём до трёх подходящих подрядчиков", "Получить рекомендации"),
        ("kk", "kk", "Үшке дейін лайықты мердігер табамыз", "Ұсынымдарды алу"),
        ("en", "en", "Find up to three suitable contractors", "Get recommendations"),
    ),
)
def test_product_locales_and_html_lang(locale, lang, heading, submit):
    response = make_client(StubService()).get(f"/?locale={locale}")
    assert response.status_code == 200
    assert f'<html lang="{lang}" data-bs-theme="light"' in response.text
    assert heading in response.text
    assert submit in response.text


def test_unknown_locale_falls_back_to_russian():
    response = make_client(StubService()).get("/?locale=unsupported")
    assert '<html lang="ru" data-bs-theme="light"' in response.text
    assert "Получить рекомендации" in response.text


def test_locale_switch_keeps_contractor_language_independent():
    service = StubService({"status": "matched", "recommendations": [recommendation()]})
    client = make_client(service)
    initial = client.post("/", data=valid_form())
    response = client.post(
        "/",
        data={
            **valid_form(),
            "locale": "en",
            "switch_locale": "1",
            "view_id": _export_id(initial),
        },
    )
    assert response.status_code == 200
    assert '<html lang="en" data-bs-theme="light"' in response.text
    assert '<option value="казахский" selected>Kazakh</option>' in response.text
    assert service.payload["language"] == "казахский"
    assert service.calls == 1
    assert service.payload["locale"] == "ru"
    assert "switch_locale" not in service.payload


def test_new_search_labels_explanation_with_generation_locale():
    result = {
        "status": "matched",
        "message": "Найден один подрядчик.",
        "recommendations": [recommendation(synthetic=True, price_imputed=True)],
    }
    response = make_client(StubService(result)).post("/", data={**valid_form(), "locale": "en"})
    assert "Why this matches · English" in response.text
    assert 'class="mb-0 explanation-text" lang="en"' in response.text
    assert "Synthetic profile" in response.text
    assert "Price filled automatically" in response.text
    assert "Price from" in response.text
    assert "Original explanation (Russian)" not in response.text


@pytest.mark.parametrize(
    ("locale", "title", "reason"),
    (
        ("kk", "Лайықты нұсқалар жоқ", "таңдалған күні бос емес"),
        ("en", "No eligible options", "unavailable on the selected date"),
    ),
)
def test_zero_result_reasons_are_localized(locale, title, reason):
    result = {
        "status": "no_eligible_candidates",
        "reasons": {"busy": 2, "over_budget": 0},
        "recommendations": [],
    }
    response = make_client(StubService(result)).post("/", data={**valid_form(), "locale": locale})
    assert title in response.text
    assert reason in response.text
    assert "заняты на выбранную дату" not in response.text


def _export_id(response):
    match = re.search(r'name="export_id" value="([^"]+)"', response.text)
    assert match is not None
    return match.group(1)


def test_export_controls_exist_for_successful_and_zero_recommendations():
    matched = make_client(
        StubService({"status": "matched", "recommendations": [recommendation()]})
    ).post("/", data=valid_form())
    assert "Скачать CSV" in matched.text
    assert "Скачать JSON" in matched.text

    initial = make_client(StubService()).get("/")
    empty = make_client(StubService({"status": "category_not_found", "recommendations": []})).post(
        "/", data=valid_form()
    )
    assert "Скачать CSV" not in initial.text
    assert "Скачать CSV" in empty.text


def test_json_export_preserves_exact_query_and_visible_candidates():
    items = [recommendation(1), recommendation(2, price_from_kzt=650000)]
    client = make_client(StubService({"status": "matched", "recommendations": items}))
    shown = client.post("/", data={**valid_form(), "locale": "en"})
    token = _export_id(shown)

    exported = client.post(
        "/recommendations/export/json", data={"export_id": token, "locale": "en"}
    )
    payload = json.loads(exported.text)
    assert exported.status_code == 200
    assert exported.content_type == "application/json; charset=utf-8"
    assert exported.headers["Content-Disposition"] == 'attachment; filename="recommendations.json"'
    assert payload["request"] == {
        "city": "Астана",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": 1000000,
        "duration_hours": 6.0,
        "language": "казахский",
    }
    assert [item["id"] for item in payload["result"]["recommendations"]] == ["HK-00001", "HK-00002"]


def test_csv_export_preserves_query_and_candidates():
    client = make_client(StubService({"status": "matched", "recommendations": [recommendation()]}))
    shown = client.post("/", data=valid_form())
    exported = client.post(
        "/recommendations/export/csv", data={"export_id": _export_id(shown), "locale": "ru"}
    )
    rows = list(csv.DictReader(io.StringIO(exported.text.lstrip("\ufeff"))))
    assert exported.status_code == 200
    assert exported.content_type == "text/csv; charset=utf-8"
    assert exported.headers["Content-Disposition"] == 'attachment; filename="recommendations.csv"'
    assert rows[0]["request_language"] == "казахский"
    assert rows[0]["id"] == "HK-00001"


def test_unknown_export_snapshot_is_non_blank_and_cannot_be_tampered():
    response = make_client(StubService()).post(
        "/recommendations/export/json",
        data={"export_id": "attacker-controlled", "locale": "en", "anon_name": "Injected"},
    )
    assert response.status_code == 404
    assert "Export unavailable" in response.text
    assert "Injected" not in response.text


def test_expired_export_snapshot_is_non_blank():
    client = make_client(
        StubService({"status": "matched", "recommendations": [recommendation()]}),
        export_store=ExportStore(ttl_seconds=0),
    )
    shown = client.post("/", data=valid_form())
    response = client.post(
        "/recommendations/export/json",
        data={"export_id": _export_id(shown), "locale": "ru"},
    )
    assert response.status_code == 404
    assert "Экспорт недоступен" in response.text


@pytest.mark.parametrize("count", (2, 3))
def test_comparison_renders_two_or_three_candidates_without_reranking(count):
    items = [
        recommendation(index, price_from_kzt=600000 + index * 10000)
        for index in range(1, count + 1)
    ]
    response = make_client(StubService({"status": "matched", "recommendations": items})).post(
        "/", data={**valid_form(), "locale": "en"}
    )
    assert "Compare recommendations" in response.text
    assert "Scrollable recommendation comparison table" in response.text
    assert '<caption class="visually-hidden">' in response.text
    assert response.text.count('scope="col"') == count + 1
    positions = [response.text.rfind(f"Contractor {index}") for index in range(1, count + 1)]
    assert positions == sorted(positions)
    assert "winner" not in response.text.casefold()
    for index in range(1, count + 1):
        assert f"Specific explanation for contractor {index}." not in response.text
        assert f"Конкретное объяснение для подрядчика {index}." in response.text


def test_comparison_is_hidden_for_one_or_zero_results():
    one = make_client(
        StubService({"status": "matched", "recommendations": [recommendation()]})
    ).post("/", data=valid_form())
    zero = make_client(StubService({"status": "matched", "recommendations": []})).post(
        "/", data=valid_form()
    )
    assert "Сравнение рекомендаций" not in one.text
    assert "Сравнение рекомендаций" not in zero.text


def test_no_eligible_without_reasons_and_unknown_status_are_non_blank():
    no_reasons = make_client(
        StubService({"status": "no_eligible_candidates", "recommendations": [], "reasons": {}})
    ).post("/", data={**valid_form(), "locale": "en"})
    unknown = make_client(StubService({"status": "future_status"})).post(
        "/", data={**valid_form(), "locale": "en"}
    )
    assert "No eligible options" in no_reasons.text
    assert "Change the criteria in the form or try again." in no_reasons.text
    assert "No recommendations received" in unknown.text


def test_accessibility_critical_labels_are_present():
    response = make_client(StubService()).get("/?locale=en")
    assert 'aria-label="Interface language"' in response.text
    assert 'aria-describedby="city-error"' in response.text
    assert 'aria-describedby="event-date-help event-date-error"' in response.text
    assert "Contractor communication language" in response.text
