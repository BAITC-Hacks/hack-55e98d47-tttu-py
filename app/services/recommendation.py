from typing import Protocol

from app.models import Contractor, RecommendationRequest
from app.services.evidence import build_evidence
from app.services.explanation import ExplanationService
from app.services.filters import REASONS, violations
from app.services.ranking import rank


class Repository(Protocol):
    def discover(self, city: str, category: str) -> tuple[Contractor, ...]: ...


class RecommendationService:
    def __init__(self, repository: Repository, explanations: ExplanationService | None = None):
        self.repository = repository
        self.explanations = explanations or ExplanationService()

    def recommend(self, payload: object) -> dict:
        # Web routes pass a dict too, so both transports use the same validation.
        request = RecommendationRequest.from_payload(payload)
        candidates = tuple(
            candidate
            for candidate in self.repository.discover(request.city, request.category)
            if candidate.city == request.city and request.category in candidate.categories
        )
        if not candidates:
            return {
                "status": "category_not_found",
                "count": 0,
                "message": f"В городе «{request.city}» нет подрядчиков категории «{request.category}».",
                "recommendations": [],
            }
        diagnostics = dict.fromkeys(REASONS, 0)
        eligible = []
        for candidate in candidates:
            rejected = violations(candidate, request)
            for reason in rejected:
                diagnostics[reason] += 1
            if not rejected:
                eligible.append(candidate)
        if not eligible:
            return {
                "status": "no_eligible_candidates",
                "count": 0,
                "message": "Подрядчики этой категории есть, но ни один не прошёл условия заказа.",
                "reasons": diagnostics,
                "recommendations": [],
            }
        top = rank(tuple(eligible), request)[:3]
        evidence = tuple(build_evidence(candidate, request) for candidate in top)
        explanations = self.explanations.explain(evidence)
        cards = [
            {
                "id": candidate.id,
                "anon_name": candidate.anon_name,
                "category": request.category,
                "city": candidate.city,
                "price_from_kzt": candidate.price_from_kzt,
                "synthetic": candidate.synthetic,
                "city_imputed": candidate.city_imputed,
                "price_imputed": candidate.price_imputed,
                "explanation": explanations[candidate.id],
            }
            for candidate in top
        ]
        message = f"Найдено подходящих подрядчиков: {len(cards)}."
        if len(cards) < 3:
            message += " Показаны все подрядчики города и категории, прошедшие условия заказа; их меньше трёх."
        return {
            "status": "matched",
            "count": len(cards),
            "message": message,
            "recommendations": cards,
        }
