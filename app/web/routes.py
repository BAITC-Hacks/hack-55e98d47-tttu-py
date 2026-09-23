"""Thin Flask routes for the localized server-rendered recommendation experience."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Blueprint, Response, current_app, make_response, render_template, request

from app.models import ValidationError
from app.services.export import csv_bytes, json_bytes

from .exports import ExportSnapshot, ExportStore
from .i18n import copy_for, locale_options, option_label, option_list, resolve_locale, text

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
_REASON_KEYS = {
    "busy": "reason_busy",
    "over_budget": "reason_over_budget",
    "wrong_format": "reason_wrong_format",
    "duration_too_long": "reason_duration",
    "language_mismatch": "reason_language",
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


def _service_payload(form: Mapping[str, str], locale: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = {
            "locale": locale,
            "city": form["city"],
            "event_date": form["event_date"],
            "event_format": form["event_format"],
            "category": form["category"],
            "budget_kzt": int(form["budget_kzt"]),
        }
        if form["duration_hours"]:
            duration = float(form["duration_hours"])
            payload["duration_hours"] = int(duration) if duration.is_integer() else duration
    except ValueError:
        raise ValidationError({"number": text(locale, "number_error")}) from None
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


def _export_store() -> ExportStore:
    store = current_app.extensions.get("web_export_store")
    if store is None:
        store = ExportStore()
        current_app.extensions["web_export_store"] = store
    return store


def _format_price(value: Any, locale: str) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return text(locale, "unknown_price")


def _data_notes(card: Mapping[str, Any], locale: str) -> str:
    notes = []
    if card.get("synthetic"):
        notes.append(text(locale, "synthetic"))
    if card.get("city_imputed"):
        notes.append(text(locale, "city_imputed"))
    if card.get("price_imputed"):
        notes.append(text(locale, "price_imputed"))
    return "; ".join(notes) if notes else text(locale, "no_data_notes")


def _comparison(cards: list[dict[str, Any]], locale: str) -> dict[str, Any] | None:
    if len(cards) < 2:
        return None
    return {
        "columns": [{"name": card["anon_name"]} for card in cards],
        "rows": [
            {"label": text(locale, "profile_id"), "values": [card["id"] for card in cards]},
            {"label": text(locale, "category"), "values": [card["category"] for card in cards]},
            {"label": text(locale, "city"), "values": [card["city"] for card in cards]},
            {
                "label": text(locale, "price_from"),
                "values": [f'{card["price"]} ₸' for card in cards],
            },
            {
                "label": text(locale, "data_notes"),
                "values": [card["data_notes"] for card in cards],
            },
        ],
    }


def _matched_view(result: Mapping[str, Any], locale: str, generation_locale: str) -> dict[str, Any]:
    raw_source_items = list(result.get("recommendations") or [])
    source_items = [dict(item) for item in raw_source_items[:3] if isinstance(item, Mapping)]
    cards = []
    for item in source_items:
        card = {
            "id": item.get("id", ""),
            "anon_name": item.get("anon_name") or text(locale, "unknown_contractor"),
            "category": option_label(
                locale, "categories", item.get("category") or text(locale, "unknown_category")
            ),
            "city": option_label(
                locale, "cities", item.get("city") or text(locale, "unknown_city")
            ),
            "price": _format_price(item.get("price_from_kzt"), locale),
            "explanation": item.get("explanation") or text(locale, "missing_explanation"),
            "synthetic": bool(item.get("synthetic")),
            "city_imputed": bool(item.get("city_imputed")),
            "price_imputed": bool(item.get("price_imputed")),
        }
        card["data_notes"] = _data_notes(card, locale)
        cards.append(card)

    if not cards:
        return {
            "kind": "empty",
            "title": text(locale, "empty_title"),
            "message": text(locale, "empty_message"),
        }

    count = len(cards)
    count_key = {1: "count_one", 2: "count_two", 3: "count_three"}[count]
    backend_message = result.get("message")
    return {
        "kind": "matched",
        "title": text(locale, "matched_title"),
        "message": (
            text(locale, "truncated_message", count=count)
            if len(raw_source_items) > 3
            else (
                str(backend_message)
                if locale == generation_locale and backend_message
                else text(locale, "matched_message", count=count)
            )
        ),
        "source_message": (
            str(backend_message) if locale != generation_locale and backend_message else None
        ),
        "count_note": text(locale, count_key),
        "cards": cards,
        "comparison": _comparison(cards, locale),
        "generation_locale": generation_locale,
        "explanation_label": text(
            locale,
            "explanation_language",
            language=option_label(
                locale,
                "languages",
                {"ru": "русский", "kk": "казахский", "en": "английский"}[generation_locale],
            ),
        ),
    }


def _result_view(result: Mapping[str, Any], locale: str, form: Mapping[str, str]) -> dict[str, Any]:
    status = str(result.get("status", "")).lower()
    if status == "matched":
        return _matched_view(result, locale, resolve_locale(form.get("locale")))
    if status == "category_not_found":
        return {
            "kind": "category_not_found",
            "title": text(locale, "category_not_found_title"),
            "message": text(
                locale,
                "category_not_found_message",
                city=option_label(locale, "cities", form["city"]),
                category=option_label(locale, "categories", form["category"]),
            ),
        }
    if status == "no_eligible_candidates":
        raw_reasons = result.get("reasons") or {}
        reasons = [
            {"label": text(locale, label_key), "count": int(raw_reasons.get(key, 0))}
            for key, label_key in _REASON_KEYS.items()
            if int(raw_reasons.get(key, 0)) > 0
        ]
        return {
            "kind": "no_eligible_candidates",
            "title": text(locale, "no_eligible_title"),
            "message": text(locale, "no_eligible_message"),
            "reasons": reasons,
        }
    return {
        "kind": "empty",
        "title": text(locale, "empty_title"),
        "message": text(locale, "empty_message"),
    }


def _idle_view(locale: str) -> dict[str, str]:
    return {
        "kind": "idle",
        "title": text(locale, "idle_title"),
        "message": text(locale, "idle_message"),
    }


def _error_view(locale: str, kind: str, message: str | None = None) -> dict[str, str]:
    if kind == "validation_error":
        return {
            "kind": kind,
            "title": text(locale, "validation_title"),
            "message": (
                message if locale == "ru" and message else text(locale, "validation_message")
            ),
        }
    return {
        "kind": "backend_error",
        "title": text(locale, "backend_title"),
        "message": text(locale, "backend_message"),
    }


def _view_from_snapshot(
    snapshot: ExportSnapshot, locale: str, form: Mapping[str, str]
) -> dict[str, Any]:
    if snapshot.state_kind in {"validation_error", "backend_error"}:
        return _error_view(locale, snapshot.state_kind)
    if snapshot.result is None:
        return _idle_view(locale)
    return _result_view(snapshot.result, locale, snapshot.query)


def _render_index(
    *, form: Mapping[str, str], result_view: Mapping[str, Any], locale: str, status: int = 200
):
    response = make_response(
        render_template(
            "index.html",
            form=form,
            locale=locale,
            locale_options=locale_options(locale),
            copy=copy_for(locale),
            cities=option_list(locale, "cities", _CITIES),
            event_formats=option_list(locale, "event_formats", _EVENT_FORMATS),
            categories=option_list(locale, "categories", _CATEGORIES),
            languages=option_list(locale, "languages", _LANGUAGES),
            result=result_view,
        ),
        status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


def _capture(result_view, item, locale):
    try:
        view_id = _export_store().put(item)
        result_view["view_id"] = view_id
        if item.result is not None and result_view["kind"] in {
            "matched",
            "category_not_found",
            "no_eligible_candidates",
        }:
            result_view["export_id"] = view_id
    except Exception:
        result_view["export_notice"] = text(locale, "export_unavailable_notice")


@web.route("/", methods=["GET", "POST"])
def index():
    locale = resolve_locale(request.form.get("locale") or request.args.get("locale"))
    form = _blank_form()
    result_view: dict[str, Any] = _idle_view(locale)
    response_status = 200

    if request.method == "POST":
        form = _submitted_form()
        if request.form.get("switch_locale"):
            view_id = request.form.get("view_id", "")
            try:
                saved = _export_store().get(view_id) if view_id else None
            except Exception:
                saved = None
            if saved:
                result_view = _view_from_snapshot(saved, locale, form)
                result_view["view_id"] = view_id
                if saved.document and result_view["kind"] in {
                    "matched",
                    "category_not_found",
                    "no_eligible_candidates",
                }:
                    result_view["export_id"] = view_id
            elif view_id:
                result_view = {
                    "kind": "snapshot_expired",
                    "title": text(locale, "export_expired_title"),
                    "message": text(locale, "snapshot_expired"),
                }
        else:
            try:
                payload = _service_payload(form, locale)
                result = _get_service().recommend(payload)
                if not isinstance(result, Mapping):
                    raise TypeError("Recommendation service returned a non-mapping result")
                result_view = _result_view(result, locale, payload)
            except ValidationError as exc:
                message = text(locale, "number_error") if "number" in exc.details else None
                result_view = _error_view(locale, "validation_error", message)
                _capture(result_view, ExportSnapshot({}, None, "validation_error"), locale)
                response_status = 422
            except Exception:
                result_view = _error_view(locale, "backend_error")
                _capture(result_view, ExportSnapshot({}, None, "backend_error"), locale)
                response_status = 503
            else:
                _capture(result_view, ExportSnapshot(dict(payload), dict(result)), locale)

    return _render_index(form=form, result_view=result_view, locale=locale, status=response_status)


@web.post("/recommendations/export/<format_name>")
def export_recommendations(format_name: str):
    locale = resolve_locale(request.form.get("locale"))
    try:
        saved = _export_store().get(request.form.get("export_id", ""))
        if saved is None or saved.document is None or format_name not in {"csv", "json"}:
            status = 404
        else:
            data = csv_bytes(saved.document) if format_name == "csv" else json_bytes(saved.document)
            response = Response(
                data,
                content_type=f"{'text/csv' if format_name == 'csv' else 'application/json'}; charset=utf-8",
            )
            response.headers["Content-Disposition"] = (
                f'attachment; filename="recommendations.{format_name}"'
            )
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
    except Exception:
        status = 503
    response = make_response(
        render_template(
            "export_error.html",
            locale=locale,
            locale_options=locale_options(locale),
            copy=copy_for(locale),
            form=None,
        ),
        status,
    )
    response.headers["Cache-Control"] = "no-store"
    return response
