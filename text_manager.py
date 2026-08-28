"""Dynamic text management system with database overrides."""

# Default texts organized by category
DEFAULT_TEXTS = {
    # === Система ===
    "WELCOME": {
        "text": "Привет! 👋\n\nЭто бот для обмена кружочками.",
        "description": "Приветственное сообщение",
        "category": "Система"
    },
    "ACCEPTED": {
        "text": "Готово. Приятного просмотра 🙂",
        "description": "Подтверждение согласия",
        "category": "Система"
    },
    "BANNED": {
        "text": "Доступ закрыт.",
        "description": "Сообщение для забаненных",
        "category": "Система"
    },
    "MAINTENANCE": {
        "text": "🔧 Бот на техработах. Загляни чуть позже.",
        "description": "Режим обслуживания",
        "category": "Система"
    },

    # === Профиль автора ===
    "PROFILE_INTRO": {
        "text": "📋 Создай анкету автора, чтобы зарабатывать на своих кружочках.",
        "description": "Введение в профиль",
        "category": "Профиль"
    },
    "PROFILE_PHOTO": {
        "text": "🖼 <b>Профиль автора</b>\n\nПришли фото для анкеты — его увидят все, кто листает кружочки. Чем лучше смотрится, тем больше шансов на покупку.",
        "description": "Запрос фото профиля",
        "category": "Профиль"
    },
    "PROFILE_GENDER": {
        "text": "Кто ты?",
        "description": "Выбор пола",
        "category": "Профиль"
    },
    "PROFILE_CONTACT_ASK": {
        "text": "Продавать личку? Её купят — откроется username, пишут напрямую.",
        "description": "Вопрос о продаже контакта",
        "category": "Профиль"
    },
    "PROFILE_NO_USERNAME": {
        "text": "У тебя нет username — личку продать не получится. Заведи его в настройках Telegram и возвращайся.",
        "description": "Нет username",
        "category": "Профиль"
    },
    "PROFILE_STILL_NO_USERNAME": {
        "text": "Username всё ещё нет. Заведи его и возвращайся.",
        "description": "Повтор - нет username",
        "category": "Профиль"
    },
    "PROFILE_SENT": {
        "text": "📬 Анкета отправлена на проверку. Как одобрят — придёт уведомление.",
        "description": "Анкета на модерацию",
        "category": "Профиль"
    },
    "PROFILE_NOT_PHOTO": {
        "text": "Нужно именно фото.",
        "description": "Ошибка типа файла",
        "category": "Профиль"
    },
    "PROFILE_APPROVED": {
        "text": "🟢 Твоя анкета одобрена — её уже показывают.",
        "description": "Анкета одобрена",
        "category": "Профиль"
    },
    "PROFILE_EMPTY_WAIT": {
        "text": "Анкет пока нет — все просмотрены. Загляни позже.",
        "description": "Нет анкет для просмотра",
        "category": "Профиль"
    },

    # === Загрузка кружков ===
    "UPLOAD_NEEDS_PROFILE": {
        "text": "🎬 Сначала анкета.\n\nКружочки показываются вместе с анкетой автора: зритель может её открыть и купить доступ ко всем твоим кружочкам. Без анкеты продавать нечего.",
        "description": "Нужна анкета для загрузки",
        "category": "Загрузка"
    },
    "NOT_A_CIRCLE": {
        "text": "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение.",
        "description": "Неверный формат",
        "category": "Загрузка"
    },
    "DUPLICATE": {
        "text": "Такой кружок уже есть в базе.",
        "description": "Дубликат кружка",
        "category": "Загрузка"
    },
    "TOO_MANY_PENDING": {
        "text": "У тебя уже несколько кружков на проверке. Дождись решения.",
        "description": "Слишком много на модерации",
        "category": "Загрузка"
    },
    "REJECTED": {
        "text": "🔴 Кружок отклонён модератором.",
        "description": "Кружок отклонён",
        "category": "Загрузка"
    },

    # === Просмотр ===
    "EMPTY": {
        "text": "Свежих кружочков этого типа пока нет — ты посмотрел все.\nЗагляни позже или смени тип.",
        "description": "Нет новых кружков",
        "category": "Просмотр"
    },
    "ARCHIVE_NOTE": {
        "text": "Это кружок из архива бота — он без автора, анкеты у него нет.",
        "description": "Архивный кружок",
        "category": "Просмотр"
    },

    # === Жалобы ===
    "REPORT_SENT": {
        "text": "Жалоба отправлена модераторам.",
        "description": "Жалоба отправлена",
        "category": "Жалобы"
    },
    "REPORT_DOUBLE": {
        "text": "Ты уже жаловался на этот кружок.",
        "description": "Повторная жалоба на кружок",
        "category": "Жалобы"
    },
    "REPORT_DOUBLE_PROFILE": {
        "text": "Ты уже жаловался на эту анкету.",
        "description": "Повторная жалоба на анкету",
        "category": "Жалобы"
    },
    "CIRCLE_REMOVED": {
        "text": "🔴 Твой кружок удалён по жалобам.",
        "description": "Кружок удалён",
        "category": "Жалобы"
    },

    # === Покупки ===
    "CONTACT_NOT_FOR_SALE": {
        "text": "Автор не продаёт личку.",
        "description": "Контакт не продаётся",
        "category": "Покупки"
    },
    "NOTHING_TO_SELL": {
        "text": "У автора пока нет кружочков — покупать нечего.",
        "description": "Нет контента",
        "category": "Покупки"
    },
    "ALREADY_BOUGHT": {
        "text": "Уже куплено.",
        "description": "Уже куплен доступ",
        "category": "Покупки"
    },

    # === Выплаты ===
    "PAYOUT_ASK_DETAILS": {
        "text": "💸 <b>Вывод средств</b>\n\nПришли реквизиты для перевода и сумму.\n\nПример:\n<code>СБП 79991234567 500₽</code>",
        "description": "Запрос реквизитов",
        "category": "Выплаты"
    },

    # === Рефералы ===
    "TRAFFER_UNKNOWN": {
        "text": "Команда не подходит — проверь её у того, кто выдал ссылку.",
        "description": "Неизвестная команда",
        "category": "Рефералы"
    },

    # === Подписка ===
    "SUBSCRIBE_MISSING": {
        "text": "Подписки не вижу. Подпишись на канал и нажми ещё раз.",
        "description": "Нет подписки",
        "category": "Подписка"
    },
}

# Cache for custom texts loaded from database
_custom_texts = {}


async def load_from_db():
    """Load custom texts from database."""
    import db

    global _custom_texts
    _custom_texts = {}

    async with db.conn().execute("SELECT key, text, description FROM custom_texts") as cur:
        async for row in cur:
            _custom_texts[row["key"]] = {
                "text": row["text"],
                "description": row["description"] or "",
            }


def get(key: str) -> str:
    """Get text by key, returning custom version if available."""
    if key in _custom_texts:
        return _custom_texts[key]["text"]
    if key in DEFAULT_TEXTS:
        return DEFAULT_TEXTS[key]["text"]
    return f"[Текст {key} не найден]"


def list_all_texts() -> dict:
    """List all available texts with their current values."""
    result = {}
    for key, data in DEFAULT_TEXTS.items():
        custom = _custom_texts.get(key)
        result[key] = {
            "text": custom["text"] if custom else data["text"],
            "description": custom.get("description") if custom else data["description"],
            "category": data.get("category", "Разное"),
            "is_custom": key in _custom_texts,
        }
    # Add custom texts not in defaults
    for key in _custom_texts:
        if key not in result:
            result[key] = {
                "text": _custom_texts[key]["text"],
                "description": _custom_texts[key].get("description", ""),
                "category": "Разное",
                "is_custom": True,
            }
    return result
