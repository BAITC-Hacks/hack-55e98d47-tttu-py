import math
import re
from dataclasses import dataclass
from datetime import date


class ValidationError(ValueError):
    def __init__(self, details: dict[str, str]):
        super().__init__("Некорректные параметры запроса.")
        self.details = details


@dataclass(frozen=True, slots=True)
class RecommendationRequest:
    city: str
    event_date: str
    event_format: str
    category: str
    budget_kzt: int
    duration_hours: int | float | None = None
    language: str | None = None

    @classmethod
    def from_payload(cls, payload: object) -> "RecommendationRequest":
        if not isinstance(payload, dict):
            raise ValidationError({"body": "Ожидается JSON-объект."})
        errors = {}
        values = {}
        for field in ("city", "event_format", "category"):
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 120:
                errors[field] = "Ожидается непустая строка длиной до 120 символов."
            else:
                values[field] = value.strip()
        value = payload.get("event_date")
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            date.fromisoformat(value)
            values["event_date"] = value
        except ValueError:
            errors["event_date"] = "Ожидается существующая дата YYYY-MM-DD."
        budget = payload.get("budget_kzt")
        if type(budget) is not int or not 0 <= budget <= 10**15:
            errors["budget_kzt"] = "Ожидается целое число от 0 до 1000000000000000."
        else:
            values["budget_kzt"] = budget
        duration = payload.get("duration_hours")
        if duration is not None and (
            type(duration) not in (int, float)
            or not 0 < duration <= 10**6
            or not math.isfinite(duration)
        ):
            errors["duration_hours"] = "Ожидается положительное конечное число часов."
        else:
            values["duration_hours"] = duration
        language = payload.get("language")
        if language is not None and (
            not isinstance(language, str) or not language.strip() or len(language) > 120
        ):
            errors["language"] = "Ожидается непустая строка языка или null."
        else:
            values["language"] = language.strip() if language is not None else None
        if errors:
            raise ValidationError(errors)
        return cls(**values)
