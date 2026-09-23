
# CONTRACT.md

## 0. Contract Authority

Этот файл является **единственным source of truth** проекта.

Отдельные `SPEC.md`, `openapi.yaml` и альтернативные API-контракты не создаются.

Приоритет:

1. Требования хакатон-кейса.
2. Этот `CONTRACT.md`.
3. Тесты, реализующие контракт.
4. Реализация.

`feature/jonas` владеет контрактом.

`backend/ksusha` реализует backend согласно контракту.

`frontend/denis` реализует UI согласно контракту.

Любое изменение поведения, API, DTO, фильтрации, ranking или результата сначала отражается здесь.

---

# 1. Product

## 1.1 Problem

Пользователь уже выбрал тип мероприятия и получил каталог event-подрядчиков своего города.

Система НЕ должна расширять каталог.

Задача системы — выбрать из существующего каталога до трёх наиболее подходящих подрядчиков и понятно объяснить, почему каждый оказался в рекомендации.

Главная ценность продукта:

**качество конкретного объяснения, а не сама сортировка.**

## 1.2 Input

Обязательные параметры:

* `city`
* `event_date`
* `event_format`
* `category`
* `budget_kzt`

Опциональные:

* `duration_hours`
* `language`

## 1.3 Output

Система возвращает максимум 3 подрядчиков.

Каждая карточка содержит:

* `id`
* `anon_name`
* подходящую категорию
* город
* `price_from_kzt`
* synthetic/imputed indicators, если применимо
* 1–2 предложения персонального объяснения

Объяснение должно ссылаться на реальные свойства конкретного подрядчика:

* бюджет
* формат мероприятия
* язык
* длительность
* смысл/особенности `description`

Запрещены объяснения вида:

> отличный выбор для вашего мероприятия

или другие взаимозаменяемые generic-фразы.

Если убрать имена подрядчиков, объяснения разных карточек одного результата должны оставаться различимыми.

---

# 2. Required Outcomes

Система обязана явно различать три состояния.

## MATCHED

Найдены подходящие подрядчики.

Возвращается 1–3 карточки.

## CATEGORY_NOT_FOUND

В выбранном городе нет подрядчиков требуемой категории.

Пользователь получает явное текстовое объяснение.

## NO_ELIGIBLE_CANDIDATES

Подрядчики нужной категории в городе существуют, но после hard constraints никто не подходит.

Причины должны быть агрегированы и показаны пользователю, например:

* заняты на выбранную дату;
* превышают бюджет;
* не работают с этим форматом;
* не подходят по длительности;
* не поддерживают требуемый язык.

Пустой экран запрещён.

---

# 3. Dataset

Основной dataset содержит 66 профилей.

Используем поля:

* `id`
* `anon_name`
* `categories`
* `city`
* `price_from_kzt`
* `event_formats`
* `languages`
* `max_hours`
* `busy_dates`
* `description`
* `synthetic`
* `city_imputed`
* `price_imputed`

Города:

* Алматы
* Астана
* Зарубежье

`max_hours = null` означает, что работа подрядчика не привязана к продолжительности присутствия на площадке.

`busy_dates` является hard availability constraint.

Подрядчик, занятый в `event_date`, никогда не попадает в recommendation results.

Площадки обрабатываются тем же recommendation pipeline.

Synthetic profiles разрешены только с:

`synthetic: true`

В UI synthetic-профиль должен быть различим.

---

# 4. Technology

Основной стек:

* Python 3.13
* Flask
* Jinja2
* Bootstrap
* SQLite
* pytest

Допускается внешний LLM API для AI-части.

API key никогда не:

* hardcode;
* commit;
* выводится пользователю;
* логируется;
* возвращается API;
* помещается в CONTRACT.md.

Секрет читается только во время выполнения из локального secret/environment configuration.

---

# 5. Architecture

Используется modular monolith.

```text
Browser
   |
   v
Flask Web
   |
   +---- Jinja2 / Bootstrap
   |
   v
Recommendation Service
   |
   +---- Deterministic Hard Filters
   |
   +---- Deterministic Ranking
   |
   +---- Explanation Context Builder
   |
   +---- AI Explanation Layer
   |
   v
Dataset Repository
   |
   v
CSV / SQLite
```

JSON API использует тот же recommendation service:

```text
Web Route ----\
               \
                RecommendationService
               /
API Route ----/
        |
        v
Repository
```

Нельзя создавать отдельный recommendation algorithm для UI и API.

---

# 6. AI Agent Architecture

AI используется там, где он добавляет ценность: **семантическое понимание и объяснение результата**.

AI не должен принимать решения, нарушающие hard constraints.

Pipeline:

```text
USER QUERY
   |
   v
INPUT VALIDATION
   |
   v
CITY + CATEGORY CANDIDATE DISCOVERY
   |
   v
HARD FILTERS
   |
   v
DETERMINISTIC SCORING
   |
   v
TOP CANDIDATES
   |
   v
EVIDENCE BUILDER
   |
   v
AI EXPLANATION
   |
   v
VALIDATION / FALLBACK
   |
   v
TOP <= 3
```

## 6.1 Deterministic Core

LLM запрещено самостоятельно решать:

* доступен ли подрядчик;
* соответствует ли город;
* соответствует ли категория;
* проходит ли бюджет;
* поддерживает ли формат;
* проходит ли duration constraint;
* поддерживает ли обязательный язык.

Эти факты вычисляются Python-кодом.

## 6.2 AI Responsibility

AI получает только уже проверенных кандидатов и структурированные evidence.

AI может:

* анализировать смысл `description`;
* выделять конкретные особенности;
* формулировать 1–2 предложения объяснения;
* объяснять различия между подходящими кандидатами.

AI не может придумывать отсутствующие факты.

## 6.3 Deterministic Requirement

Одинаковый запрос и одинаковый dataset должны давать одинаковый порядок карточек.

Поэтому LLM output не участвует в окончательной сортировке.

Финальный tie-breaker:

`id ASC`

или другая одна явно зафиксированная deterministic стратегия.

Temperature AI-вызова должна быть минимальной/детерминированной, если используемый API это поддерживает.

---

# 7. Hard Filtering

Фильтрация выполняется последовательно и диагностируемо.

## Stage 1 — City

`candidate.city == request.city`

Если после city+category discovery кандидатов нет:

`CATEGORY_NOT_FOUND`

## Stage 2 — Category

Requested category должна присутствовать в `categories`.

Мультикатегорийный профиль считается подходящим, если requested category входит в список.

## Stage 3 — Availability

`event_date NOT IN busy_dates`

Занятый кандидат исключается безусловно.

## Stage 4 — Budget

`price_from_kzt <= budget_kzt`

Цена трактуется как цена «от».

Система не должна утверждать, что итоговая стоимость гарантированно равна `price_from_kzt`.

## Stage 5 — Event Format

`event_format IN event_formats`

## Stage 6 — Duration

Если `duration_hours` не задан:

constraint не применяется.

Если `max_hours == null`:

constraint не применяется.

Иначе:

`duration_hours <= max_hours`

## Stage 7 — Language

Если `language` не задан:

constraint не применяется.

Иначе:

`language IN languages`

---

# 8. Failure Diagnostics

Pipeline сохраняет причины исключения кандидатов.

Пример internal diagnostics:

```json
{
  "busy": 4,
  "over_budget": 2,
  "wrong_format": 1,
  "duration_too_long": 0,
  "language_mismatch": 0
}
```

Это позволяет объяснить `NO_ELIGIBLE_CANDIDATES`.

Один кандидат может нарушать несколько constraints.

Диагностика не должна менять ranking.

---

# 9. Ranking

После hard filtering остаются только допустимые кандидаты.

Ranking должен быть прозрачным и deterministic.

Начальная стратегия:

```text
format match       mandatory
budget fit         scoring signal
language match     scoring signal when requested
duration fit       scoring signal when requested
description match  semantic scoring signal
stable tie-break   mandatory
```

Hard constraints нельзя компенсировать высоким semantic score.

Например:

занятого подрядчика нельзя вернуть потому, что его description очень хорошо подходит запросу.

## Budget Signal

Предпочтение может отдаваться кандидату, рационально использующему бюджет.

При этом цена не должна быть единственным ranking factor.

## Optional Constraints

Если пользователь явно указал язык или длительность, совпадение должно отражаться в evidence и объяснении.

## Semantic Signal

`description` используется для различения нескольких уже допустимых кандидатов.

Semantic signal должен быть bounded и не иметь возможности отменить hard constraints.

---

# 10. Evidence Object

Перед AI explanation для каждого финального кандидата создаётся evidence object.

Пример:

```json
{
  "candidate_id": "HK-00000",
  "requested_category": "Ведущий",
  "available_on_date": true,
  "price_from_kzt": 600000,
  "budget_kzt": 800000,
  "event_format_match": "свадьба",
  "language_match": "казахский",
  "requested_duration_hours": 6,
  "max_hours": 8,
  "description": "...",
  "semantic_reasons": [
    "описание подчёркивает импровизацию",
    "работает со свадебными мероприятиями"
  ]
}
```

LLM получает evidence, а не весь каталог.

---

# 11. Explanation Contract

Explanation:

* русский язык;
* 1–2 предложения;
* конкретное;
* основано только на evidence;
* не содержит недоказанных утверждений;
* не использует generic praise.

Хороший паттерн:

```text
Укладывается в бюджет 800 000 ₸ с ценой от 600 000 ₸ и работает со свадьбами
на русском и казахском. В описании отдельно подчёркнуты импровизация и
интерактивный формат, поэтому кандидат отличается от остальных доступных ведущих.
```

Нельзя:

```text
Это прекрасный профессионал и отличный выбор для вашего праздника.
```

---

# 12. AI Failure Strategy

LLM является enhancement, а не single point of failure.

Если:

* API timeout;
* invalid response;
* unavailable model;
* malformed generated explanation;

система использует deterministic explanation builder.

Fallback explanation строится непосредственно из evidence.

Приложение не должно падать из-за недоступности AI API.

---

# 13. API

Base:

`/api/v1`

## Health

`GET /api/v1/health`

200:

```json
{
  "status": "ok"
}
```

## Recommendation

`POST /api/v1/recommendations`

Request:

```json
{
  "city": "Астана",
  "event_date": "2026-10-15",
  "event_format": "свадьба",
  "category": "Ведущий",
  "budget_kzt": 1000000,
  "duration_hours": 6,
  "language": "казахский"
}
```

`duration_hours` и `language` optional.

Success:

```json
{
  "status": "matched",
  "count": 2,
  "message": "Найдено 2 подходящих подрядчика.",
  "recommendations": [
    {
      "id": "HK-00000",
      "anon_name": "Example",
      "category": "Ведущий",
      "city": "Астана",
      "price_from_kzt": 700000,
      "synthetic": false,
      "city_imputed": false,
      "price_imputed": false,
      "explanation": "..."
    }
  ]
}
```

Category absent:

```json
{
  "status": "category_not_found",
  "count": 0,
  "message": "В Астане нет подрядчиков категории «Флорист».",
  "recommendations": []
}
```

No eligible candidates:

```json
{
  "status": "no_eligible_candidates",
  "count": 0,
  "message": "Подрядчики этой категории есть, но ни один не прошёл условия заказа.",
  "reasons": {
    "busy": 2,
    "over_budget": 1,
    "wrong_format": 1,
    "duration_too_long": 0,
    "language_mismatch": 0
  },
  "recommendations": []
}
```

Validation failure:

HTTP 422

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Некорректные параметры запроса.",
    "details": {}
  }
}
```

---

# 14. Web UI

UI intentionally simple.

Основная страница содержит форму:

* город;
* дата;
* тип мероприятия;
* категория;
* бюджет;
* длительность;
* язык.

После submit отображаются максимум три карточки.

Карточка:

```text
NAME
CATEGORY · CITY

от XXX XXX ₸

WHY THIS MATCH
1–2 предложения

Synthetic / imputed indicators when applicable
```

Для `< 3` результатов UI явно объясняет, почему результатов меньше.

Для zero results UI показывает соответствующее состояние, а не пустой контейнер.

---

# 15. Project Structure

```text
/
├── CONTRACT.md
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── run.py
│
├── app/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── models/
│   ├── repositories/
│   ├── services/
│   │   ├── recommendation.py
│   │   ├── ranking.py
│   │   ├── evidence.py
│   │   └── explanation.py
│   │
│   ├── ai/
│   │   ├── client.py
│   │   └── prompts.py
│   │
│   ├── api/
│   │   ├── routes.py
│   │   └── errors.py
│   │
│   ├── web/
│   │   └── routes.py
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   └── components/
│   │
│   └── static/
│       ├── css/
│       └── js/
│
├── data/
│   └── hackathon_dataset.csv
│
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── e2e/
```

---

# 16. Ownership

## backend/ksusha

Owns:

```text
app/models/**
app/repositories/**
app/services/**
app/ai/**
app/api/**
backend unit tests
```

## frontend/denis

Owns:

```text
app/web/**
app/templates/**
app/static/**
frontend tests
```

## feature/jonas

Owns:

```text
CONTRACT.md
integration tests
E2E tests
regression tests
cross-branch integration
README verification
```

---

# 17. Agent Orchestration

Все три lead agents работают как:

**Astra Sol**

Sub-agents:

**Luna 5.4 Medium**

Для substantial task Astra обязан:

1. проверить доступные skills;
2. использовать подходящие skills;
3. разбить задачу на независимые исследования;
4. делегировать узкие задачи Luna;
5. выполнять независимые исследования параллельно;
6. сравнить результаты;
7. самостоятельно принять архитектурное решение;
8. реализовать решение;
9. отправить реализацию свежим Luna на review;
10. выполнить тесты;
11. исправить подтверждённые проблемы;
12. повторить verification.

Luna используется для:

* repository reconnaissance;
* requirement extraction;
* dataset analysis;
* edge-case discovery;
* focused implementation research;
* test generation;
* code review;
* contract comparison;
* adversarial QA;
* regression analysis.

Astra отвечает за:

* architecture;
* trade-offs;
* final decisions;
* implementation strategy;
* cross-cutting decisions;
* final verification.

---

# 18. Required Demo Scenarios

Минимум три live-запроса.

## Dense Category

Использовать плотную категорию, где ranking действительно выбирает между несколькими кандидатами.

Из кейса:

* Ведущий — 15;
* Фотограф — 12;
* Банкетный зал — 8.

## Rare Category

Использовать редкую категорию.

Из кейса:

* Флорист;
* Декоратор;
* Подарки и сувениры;
* Ведущий церемонии;
* Фото и видеобудки;
* Отель;
* Инструменталист.

По 3 профиля.

## Empty Result

Запрос, где система возвращает zero results и объясняет причину.

## Date Difference

Дополнительно обязательно продемонстрировать один и тот же запрос на две разные даты.

Результаты должны различаться из-за availability.

Объяснение/состояние должно позволять понять влияние занятости.

---

# 19. Performance

Целевой response time:

`<= 10 seconds`

Dataset маленький.

Не требуется преждевременная сложная инфраструктура.

Не добавлять без доказанной необходимости:

* Redis;
* Celery;
* microservices;
* vector database;
* Kubernetes.

---

# 20. Testing

Обязательные группы:

## Unit

* input validation;
* city filtering;
* category filtering;
* busy date filtering;
* budget filtering;
* event format filtering;
* language filtering;
* duration filtering;
* deterministic ranking;
* evidence building;
* deterministic explanation fallback.

## Integration

* Flask → recommendation service;
* recommendation service → dataset;
* API request → JSON result;
* Web form → recommendation;
* AI success;
* AI failure → fallback.

## Regression

Каждый найденный integration bug получает regression test.

## Determinism

Один запрос выполнить несколько раз.

IDs и порядок должны совпадать.

## Date Sensitivity

Одинаковые параметры с разными датами должны корректно учитывать `busy_dates`.

---

# 21. Definition of Done

Проект готов только если:

* live application запускается;
* dataset загружается;
* запрос валидируется;
* занятые кандидаты исключаются;
* budget constraint работает;
* event format работает;
* optional language работает;
* optional duration работает;
* возвращается максимум 3 карточки;
* порядок deterministic;
* объяснения конкретны;
* explanations различимы;
* AI не может обойти hard constraints;
* AI failure имеет fallback;
* три zero/matched состояния различимы;
* synthetic profiles обозначены;
* ответ укладывается в разумное время;
* unit tests проходят;
* integration tests проходят;
* required demo scenarios воспроизводятся;
* README позволяет другому человеку запустить проект;
* команда может объяснить pipeline жюри.

---

# 22. Core Principle

```text
FILTER WITH CODE.
RANK DETERMINISTICALLY.
EXPLAIN WITH EVIDENCE.
USE AI WHERE AI ADDS VALUE.
NEVER LET AI OVERRIDE FACTS.
```

---

# 23. Backend product extensions

These additive extensions preserve the integrated recommendation pipeline and the
legacy response schema. Sections below refine the default Russian explanation rule
only when the caller explicitly selects another product locale.

## 23.1 Locale and contractor communication language

Recommendation payloads may contain `locale`: `ru` (default), `kk`, or `en`.
It controls server-authored messages and explanation framing only. Catalog values
and quoted original description evidence remain unchanged; quotes are labelled as
original text in kk/en. No unverified translation of evidence is performed.

`communication_language` is an optional alias of existing `language`. Both express
the required contractor language in catalog vocabulary. If both keys are supplied,
their trimmed values must agree (including null), otherwise HTTP 422. Locale is
never inferred from contractor language, nor is contractor language inferred from
locale. Locale is excluded from the ranking request and from AI evidence.

Default ru preserves existing messages, availability diagnostics, filtering,
ranking, order, and response fields. Unsupported locales produce HTTP 422.
Machine status/error/reason codes are not translated. Backend locale support does
not imply translation of the existing HTML templates.

## 23.2 Recommendation export

`POST /api/v1/recommendations/export` accepts exactly one of:

```json
{"format":"json","request":{"city":"Астана","event_date":"2026-10-15","event_format":"свадьба","category":"Ведущий","budget_kzt":1000000,"locale":"ru"}}
```

```json
{"format":"csv","export_token":"opaque-token-from-response-header"}
```

`format` is required and is `csv` or `json`. Request mode invokes the SAME
RecommendationService once and exports the result generated now; it is not a
promise to reproduce an earlier AI explanation. Token mode exports exactly the
previous snapshot without rerunning the service or AI, including its timestamp.

To capture a snapshot, normal `POST /api/v1/recommendations` may carry
`X-Enable-Export: true`. The response body stays unchanged; the response header
`X-Recommendation-Export-Token` carries an opaque bearer capability. Tokens expire
after 15 minutes, are never placed in URLs, and are held in a bounded per-process
store of 128 entries (oldest entries may be evicted). Restart or another worker
may make a token unavailable; this foundation targets one application process.
Absent/expired tokens return HTTP 404 with `EXPORT_NOT_FOUND`. Invalid export
inputs return the existing HTTP 422 validation envelope. Internal export failures
return a generic HTTP 500 error without paths or exception details.

Downloads use fixed filenames `recommendations.csv` / `recommendations.json`,
`Content-Disposition: attachment`, `Cache-Control: no-store` and `nosniff`.

JSON export is UTF-8 with this versioned structure and field order:

```json
{
  "schema_version": "recommendation-export.v1",
  "generated_at": "2026-09-23T09:00:00.000000Z",
  "locale": "ru",
  "request": {
    "city": "Астана", "event_date": "2026-10-15", "event_format": "свадьба",
    "category": "Ведущий", "budget_kzt": 1000000,
    "duration_hours": null, "language": null
  },
  "result": {"status":"matched","count":1,"message":"...","recommendations":[]}
}
```

The result contains the actual recommendation response, including cards and
`reasons` when applicable; the sketch above abbreviates the cards. Request fields
are normalized and allowlisted; `communication_language` is exported as `language`.
Unknown input fields, configuration, credentials, full catalog data and internal
evidence objects are never serialized. Timestamp is generation completion time in UTC.

CSV uses UTF-8 BOM, standard CSV quoting, CRLF row endings and this fixed column order:

```text
schema_version,generated_at,locale,request_city,request_event_date,request_event_format,request_category,request_budget_kzt,request_duration_hours,request_language,status,count,message,reasons,id,anon_name,category,city,price_from_kzt,synthetic,city_imputed,price_imputed,explanation
```

Metadata repeats on each candidate row. Zero-result responses contain one metadata
row with empty contractor columns. Reasons are a JSON object with sorted keys;
booleans are `true`/`false`, null values are empty cells. All text cells are protected
against spreadsheet formula injection, including leading whitespace/control-character
bypasses. CSV safety escaping may prefix a text cell with an apostrophe; JSON retains
the original text. No generated export is written to a public filesystem path.

## 23.3 Catalog administration foundation

There is no public upload or HTTP admin endpoint. Local Flask CLI commands
`catalog-admin validate FILE` and `catalog-admin stage FILE` require explicit
runtime `CATALOG_ADMIN_ENABLED=1` and trusted OS access. This is an operator boundary,
not a replacement for authentication in any future HTTP administration interface.
Invoke with `flask --app app.admin:create_admin_app catalog-admin ...`; this dedicated
CLI factory never initializes or reseeds the active catalog and has no HTTP routes.

Both commands accept only regular non-symlink files, read at most 1 MiB plus one
limit-check byte, require strict UTF-8 or UTF-8 BOM, reject NUL and malformed CSV,
and reuse the existing complete catalog schema/model validation. Empty catalogs,
duplicates and invalid fields fail closed. Success output contains counts only;
failures do not echo content, paths, secrets or internal exceptions.

`validate` makes no catalog changes. `stage` creates a separate SQLite snapshot at
the operator-configured `CATALOG_STAGING_PATH` (default `instance/catalog-staged.sqlite3`)
by building a temporary database and atomically replacing the staging file. Active
CSV/SQLite paths cannot be selected as staging destinations. Failure preserves the
previous staging snapshot. No automatic activation, public upload, or change to
startup seeding is included; the running recommendation catalog remains unchanged.

## 23.4 Integrated Web locale, snapshots and comparison

The HTML form supports ru / kk / en and passes its locale to the same
RecommendationService used by the API. Product text and code-authored explanation
framing use that locale; source evidence and canonical catalog data values are not translated.
Localized display labels for categories, cities and form options do not change the
underlying query, result DTO or exported values.
The contractor communication language remains an independent filter.

Switching interface locale preserves the current draft form and the previously
generated result without another recommendation or AI call. Existing explanations
remain in their generation locale, identified by an explicit language label and
correct HTML lang; submitting a new search generates explanations in the new locale.
Draft edits do not retroactively change the saved result or its export. Result messages
must refer to the saved query rather than any unsent draft. An expired snapshot produces
a localized expiry notice, not a silent empty result. With JavaScript disabled only
the last server-submitted form values can be preserved during locale switching.

Web POST /recommendations/export/<csv|json> accepts export_id in the request body.
It uses the same versioned document and serializers as section 23.2, including UTC
generation timestamp, generation locale, normalized request and unchanged result.
This replaces the earlier frontend-only query/count/recommendations download shape;
the recommendation API response remains backward compatible. Downloads never rerun
recommendations. Both successful and zero-result snapshots can be exported.
Web snapshots also expire after 15 minutes, hold at most 128 entries and at most
256 KiB per entry. HTML containing tokens is no-store; tokens are never put in URLs.

Snapshot capture is optional: a size-limit or storage failure must not turn a valid
recommendation into an error. API capture failure omits the token and returns
X-Recommendation-Export-Status: unavailable without changing the successful body.
Web capture failure retains the result and shows a localized export-unavailable notice.
Internal failures use generic messages; exception content, paths and credentials must
not be rendered or logged by recommendation/export handlers.

Comparison appears only for 2–3 returned cards, in their existing order. It uses only
the current public card fields (ID, category, city, price from and synthetic/imputed
flags), does not infer missing attributes or announce a winner, and never replaces
the explanations. Mobile tables scroll within their own container.

The integrated UI uses a light-only theme, including under a dark system preference.
Responsive visual styling does not change recommendation semantics or fabricate demo results.
