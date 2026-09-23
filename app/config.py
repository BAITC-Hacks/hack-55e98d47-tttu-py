import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def local_admin_config() -> dict:
    """Explicit local setup writes only a password hash and a random session secret."""
    path = ROOT / "instance/catalog-admin-auth.json"
    try:
        if path.is_symlink() or path.stat().st_size > 8192:
            return {}
        settings = json.loads(path.read_text(encoding="utf-8"))
        return settings if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        return {}


def runtime_config() -> dict:
    # Read at application creation; only the explicit local admin config is supported.
    local_admin = local_admin_config()
    return {
        "DATASET_PATH": os.environ.get("DATASET_PATH", str(ROOT / "data/hackathon_dataset.csv")),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", str(ROOT / "instance/catalog.sqlite3")),
        "LLM_API_KEY": os.environ.get("LLM_API_KEY", ""),
        "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", ""),
        "LLM_MODEL": os.environ.get("LLM_MODEL", ""),
        "MAX_CONTENT_LENGTH": 16384,
        "CATALOG_WEB_ADMIN_ENABLED": os.environ.get(
            "CATALOG_WEB_ADMIN_ENABLED", "1" if local_admin else "0"
        )
        == "1",
        "CATALOG_ADMIN_PASSWORD_HASH": os.environ.get(
            "CATALOG_ADMIN_PASSWORD_HASH", local_admin.get("password_hash", "")
        ),
        "SECRET_KEY": os.environ.get("FLASK_SECRET_KEY", local_admin.get("secret_key", "")),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Strict",
        "SESSION_COOKIE_SECURE": os.environ.get("SESSION_COOKIE_SECURE") == "1",
        "CATALOG_ACTIVE_PATH": os.environ.get(
            "CATALOG_ACTIVE_PATH", str(ROOT / "instance/catalog-active.csv")
        ),
        "CATALOG_ADMIN_ENABLED": os.environ.get("CATALOG_ADMIN_ENABLED") == "1",
        "CATALOG_STAGING_PATH": os.environ.get(
            "CATALOG_STAGING_PATH", str(ROOT / "instance/catalog-staged.sqlite3")
        ),
    }
