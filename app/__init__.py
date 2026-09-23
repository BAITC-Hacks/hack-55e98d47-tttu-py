from flask import Flask, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from app.ai.client import LLMClient
from app.api.errors import validation_response
from app.api.routes import api
from app.config import runtime_config
from app.models import ValidationError
from app.repositories import CatalogRepository, load_csv
from app.services import RecommendationService
from app.services.explanation import ExplanationService
from app.web import web


def create_app(config: dict | None = None, *, repository=None, ai_client=None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(runtime_config())
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    if repository is None:
        contractors = load_csv(app.config["DATASET_PATH"])
        repository = CatalogRepository(app.config["DATABASE_PATH"])
        repository.initialize(contractors)
    if ai_client is None and all(
        app.config.get(name) for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
    ):
        ai_client = LLMClient(
            app.config["LLM_API_KEY"],
            app.config["LLM_BASE_URL"],
            app.config["LLM_MODEL"],
        )
    app.extensions["catalog_repository"] = repository
    app.extensions["recommendation_service"] = RecommendationService(
        repository, ExplanationService(ai_client)
    )
    app.register_blueprint(api)
    app.register_blueprint(web)
    app.register_error_handler(ValidationError, validation_response)

    @app.errorhandler(RequestEntityTooLarge)
    def oversized_body(_error):
        return validation_response(ValidationError({"body": "Запрос слишком большой."}))

    @app.errorhandler(500)
    def internal_error(_error):
        return (
            jsonify(
                {
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Внутренняя ошибка сервера.",
                    }
                }
            ),
            500,
        )

    return app
