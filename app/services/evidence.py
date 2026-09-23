import re
from dataclasses import asdict, dataclass

from app.models import Contractor, RecommendationRequest
from app.services.filters import is_eligible
from app.services.ranking import semantic_score

# Evidence selection favors observable services, equipment and experience over
# advertising adjectives. These rules never affect eligibility or ranking.
FEATURE_STEMS = (
    "импровиз",
    "интерактив",
    "сценар",
    "монтаж",
    "дизайн",
    "цвет",
    "скрип",
    "саксоф",
    "репертуар",
    "вокал",
    "гитар",
    "съём",
    "съем",
    "фотожурнал",
    "позиров",
    "студи",
    "театр",
    "актёр",
    "актер",
    "кухн",
    "террас",
    "панорам",
    "парков",
    "кейтер",
    "печат",
    "экран",
    "конкурс",
    "игр",
    "опыт",
    "заказ",
    "тираж",
    "производ",
    "декор",
    "хореограф",
    "церемон",
    "регистрац",
    "квартет",
    "оборудован",
    "танц",
    "квн",
    "эскиз",
    "букет",
    "композици",
    "портрет",
    "документаль",
    "язык",
    "телеканал",
    "скрипк",
    "банкет",
    "фото",
    "музык",
    "светов",
    "неон",
    "сувенир",
    "открытк",
)
PRAISE = re.compile(
    r"идеальн|прекрасн|лучш|профессионал(?:ы|изм|ьный|ьные|ьных|ьным|ьного)\b|"
    r"востребован|харизм|роскош|безупреч|отличн|"
    r"уникальн|незабыва|качествен|топ[-\s]|делает уровень|держит зал",
    re.IGNORECASE,
)


def feature_score(text: str) -> int:
    words = re.findall(r"[а-яёa-z]+", text.casefold())
    return sum(any(word.startswith(stem) for word in words) for stem in FEATURE_STEMS) + bool(
        re.search(r"\d", text)
    )


@dataclass(frozen=True, slots=True)
class DescriptionReason:
    reason_id: str
    source_text: str


@dataclass(frozen=True, slots=True)
class Evidence:
    candidate_id: str
    requested_category: str
    city: str
    event_date: str
    available_on_date: bool
    price_from_kzt: int
    budget_kzt: int
    event_format_match: str
    language_match: str | None
    requested_duration_hours: int | float | None
    max_hours: int | None
    description: str
    semantic_reasons: tuple[DescriptionReason, ...]

    def as_payload(self) -> dict:
        return asdict(self)


def build_evidence(candidate: Contractor, request: RecommendationRequest) -> Evidence:
    if not is_eligible(candidate, request):
        raise ValueError("Evidence requires an eligible candidate")
    # Preserve exact source substrings, including internal whitespace. Decimal
    # points remain part of a fact. No paraphrase or truncated assertion is allowed.
    fragments = []
    for part in re.split(r"(?<!\d)[.]|[.](?!\d)|[!?…\n•;]+", candidate.description):
        part = part.strip(" \t\r\n;:–—-")
        if not 8 <= len(part) <= 600 or PRAISE.search(part) or not feature_score(part):
            continue
        if part not in fragments:
            fragments.append(part)
    fragments.sort(key=lambda text: (-feature_score(text), -semantic_score(text, request), text))
    reasons = tuple(
        DescriptionReason(f"{candidate.id}:description:{index}", fragment)
        for index, fragment in enumerate(fragments[:6])
    )
    return Evidence(
        candidate_id=candidate.id,
        requested_category=request.category,
        city=candidate.city,
        event_date=request.event_date,
        available_on_date=True,
        price_from_kzt=candidate.price_from_kzt,
        budget_kzt=request.budget_kzt,
        event_format_match=request.event_format,
        language_match=request.language,
        requested_duration_hours=request.duration_hours,
        max_hours=candidate.max_hours,
        description=candidate.description,
        semantic_reasons=reasons,
    )
