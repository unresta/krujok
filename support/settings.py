"""Runtime settings an admin can change from the panel without a redeploy.

Same contract as the main bot's settings.py: config.py holds the defaults, edits
land in the database and are loaded back on start. Always read through get() at
call time — importing a value into a module constant freezes it.
"""

import config
import db

DEFAULTS: dict[str, int] = {
    "sla_hours": config.SLA_HOURS,
    "sla_repeat_hours": config.SLA_REPEAT_HOURS,
}

TEXT_DEFAULTS: dict[str, str] = {
    "chat": config.SUPPORT_CHAT,  # empty means cards fall back to admins' DMs
}

TITLES: dict[str, str] = {
    "sla_hours": "Напомнить через, ч",
    "sla_repeat_hours": "Повторять не чаще, ч",
}

LIMITS: dict[str, tuple[int, int]] = {
    "sla_hours": (1, 168),
    "sla_repeat_hours": (1, 168),
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


async def set(key: str, value: int) -> None:
    _values[key] = value
    await db.save_setting(key, value)


def get_text(key: str) -> str:
    return _texts[key]


async def set_text(key: str, value: str) -> None:
    _texts[key] = value
    await db.save_text_setting(key, value)


def support_chat() -> int | str:
    """Where cards go. Empty string when unset — the caller decides the fallback."""
    raw = _texts["chat"].strip()
    if not raw:
        return ""
    if raw.startswith("@"):
        return raw
    try:
        return int(raw)
    except ValueError:
        return raw
