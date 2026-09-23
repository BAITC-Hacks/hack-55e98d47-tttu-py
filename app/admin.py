"""Trusted local operator tooling. Deliberately no HTTP upload/activation route."""

import os
import sqlite3
import stat
import tempfile
from pathlib import Path

import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from app.config import runtime_config
from app.repositories import CatalogRepository, DatasetError
from app.repositories.catalog import load_csv_bytes

MAX_CATALOG_BYTES = 1024 * 1024


def create_admin_app(config: dict | None = None) -> Flask:
    """CLI-only factory: never seed or initialize the active catalog."""
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(runtime_config())
    if config:
        app.config.update(config)
    app.cli.add_command(catalog_admin)
    return app


def read_admin_catalog(path: Path):
    if not current_app.config.get("CATALOG_ADMIN_ENABLED", False):
        raise PermissionError
    if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
        raise DatasetError("Catalog must be a regular file")
    with path.open("rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise DatasetError("Catalog must be a regular file")
        data = source.read(MAX_CATALOG_BYTES + 1)
    if len(data) > MAX_CATALOG_BYTES:
        raise DatasetError("Catalog size limit exceeded")
    return load_csv_bytes(data)


def stage_catalog(path: Path) -> int:
    contractors = read_admin_catalog(path)
    destination = Path(current_app.config["CATALOG_STAGING_PATH"])
    protected = {
        Path(current_app.config[key]).resolve() for key in ("DATABASE_PATH", "DATASET_PATH")
    }
    protected.add(path.resolve())
    if destination.is_symlink() or destination.resolve() in protected:
        raise DatasetError("Staging must be separate from active data")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix="catalog-stage-", suffix=".sqlite3", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(name)
        CatalogRepository(temporary).initialize(contractors)
        os.replace(temporary, destination)
        return len(contractors)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@click.group("catalog-admin")
def catalog_admin():
    """Validate or stage a catalog; requires trusted OS access and explicit enablement."""


def _execute(action, source: str):
    try:
        count = action(Path(source))
    except PermissionError:
        raise click.ClickException(
            "Catalog administration is disabled or access was denied."
        ) from None
    except (OSError, ValueError, sqlite3.Error):
        raise click.ClickException(
            "Catalog operation failed; check UTF-8, schema, file size and configuration."
        ) from None
    click.echo(f"Validated profiles: {count}")


@catalog_admin.command("validate")
@click.argument("source", type=str)
@with_appcontext
def validate_command(source):
    """Validate a local CSV without changing the running catalog."""
    _execute(lambda path: len(read_admin_catalog(path)), source)


@catalog_admin.command("stage")
@click.argument("source", type=str)
@with_appcontext
def stage_command(source):
    """Build an isolated staging database, without activating it."""
    _execute(stage_catalog, source)
