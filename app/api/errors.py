from flask import g, jsonify

from app.localization import error_details, text
from app.models import ValidationError


def validation_response(error: ValidationError):
    locale = getattr(g, "product_locale", "ru")
    return (
        jsonify(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": text("validation", locale),
                    "details": error_details(error.details, locale),
                }
            }
        ),
        422,
    )
