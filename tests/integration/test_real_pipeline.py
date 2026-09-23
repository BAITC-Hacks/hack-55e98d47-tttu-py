from time import monotonic


def query(**changes):
    return {
        "city": "Алматы",
        "event_date": "2026-10-15",
        "event_format": "свадьба",
        "category": "Ведущий",
        "budget_kzt": 6000000,
        **changes,
    }


def test_dense_rare_empty_and_date_demo(real_app, real_catalog):
    client = real_app.test_client()
    responses = [
        client.post("/api/v1/recommendations", json=payload)
        for payload in (
            query(),
            query(category="Флорист"),
            query(budget_kzt=0),
            query(event_date="2026-10-16"),
            query(city="Зарубежье", category="Флорист"),
        )
    ]
    assert all(response.status_code == 200 for response in responses)
    dense, rare, rejected, next_date, absent = [response.json for response in responses]
    assert dense["count"] == 3
    assert [card["id"] for card in dense["recommendations"]] == [
        "HK-35215",
        "HK-27222",
        "HK-77838",
    ]
    assert rare["count"] == 2
    assert any(card["synthetic"] for card in rare["recommendations"])
    assert rejected["status"] == "no_eligible_candidates"
    assert absent["status"] == "category_not_found"
    ids_first = {card["id"] for card in dense["recommendations"]}
    ids_second = {card["id"] for card in next_date["recommendations"]}
    assert ids_first != ids_second
    assert "заняты 2 подрядчика" in dense["message"]
    assert "заняты 5 подрядчиков" in next_date["message"]
    by_id = {profile.id: profile for profile in real_catalog}
    assert any(
        "2026-10-16" in by_id[candidate_id].busy_dates for candidate_id in ids_first - ids_second
    )
    for day, result in (("2026-10-15", dense), ("2026-10-16", next_date)):
        assert all(day not in by_id[card["id"]].busy_dates for card in result["recommendations"])


def test_real_catalog_adversarial_constraints_are_diagnostic(real_app):
    result = (
        real_app.test_client()
        .post(
            "/api/v1/recommendations",
            json=query(budget_kzt=0, duration_hours=24, language="казахский"),
        )
        .json
    )
    assert result["status"] == "no_eligible_candidates"
    assert result["reasons"] == {
        "busy": 2,
        "over_budget": 10,
        "wrong_format": 4,
        "duration_too_long": 10,
        "language_mismatch": 5,
    }


def test_venues_use_the_same_pipeline(real_app):
    result = (
        real_app.test_client()
        .post(
            "/api/v1/recommendations",
            json=query(category="Банкетный зал", event_date="2027-01-01"),
        )
        .json
    )
    assert result["status"] == "matched"
    assert all(card["category"] == "Банкетный зал" for card in result["recommendations"])


def test_real_api_determinism_and_response_budget(real_app):
    start = monotonic()
    client = real_app.test_client()
    results = [client.post("/api/v1/recommendations", json=query()).json for _ in range(20)]
    assert all(result == results[0] for result in results)
    assert monotonic() - start < 10
