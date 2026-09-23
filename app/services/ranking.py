"""Bounded deterministic signals; scores are only evaluated AFTER hard filtering."""

import re
from fractions import Fraction

from app.models import Contractor, RecommendationRequest

# Russian stems handle the forms actually used in the supplied descriptions.
FORMAT_STEMS = {
    "свадьба": ("свад", "невест", "жених", "брак"),
    "той": ("той", "тоя", "казах", "традиц"),
    "корпоратив": ("корпоратив", "команд", "компани", "бизнес"),
    "конференция": ("конференц", "форум", "делов", "бизнес"),
    "юбилей": ("юбиле", "семейн", "праздник"),
    "день рождения": ("рожден", "рождён", "именин", "праздник"),
}


def semantic_score(description: str, request: RecommendationRequest) -> Fraction:
    """Lexical semantic proxy in [0, 1], with no remote model or corpus-order effects."""
    words = re.findall(r"[а-яёa-z]+", description.casefold())
    stems = FORMAT_STEMS.get(request.event_format, (request.event_format.casefold(),))
    format_hits = sum(any(word.startswith(stem) for word in words) for stem in stems)
    category_words = re.findall(r"[а-яёa-z]+", request.category.casefold())
    category_hits = sum(any(word.startswith(term[:5]) for word in words) for term in category_words)
    return (
        Fraction(format_hits, len(stems)) + Fraction(category_hits, max(1, len(category_words)))
    ) / 2


def score(candidate: Contractor, request: RecommendationRequest) -> Fraction:
    # Budget utilization 35%, description 45%, optional language/duration 10% each.
    # Fractions avoid floating-point tie drift; id ASC resolves all remaining ties.
    budget = (
        Fraction(candidate.price_from_kzt, request.budget_kzt)
        if request.budget_kzt
        else Fraction(1)
    )
    language = int(request.language is not None and request.language in candidate.languages)
    duration = Fraction(0)
    if request.duration_hours is not None:
        duration = (
            Fraction(str(request.duration_hours)) / candidate.max_hours
            if candidate.max_hours is not None
            else Fraction(1)
        )
    return (
        35 * budget
        + 45 * semantic_score(candidate.description, request)
        + 10 * language
        + 10 * duration
    )


def rank(candidates: tuple[Contractor, ...], request: RecommendationRequest) -> list[Contractor]:
    return sorted(candidates, key=lambda candidate: (-score(candidate, request), candidate.id))
