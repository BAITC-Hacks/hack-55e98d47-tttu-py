"""Product text only. Catalog vocabulary and evidence are never translated here."""

SUPPORTED_LOCALES = ("ru", "kk", "en")

MESSAGES = {
    "ru": {
        "absent": "В городе «{city}» нет подрядчиков категории «{category}».",
        "rejected": "Подрядчики этой категории есть, но ни один не прошёл условия заказа.",
        "matched": "Найдено подходящих подрядчиков: {count}.",
        "busy": " На выбранную дату заняты {count} {label} этой категории; они исключены из подбора.",
        "few": " Показаны все подрядчики города и категории, прошедшие условия заказа; их меньше трёх.",
        "validation": "Некорректные параметры запроса.",
        "internal": "Внутренняя ошибка сервера.",
        "missing_export": "Результат экспорта не найден или срок хранения истёк.",
        "profile": "Профиль",
    },
    "kk": {
        "absent": "«{city}» қаласында «{category}» санатындағы мердігерлер жоқ.",
        "rejected": "Бұл санатта мердігерлер бар, бірақ ешқайсысы тапсырыс шарттарына сай келмейді.",
        "matched": "Сәйкес мердігерлер саны: {count}.",
        "busy": " Таңдалған күні осы санаттағы {count} мердігер бос емес; олар іріктеуден шығарылды.",
        "few": " Қала мен санат бойынша барлық шарттарға сай мердігерлер көрсетілді; олардың саны үштен аз.",
        "validation": "Сұрау параметрлері дұрыс емес.",
        "internal": "Сервердің ішкі қатесі.",
        "missing_export": "Экспорт нәтижесі табылмады немесе сақтау мерзімі аяқталды.",
        "profile": "Профиль",
    },
    "en": {
        "absent": "No contractors in category “{category}” were found in “{city}”.",
        "rejected": "Contractors in this category exist, but none meet the request constraints.",
        "matched": "Matching contractors found: {count}.",
        "busy": " On the selected date, {count} contractors in this category are busy and excluded.",
        "few": " All contractors in this city and category meeting the request are shown; fewer than three qualify.",
        "validation": "Invalid request parameters.",
        "internal": "Internal server error.",
        "missing_export": "Export result was not found or has expired.",
        "profile": "Profile",
    },
}

# Existing Russian validation text remains unchanged; translations use exact keys,
# not arbitrary machine translation of exceptions or catalog data.
ERROR_TEXT = {
    "Ожидается JSON-объект.": ("JSON нысаны қажет.", "A JSON object is required."),
    "Ожидается корректный JSON-объект.": (
        "Дұрыс JSON нысаны қажет.",
        "A valid JSON object is required.",
    ),
    "Ожидается непустая строка длиной до 120 символов.": (
        "120 таңбаға дейінгі бос емес жол қажет.",
        "A nonempty string of at most 120 characters is required.",
    ),
    "Ожидается существующая дата YYYY-MM-DD.": (
        "YYYY-MM-DD пішіміндегі жарамды күн қажет.",
        "A valid date in YYYY-MM-DD format is required.",
    ),
    "Ожидается целое число от 0 до 1000000000000000.": (
        "0 мен 1000000000000000 аралығындағы бүтін сан қажет.",
        "An integer between 0 and 1000000000000000 is required.",
    ),
    "Ожидается положительное конечное число часов.": (
        "Сағат саны оң және шекті болуы керек.",
        "A positive finite number of hours is required.",
    ),
    "Ожидается непустая строка языка или null.": (
        "Тіл атауы немесе null қажет.",
        "A nonempty language string or null is required.",
    ),
    "Запрос слишком большой.": ("Сұрау тым үлкен.", "Request is too large."),
    "Допустимые locale: ru, kk, en.": (
        "Рұқсат етілген locale: ru, kk, en.",
        "Supported locales: ru, kk, en.",
    ),
    "language и communication_language должны совпадать.": (
        "language және communication_language мәндері бірдей болуы керек.",
        "language and communication_language must agree.",
    ),
    "Формат экспорта должен быть csv или json.": (
        "Экспорт пішімі csv немесе json болуы керек.",
        "Export format must be csv or json.",
    ),
    "Передайте request или export_token, но не оба.": (
        "Тек request немесе export_token беріңіз.",
        "Supply either request or export_token, not both.",
    ),
    "Некорректный токен экспорта.": ("Экспорт токені дұрыс емес.", "Invalid export token."),
    "Неизвестные параметры экспорта.": (
        "Экспорт параметрлері белгісіз.",
        "Unknown export parameters.",
    ),
}


def text(key: str, locale: str = "ru", **values) -> str:
    return MESSAGES[locale][key].format(**values)


def locale_from_payload(payload: object, *, strict: bool = True) -> str:
    value = payload.get("locale", "ru") if isinstance(payload, dict) else "ru"
    if isinstance(value, str) and value in SUPPORTED_LOCALES:
        return value
    if strict:
        from app.models import ValidationError

        raise ValidationError({"locale": "Допустимые locale: ru, kk, en."})
    return "ru"


def error_details(details: dict[str, str], locale: str) -> dict[str, str]:
    if locale == "ru":
        return details
    index = 0 if locale == "kk" else 1
    return {
        key: ERROR_TEXT[value][index] if value in ERROR_TEXT else text("validation", locale)
        for key, value in details.items()
    }


def localized_explanation(evidence, source_text: str | None, locale: str, money) -> str:
    if locale == "en":
        result = (
            f"Price from {money(evidence.price_from_kzt)} ₸ against a budget of {money(evidence.budget_kzt)} ₸; "
            f"category “{evidence.requested_category}”, city {evidence.city}, "
            f"format “{evidence.event_format_match}”, available on {evidence.event_date}"
        )
        if evidence.language_match:
            result += f"; supported communication language: {evidence.language_match}"
        if evidence.requested_duration_hours is not None:
            hours = evidence.requested_duration_hours
            result += (
                f"; for a {hours}-hour request, this service is not tied to time on site"
                if evidence.max_hours is None
                else f"; requested duration {hours} hours is within the {evidence.max_hours}-hour limit"
            )
        result += "."
        if source_text:
            result += f" Original description (untranslated): “{source_text}”."
        return result
    result = (
        f"Бағасы {money(evidence.price_from_kzt)} ₸ бастап, бюджет {money(evidence.budget_kzt)} ₸; "
        f"санат «{evidence.requested_category}», қала — {evidence.city}, "
        f"формат — «{evidence.event_format_match}», {evidence.event_date} күні бос"
    )
    if evidence.language_match:
        result += f"; қолдау көрсетілетін қарым-қатынас тілі — {evidence.language_match}"
    if evidence.requested_duration_hours is not None:
        hours = str(evidence.requested_duration_hours).replace(".", ",")
        result += (
            f"; {hours} сағаттық сұрау үшін қызмет алаңда болу ұзақтығына байланысты емес"
            if evidence.max_hours is None
            else f"; сұралған {hours} сағат ұзақтық {evidence.max_hours} сағат шегінен аспайды"
        )
    result += "."
    if source_text:
        result += f" Сипаттаманың түпнұсқасы (аударылмаған): «{source_text}»."
    return result
