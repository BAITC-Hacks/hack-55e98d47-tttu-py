from dataclasses import replace

from app.models import RecommendationRequest
from app.services.ranking import rank, score, semantic_score


def test_semantic_signal_is_bounded(profile, payload):
    request = RecommendationRequest.from_payload(payload)
    for text in ("", profile.description, "свадьба невеста жених брак ведущий " * 1000):
        assert 0 <= semantic_score(text, request) <= 1


def test_price_is_not_the_only_ranking_factor(profile, payload):
    request = RecommendationRequest.from_payload(payload)
    relevant = replace(
        profile,
        id="relevant",
        description="Ведущий свадеб: невеста, жених и брак",
        price_from_kzt=600000,
    )
    expensive = replace(
        profile,
        id="expensive",
        description="Общее описание услуг",
        price_from_kzt=1000000,
    )
    assert rank((expensive, relevant), request)[0].id == "relevant"


def test_stable_id_tie_break_and_optional_signals(profile, payload):
    request = RecommendationRequest.from_payload(payload)
    assert rank((replace(profile, id="b"), replace(profile, id="a")), request)[0].id == "a"
    assert score(profile, request) > score(
        profile, replace(request, duration_hours=None, language=None)
    )
