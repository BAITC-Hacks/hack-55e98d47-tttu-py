"""Regression coverage for the production Flask → Jinja integration."""


def test_application_registers_web_flow_and_uses_shared_service(client, payload):
    initial = client.get("/")
    assert initial.status_code == 200
    assert "Здесь появятся рекомендации" in initial.text

    response = client.post(
        "/",
        data={
            **payload,
            "budget_kzt": str(payload["budget_kzt"]),
            "duration_hours": str(payload["duration_hours"]),
        },
    )
    assert response.status_code == 200
    assert "Тестовый ведущий" in response.text
    assert "Почему подходит" in response.text


def test_web_distinguishes_all_contract_outcomes(client, payload):
    form = {
        **payload,
        "budget_kzt": str(payload["budget_kzt"]),
        "duration_hours": str(payload["duration_hours"]),
    }
    matched = client.post("/", data=form)
    unavailable = client.post("/", data={**form, "budget_kzt": "0"})
    absent = client.post("/", data={**form, "category": "Фотограф"})

    assert matched.status_code == unavailable.status_code == absent.status_code == 200
    assert "Подходящие подрядчики" in matched.text
    assert "Нет подходящих вариантов" in unavailable.text
    assert "превышают указанный бюджет" in unavailable.text
    assert "Категория не найдена" in absent.text
