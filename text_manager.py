"""Dynamic text management system with database overrides."""

# Default texts (fallback values)
DEFAULT_TEXTS = {
    "WELCOME": {
        "text": "Привет! 👋\n\nЭто бот для обмена кружочками.",
        "description": "Приветственное сообщение"
    },
    "UPLOAD_NEEDS_PROFILE": {
        "text": "Чтобы загружать кружочки, нужно сначала заполнить анкету автора.",
        "description": "Сообщение когда нет профиля"
    },
    "PROFILE_INTRO": {
        "text": "📋 Создай анкету автора, чтобы зарабатывать на своих кружочках.",
        "description": "Введение в создание профиля"
    },
    "PROFILE_PHOTO": {
        "text": "🖼 <b>Профиль автора</b>\n\nПришли фото для анкеты — его увидят все, кто листает анкеты.\nЛицо показывать необязательно.",
        "description": "Запрос фото для профиля"
    },
    "PROFILE_GENDER": {
        "text": "👤 Выбери пол для анкеты:",
        "description": "Запрос пола"
    },
    "PROFILE_NOT_PHOTO": {
        "text": "❌ Это не фото. Пришли фото для анкеты.",
        "description": "Ошибка - не фото"
    },
    "PROFILE_NO_USERNAME": {
        "text": "⚠️ У тебя нет username в Telegram. Без него покупатели не смогут написать тебе.\n\nУстанови username в настройках Telegram, потом нажми «Проверить».",
        "description": "Нет username"
    },
    "PROFILE_STILL_NO_USERNAME": {
        "text": "Всё ещё не вижу username. Установи его в настройках Telegram.",
        "description": "Username всё ещё нет"
    },
    "PROFILE_CONTACT_ASK": {
        "text": "💬 Хочешь продавать свой username?\n\nПокупатель сможет написать тебе напрямую.",
        "description": "Спросить про продажу контакта"
    },
}

# Runtime storage
_custom_texts = {}


async def load_from_db():
    """Load custom texts from database."""
    import db
    _custom_texts.clear()
    _custom_texts.update(await db.load_custom_texts())


def get(key: str) -> str:
    """Get text from custom or default."""
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
            "is_custom": key in _custom_texts,
        }
    # Add custom texts not in defaults
    for key in _custom_texts:
        if key not in result:
            result[key] = {
                "text": _custom_texts[key]["text"],
                "description": _custom_texts[key].get("description", ""),
                "is_custom": True,
            }
    return result
