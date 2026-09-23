from app.models import Contractor, RecommendationRequest

REASONS = (
    "busy",
    "over_budget",
    "wrong_format",
    "duration_too_long",
    "language_mismatch",
)


def violations(candidate: Contractor, request: RecommendationRequest) -> tuple[str, ...]:
    checks = (
        request.event_date in candidate.busy_dates,
        candidate.price_from_kzt > request.budget_kzt,
        request.event_format not in candidate.event_formats,
        request.duration_hours is not None
        and candidate.max_hours is not None
        and request.duration_hours > candidate.max_hours,
        request.language is not None and request.language not in candidate.languages,
    )
    return tuple(reason for reason, failed in zip(REASONS, checks, strict=True) if failed)


def is_eligible(candidate: Contractor, request: RecommendationRequest) -> bool:
    return (
        candidate.city == request.city
        and request.category in candidate.categories
        and not violations(candidate, request)
    )
