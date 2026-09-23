from flask import Flask

from app.web import web


class StubService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.payload = None

    def recommend(self, payload):
        self.payload = payload
        if self.error:
            raise self.error
        return self.result


def make_client(service):
    app = Flask(__name__, template_folder="../../app/templates", static_folder="../../app/static")
    app.config.update(TESTING=True, RECOMMENDATION_SERVICE=service)
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
        "price_from_kzt": 700000,
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
    validation = make_client(StubService(error=ValueError("Бюджет некорректен"))).post(
        "/", data=valid_form()
    )
    assert validation.status_code == 422
    assert "Бюджет некорректен" in validation.text
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
