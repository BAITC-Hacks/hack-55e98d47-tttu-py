"""Thin Flask routes for the server-rendered recommendation experience."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Blueprint, current_app, render_template, request

web = Blueprint("web", __name__)

_CITIES = ("Алматы", "Астана", "Зарубежье")
_EVENT_FORMATS = ("свадьба", "той", "корпоратив", "конференция", "юбилей", "день рождения")
_CATEGORIES = (
    "Банкетный зал",
    "Ведущий",
    "Ведущий церемонии",
    "Видеограф",
    "Декоратор",
    "Загородная площадка",
    "Инструменталист",
    "Лайв-бэнд",
    "Национальный ансамбль",
    "Отель",
    "Подарки и сувениры",
    "Ресторан",
    "Танцевальный коллектив",
    "Флорист",
    "Фото и видеобудки",
    "Фотограф",
    "Шоу-программа",
)
_LANGUAGES = ("русский", "казахский", "английский")
_REASON_LABELS = {
    "busy": "заняты на выбранную дату",
    "over_budget": "превышают указанный бюджет",
    "wrong_format": "не работают с выбранным форматом",
    "duration_too_long": "не подходят по длительности",
    "language_mismatch": "не поддерживают выбранный язык",
}


def _blank_form() -> dict[str, str]:
    return {
        "city": "",
        "event_date": "",
        "event_format": "",
        "category": "",
        "budget_kzt": "",
        "duration_hours": "",
        "language": "",
    }


def _submitted_form() -> dict[str, str]:
    return {name: request.form.get(name, "").strip() for name in _blank_form()}


def _service_payload(form: Mapping[str, str]) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = {
            "city": form["city"],
            "event_date": form["event_date"],
            "event_format": form["event_format"],
            "category": form["category"],
            "budget_kzt": int(form["budget_kzt"]),
        }
        if form["duration_hours"]:
            payload["duration_hours"] = float(form["duration_hours"])
    except ValueError:
        raise ValueError("Проверьте бюджет и длительность: нужны числовые значения.") from None
    if form["language"]:
        payload["language"] = form["language"]
    return payload


def _get_service() -> Any:
    service = current_app.extensions.get("recommendation_service")
    if service is None:
        service = current_app.config.get("RECOMMENDATION_SERVICE")
    if service is None:
        raise RuntimeError("Recommendation service is not configured")
    return service


def _format_price(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "не указана"


def _matched_view(result: Mapping[str, Any]) -> dict[str, Any]:
    source_items = list(result.get("recommendations") or [])
    cards = []
    for item in source_items[:3]:
        cards.append(
            {
                "id": item.get("id", ""),
                "anon_name": item.get("anon_name") or "Подрядчик",
                "category": item.get("category") or "Категория не указана",
                "city": item.get("city") or "Город не указан",
                "price": _format_price(item.get("price_from_kzt")),
                "explanation": item.get("explanation") or "Объяснение временно недоступно.",
                "synthetic": bool(item.get("synthetic")),
                "city_imputed": bool(item.get("city_imputed")),
                "price_imputed": bool(item.get("price_imputed")),
            }
        )

    if not cards:
        return {
            "kind": "empty",
            "title": "Рекомендации не получены",
            "message": "Сервис вернул пустой результат. Измените условия или повторите попытку.",
        }

    count = len(cards)
    suffix = (
        "Показан единственный найденный вариант."
        if count == 1
        else ("Показаны оба найденных варианта." if count == 2 else "Показаны три лучших варианта.")
    )
    return {
        "kind": "matched",
        "title": "Подходящие подрядчики",
        "message": (
            f"Показано лучших вариантов: {count}."
            if len(source_items) > 3
            else result.get("message") or f"Найдено вариантов: {count}."
        ),
        "count_note": suffix,
        "cards": cards,
    }


def _result_view(result: Mapping[str, Any]) -> dict[str, Any]:
    status = str(result.get("status", "")).lower()
    if status == "matched":
        return _matched_view(result)
    if status == "category_not_found":
        return {
            "kind": "category_not_found",
            "title": "Категория не найдена",
            "message": result.get("message")
            or "В этом городе нет подрядчиков выбранной категории.",
        }
    if status == "no_eligible_candidates":
        reasons = [
            {"label": label, "count": int((result.get("reasons") or {}).get(key, 0))}
            for key, label in _REASON_LABELS.items()
            if int((result.get("reasons") or {}).get(key, 0)) > 0
        ]
        return {
            "kind": "no_eligible_candidates",
            "title": "Нет подходящих вариантов",
            "message": result.get("message")
            or "Подрядчики есть, но ни один не прошёл условия заказа.",
            "reasons": reasons,
        }
    return {
        "kind": "empty",
        "title": "Рекомендации не получены",
        "message": "Сервис вернул ответ без понятного статуса. Повторите попытку.",
    }


@web.route("/", methods=["GET", "POST"])
def index():
    form = _blank_form()
    result_view = {
        "kind": "idle",
        "title": "Здесь появятся рекомендации",
        "message": "Заполните форму — мы покажем до трёх подходящих подрядчиков и объясним каждый выбор.",
    }
    response_status = 200

    if request.method == "POST":
        form = _submitted_form()
        try:
            result = _get_service().recommend(_service_payload(form))
            if not isinstance(result, Mapping):
                raise TypeError("Recommendation service returned a non-mapping result")
            result_view = _result_view(result)
        except (ValueError, TypeError) as exc:
            result_view = {
                "kind": "validation_error",
                "title": "Проверьте введённые данные",
                "message": str(exc) or "Некорректные параметры запроса.",
            }
            response_status = 422
        except Exception:
            current_app.logger.exception("Web recommendation request failed")
            result_view = {
                "kind": "backend_error",
                "title": "Не удалось получить рекомендации",
                "message": "Сервис временно недоступен. Попробуйте ещё раз — введённые данные сохранены.",
            }
            response_status = 503

    return (
        render_template(
            "index.html",
            form=form,
            cities=_CITIES,
            event_formats=_EVENT_FORMATS,
            categories=_CATEGORIES,
            languages=_LANGUAGES,
            result=result_view,
        ),
        response_status,
    )
