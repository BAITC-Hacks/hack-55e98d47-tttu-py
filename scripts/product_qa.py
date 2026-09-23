"""Run compact live product QA against the default Flask server.

The script uses only the Python standard library and keeps all observations in memory.
It exits nonzero when a required product assertion fails.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from html import unescape
from time import perf_counter
from urllib.parse import urlencode
from urllib.request import Request, urlopen

COMMON = {
    "city": "Алматы",
    "event_date": "2026-10-15",
    "event_format": "свадьба",
    "category": "Ведущий",
    "budget_kzt": 6000000,
}
LOCALES = ("ru", "kk", "en")
CARD_ID_RE = re.compile(r'<p class="contractor-id">[^<]*:\s*([^<]+)</p>')
EXPORT_ID_RE = re.compile(r'name="export_id" value="([^"]+)"')


class QAError(AssertionError):
    pass


def request_json(url: str, payload: dict) -> tuple[dict, float, dict[str, str]]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    started = perf_counter()
    with urlopen(request, timeout=10) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
    return json.loads(body.decode("utf-8")), perf_counter() - started, headers


def request_bytes(url: str, payload: dict) -> tuple[bytes, float, dict[str, str]]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "*/*"},
    )
    started = perf_counter()
    with urlopen(request, timeout=10) as response:
        body = response.read()
        headers = {key.lower(): value for key, value in response.headers.items()}
    return body, perf_counter() - started, headers


def request_form(url: str, payload: dict[str, str]) -> tuple[str, float, dict[str, str]]:
    request = Request(
        url,
        data=urlencode(payload).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html"},
    )
    started = perf_counter()
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
        headers = {key.lower(): value for key, value in response.headers.items()}
    return body, perf_counter() - started, headers


def card_ids(result: dict) -> list[str]:
    return [str(card["id"]) for card in result.get("recommendations", [])]


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise QAError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    api = base + "/api/v1"
    elapsed: dict[str, float] = {}
    summary: dict[str, object] = {"base_url": base, "ids": {}, "elapsed_seconds": elapsed}

    def api_call(payload: dict) -> dict:
        result, seconds, _ = request_json(api + "/recommendations", payload)
        elapsed.setdefault("api", 0.0)
        elapsed["api"] += seconds
        elapsed["api_max"] = max(elapsed.get("api_max", 0.0), seconds)
        assert_true(seconds <= 10, "API latency exceeds target")
        return result

    dense = api_call(COMMON)
    rare = api_call({**COMMON, "category": "Флорист"})
    zero = api_call({**COMMON, "budget_kzt": 0})
    next_date = api_call({**COMMON, "event_date": "2026-10-16"})
    absent = api_call({**COMMON, "city": "Зарубежье", "category": "Флорист"})
    assert_true(dense["status"] == "matched" and dense["count"] == 3, "dense scenario")
    assert_true(rare["status"] == "matched" and rare["count"] == 2, "rare scenario")
    assert_true(zero["status"] == "no_eligible_candidates", "zero scenario")
    assert_true(absent["status"] == "category_not_found", "absent scenario")
    dense_ids, next_ids = card_ids(dense), card_ids(next_date)
    assert_true(dense_ids != next_ids, "date sensitivity")
    summary["ids"] = {"dense": dense_ids, "rare": card_ids(rare), "next_date": next_ids}

    locale_results = {locale: api_call({**COMMON, "locale": locale}) for locale in LOCALES}
    for locale, result in locale_results.items():
        assert_true(card_ids(result) == dense_ids, f"locale order changed: {locale}")
    russian = api_call({**COMMON, "language": "русский"})
    alias = api_call({**COMMON, "communication_language": "русский"})
    assert_true(card_ids(russian) == card_ids(alias), "communication language alias changed IDs")
    summary["locale_ids"] = {locale: card_ids(result) for locale, result in locale_results.items()}
    summary["alias_ids"] = card_ids(alias)

    export_payload = {"format": "json", "request": COMMON}
    export_body, seconds, _ = request_bytes(api + "/recommendations/export", export_payload)
    elapsed["api_export_json"] = seconds
    exported = json.loads(export_body.decode("utf-8"))
    assert_true(exported.get("schema_version") == "recommendation-export.v1", "API export schema")
    assert_true(card_ids(exported["result"]) == dense_ids, "API export IDs")

    form = {
        **{key: str(value) for key, value in COMMON.items()},
        "locale": "ru",
        "duration_hours": "",
        "language": "",
    }
    html, seconds, _ = request_form(base + "/", form)
    elapsed["web"] = seconds
    export_match = EXPORT_ID_RE.search(html)
    assert_true(export_match is not None, "web export_id missing")
    web_ids = [unescape(item).strip() for item in CARD_ID_RE.findall(html)]
    assert_true(web_ids[:3] == dense_ids, "web card IDs differ from API")
    assert_true("comparison-panel" in html, "web comparison missing")
    export_id = export_match.group(1)

    web_json, seconds, _ = request_form(
        base + "/recommendations/export/json", {"locale": "ru", "export_id": export_id}
    )
    elapsed["web_export_json"] = seconds
    web_document = json.loads(web_json)
    assert_true(web_document.get("schema_version") == "recommendation-export.v1", "web JSON schema")
    assert_true(card_ids(web_document["result"]) == dense_ids, "web JSON IDs")

    web_csv, seconds, headers = request_form(
        base + "/recommendations/export/csv", {"locale": "ru", "export_id": export_id}
    )
    elapsed["web_export_csv"] = seconds
    assert_true(web_csv.startswith("\ufeff"), "web CSV BOM")
    rows = list(csv.DictReader(io.StringIO(web_csv.lstrip("\ufeff"), newline="")))
    assert_true(
        rows and rows[0].get("schema_version") == "recommendation-export.v1", "web CSV schema"
    )
    assert_true([row.get("id") for row in rows] == dense_ids, "web CSV IDs")
    assert_true(headers.get("cache-control") == "no-store", "web export cache policy")

    summary["web_ids"] = web_ids[:3]
    summary["exported_ids"] = {
        "api_json": card_ids(exported["result"]),
        "web_json": card_ids(web_document["result"]),
        "web_csv": [row.get("id") for row in rows],
    }
    assert_true(
        all(value <= 10 for key, value in elapsed.items() if key != "api"),
        "request latency exceeds target",
    )
    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (QAError, OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(
            json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        raise SystemExit(1)
