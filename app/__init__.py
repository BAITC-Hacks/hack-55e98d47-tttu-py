from pathlib import Path

from flask import Flask, g, jsonify
from werkzeug.exceptions import RequestEntityTooLarge

from app.ai.client import LLMClient
from app.api.errors import validation_response
from app.api.routes import api
from app.config import runtime_config
from app.localization import text
from app.models import ValidationError
from app.repositories import CatalogRepository, load_csv
from app.services import RecommendationService
from app.services.catalog_management import CatalogManager
from app.services.explanation import ExplanationService
from app.services.export import SnapshotStore
from app.web import web
from app.web.catalog_admin import LoginLimiter, catalog_admin


def create_app(config: dict | None = None, *, repository=None, ai_client=None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(runtime_config())
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    initialize_repository = repository is None
    if initialize_repository:
        repository = CatalogRepository(app.config["DATABASE_PATH"])
    manager = CatalogManager(
        app.config["CATALOG_ACTIVE_PATH"], app.config["DATASET_PATH"], repository
    )
    if initialize_repository:
        active = Path(app.config["CATALOG_ACTIVE_PATH"])
        contractors = load_csv(active if active.exists() else app.config["DATASET_PATH"])
        repository.initialize(contractors)
    if ai_client is None and all(
        app.config.get(name) for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
    ):
        ai_client = LLMClient(
            app.config["LLM_API_KEY"],
            app.config["LLM_BASE_URL"],
            app.config["LLM_MODEL"],
        )
    app.extensions["catalog_repository"] = manager
    app.extensions["catalog_manager"] = manager
    app.extensions["catalog_login_limiter"] = LoginLimiter()
    app.extensions["export_snapshots"] = SnapshotStore()
    app.extensions["recommendation_service"] = RecommendationService(
        manager, ExplanationService(ai_client)
    )
    app.register_blueprint(api)
    app.register_blueprint(web)
    app.register_blueprint(catalog_admin)
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
                        "message": text("internal", getattr(g, "product_locale", "ru")),
                    }
                }
            ),
            500,
        )

    return app
