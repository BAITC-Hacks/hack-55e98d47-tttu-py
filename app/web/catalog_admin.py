"""Authenticated, CSRF-protected operator UI; public recommendation routes stay read-only."""

import csv
import hashlib
import hmac
import io
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import asdict

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash

from app.repositories import load_csv
from app.services.catalog_management import CatalogOperationError
from app.web.catalog_i18n import admin_copy_for
from app.web.i18n import copy_for, locale_options, resolve_locale

catalog_admin = Blueprint("catalog_admin", __name__, url_prefix="/admin/catalog")
MAX_UPLOAD = 1024 * 1024


class LoginLimiter:
    """Bounded single-process per-IP and account-wide brute-force throttling."""

    def __init__(self):
        self.attempts = OrderedDict()
        self.global_attempts = []
        self.lock = threading.Lock()

    def allow(self, address):
        now = time.monotonic()
        with self.lock:
            self.global_attempts = [
                instant for instant in self.global_attempts if now - instant < 60
            ]
            values = [instant for instant in self.attempts.get(address, []) if now - instant < 60]
            if len(values) >= 5 or len(self.global_attempts) >= 30:
                return False
            self.global_attempts.append(now)
            self.attempts[address] = [*values, now]
            self.attempts.move_to_end(address)
            while len(self.attempts) > 1024:
                self.attempts.popitem(last=False)
            return True


def configured():
    config = current_app.config
    password_hash = config.get("CATALOG_ADMIN_PASSWORD_HASH")
    key = config.get("SECRET_KEY")
    return bool(
        config.get("CATALOG_WEB_ADMIN_ENABLED")
        and isinstance(password_hash, str)
        and password_hash.startswith(("scrypt:", "pbkdf2:"))
        and len(password_hash) <= 512
        and isinstance(key, str)
        and len(key) >= 32
    )


def credential_version():
    return hashlib.sha256(current_app.config["CATALOG_ADMIN_PASSWORD_HASH"].encode()).hexdigest()


def authenticated():
    return bool(
        configured()
        and session.get("catalog_owner")
        and session.get("catalog_until", 0) > time.time()
        and session.get("catalog_credential") == credential_version()
    )


def csrf_token():
    if "catalog_csrf" not in session:
        session["catalog_csrf"] = secrets.token_urlsafe(32)
    return session["catalog_csrf"]


def render_admin(state=None, *, error=None, preview=None, status=200):
    locale = getattr(g, "catalog_locale", "ru")
    copy = admin_copy_for(locale)
    logged_in = authenticated()
    if state is None:
        state = "upload" if logged_in else "login"
    current_catalog = None
    if logged_in:
        try:
            current_catalog = current_app.extensions["catalog_manager"].current()
        except Exception:
            error = "failure"
    return (
        render_template(
            "catalog_admin.html",
            locale=locale,
            locale_options=locale_options(locale),
            locale_target="catalog_admin.index",
            copy=copy_for(locale),
            form=None,
            admin_copy=copy,
            state=state,
            authenticated=logged_in,
            csrf_token=csrf_token() if configured() else "",
            preview=preview,
            current_catalog=current_catalog,
            error=copy.get("error_" + error) if error else None,
        ),
        status,
    )


@catalog_admin.before_request
def guard():
    g.catalog_locale = resolve_locale(request.args.get("locale"))
    if not configured():
        return render_admin("disabled", status=503)
    if request.endpoint == "catalog_admin.upload":
        request.max_content_length = MAX_UPLOAD + 65536
    if request.method == "POST":
        if request.endpoint != "catalog_admin.login" and not authenticated():
            return render_admin("login", error="session", status=401)
        g.catalog_locale = resolve_locale(request.form.get("locale") or request.args.get("locale"))
        supplied = request.form.get("csrf_token", "")
        expected = session.get("catalog_csrf", "")
        if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
            return render_admin(error="csrf", status=403)
    elif request.endpoint == "catalog_admin.sample" and not authenticated():
        return render_admin("login", error="session", status=401)


@catalog_admin.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@catalog_admin.errorhandler(RequestEntityTooLarge)
def too_large(_error):
    return render_admin(error="size", status=413)


@catalog_admin.get("")
def index():
    if authenticated() and session.get("catalog_preview"):
        try:
            preview = current_app.extensions["catalog_manager"].get_preview(
                session["catalog_preview"], session["catalog_owner"]
            )
            return render_admin("preview", preview=preview)
        except CatalogOperationError as error:
            session.pop("catalog_preview", None)
            return render_admin(error=error.code, status=422)
        except Exception:
            return render_admin(error="failure", status=503)
    return render_admin()


@catalog_admin.post("/login")
def login():
    limiter = current_app.extensions["catalog_login_limiter"]
    if not limiter.allow(request.remote_addr or "unknown"):
        return render_admin("login", error="rate", status=429)
    password = request.form.get("password", "")
    valid = False
    if 1 <= len(password) <= 256:
        try:
            valid = check_password_hash(current_app.config["CATALOG_ADMIN_PASSWORD_HASH"], password)
        except (ValueError, TypeError):
            pass
    if not valid:
        return render_admin("login", error="auth", status=401)
    session.clear()
    session["catalog_owner"] = secrets.token_urlsafe(32)
    session["catalog_until"] = time.time() + 1800
    session["catalog_credential"] = credential_version()
    csrf_token()
    return redirect(url_for("catalog_admin.index", locale=g.catalog_locale), code=303)


@catalog_admin.post("/logout")
def logout():
    current_app.extensions["catalog_manager"].discard(session["catalog_owner"])
    session.clear()
    return redirect(url_for("catalog_admin.index", locale=g.catalog_locale), code=303)


@catalog_admin.post("/cancel")
def cancel():
    current_app.extensions["catalog_manager"].discard(session["catalog_owner"])
    session.pop("catalog_preview", None)
    return redirect(url_for("catalog_admin.index", locale=g.catalog_locale), code=303)


@catalog_admin.post("/upload")
def upload():
    files = request.files.getlist("catalog_file")
    if len(files) != 1 or not files[0].filename or not files[0].filename.lower().endswith(".csv"):
        return render_admin(error="file", status=422)
    try:
        data = files[0].stream.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            return render_admin(error="size", status=413)
        preview = current_app.extensions["catalog_manager"].stage(data, session["catalog_owner"])
    except CatalogOperationError as error:
        return render_admin(error=error.code, status=422)
    except Exception:
        return render_admin(error="failure", status=503)
    session["catalog_preview"] = preview["preview_id"]
    return render_admin("preview", preview=preview)


@catalog_admin.post("/activate")
def activate():
    try:
        result = current_app.extensions["catalog_manager"].commit(
            request.form.get("preview_id", ""), session["catalog_owner"]
        )
    except CatalogOperationError as error:
        return render_admin(error=error.code, status=409 if error.code == "conflict" else 422)
    except Exception:
        return render_admin(error="failure", status=503)
    session.pop("catalog_preview", None)
    return render_admin("success", preview=result)


@catalog_admin.get("/sample")
def sample():
    # Build a schema-correct starter from a real source profile, never an export document.
    try:
        profile = load_csv(current_app.config["DATASET_PATH"])[0]
        row = asdict(profile)
        for field in ("categories", "event_formats", "languages", "busy_dates"):
            row[field] = "|".join(row[field])
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(row), lineterminator="\r\n")
        writer.writeheader()
        writer.writerow(row)
        response = Response(
            output.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8"
        )
        response.headers["Content-Disposition"] = 'attachment; filename="catalog-template.csv"'
        return response
    except Exception:
        return render_admin(error="failure", status=503)
