import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def runtime_config() -> dict:
    # Read at application creation, never at import time; no secret-file auto-discovery.
    return {
        "DATASET_PATH": os.environ.get("DATASET_PATH", str(ROOT / "data/hackathon_dataset.csv")),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", str(ROOT / "instance/catalog.sqlite3")),
        "LLM_API_KEY": os.environ.get("LLM_API_KEY", ""),
        "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", ""),
        "LLM_MODEL": os.environ.get("LLM_MODEL", ""),
        "MAX_CONTENT_LENGTH": 16384,
    }
