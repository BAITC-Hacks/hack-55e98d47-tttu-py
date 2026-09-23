# Event contractor matching

Backend ветки `backend/ksusha`: Flask, Python 3.13, SQLite и evidence-based рекомендации.
Единственный API/product contract — [CONTRACT.md](CONTRACT.md).

## Запуск

Из корня репозитория, с установленным Python 3.13:

```powershell
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe run.py
```

На macOS/Linux замените `py -3.13` на `python3.13`, а `.venv/Scripts/python.exe` — на `.venv/bin/python`.
Backend слушает `127.0.0.1:5000`; health-check: `GET /api/v1/health`.
JSON-рекомендации: `POST /api/v1/recommendations`, DTO и примеры — в разделе 13 контракта.
Главная страница `/` — это серверная HTML-форма: она использует тот же
`RecommendationService`, что и JSON API, и показывает до трёх карточек с объяснениями,
synthetic/imputed-индикаторами и отдельными состояниями «категория не найдена» и
«нет подходящих вариантов».

CSV `data/hackathon_dataset.csv` — неизменённая копия исходных 66 профилей.
При старте файл полностью валидируется и атомарно загружается в локальную SQLite
`instance/catalog.sqlite3`; невалидный или отсутствующий каталог останавливает запуск.
Импорт сохраняет исходные описания, multi-category, 13 synthetic-профилей и все imputed-флаги.
Отдельные миграции не нужны: две таблицы `contractors` / `categories` создаются при первом запуске.
SQLite — восстанавливаемый snapshot CSV, не место для ручного редактирования каталога.

## Runtime configuration

`.env.example` перечисляет переменные; `.env` не загружается автоматически.
Переменные нужно передать процессу через shell/secret manager. Реальные ключи не добавляйте в файлы Git.

| Переменная | Назначение |
| --- | --- |
| `DATASET_PATH` | Путь к CSV; по умолчанию `data/hackathon_dataset.csv` относительно корня проекта |
| `DATABASE_PATH` | Путь к SQLite; по умолчанию `instance/catalog.sqlite3` |
| `LLM_API_KEY` | Runtime credential провайдера; необязательно |
| `LLM_BASE_URL` | HTTPS API base URL провайдера, включая version prefix, без `/chat/completions` |
| `LLM_MODEL` | Идентификатор модели у провайдера |

AI включается только при наличии всех трёх `LLM_*` значений. Используется совместимый с
chat-completions JSON endpoint с поддержкой `response_format=json_object` и `temperature=0`.
Если провайдер не поддерживает параметры, отвечает некорректно или недоступен, работает fallback.
Файл `API key.txt` исключён из текущего Git index и игнорируется; приложение его не читает.
Для локального запуска ключ можно прочитать из своего secret-хранилища в `LLM_API_KEY` без вывода значения.

## Pipeline и AI

Общий сервис доступен как `app.extensions["recommendation_service"].recommend(payload)`.
Web-интеграция передаёт сюда словарь с JSON-типами полей после разбора HTML-формы и
обрабатывает `ValidationError.details`; отдельный алгоритм рекомендаций не нужен.
Каталог для вариантов формы доступен через `app.extensions["catalog_repository"].all()`.
`create_app(config, repository=..., ai_client=...)` позволяет изолированно тестировать оба транспорта.

Все hard constraints проверяет Python. Диагностика считает каждое нарушенное условие,
поэтому один профиль может учитываться в нескольких причинах отказа.
После фильтров deterministic ranking использует bounded lexical semantic signal описания,
бюджет и optional-параметры; точная формула находится в `app/services/ranking.py`.
Последний tie-breaker — `id ASC`. Внешняя модель не участвует в score или сортировке.

AI получает evidence только для финальных ≤3 кандидатов одним batch-запросом.
Он выбирает подходящий `reason_id` из конкретных фрагментов описания каждого кандидата.
Python проверяет принадлежность каждого ID и собирает 1–2 русских предложения из фактов
и выбранной цитаты. Свободные неподтверждённые утверждения от модели не принимаются.
Это намеренно ограниченная AI-часть: семантический выбор evidence, а не свободная генерация прозы.
При отсутствии подходящего содержательного фрагмента используются точные структурированные факты.
Цена всегда указана «от»; `max_hours=null` не интерпретируется как гарантия безлимитной работы.
Один вызов ограничен общим deadline 3 секунды, без повторов; любой сбой ведёт к deterministic fallback.

## Проверка и live demo

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m black --check app tests scripts run.py
```

Unit tests проверяют загрузку, валидацию, каждый фильтр, ranking, evidence и AI transport.
Backend integration tests проверяют Flask → сервис → реальный CSV/SQLite, JSON DTO и AI success/failure.
Ни один тест не отправляет реальный ключ или сетевой запрос внешнему AI-провайдеру.

При работающем `run.py` выполните в другом терминале:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/demo.py
```

Скрипт выполняет пять настоящих HTTP-запросов и проверяет результат: плотная категория
«Ведущий», редкая «Флорист», все отклонены по бюджету, изменение только даты
с 2026-10-15 на 2026-10-16, отсутствие категории в городе.
Он печатает конкретные карточки, объяснения, причины отказа и время ответа.

HTML-форма, UI badges и три пользовательских исхода покрыты frontend и integration
тестами; оба транспорта используют один recommendation pipeline.

## Экспорт и locale

Расширения описаны в разделе 23 [CONTRACT.md](CONTRACT.md). Старый JSON response
не меняет структуру. Payload может содержать `locale`: `ru` (default), `kk`, `en`.
Это язык текстов продукта; `language` или его alias `communication_language` остаётся
требованием к языку подрядчика. При одновременной передаче alias и `language` значения
должны совпадать. Исходные описания и значения каталога не переводятся.

Для экспорта нового результата отправьте `POST /api/v1/recommendations/export`
с `{"format":"csv","request":{...параметры рекомендации...}}`; для JSON замените
`csv` на `json`. Выполняется ровно один вызов общего RecommendationService.

Чтобы экспортировать именно показанный API-результат, передайте `X-Enable-Export: true`
обычному `POST /api/v1/recommendations`. Сохраните ответный заголовок
`X-Recommendation-Export-Token`, затем отправьте его в JSON body экспортного запроса:
`{"format":"json","export_token":"..."}`. Этот путь не пересчитывает рекомендации
и не вызывает AI; сохраняются объяснения, locale и timestamp исходного результата.
Frontend может подключить этот API без второго алгоритма рекомендаций.

Snapshot хранится 15 минут в памяти одного процесса, максимум 128 записей размером
до 256 KiB каждая. Старые записи могут вытесняться; перезапуск очищает snapshots.
Для нескольких workers потребуется общее хранилище либо привязка запросов к одному
worker. Токен является bearer capability: не помещайте его в URL или журналы.

CSV содержит UTF-8 BOM, фиксированные колонки, корректное quoting и защиту от
формул Excel. У потенциально опасных текстовых ячеек добавляется апостроф; JSON
сохраняет исходный текст. Даже zero-result экспорт содержит параметры и состояние.
Файлы формируются в памяти, с фиксированными именами, без сохранения на диск.

## Локальная административная подготовка каталога

Публичного upload endpoint нет. Используйте отдельную CLI-фабрику, чтобы не запускать
инициализацию рабочего каталога:

```powershell
$env:CATALOG_ADMIN_ENABLED = "1"
.venv/Scripts/python.exe -m flask --app app.admin:create_admin_app catalog-admin validate data/hackathon_dataset.csv
.venv/Scripts/python.exe -m flask --app app.admin:create_admin_app catalog-admin stage data/hackathon_dataset.csv
```

Операции доступны только доверенному локальному оператору с явным enablement.
Поддерживаются UTF-8 / UTF-8 BOM, максимум 1 MiB; схема проверяется тем же parser,
что при запуске backend. Ошибка оставляет прежнюю staging-базу без изменений.
`validate` ничего не импортирует. `stage` атомарно создаёт отдельную SQLite-базу
`instance/catalog-staged.sqlite3`; путь задаётся через `CATALOG_STAGING_PATH` и
не может совпадать с активными CSV/SQLite. Активный каталог не переключается.
Новая функциональность не меняет существующий startup seed из CSV.
