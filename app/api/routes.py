from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from app.models import ValidationError

api = Blueprint("api", __name__, url_prefix="/api/v1")


@api.get("/health")
def health():
    return jsonify({"status": "ok"})


@api.post("/recommendations")
def recommendations():
    try:
        payload = request.get_json()
    except (BadRequest, UnsupportedMediaType):
        raise ValidationError({"body": "Ожидается корректный JSON-объект."}) from None
    return jsonify(current_app.extensions["recommendation_service"].recommend(payload))
