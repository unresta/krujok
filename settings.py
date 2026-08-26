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
    "min_duration_short": config.MIN_DURATION_SHORT,
    "reward_f_short": config.REWARD_SHORT["f"],
    "reward_m_short": config.REWARD_SHORT["m"],
    "max_pending": config.MAX_PENDING,
    "ref_reward": config.REF_REWARD,
    "maintenance": 0,
}

# Free-form values live apart: the settings table holds integers.
TEXT_DEFAULTS: dict[str, str] = {
    "channel": config.CHANNEL,  # @name or -100… ; empty disables the gate
}

TITLES: dict[str, str] = {
    "watch_cost": "Просмотр, монеток",
    "reward_f": "Награда за женский",
    "reward_m": "Награда за мужской",
    "stars_rate": "Монеток за 1 ⭐",
    "min_stars": "Минимум ⭐ за раз",
    "min_duration": "Полная награда от, сек",
    "min_duration_short": "Принимаем от, сек",
    "reward_f_short": "Короткий женский",
    "reward_m_short": "Короткий мужской",
    "max_pending": "Кружков на проверке",
    "ref_reward": "За реферала",
}

LIMITS: dict[str, tuple[int, int]] = {
    "watch_cost": (1, 1000),
    "reward_f": (0, 1000),
    "reward_m": (0, 1000),
    "stars_rate": (1, 1000),
    "min_stars": (1, 10_000),
    "min_duration": (1, 60),
    "min_duration_short": (1, 60),
    "reward_f_short": (0, 1000),
    "reward_m_short": (0, 1000),
    "max_pending": (1, 100),
    "ref_reward": (0, 1000),
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


def reward(gender: str, duration: int | None = None) -> int:
    """Full price by default; a circle under min_duration is worth less."""
    short = duration is not None and duration < _values["min_duration"]
    return _values[f"reward_{gender}{'_short' if short else ''}"]


def maintenance() -> bool:
    return bool(_values["maintenance"])


async def set(key: str, value: int) -> None:
    _values[key] = value
    await db.save_setting(key, value)


def get_text(key: str) -> str:
    return _texts[key]


async def set_text(key: str, value: str) -> None:
    _texts[key] = value
    await db.save_text_setting(key, value)
