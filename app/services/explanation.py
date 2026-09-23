from typing import Protocol

from app.services.evidence import Evidence


class ExplanationClient(Protocol):
    def select_reasons(self, evidence: tuple[Evidence, ...]) -> object: ...


def money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def render_explanation(evidence: Evidence, reason_id: str | None = None) -> str:
    """Only code-owned facts and verbatim source excerpts become user-facing prose."""
    text = (
        f"Цена от {money(evidence.price_from_kzt)} ₸ при бюджете {money(evidence.budget_kzt)} ₸; "
        f"категория «{evidence.requested_category}», город — {evidence.city}, "
        f"формат — «{evidence.event_format_match}», дата {evidence.event_date} свободна"
    )
    if evidence.language_match:
        text += f"; поддерживаемый язык — {evidence.language_match}"
    if evidence.requested_duration_hours is not None:
        hours = str(evidence.requested_duration_hours).replace(".", ",")
        if evidence.max_hours is None:
            text += f"; для запроса на {hours} ч услуга не привязана к длительности присутствия"
        else:
            text += f"; длительность {hours} ч не превышает лимит {evidence.max_hours} ч"
    text += "."
    reasons = evidence.semantic_reasons
    if reasons:
        reason = next((item for item in reasons if item.reason_id == reason_id), reasons[0])
        text += f" В описании: «{reason.source_text}»."
    return text


def validate_selection(response: object, evidence: tuple[Evidence, ...]) -> dict[str, str | None]:
    if not isinstance(response, dict) or set(response) != {"items"}:
        raise ValueError("Invalid AI envelope")
    items = response["items"]
    if not isinstance(items, list) or len(items) != len(evidence):
        raise ValueError("Invalid AI item count")
    expected = {item.candidate_id: item for item in evidence}
    selected = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"candidate_id", "reason_id"}:
            raise ValueError("Invalid AI item")
        candidate_id, reason_id = item["candidate_id"], item["reason_id"]
        if (
            not isinstance(candidate_id, str)
            or candidate_id not in expected
            or candidate_id in selected
        ):
            raise ValueError("Invalid AI candidate")
        allowed = {reason.reason_id for reason in expected[candidate_id].semantic_reasons}
        if allowed:
            if not isinstance(reason_id, str) or reason_id not in allowed:
                raise ValueError("Unsupported AI evidence")
        elif reason_id is not None:
            raise ValueError("Unsupported AI evidence")
        selected[candidate_id] = reason_id
    return selected


class ExplanationService:
    def __init__(self, client: ExplanationClient | None = None):
        self.client = client

    def explain(self, evidence: tuple[Evidence, ...]) -> dict[str, str]:
        selected = {}
        if self.client is not None and evidence:
            try:
                selected = validate_selection(self.client.select_reasons(evidence), evidence)
            except Exception:
                # Provider exceptions may contain credentials or raw response data.
                # Deliberately do not log, stringify, or return them.
                selected = {}
        result = {
            item.candidate_id: render_explanation(item, selected.get(item.candidate_id))
            for item in evidence
        }
        # Even identical source profiles remain identifiable without using their names.
        duplicates = {text for text in result.values() if list(result.values()).count(text) > 1}
        for candidate_id, text in result.items():
            if text in duplicates:
                result[candidate_id] = f"Профиль {candidate_id}: {text[0].lower()}{text[1:]}"
        return result
