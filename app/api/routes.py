from flask import Blueprint, Response, current_app, g, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from app.localization import locale_from_payload, text
from app.models import ValidationError
from app.services.export import csv_bytes, json_bytes, snapshot

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.get("/health")
def health():
    return jsonify({"status": "ok"})


def read_payload():
    try:
        payload = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        raise ValidationError({"body": "Ожидается корректный JSON-объект."}) from None
    g.product_locale = locale_from_payload(payload, strict=False)
    return payload


@api.post("/recommendations")
def recommendations():
    payload = read_payload()
    try:
        result = current_app.extensions["recommendation_service"].recommend(payload)
    except ValidationError:
        raise
    except Exception:
        return (
            jsonify(
                {"error": {"code": "INTERNAL_ERROR", "message": text("internal", g.product_locale)}}
            ),
            500,
        )
    response = jsonify(result)
    if request.headers.get("X-Enable-Export") == "true":
        response.headers["Cache-Control"] = "no-store"
        try:
            token = current_app.extensions["export_snapshots"].put(snapshot(payload, result))
            response.headers["X-Recommendation-Export-Token"] = token
        except Exception:
            response.headers["X-Recommendation-Export-Status"] = "unavailable"
    return response


@api.post("/recommendations/export")
def export_recommendations():
    body = read_payload()
    if not isinstance(body, dict):
        raise ValidationError({"body": "Ожидается JSON-объект."})
    if "request" in body:
        g.product_locale = locale_from_payload(body["request"], strict=False)
    if set(body) - {"format", "request", "export_token"}:
        raise ValidationError({"body": "Неизвестные параметры экспорта."})
    export_format = body.get("format")
    if export_format not in ("csv", "json"):
        raise ValidationError({"format": "Формат экспорта должен быть csv или json."})
    if ("request" in body) == ("export_token" in body):
        raise ValidationError({"body": "Передайте request или export_token, но не оба."})
    try:
        if "export_token" in body:
            token = body["export_token"]
            if not isinstance(token, str) or not 1 <= len(token) <= 100:
                raise ValidationError({"export_token": "Некорректный токен экспорта."})
            document = current_app.extensions["export_snapshots"].get(token)
            if document is None:
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "EXPORT_NOT_FOUND",
                                "message": text("missing_export", g.product_locale),
                            }
                        }
                    ),
                    404,
                )
            g.product_locale = document["locale"]
        else:
            payload = body["request"]
            result = current_app.extensions["recommendation_service"].recommend(payload)
            document = snapshot(payload, result)
        data = csv_bytes(document) if export_format == "csv" else json_bytes(document)
    except ValidationError:
        raise
    except Exception:
        # Do not expose or log provider, serializer or repository exception contents.
        return (
            jsonify(
                {"error": {"code": "INTERNAL_ERROR", "message": text("internal", g.product_locale)}}
            ),
            500,
        )
    response = Response(
        data,
        content_type=f"{'text/csv' if export_format == 'csv' else 'application/json'}; charset=utf-8",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="recommendations.{export_format}"'
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
