"""Exercise the required demo scenarios against a running backend."""

import argparse
import json
from time import monotonic
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    args = parser.parse_args()
    common = {
        "city": "Алматы",
        "category": "Ведущий",
        "event_format": "свадьба",
        "event_date": "2026-10-15",
        "budget_kzt": 6000000,
    }
    scenarios = (
        ("Dense category", common),
        ("Rare category", {**common, "category": "Флорист"}),
        ("All rejected", {**common, "budget_kzt": 0}),
        ("Same request, next date", {**common, "event_date": "2026-10-16"}),
        ("Category absent", {**common, "city": "Зарубежье", "category": "Флорист"}),
    )
    results = []
    for name, payload in scenarios:
        request = Request(
            args.base_url.rstrip("/") + "/api/v1/recommendations",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        start = monotonic()
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        elapsed = monotonic() - start
        print(f"{name}: {result['status']}; count={result['count']}; {elapsed:.3f}s")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert elapsed <= 10
        results.append(result)
    assert results[0]["count"] == 3
    assert results[1]["count"] == 2
    assert results[2]["status"] == "no_eligible_candidates"
    assert results[4]["status"] == "category_not_found"
    assert [card["id"] for card in results[0]["recommendations"]] != [
        card["id"] for card in results[3]["recommendations"]
    ]


if __name__ == "__main__":
    main()
