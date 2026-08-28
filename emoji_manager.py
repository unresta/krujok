"""Dynamic emoji management system with database overrides."""

import emoji as emoji_module

# Default emoji IDs (fallback values)
DEFAULT_EMOJI = {
    "UPLOAD": {"emoji_id": "6028115612163641653", "fallback": "⬆️", "description": "Кнопка загрузки"},
    "WATCH": {"emoji_id": "5850346984501680054", "fallback": "👀", "description": "Кнопка смотреть"},
    "PROFILE": {"emoji_id": "6035084557378654059", "fallback": "👤", "description": "Кнопка профиль"},
    "REF": {"emoji_id": "6033108709213736873", "fallback": "👥", "description": "Кнопка реферал"},
    "SHOP": {"emoji_id": "6028338546736107668", "fallback": "🛒", "description": "Кнопка магазин"},
    "RULES": {"emoji_id": "5334544901428229844", "fallback": "📋", "description": "Кнопка правила"},
    "FEED": {"emoji_id": "5850309953293653168", "fallback": "📺", "description": "Кнопка лента"},
    "LIKE": {"emoji_id": "5307804022726467465", "fallback": "👍", "description": "Кнопка лайк"},
    "DISLIKE": {"emoji_id": "5346076867143147808", "fallback": "👎", "description": "Кнопка дизлайк"},
    "AUTHOR_PROFILE": {"emoji_id": "6032994772321309200", "fallback": "👤", "description": "Профиль автора"},
    "NEXT_CIRCLE": {"emoji_id": "5850346984501680054", "fallback": "▶️", "description": "Следующий кружок"},
    "REPORT": {"emoji_id": "5834895792409677476", "fallback": "⚠️", "description": "Пожаловаться"},
    "MY_CIRCLES": {"emoji_id": "5798430918771220206", "fallback": "⚪", "description": "Мои кружки"},
    "PROFILE_HEADER": {"emoji_id": "6032693626394382504", "fallback": "👤", "description": "Заголовок профиля"},
    "UPLOADED_COUNT": {"emoji_id": "5294299296928117557", "fallback": "📤", "description": "Загружено кружков"},
    "RATINGS_ICON": {"emoji_id": "5350790271627968474", "fallback": "⭐", "description": "Иконка оценок"},
    "LIKE_EMOJI": {"emoji_id": "5307804022726467465", "fallback": "👍", "description": "Эмодзи лайк"},
    "DISLIKE_EMOJI": {"emoji_id": "5346076867143147808", "fallback": "👎", "description": "Эмодзи дизлайк"},
    "VIEWS_COUNT": {"emoji_id": "6030506650522096180", "fallback": "👀", "description": "Просмотрено"},
    "BALANCE_ICON": {"emoji_id": "5404359483155570991", "fallback": "💰", "description": "Баланс"},
    "COIN_EMOJI": {"emoji_id": "5431736165374011268", "fallback": "🪙", "description": "Монета"},
    "EARNINGS_ICON": {"emoji_id": "5904462880941545555", "fallback": "💵", "description": "Заработок"},
    "ABOUT": {"emoji_id": "5787709748230672441", "fallback": "📝", "description": "Описание"},
    "CIRCLE_COUNT": {"emoji_id": "5294299296928117557", "fallback": "🎥", "description": "Количество кружков"},
    "PRICE": {"emoji_id": "5404359483155570991", "fallback": "💰", "description": "Цена"},
    "SOLD": {"emoji_id": "6028338546736107668", "fallback": "🛒", "description": "Продано"},
    "INFO": {"emoji_id": "5787544344245477551", "fallback": "ℹ️", "description": "Информация"},
    "FILM": {"emoji_id": "5294299296928117557", "fallback": "🎬", "description": "Фильм"},
}

# Runtime storage
_custom_emoji = {}
_emoji_map = {}


async def load_from_db():
    """Load custom emoji from database."""
    import db
    _custom_emoji.clear()
    _custom_emoji.update(await db.load_custom_emoji())


def get_emoji_id(key: str) -> str:
    """Get emoji ID from custom or default."""
    if key in _custom_emoji:
        return _custom_emoji[key]["emoji_id"]
    if key in DEFAULT_EMOJI:
        return DEFAULT_EMOJI[key]["emoji_id"]
    return ""


def get_fallback(key: str) -> str:
    """Get fallback text emoji."""
    if key in _custom_emoji:
        return _custom_emoji[key]["fallback"]
    if key in DEFAULT_EMOJI:
        return DEFAULT_EMOJI[key]["fallback"]
    return "❓"


def icon(key: str) -> str | None:
    """Get resolved emoji ID for inline button (returns None if not resolved)."""
    if key in _emoji_map:
        return _emoji_map[key]
    return None


def text(key: str) -> str:
    """Get emoji as text (resolved custom emoji or fallback)."""
    if key in _emoji_map:
        eid = _emoji_map[key]
        # Return the custom emoji in text format
        return emoji_module.text(eid) if eid else get_fallback(key)
    return get_fallback(key)


async def resolve(bot):
    """Resolve all emoji IDs with Telegram."""
    import emoji as emoji_module
    from aiogram.exceptions import TelegramAPIError
    from config import PREMIUM_EMOJI

    _emoji_map.clear()

    if not PREMIUM_EMOJI:
        return

    all_emoji = {}
    # Merge custom over defaults
    for key, data in DEFAULT_EMOJI.items():
        all_emoji[key] = data["emoji_id"]
    for key, data in _custom_emoji.items():
        all_emoji[key] = data["emoji_id"]

    # Get unique IDs
    unique_ids = list(set(all_emoji.values()))

    try:
        stickers = await bot.get_custom_emoji_stickers(custom_emoji_ids=unique_ids)
    except TelegramAPIError:
        # If resolution fails, just return - emoji will use fallbacks
        return

    # Create ID -> resolved mapping
    resolved_ids = set()
    for sticker in stickers:
        if sticker.custom_emoji_id:
            resolved_ids.add(sticker.custom_emoji_id)

    # Map back to keys - only resolved IDs
    for key, emoji_id in all_emoji.items():
        if emoji_id in resolved_ids:
            _emoji_map[key] = emoji_id
        else:
            _emoji_map[key] = None


def list_all_emoji() -> dict:
    """List all available emoji with their current values."""
    result = {}
    for key, data in DEFAULT_EMOJI.items():
        custom = _custom_emoji.get(key)
        result[key] = {
            "emoji_id": custom["emoji_id"] if custom else data["emoji_id"],
            "fallback": custom["fallback"] if custom else data["fallback"],
            "description": custom.get("description") if custom else data["description"],
            "is_custom": key in _custom_emoji,
        }
    # Add custom emoji not in defaults
    for key in _custom_emoji:
        if key not in result:
            result[key] = {
                "emoji_id": _custom_emoji[key]["emoji_id"],
                "fallback": _custom_emoji[key]["fallback"],
                "description": _custom_emoji[key].get("description", ""),
                "is_custom": True,
            }
    return result
