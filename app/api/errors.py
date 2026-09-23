from flask import jsonify

from app.models import ValidationError


def validation_response(error: ValidationError):
    return (
        jsonify(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Некорректные параметры запроса.",
                    "details": error.details,
                }
            }
        ),
        422,
    )
