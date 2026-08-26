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
    "maintenance": 0,
}

TITLES: dict[str, str] = {
    "watch_cost": "Просмотр, монеток",
    "reward_f": "Награда за женский",
    "reward_m": "Награда за мужской",
    "stars_rate": "Монеток за 1 ⭐",
    "min_stars": "Минимум ⭐ за раз",
    "min_duration": "Мин. длина, сек",
    "max_pending": "Кружков на проверке",
}

LIMITS: dict[str, tuple[int, int]] = {
    "watch_cost": (1, 1000),
    "reward_f": (0, 1000),
    "reward_m": (0, 1000),
    "stars_rate": (1, 1000),
    "min_stars": (1, 10_000),
    "min_duration": (1, 60),
    "max_pending": (1, 100),
}

_values: dict[str, int] = dict(DEFAULTS)


async def load() -> None:
    _values.update(DEFAULTS)
    _values.update(await db.load_settings())


def get(key: str) -> int:
    return _values[key]


def reward(gender: str) -> int:
    return _values["reward_f" if gender == "f" else "reward_m"]


def maintenance() -> bool:
    return bool(_values["maintenance"])


async def set(key: str, value: int) -> None:
    _values[key] = value
    await db.save_setting(key, value)
