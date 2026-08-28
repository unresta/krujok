"""Economy knobs an admin can turn without a redeploy.

config.py holds the defaults; whatever the admin changes lands in the settings
table and is loaded back on start. Read through get()/reward() at call time —
never import a value into a module constant, or edits stop taking effect.
"""

import config
import db

DEFAULTS: dict[str, int] = {
    "watch_cost": config.WATCH_COST,
    "reward_f": config.REWARD["f"],
    "reward_m": config.REWARD["m"],
    "stars_rate": config.STARS_RATE,
    "min_stars": config.MIN_STARS,
    "min_duration": config.MIN_DURATION,
    "max_pending": config.MAX_PENDING,
    "ref_reward": config.REF_REWARD,
    "welcome_bonus": config.WELCOME_BONUS,
    "sub_bonus": config.SUB_BONUS,
    "view_payout": config.VIEW_PAYOUT,
    "like_bonus": config.LIKE_BONUS,
    "like_boost": config.LIKE_BOOST,
    "reports_to_hide": config.REPORTS_TO_HIDE,
    "push_enabled": config.PUSH_ENABLED,
    "push_idle_hours": config.PUSH_IDLE_HOURS,
    "push_cooldown_hours": config.PUSH_COOLDOWN_HOURS,
    "push_batch": config.PUSH_BATCH,
    "push_free_views": config.PUSH_FREE_VIEWS,
    "author_share": config.AUTHOR_SHARE,
    "price_min": config.PRICE_MIN,
    "price_max": config.PRICE_MAX,
    "payout_min": config.PAYOUT_MIN,
    "payout_rate": config.PAYOUT_RATE,
    "star_price": config.STAR_PRICE,
    "maintenance": 0,
}

# Free-form values live apart: the settings table holds integers.
TEXT_DEFAULTS: dict[str, str] = {
    "channel": config.CHANNEL,  # @name or -100… ; empty disables the gate
    "reports_chat": config.REPORTS_CHAT,  # empty falls back to ADMIN_CHAT_ID
    "profiles_chat": config.PROFILES_CHAT,
    "circles_chat": config.CIRCLES_CHAT,
    "currency": config.CURRENCY,
}

TITLES: dict[str, str] = {
    "watch_cost": "Просмотр, монеток",
    "reward_f": "Награда за женский",
    "reward_m": "Награда за мужской",
    "stars_rate": "Монеток за 1 ⭐",
    "min_stars": "Минимум ⭐ за раз",
    "min_duration": "Минимум, сек",
    "max_pending": "Кружков на проверке",
    "ref_reward": "За реферала",
    "welcome_bonus": "Новичку при старте",
    "sub_bonus": "За подписку на канал",
    "view_payout": "Автору за просмотр",
    "like_bonus": "Автору за лайк",
    "like_boost": "Вес лайка в выдаче",
    "reports_to_hide": "Жалоб до скрытия",
    "push_idle_hours": "Напоминание после, ч",
    "push_cooldown_hours": "Не чаще чем раз в, ч",
    "push_batch": "Напоминаний за проход",
    "push_free_views": "Кружков в подарок",
    "author_share": "Автору с продажи, %",
    "price_min": "Мин. цена анкеты",
    "price_max": "Макс. цена анкеты",
    "payout_min": "Минимум вывода",
    "payout_rate": "Монеток за 1 ⭐ (вывод)",
    "star_price": "Цена 1 ⭐ в копейках",
}

# Twenty-four knobs in one column is a wall; the panel shows them by subject.
GROUPS: dict[str, tuple[str, ...]] = {
    "🎬 Просмотр и лента": (
        "watch_cost",
        "view_payout",
        "like_bonus",
        "like_boost",
        "min_duration",
        "max_pending",
        "reward_f",
        "reward_m",
    ),
    "💰 Продажи": ("author_share", "price_min", "price_max"),
    "⭐ Покупка монеток": ("stars_rate", "min_stars", "star_price"),
    "💸 Вывод": ("payout_min", "payout_rate"),
    "🎁 Бонусы": ("welcome_bonus", "sub_bonus", "ref_reward"),
    "🔔 Напоминания": (
        "push_idle_hours",
        "push_cooldown_hours",
        "push_batch",
        "push_free_views",
    ),
    "⚠️ Модерация": ("reports_to_hide",),
}

LIMITS: dict[str, tuple[int, int]] = {
    "watch_cost": (1, 1000),
    "reward_f": (0, 1000),
    "reward_m": (0, 1000),
    "stars_rate": (1, 1000),
    "min_stars": (1, 10_000),
    "min_duration": (1, 60),
    "max_pending": (1, 100),
    "ref_reward": (0, 1000),
    "welcome_bonus": (0, 1000),
    "sub_bonus": (0, 1000),
    "view_payout": (0, 1000),
    "like_bonus": (0, 1000),
    "like_boost": (0, 100),
    "reports_to_hide": (1, 1000),
    "push_enabled": (0, 1),
    "push_idle_hours": (1, 720),
    "push_cooldown_hours": (1, 720),
    "push_batch": (1, 1000),
    "push_free_views": (0, 10),
    "author_share": (0, 100),
    "price_min": (1, 10_000),
    "price_max": (1, 100_000),
    "payout_min": (1, 1_000_000),
    "payout_rate": (1, 1000),
    "star_price": (1, 1_000_000),
}

_values: dict[str, int] = dict(DEFAULTS)
_texts: dict[str, str] = dict(TEXT_DEFAULTS)


async def load() -> None:
    _values.update(DEFAULTS)
    _values.update(await db.load_settings())
    _texts.update(TEXT_DEFAULTS)
    _texts.update(await db.load_text_settings())


def get(key: str) -> int:
    return _values[key]


def reward(gender: str) -> int:
    return _values["reward_f" if gender == "f" else "reward_m"]


def author_share(price: int) -> int:
    """What the author keeps from a sale; the rest is the service's cut."""
    return price * _values["author_share"] // 100


def stars_for(coins: int) -> int:
    return coins // _values["payout_rate"]


def reports_chat() -> int | str:
    """Where complaints land: their own chat if set, the moderation one if not."""
    return _texts["reports_chat"].strip() or config.ADMIN_CHAT_ID


def money(minor: int) -> str:
    """Minor units to something a human reads: 1073720 -> «10737.20 ₽»."""
    return f"{minor // 100}.{minor % 100:02d} {_texts['currency']}"


def revenue_of(stars: int) -> int:
    """What those stars are worth, in minor units."""
    return stars * _values["star_price"]


def circles_chat() -> int | str:
    """Where uploaded circles go for review."""
    return _texts["circles_chat"].strip() or config.ADMIN_CHAT_ID


def profiles_chat() -> int | str:
    """Where profiles go for review: their own chat, or the moderation one."""
    return _texts["profiles_chat"].strip() or config.ADMIN_CHAT_ID


def maintenance() -> bool:
    return bool(_values["maintenance"])


async def set(key: str, value: int) -> None:
    _values[key] = value
    await db.save_setting(key, value)


def default(key: str) -> int:
    return DEFAULTS[key]


def groups() -> dict[str, tuple[str, ...]]:
    """Every titled setting belongs somewhere, even one added after the fact."""
    known = {key for keys in GROUPS.values() for key in keys}
    rest = tuple(key for key in TITLES if key not in known)
    return {**GROUPS, "📋 Прочее": rest} if rest else dict(GROUPS)


def get_text(key: str) -> str:
    return _texts[key]


async def set_text(key: str, value: str) -> None:
    _texts[key] = value
    await db.save_text_setting(key, value)
