# EventMatch — final integration and product QA

Date: 2026-09-23. Branch: `feature/jonas`.
Tested implementation: `54c0e933c1fb5322738be54b7057ff7caa969e4c`.
This report is evidence, not an alternative product contract.

## Integrated baseline

Fetched `origin` before implementation and again before the final commit.
Latest `origin/main` was `ebfd9b0`; `git merge origin/main` reported already up to
date, and the final ancestry check succeeded. Existing backend improvements
(`2764ee9`) and frontend improvements (`90a5d67`, integrated by `44507a6`) were present.
The pre-existing uncommitted CONTRACT section 23.4 was preserved and implemented.
No reset, history rewrite, push, or merge into main was performed.

Baseline: **241 passed** on the pre-existing Python 3.12.14 environment with
`pytest -q --basetemp=.pytest_cache/jonas-baseline`. The first attempt without a
workspace-local basetemp produced 125 passed / 116 setup errors because pytest
could not access the system temporary directory. These were environment failures.

Final verification used a separate Python **3.13.15** environment in
`instance/qa-venv313`, leaving the original venv intact. Runtime dependencies:
Flask 3.1.3, httpx 0.28.1; pytest 8.4.2, Ruff 0.16.8, Black 26.5.1.

## Result and defects fixed

The Web and JSON API both use RecommendationService → repository discovery →
hard filters → deterministic ranking → evidence → AI reason selection or fallback.
No filter/ranking implementation was changed or duplicated.

- Web now forwards the product locale independently of contractor language.
- Explanations and saved service messages retain their generation language after
  locale switching, with explicit labels and correct HTML language attributes.
- Locale switching copies live draft values; saved results and downloads continue
  to refer to the original query. Expired snapshots produce a localized notice.
- Web uses the shared versioned JSON/CSV serializers, UTC timestamp, normalized
  request, original result, and bounded immutable snapshot implementation.
- Both zero-result states can be exported, including a CSV metadata row.
- Shared CSV escaping closes the former Web whitespace/control-prefix formula bypass.
- Optional snapshot failure no longer discards a valid recommendation. API returns
  its unchanged successful body with export-unavailable header; Web shows a notice.
- Unexpected exceptions are no longer rendered or logged by recommendation/export
  handlers. Only actual validation errors are classified as invalid user input.
- Token-bearing HTML is no-store. Tokens remain in POST bodies, not URLs.
- User-requested light-only visual redesign follows the supplied HTML concept:
  compact responsive form, white cards, purple accents, price beside identity,
  prominent explanations, factual comparison and export controls. No mock results
  from the concept were introduced into the application.
- Fixed 320 px overflow and versioned CSS/JS URLs to avoid stale cached assets.

CONTRACT section 23.4 records the integrated snapshot/locale behavior. It clarifies
that translated display labels leave canonical DTO/export values unchanged, and
records the user's light-only design requirement. Legacy recommendation API response
fields are preserved; the former frontend-only download shape is replaced explicitly.

## Final automated checks

Commands were run from the repository root:

```powershell
instance/qa-venv313/Scripts/python.exe -m pytest -q --basetemp=.pytest_cache/jonas313-release --tb=short
instance/qa-venv313/Scripts/python.exe -m ruff check .
instance/qa-venv313/Scripts/python.exe -m black --check app tests scripts run.py
git diff --check
```

Final suite: **272 passed, 0 failed, 0 errors, 3.88 seconds**. Ruff passed; Black
reported 47 files unchanged; whitespace check passed. This is the complete suite,
including unit, backend/API integration, frontend and product regression tests.
There is no separate configured browser E2E runner; browser checks below were
executed using the actual application. The new product integration file adds 31
cases, including a real-catalog matrix covering 0/1/2/3 cards in all three locales.

The new regression tests were first executed against the defective implementation:
13 failed. They now pass along with the broader suite. Additional coverage checks
shared CSV protection, HTML escaping, immutable/size-limited snapshots, exact saved
generation preservation, and unchanged successful responses under capture failure.

## Reproducible real-data demo

Local HTTP server: Python 3.13.15, Flask development server on 127.0.0.1:5058,
external AI explicitly disabled through an empty LLM_API_KEY. Health returned
HTTP 200 with `{"status":"ok"}`. The original five-scenario `scripts/demo.py`
was also executed successfully earlier in the session.

```powershell
instance/qa-venv313/Scripts/python.exe -m flask --app run:app run --host 127.0.0.1 --port 5058
instance/qa-venv313/Scripts/python.exe -X utf8 scripts/product_qa.py --base-url http://127.0.0.1:5058
```

Common query: Алматы, свадьба, 2026-10-15, budget 6,000,000 KZT, optional constraints
omitted unless specified below. Dataset is the existing 66-profile CSV.

| Scenario | Verified result |
| --- | --- |
| Dense: Ведущий | HK-35215, HK-27222, HK-77838, in that order |
| Rare: Флорист | HK-90001 (synthetic), HK-39372 (price imputed) |
| One: Флорист, budget 200,000 | HK-39372; comparison absent |
| Empty: Ведущий, budget 0 | no_eligible_candidates; busy 2, over_budget 10, wrong_format 4 |
| Absent: Зарубежье, Флорист | category_not_found; explicit message |
| Date-sensitive: Ведущий, 2026-10-16 | HK-72938, HK-77838, HK-44923 |
| RU / KK / EN | Identical ordered IDs; translated framing; source evidence unchanged |
| Language alias | language=русский and communication_language=русский give identical IDs |
| Web / JSON / CSV | Visible IDs and order match exported IDs and API IDs |

Existing and new tests cover all hard constraints, exact budget/duration boundaries,
unsupported format/language, busy dates, null duration limits, repeat/reordered
catalog determinism, and AI success/failure without changing eligibility or order.

## Browser and export QA

Actual in-app Chromium checks used desktop 1366×1000 and mobile 320×800 viewports.
Manually inspected RU, EN and KK, filled/submitted the form, switched locale with
an unsent budget edit, verified the old result remained tied to its old query,
then generated a new result in the new locale. Inspected 3-card and 2-card
comparisons, 1-card state without comparison, both empty outcomes, synthetic and
imputed labels, and generation-language labels. Focus moved to the result heading.

At mobile width, document client/scroll widths both measured 305 px (320 px viewport
minus native scrollbar); comparison container was 218 px with 640 px internally
scrollable content. Long real descriptions wrapped without page overflow. Light-only
HTML/CSS settings and computed `color-scheme: light only` were verified. OS theme
settings were not changed. Native date-picker language remains browser-controlled.

JSON and CSV were downloaded over HTTP and parsed. CSV BOM, fixed columns, CRLF,
escaping, formula protections and zero-result rows have automated coverage. Both
formats retain snapshot metadata and result semantics. Excel itself was not opened;
Excel-oriented compatibility is based on verified encoding and serialization.

## Explanation quality and AI failure

Fresh independent review manually compared real host, florist, photographer and
banquet outputs across RU/KK/EN with CSV/evidence. Price-from, budget, city, category,
format and available date were factual; chosen description fragments were exact
source text. Examples distinguish multilingual hosting, television/theatre experience,
seasonal floral compositions and order volume. No invented winner, rating, capacity
or other unsupported attribute was found. These are sample-based quality observations,
not a claim that keyword tests prove all explanation quality.

AI can select only a validated reason ID belonging to an eligible candidate. Free
prose is not accepted. Tests exercise provider failures, invalid selections, malformed
responses, response limits and transport deadlines. An additional real-dataset Flask
request with a client raising a simulated provider error returned HTTP 200 and an
identical full result to disabled-AI fallback, in 10.96 ms.

## Performance observations

Single local run, warmed development server, real CSV/SQLite, no external AI.
Measured with perf_counter in product_qa.py; these are not load-test percentiles.

| Request | Time |
| --- | --- |
| Slowest of 10 normal API requests | 67.72 ms |
| All 10 API requests combined | 199.23 ms |
| API JSON export with new recommendation | 29.21 ms |
| Web recommendation | 9.42 ms |
| Web saved JSON export | 17.37 ms |
| Web saved CSV export | 14.28 ms |

All measured individual requests were below 10 seconds. Real external AI latency
was **not measured**; mocked transport and simulated failure do not establish it.

## Security, independent review and limitations

Inspected runtime key configuration, .gitignore, exception handling, template
escaping, CSV/JSON allowlists and local catalog tooling. No credential values were
opened, printed, copied or added. Historical tracking of `API key.txt` at `a6b86bf`
was confirmed by filename-only Git history; the backend report records a historical
credential. Rotation is unverified. Revoke/rotate that key before public publication
if this has not already been done; history was not rewritten.

Catalog administration remains disabled by default, trusted-local-CLI only, with
1 MiB limit, strict UTF-8/BOM/schema/rows/IDs/date/flag validation and atomic separate
staging. Public upload, HTTP authentication, checksum/version metadata, activation
and rollback were not implemented and are not claimed. The current catalog is unchanged.

Initial independent investigations covered contract/runtime, backend/adversarial QA
and frontend. Fresh final reviewers covered A+B contract/integration, C+D
locale/explanation quality, E+F security/documentation. The requested Luna 5.4 was
unavailable, so gpt-5.6-luna at medium reasoning was used. The lead verified findings:
fixed the README overclaim about smoke-script coverage, clarified canonical values
versus translated labels, and reran the full final suite after the visual changes.

Known limits: per-process 15-minute snapshots; a restart or different worker loses
them; Bootstrap requires CDN access or a cached asset; source evidence is deliberately
not translated; comparison is limited to public DTO facts. No real provider call,
load test, native Excel check or full screen-reader audit was performed.

The tested implementation is ready for local demo and merge review. Public release
still requires confirmation of historical credential rotation. README includes the
actual startup, tests, smoke commands, product behavior and limitations.
