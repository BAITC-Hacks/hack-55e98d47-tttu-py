"""Configure local catalog administrator access without printing or storing a password."""

import getpass
import json
import os
import secrets
import tempfile
from pathlib import Path

from werkzeug.security import generate_password_hash


def main():
    password = getpass.getpass("New catalog administrator password (at least 12 characters): ")
    if len(password) < 12 or len(password) > 256:
        raise SystemExit("Use a password between 12 and 256 characters.")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match; nothing changed.")
    target = Path(__file__).resolve().parents[1] / "instance/catalog-admin-auth.json"
    if target.is_symlink():
        raise SystemExit("Configuration destination is not supported.")
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"password_hash": generate_password_hash(password), "secret_key": secrets.token_hex(32)}
    descriptor, name = tempfile.mkstemp(prefix="admin-auth-", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    print("Catalog administrator configured. Restart the application, then open /admin/catalog.")


if __name__ == "__main__":
    main()
