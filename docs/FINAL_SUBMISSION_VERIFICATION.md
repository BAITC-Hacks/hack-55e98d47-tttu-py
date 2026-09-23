# FINAL SUBMISSION VERIFICATION

Date: 2026-09-23. This is the current release verification record, not another contract.

**Branch:** `feature/jonas`.
**Commit (verified application code and dependencies):** `29271b8708545ae23fc688529c56f22788e7d854`.
The subsequent documentation-only commit supplies this report and corrects README test commands;
use `git rev-parse HEAD` to identify that final submission commit.

## CLEANUP

**Removed:** `BACKEND_REPORT.md`, `FRONTEND_REPORT.md`, `INTEGRATION_REPORT.md`,
`CATALOG_UPLOAD_REPORT.md`. Useful current setup, architecture and feature details
were consolidated into README; old branch ownership, counts and incomplete phase
status are no longer evaluator-facing. Git history retains the original reports.

**Gitignored:** runtime databases/configuration, Python/pytest/Ruff caches and virtual
environments remain ignored; added log/database variants, coverage variants, IDE/OS
files, temporary pytest directories and local exports. Existing operator data was preserved.

**Legacy retained/moved:** none in the delivered tree. No unused runtime module,
dependency, template or script was confirmed; no speculative code deletion was made.
pytest was moved from runtime to development requirements. The shared service remains
one recommendation pipeline for Web/API; export adapters do not duplicate it.

## DOCUMENTATION

**README:** rewritten around product input/output/value, exact setup, all 14 supported
application environment variables, implemented features, actual API response, algorithm,
demos, administration, testing and single-process production startup.

**CONTRACT:** clarified bounded AI reason selection, locale framing and exact ranking
formula; corrected a response count, real project paths and CLI/browser activation
wording. Removed historical branch ownership and agent workflow from the product contract.

**Contradictions fixed:** old test counts and branch reports, free-prose AI claims,
Russian-only explanation wording, missing administration variables, misleading relative
path wording and CLI/public-upload wording. The README checklist is for the evaluator.

A clean-clone attempt exposed a README defect: `--basetemp=instance/qa-pytest` required
an existing parent directory. Final commands use `.pytest-release-temp` / `.pytest-ai-temp`
in the repository root, both ignored. The commands below are the corrected form.

## RUNTIME

**Development startup:** executed `python run.py` on Python 3.13.15 with debug off.
HOST/PORT were exercised on loopback port 5059; a clean clone used PORT=5060.
The user's older Python 3.12 service already occupied port 5000 and was left intact;
its responses were excluded from release evidence.

**Production startup:** executed with Waitress 3.0.2, one process / four threads:

```powershell
.venv/Scripts/python.exe -m waitress --host=127.0.0.1 --port=8080 --threads=4 --max-request-body-size=1114112 --call app:create_app
```

The root verification environment used `instance/release-venv/Scripts/python.exe`
in place of `.venv/Scripts/python.exe`. Factory import, debug=False, 66 catalog
profiles and HTTP responses were checked. Production and development used separate
runtime directories so they did not compete for the same data.

**Health endpoint:** actual HTTP `GET /api/v1/health` returned `200 {"status":"ok"}`
under both development and Waitress. It is a liveness check, not a disk/provider probe.

## TESTING

**Environment:** Windows, Python 3.13.15; Flask 3.1.3, Jinja2 3.1.6, Werkzeug 3.1.8,
httpx 0.28.1, Waitress 3.0.2, pytest 8.4.2, Ruff 0.16.8, Black 26.5.1.
Direct dependency versions are pinned; transitive dependencies are resolved by pip.

**Baseline:** actual pre-edit suite: 290 passed on Python 3.13.15. The first run in
an existing Python 3.12 environment had system-temp permission errors; redirecting
pytest temporary files resolved those environment errors before implementation.

**Clean reproduction:** created a separate local Git clone of the verified code commit,
created a new `.venv` using the available Python 3.13.15 interpreter, copied `.env.example`
to `.env`, and installed `requirements-dev.txt` (which includes runtime requirements).
The machine has no registered `py -3.13` launcher installation, so the explicit 3.13
interpreter was used for venv creation. The GitHub clone step and POSIX commands were
not executed; the local clone tested the committed source without developer runtime data.

**Full test command:**

```powershell
.venv/Scripts/python.exe -m pytest -q --basetemp=.pytest-release-temp
```

**Actual result:** 291 passed. One added regression first failed on the unmodified
CLI: staging overwrote an existing active CSV with SQLite. It now rejects that path
and preserves the original bytes; the focused CLI suite passed all 19 tests.

**Lint:** `python -m ruff check .` — all checks passed.
**Formatting:** `python -m black --check app tests scripts run.py` — 53 files unchanged.
**Dependency consistency:** `python -m pip check` — no broken requirements.
**Diff whitespace:** `git diff --check` — passed.
No separate build or type-check command is declared for this Python/Jinja project.

## RECOMMENDATION QA

Both live `scripts/demo.py` and `scripts/product_qa.py` were executed; product QA
also ran against Waitress and the clean clone. Inputs are in README.

| Check | Actual evidence |
| --- | --- |
| Dense | `matched`, three IDs: HK-35215, HK-27222, HK-77838 |
| Rare | `matched`, HK-90001 and HK-39372; synthetic and price-imputed markers retained |
| Empty | `no_eligible_candidates`; busy=2, over_budget=10, wrong_format=4, duration/language=0 |
| Category absent | `category_not_found`, empty cards, meaningful message |
| Date-sensitive | 2026-10-16 gives HK-72938, HK-77838, HK-44923; busy diagnostic changes from 2 to 5 |
| Determinism | repeated-request regression plus identical IDs across RU/KK/EN and Web/API/export |
| Optional constraints | unit/integration tests exercise duration, language and every hard filter |
| Evidence / AI boundary | only top eligible evidence reaches the provider; response cannot add/reorder cards |
| AI fallback | 14 focused AI transport/integration tests pass, including timeout, malformed response, HTTP errors and redirects |
| Export/comparison | live API JSON, Web JSON and Web CSV share IDs; comparison appears for three cards |

Waitress product-QA observed a maximum API request time of about 0.066 s and Web
request time of about 0.083 s on loopback with AI disabled. These are smoke measurements,
not load tests or an external-provider latency guarantee.

**Browser:** actual form submission under Waitress displayed all three expected
cards, evidence and comparison. Editing budget to 5,500,000 and switching RU → KK → EN
preserved the draft while the saved explanations still described the original
6,000,000 budget and Russian generation locale. At 320 px the document had no
horizontal overflow; the comparison table scrolled inside its container. Browser
console inspection returned no errors. The temporary viewport override was reset.

**Administration:** clean-clone CLI validate/stage both reported 66 profiles.
The full suite exercised authenticated upload/preview/apply, CSRF, owner/expiry,
invalid files, failure preservation and restart persistence. A new manual browser
admin upload was not performed in this release pass; no production catalog was replaced.

## SECURITY

**Tracked secret scan:** scanned current tracked text for private-key blocks, common
provider-token formats and credential assignments; output contained locations only.
The sole credential-assignment match was the intentionally fake password in an isolated
admin test fixture. Manual review and filename scan found no active credential,
tracked `.env`, runtime database, log or generated export in the delivered source.
Pattern scanning is not proof about arbitrary secrets or credential validity.

**Environment configuration:** safe `.env.example`; AI secret optional, administration
requires explicit configuration, local hash/session configuration remains ignored.
Session/CSRF/upload bounds and generic recommendation/export failures were reviewed.

**Known historical credential issue:** Rotate previously exposed credentials before public publication.

## DEPLOYMENT

**Method:** single-process Waitress WSGI deployment on Windows; command above.
**Verified:** factory import, debug off, custom host/port, HTTP health, Web/API,
all demo outcomes, localized IDs, CSV/JSON and fallback tests.

Read-only source CSV and writable SQLite/active/staging directories are documented.
Active CSV must persist across restarts. Snapshots, login limits and previews are
process-local; multi-process deployment is not supported. HTTPS reverse proxy,
secure cookies and a service supervisor are documented operational requirements;
no remote deployment, TLS setup, Linux run or cloud build is claimed.

## EVALUATION EVIDENCE

| Criterion | Evidence, without an invented score |
| --- | --- |
| Task fit / 25 | Existing catalog only, top ≤3, dense/rare/empty/date demo, all constraints and truthful indicators |
| Technical implementation / 25 | One modular service, deterministic Fraction ranking, bounded evidence AI, SQLite transactions, regression and integration tests |
| README/reproducibility / 25 | Clean local clone and new venv, declarations installed, corrected startup/test commands, real API response, live production smoke |
| Practical value / 15 | Shortlist with concrete reasons, actionable rejection diagnostics, comparison and immutable downloadable results |
| Growth/originality / 10 | Clear code/AI boundary; existing locale/export/admin distinguished from catalog history, saved-search and observability roadmap |

Two Luna audit agents covered repository, documentation, production/security and
evaluator gaps in parallel waves. Two fresh Luna reviewers then covered the six
final review tracks. The confirmed staging defect was fixed; the missing-report
link finding is closed by this file. No reviewer score is used as evidence.

## KNOWN LIMITATIONS

- One process; SQLite and memory-only snapshots/preview/session-rate limits do not provide horizontal scaling.
- No live external AI quality/latency test, load test, TLS/cloud deployment or POSIX execution.
- Bootstrap CSS requires CDN access; full offline visual delivery is not claimed.
- No catalog version-history/rollback UI, booking, saved searches or multi-user administration.
- Historical secret warning above remains a prerequisite for public publication.
- Final merge/push is not performed by this release preparation.

## FINAL STATUS

**READY for final merge and a single-process evaluator demo.**
The public-publication prerequisite and unexecuted deployment surfaces above are
explicitly outside the verified readiness claim. No unexecuted check is marked PASS.
