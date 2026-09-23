# Отчёт по frontend — Event Match

## Базовая информация

- Ветка: `frontend/denis`
- Интеграционная база: `origin/main`, commit `ebfd9b0`
- Стек: Flask, Jinja2, Bootstrap 5, минимальный JavaScript
- Источник продуктового контракта: `CONTRACT.md`

Перед улучшениями ветка была синхронизирована с последним `origin/main`. Незакоммиченный отчёт был сохранён через `git stash` и восстановлен после merge. Полный baseline suite прошёл без ошибок: `159 passed`.

## Реализованный recommendation flow

Главная страница содержит серверную форму со следующими параметрами:

- город;
- дата события;
- формат события;
- категория подрядчика;
- бюджет в KZT;
- необязательная продолжительность;
- необязательный язык общения подрядчика.

Web route использует тот же `RecommendationService`, что и JSON API. Во frontend отсутствуют собственные фильтрация, ranking, SQL и AI-вызовы.

Поддерживаются все состояния:

- initial;
- `MATCHED` с 1–3 рекомендациями;
- `CATEGORY_NOT_FOUND`;
- `NO_ELIGIBLE_CANDIDATES` с агрегированными причинами;
- validation error;
- backend error;
- пустой или неизвестный ответ сервиса.

Карточки показывают имя, категорию, город, цену «от», ID профиля, объяснение, synthetic и imputed-признаки. Объяснение остаётся визуально главным содержательным блоком.

## RU / ҚАЗ / EN локализация

Добавлены три интерфейсные локали:

- русский — `ru`;
- қазақша — `kk`;
- English — `en`.

Переключатель локали расположен в шапке, доступен с клавиатуры и обозначает текущую локаль через `aria-current`.

Локализованы:

- HTML title и meta description;
- `html lang`;
- skip link и подпись переключателя;
- заголовки и пояснения формы;
- labels, placeholders, help и validation messages;
- кнопка отправки;
- initial/matched/zero/error states;
- причины исключения кандидатов;
- подписи recommendation card;
- synthetic/imputed labels;
- цена и предупреждение о возможном изменении стоимости;
- export и comparison UI;
- export error state.

Canonical values формы не переводятся перед отправкой backend. В интерфейсе переводится только видимый label.

### Locale и язык общения разделены

`locale` управляет только языком интерфейса.

`language` остаётся отдельным фильтром языка общения подрядчика. Например, английский интерфейс может отправить `language=русский` или `language=казахский`.

Переключение локали:

- сохраняет заполненную форму;
- сохраняет выбранный фильтр языка общения;
- сохраняет текущее состояние результата;
- перерисовывает сохранённый server snapshot;
- не вызывает recommendation service повторно.

Русские recommendation explanations не объявляются переведёнными. В интерфейсах ҚАЗ/EN они показываются как оригинальный текст с `lang="ru"` и явной локализованной подписью.

## Recommendation export

После успешного `MATCHED` доступны:

- Download CSV;
- Download JSON.

Frontend не создаёт второй результат в JavaScript и не вызывает recommendation service повторно при скачивании.

После подбора сервер сохраняет bounded TTL snapshot:

- точный canonical query;
- точные 1–3 карточки, показанные пользователю;
- непрозрачный случайный `export_id`;
- TTL 15 минут;
- максимальная вместимость 128 snapshots.

Экспортные маршруты принимают только `export_id`, получают snapshot на сервере и возвращают attachment с `Cache-Control: no-store` и `X-Content-Type-Options: nosniff`.

CSV:

- UTF-8 с BOM;
- содержит query-поля и recommendation-поля;
- защищает ячейки от spreadsheet formula injection.

JSON:

- UTF-8;
- содержит `query`, `count` и `recommendations`;
- сохраняет Unicode без ASCII escaping.

Неизвестный или истёкший snapshot возвращает локализованную непустую страницу `404`.

## Сравнение подрядчиков

Для двух или трёх рекомендаций после карточек показывается отдельная comparison table.

Сравниваются только факты текущего recommendation DTO:

- ID профиля;
- категория;
- город;
- цена от;
- synthetic/imputed-признаки.

Сравнение:

- сохраняет backend-порядок;
- не выполняет ranking;
- не объявляет победителя;
- не скрывает и не заменяет исходные объяснения;
- не извлекает факты из свободного текста;
- отсутствует для 0–1 результата.

Таблица имеет `caption`, корректные `scope` у заголовков и доступную с клавиатуры responsive scroll region. На узких экранах она прокручивается внутри контейнера, не создавая overflow всей страницы.

## Доступность и mobile

Сохранены и расширены:

- видимые labels;
- `aria-describedby` для ошибок и подсказок;
- управление `aria-invalid`;
- фокус на первом невалидном поле;
- фокус на результате после POST;
- `aria-live` для результата;
- текстовые обозначения состояний и data markers;
- доступный locale switcher;
- доступные названия export controls;
- семантическая comparison table;
- `prefers-reduced-motion`;
- поддержка ширины от 320 px.

## Тестирование

Добавлены frontend-тесты для:

- RU, ҚАЗ и EN;
- неизвестной locale и fallback на RU;
- `html lang`;
- переключения locale без повторного вызова recommendation service;
- независимости locale от contractor-language filter;
- локализованных zero-result причин;
- маркировки оригинального русского explanation;
- видимости export controls только при `MATCHED`;
- точного JSON/CSV snapshot export;
- сохранения query и порядка кандидатов;
- неизвестного и истёкшего export token;
- comparison для двух и трёх кандидатов;
- отсутствия comparison при 0–1 результате;
- no-eligible без diagnostics;
- unknown backend status;
- accessibility-critical labels и table semantics;
- всех существовавших empty/error states.

Финальные проверки:

```text
ruff: passed
frontend + web integration: 29 passed
complete suite: 177 passed
```

Также выполнен визуальный smoke-test интегрированного приложения с реальным dataset: EN matched flow вернул три карточки, export и comparison; переключение на ҚАЗ сохранило результат и фильтр языка общения.

## Независимые ревью

До реализации выполнены отдельные исследования:

- localization UX;
- export/backend integration;
- comparison + accessibility/mobile;
- test/state matrix.

После реализации свежие Luna reviewers проверили:

- localization consistency;
- accessibility;
- mobile/responsive behavior;
- integration assumptions;
- missing UI states.

Подтверждённый дефект locale switch, повторно вызывавший service, исправлен и повторно проверен reviewer-ом.

## Изменённые frontend-файлы

```text
app/web/routes.py
app/web/i18n.py
app/web/exports.py
app/templates/base.html
app/templates/index.html
app/templates/export_error.html
app/static/css/app.css
tests/frontend/test_web_routes.py
FRONTEND_REPORT.md
```

## Оставшиеся ограничения

1. Recommendation DTO не содержит полного списка языков подрядчика, `max_hours` и структурированного profile/evidence feature. Поэтому comparison честно ограничен фактами текущего контракта. Для расширения требуется сначала изменить `CONTRACT.md` и backend DTO.

2. Export snapshot store находится в памяти одного Flask-процесса. Это подходит для текущего demo/runtime, но при multi-worker или multi-replica deployment потребуется общий TTL store либо sticky routing. После перезапуска процесса старые export links ожидаемо становятся недействительными.
