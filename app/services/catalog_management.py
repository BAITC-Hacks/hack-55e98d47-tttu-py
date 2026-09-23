"""Bounded, in-process catalog upload previews and activation."""

from __future__ import annotations

import hashlib
import os
import secrets
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Callable

from app.repositories.catalog import CatalogRepository, DatasetError, load_csv_bytes

MAX_CATALOG_BYTES = 1024 * 1024
MAX_PREVIEWS = 16
PREVIEW_TTL_SECONDS = 15 * 60


class CatalogOperationError(ValueError):
    """Safe, stable error for catalog management operations."""

    def __init__(self, code: str, message: str = "Catalog operation failed"):
        self.code = code
        super().__init__(message)


class CatalogManager:
    """Manage ephemeral validated previews and serialized catalog activation."""

    def __init__(
        self,
        active_path: str | Path,
        fallback_path: str | Path,
        repository: CatalogRepository,
        clock: Callable[[], float] | None = None,
    ):
        self.active_path = Path(active_path)
        self.fallback_path = Path(fallback_path)
        self.repository = repository
        self._clock = clock or time.time
        self._previews: dict[str, dict] = {}
        self.lock = threading.RLock()
        self._generated_repositories: set[Path] = set()
        if self.active_path.resolve() == self.fallback_path.resolve():
            raise ValueError("Active and fallback catalog paths must differ")
        if self.active_path.resolve() == Path(repository.path).resolve():
            raise ValueError("Active CSV and repository paths must differ")
        if self.active_path.is_symlink():
            raise ValueError("Active catalog path must not be a symlink")

    def stage(self, data: bytes, owner: str) -> dict:
        if not isinstance(data, bytes) or len(data) > MAX_CATALOG_BYTES:
            raise CatalogOperationError("invalid", "Catalog size limit exceeded")
        if not isinstance(owner, str) or not owner:
            raise CatalogOperationError("invalid", "Catalog owner is required")
        try:
            profiles = load_csv_bytes(data)
        except (DatasetError, ValueError):
            raise CatalogOperationError("invalid", "Catalog data is invalid") from None
        self._validate_bounds(profiles)

        with self.lock:
            self._purge_expired()
            for key, item in list(self._previews.items()):
                if item["owner"] == owner:
                    del self._previews[key]
            if len(self._previews) >= MAX_PREVIEWS:
                raise CatalogOperationError("invalid", "Too many catalog previews")
            preview_id = secrets.token_urlsafe(24)
            checksum = hashlib.sha256(data).hexdigest()
            preview = {
                "preview_id": preview_id,
                "owner": owner,
                "data": data,
                "created_at": self._clock(),
                "base_checksum": self._current_checksum(),
                "checksum": checksum,
                "profiles": profiles,
            }
            self._previews[preview_id] = preview
        cities = Counter(item.city for item in profiles)
        categories = Counter(category for item in profiles for category in item.categories)
        return {
            "preview_id": preview_id,
            "sha256": checksum,
            "count": len(profiles),
            "cities": dict(sorted(cities.items())),
            "categories": dict(sorted(categories.items())),
            "sample": [self._public_row(item) for item in profiles[:5]],
            "expires_in_seconds": PREVIEW_TTL_SECONDS,
        }

    def get_preview(self, preview_id: str, owner: str) -> dict:
        with self.lock:
            self._purge_expired()
            item = self._previews.get(preview_id)
            if item is None:
                raise CatalogOperationError("expired", "Catalog preview expired")
            if item["owner"] != owner:
                raise CatalogOperationError("invalid", "Catalog preview owner mismatch")
            return self._summary(item["profiles"], item["checksum"], preview_id)

    preview = get_preview

    def discard(self, owner: str) -> None:
        with self.lock:
            for key, item in list(self._previews.items()):
                if item["owner"] == owner:
                    del self._previews[key]

    def current(self) -> dict:
        with self.lock:
            try:
                data = self.active_path.read_bytes()
            except FileNotFoundError:
                data = self.fallback_path.read_bytes()
            return {"sha256": hashlib.sha256(data).hexdigest(), "count": len(self.repository.all())}

    def all(self):
        with self.lock:
            return self.repository.all()

    def discover(self, city: str, category: str):
        with self.lock:
            return self.repository.discover(city, category)

    def commit(self, preview_id: str, owner: str) -> dict:
        with self.lock:
            self._purge_expired()
            preview = self._previews.get(preview_id)
            if preview is None:
                raise CatalogOperationError("expired", "Catalog preview expired")
            if preview["owner"] != owner:
                raise CatalogOperationError("invalid", "Catalog preview owner mismatch")
            if preview["base_checksum"] != self._current_checksum():
                del self._previews[preview_id]
                raise CatalogOperationError("conflict", "Catalog changed since preview")

            old_repository = self.repository
            generated_db: Path | None = None
            temporary: Path | None = None
            try:
                if self.active_path.is_symlink():
                    raise OSError("active catalog path must not be a symlink")
                self.active_path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, db_name = tempfile.mkstemp(
                    prefix="catalog-version-", suffix=".sqlite3", dir=self.active_path.parent
                )
                os.close(descriptor)
                generated_db = Path(db_name)
                new_repository = CatalogRepository(generated_db)
                new_repository.initialize(preview["profiles"])
                temporary = self._write_durable_temp(preview["data"])
                os.replace(temporary, self.active_path)
                temporary = None
            except Exception:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                if generated_db is not None:
                    generated_db.unlink(missing_ok=True)
                raise CatalogOperationError("failure", "Catalog activation failed") from None
            self.repository = new_repository
            # Publication succeeded. Cleanup/directory sync cannot turn success into
            # an error that falsely promises the old catalog is still active.
            try:
                self._fsync_directory(self.active_path.parent)
            except OSError:
                pass
            self._generated_repositories.add(generated_db)
            if (
                old_repository.path in self._generated_repositories
                and old_repository.path != generated_db
            ):
                try:
                    old_repository.path.unlink(missing_ok=True)
                    self._generated_repositories.discard(old_repository.path)
                except OSError:
                    pass
            del self._previews[preview_id]
            return {
                "sha256": preview["checksum"],
                "count": len(preview["profiles"]),
            }

    def _current_checksum(self) -> str:
        try:
            data = self.active_path.read_bytes()
        except FileNotFoundError:
            try:
                data = self.fallback_path.read_bytes()
            except OSError:
                raise CatalogOperationError("failure") from None
        except OSError:
            raise CatalogOperationError("failure") from None
        return hashlib.sha256(data).hexdigest()

    def _validate_bounds(self, profiles) -> None:
        if len(profiles) > 1000:
            raise CatalogOperationError("invalid", "Catalog has too many profiles")
        allowed = None
        try:
            fallback = load_csv_bytes(self.fallback_path.read_bytes())
            allowed = {
                key: {value for item in fallback for value in getattr(item, key)}
                for key in ("categories", "event_formats", "languages")
            }
        except (OSError, DatasetError, ValueError):
            raise CatalogOperationError("invalid", "Fallback catalog is unavailable") from None
        for item in profiles:
            if any(
                len(getattr(item, field)) > limit
                for field, limit in (
                    ("categories", 32),
                    ("event_formats", 32),
                    ("languages", 32),
                    ("busy_dates", 366),
                )
            ):
                raise CatalogOperationError("invalid", "Catalog row exceeds limits")
            if len(item.id) > 120 or len(item.anon_name) > 120 or len(item.description) > 6000:
                raise CatalogOperationError("invalid", "Catalog text exceeds limits")
            if allowed and any(
                not set(getattr(item, field)).issubset(allowed[field])
                for field in ("categories", "event_formats", "languages")
            ):
                raise CatalogOperationError("invalid", "Catalog vocabulary is unsupported")

    @classmethod
    def _summary(cls, profiles, checksum, preview_id):
        cities = Counter(item.city for item in profiles)
        categories = Counter(category for item in profiles for category in item.categories)
        return {
            "preview_id": preview_id,
            "sha256": checksum,
            "count": len(profiles),
            "cities": dict(sorted(cities.items())),
            "categories": dict(sorted(categories.items())),
            "sample": [cls._public_row(item) for item in profiles[:5]],
            "expires_in_seconds": PREVIEW_TTL_SECONDS,
        }

    def _purge_expired(self) -> None:
        now = self._clock()
        for key, item in list(self._previews.items()):
            if now - item["created_at"] >= PREVIEW_TTL_SECONDS:
                del self._previews[key]

    @staticmethod
    def _public_row(item) -> dict:
        return {
            "id": item.id,
            "anon_name": item.anon_name,
            "city": item.city,
            "categories": list(item.categories),
            "price_from_kzt": item.price_from_kzt,
            "synthetic": item.synthetic,
            "city_imputed": item.city_imputed,
            "price_imputed": item.price_imputed,
        }

    def _write_durable_temp(self, data: bytes) -> Path:
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix="catalog-active-", suffix=".csv", dir=self.active_path.parent
        )
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return temporary
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        try:
            descriptor = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
