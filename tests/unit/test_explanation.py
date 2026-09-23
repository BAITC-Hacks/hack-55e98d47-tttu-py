from dataclasses import replace

import pytest

from app.models import RecommendationRequest
from app.services import RecommendationService
from app.services.evidence import build_evidence
from app.services.explanation import ExplanationService, render_explanation


class FakeAI:
    def __init__(self, output=None, fail=False):
        self.output = output
        self.fail = fail
        self.received = None

    def select_reasons(self, evidence):
        self.received = evidence
        if self.fail:
            raise TimeoutError("private-provider-detail")
        return self.output


def test_evidence_is_specific(profile, payload):
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    assert evidence.candidate_id == profile.id
    assert evidence.available_on_date
    assert evidence.description == profile.description
    assert evidence.language_match == payload["language"]
    assert evidence.requested_duration_hours == 6
    assert evidence.max_hours == 8
    assert evidence.semantic_reasons
    assert all(reason.source_text in profile.description for reason in evidence.semantic_reasons)


def test_ai_success_selects_grounded_reason(profile, payload):
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    reason = evidence.semantic_reasons[-1]
    ai = FakeAI({"items": [{"candidate_id": profile.id, "reason_id": reason.reason_id}]})
    text = ExplanationService(ai).explain((evidence,))[profile.id]
    assert reason.source_text in text
    assert "Цена от 600 000 ₸" in text
    assert "казахский" in text
    assert "6 ч" in text
    assert "8 ч" in text


@pytest.mark.parametrize(
    "output",
    [
        None,
        "Отличный профессионал",
        {},
        {"items": []},
        {"items": "bad"},
        {"items": [{"candidate_id": "unknown", "reason_id": None}]},
        {"items": [{"candidate_id": "HK-00001", "reason_id": "made-up"}]},
        {"items": [{"candidate_id": "HK-00001", "reason_id": []}]},
        {"items": [{"candidate_id": [], "reason_id": None}]},
        {
            "items": [
                {
                    "candidate_id": "HK-00001",
                    "reason_id": None,
                    "explanation": "Гарантированная скидка",
                }
            ]
        },
    ],
)
def test_invalid_ai_output_falls_back(profile, payload, output):
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    assert ExplanationService(FakeAI(output)).explain((evidence,)) == {
        profile.id: render_explanation(evidence)
    }


def test_ai_failure_is_deterministic_and_private(profile, payload):
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    service = ExplanationService(FakeAI(fail=True))
    answers = [service.explain((evidence,)) for _ in range(4)]
    assert answers == [{profile.id: render_explanation(evidence)}] * 4
    assert "private-provider-detail" not in str(answers)


def test_only_top_eligible_evidence_sent_and_ai_never_orders(repository, many_profiles, payload):
    rejected = replace(many_profiles[0], id="busy", busy_dates=(payload["event_date"],))
    repository.initialize(many_profiles + (rejected,))
    ai = FakeAI()
    service = RecommendationService(repository, ExplanationService(ai))
    result = service.recommend(payload)
    expected = [card["id"] for card in result["recommendations"]]
    assert [item.candidate_id for item in ai.received] == expected
    assert len(ai.received) == 3
    ai.output = {
        "items": [
            {
                "candidate_id": item.candidate_id,
                "reason_id": item.semantic_reasons[0].reason_id,
            }
            for item in ai.received[::-1]
        ]
    }
    assert [card["id"] for card in service.recommend(payload)["recommendations"]] == expected


def test_no_ai_for_zero_candidates(repository, payload):
    ai = FakeAI(fail=True)
    payload["budget_kzt"] = 0
    RecommendationService(repository, ExplanationService(ai)).recommend(payload)
    assert ai.received is None


def test_duplicate_or_cross_candidate_reason_is_rejected(profile, payload):
    first = build_evidence(profile, RecommendationRequest.from_payload(payload))
    second = build_evidence(
        replace(profile, id="HK-00002"), RecommendationRequest.from_payload(payload)
    )
    for items in (
        [
            {
                "candidate_id": first.candidate_id,
                "reason_id": first.semantic_reasons[0].reason_id,
            }
        ]
        * 2,
        [
            {
                "candidate_id": first.candidate_id,
                "reason_id": second.semantic_reasons[0].reason_id,
            },
            {
                "candidate_id": second.candidate_id,
                "reason_id": first.semantic_reasons[0].reason_id,
            },
        ],
    ):
        assert ExplanationService(FakeAI({"items": items})).explain(
            (first, second)
        ) == ExplanationService().explain((first, second))


def test_identical_profiles_still_have_distinct_explanations(profile, payload):
    request = RecommendationRequest.from_payload(payload)
    evidence = (
        build_evidence(profile, request),
        build_evidence(replace(profile, id="HK-00002"), request),
    )
    output = ExplanationService().explain(evidence)
    assert len(set(output.values())) == 2
    assert all(profile.anon_name not in text for text in output.values())


def test_source_fragments_preserve_whitespace_and_decimals(profile, payload):
    profile = replace(profile, description="Стаж  12.5 лет в свадебной съёмке. Играет на скрипке.")
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    assert all(item.source_text in profile.description for item in evidence.semantic_reasons)
    assert any("12.5 лет" in item.source_text for item in evidence.semantic_reasons)


@pytest.mark.parametrize(
    "change",
    [
        {"busy_dates": ("2026-10-15",)},
        {"price_from_kzt": 2000000},
        {"city": "Алматы"},
        {"categories": ("Фотограф",)},
    ],
)
def test_evidence_builder_refuses_ineligible_profile(profile, payload, change):
    with pytest.raises(ValueError, match="eligible"):
        build_evidence(replace(profile, **change), RecommendationRequest.from_payload(payload))


def test_generic_praise_is_not_explanation_evidence(profile, payload):
    profile = replace(
        profile,
        description="Отличный выбор для вашего праздника. Ваш праздник в руках ведущего, который делает уровень. Играет на скрипке.",
    )
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    assert [item.source_text for item in evidence.semantic_reasons] == ["Играет на скрипке"]
    assert "Отличный" not in render_explanation(evidence)


def test_real_catalog_fallback_is_specific_and_bounded(real_catalog):
    for profile in real_catalog:
        request = RecommendationRequest.from_payload(
            {
                "city": profile.city,
                "category": profile.categories[0],
                "event_format": profile.event_formats[0],
                "event_date": "2027-01-01",
                "budget_kzt": profile.price_from_kzt,
                "duration_hours": 2,
                "language": profile.languages[0],
            }
        )
        text = render_explanation(build_evidence(profile, request))
        assert "Цена от" in text
        assert profile.languages[0] in text
        assert "2 ч" in text
        assert "отличный выбор" not in text.casefold()
        assert 1 <= len(__import__("re").findall(r"[.!?](?:\s|$)", text)) <= 2


def test_professional_history_is_not_discarded_as_generic_praise(real_catalog):
    profile = next(item for item in real_catalog if item.id == "HK-27222")
    request = RecommendationRequest.from_payload(
        {
            "city": profile.city,
            "category": "Ведущий",
            "event_format": "свадьба",
            "event_date": "2027-01-01",
            "budget_kzt": 6000000,
        }
    )
    evidence = build_evidence(profile, request)
    assert any("телеканалах" in reason.source_text for reason in evidence.semantic_reasons)


def test_no_fragment_falls_back_to_verified_facts(profile, payload):
    profile = replace(profile, description="Привет")
    evidence = build_evidence(profile, RecommendationRequest.from_payload(payload))
    assert evidence.semantic_reasons == ()
    ai = FakeAI({"items": [{"candidate_id": profile.id, "reason_id": None}]})
    result = ExplanationService(ai).explain((evidence,))[profile.id]
    assert result == render_explanation(evidence)
    assert "В описании" not in result
    assert "казахский" in result and "6 ч" in result and "Цена от" in result
