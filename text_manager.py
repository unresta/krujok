"""Texts an admin can rewrite from the panel.

The defaults live in texts.py and nowhere else — this module only knows which
of them may be edited, and swaps an override straight into that module. That is
what makes a change show up in the next message instead of after a restart, and
what keeps the panel from drifting apart from the code.

A text shown in a toast or an alert is stored as plain text: Telegram renders no
HTML there, so bold and premium emoji would arrive as visible tags.
"""

import logging
from typing import NamedTuple

import db
import texts

logger = logging.getLogger(__name__)


class Item(NamedTuple):
    description: str
    category: str
    plain: bool = False  # lives in a toast/alert, where formatting is not shown


CATEGORY_ICON = {
    "Система": "⚙️",
    "Профиль": "👤",
    "Загрузка": "🎥",
    "Просмотр": "👀",
    "Жалобы": "⚠️",
    "Покупки": "💰",
    "Выплаты": "💸",
    "Рефералы": "👥",
    "Подписка": "📢",
}

EDITABLE: dict[str, Item] = {
    # --- Система ---
    "ACCEPTED": Item("Согласие принято", "Система", plain=True),
    "BANNED": Item("Сообщение забаненному", "Система", plain=True),
    "MAINTENANCE": Item("Режим техработ", "Система", plain=True),
    # --- Профиль ---
    "PROFILE_INTRO": Item("Приглашение завести анкету", "Профиль"),
    "PROFILE_PHOTO": Item("Просьба прислать фото", "Профиль"),
    "PROFILE_GENDER": Item("Вопрос о поле", "Профиль"),
    "PROFILE_ABOUT_TEXT_ONLY": Item("Описание — только текстом", "Профиль"),
    "PROFILE_CONTACT_ASK": Item("Продавать ли личку", "Профиль"),
    "PROFILE_NO_USERNAME": Item("Нужен @username", "Профиль", plain=True),
    "PROFILE_STILL_NO_USERNAME": Item("@username так и нет", "Профиль", plain=True),
    "PROFILE_SENT": Item("Анкета ушла на проверку", "Профиль"),
    "PROFILE_NOT_PHOTO": Item("Прислали не фото", "Профиль"),
    "PROFILE_APPROVED": Item("Анкета одобрена", "Профиль"),
    "PROFILE_EMPTY_WAIT": Item("Анкеты кончились", "Профиль"),
    # --- Загрузка ---
    "UPLOAD_NEEDS_PROFILE": Item("Сначала анкета", "Загрузка"),
    "NOT_A_CIRCLE": Item("Прислали не кружок", "Загрузка"),
    "DUPLICATE": Item("Кружок уже есть в базе", "Загрузка"),
    "TOO_MANY_PENDING": Item("Слишком много на проверке", "Загрузка"),
    "REJECTED": Item("Кружок отклонён", "Загрузка"),
    # --- Просмотр ---
    "EMPTY": Item("Кружки этого типа кончились", "Просмотр"),
    "ARCHIVE_NOTE": Item("Кружок из архива бота", "Просмотр", plain=True),
    # --- Жалобы ---
    "REPORT_ASK": Item("Вопрос «за что жалуешься»", "Жалобы", plain=True),
    "REPORT_SENT": Item("Жалоба отправлена", "Жалобы", plain=True),
    "REPORT_DOUBLE": Item("Повторная жалоба на кружок", "Жалобы", plain=True),
    "REPORT_DOUBLE_PROFILE": Item("Повторная жалоба на анкету", "Жалобы", plain=True),
    "CIRCLE_HIDDEN": Item("Кружок сняли с показа", "Жалобы"),
    "CIRCLE_RESTORED": Item("Кружок вернули в показ", "Жалобы"),
    "CIRCLE_REMOVED": Item("Кружок удалён по жалобам", "Жалобы"),
    # --- Покупки ---
    "CONTACT_NOT_FOR_SALE": Item("Личка не продаётся", "Покупки", plain=True),
    "NOTHING_TO_SELL": Item("У автора нет кружочков", "Покупки", plain=True),
    "ALREADY_BOUGHT": Item("Уже куплено", "Покупки", plain=True),
    "BUY_PICK_METHOD": Item("Выбери способ оплаты", "Покупки"),
    # --- Выплаты ---
    "PAYOUT_ASK_DETAILS": Item("Запрос реквизитов", "Выплаты"),
    # --- Рефералы ---
    "TRAFFER_UNKNOWN": Item("Неизвестная команда траффера", "Рефералы"),
    # --- Подписка ---
    "SUBSCRIBE_MISSING": Item("Подписки не видно", "Подписка", plain=True),
}

_defaults: dict[str, str] = {}
_custom: dict[str, str] = {}


def _snapshot() -> None:
    """The values texts.py was shipped with, taken before anything overrides."""
    if _defaults:
        return
    for key in EDITABLE:
        value = getattr(texts, key, None)
        if isinstance(value, str):
            _defaults[key] = value
        else:  # a key that no longer exists in the code must not hide the rest
            logger.warning("editable text %s is missing from texts.py", key)


def apply() -> None:
    """Push the current values into texts.py, overrides and defaults alike."""
    _snapshot()
    for key, default in _defaults.items():
        setattr(texts, key, _custom.get(key, default))


async def load_from_db() -> None:
    _snapshot()
    _custom.clear()
    for key, row in (await db.load_custom_texts()).items():
        if key in _defaults:
            _custom[key] = row["text"]
    apply()
    logger.info("custom texts loaded: %s", len(_custom))


def default(key: str) -> str:
    _snapshot()
    return _defaults.get(key, "")


def get(key: str) -> str:
    return _custom.get(key) or default(key)


def is_custom(key: str) -> bool:
    return key in _custom


def known(key: str) -> bool:
    _snapshot()
    return key in _defaults


def keys_in(category: str) -> list[str]:
    return [
        key
        for key in EDITABLE
        if EDITABLE[key].category == category and known(key)
    ]


def categories() -> list[tuple[str, int, int]]:
    """(name, texts in it, how many of them are overridden)"""
    out = []
    for name in CATEGORY_ICON:
        keys = keys_in(name)
        if keys:
            out.append((name, len(keys), sum(is_custom(k) for k in keys)))
    return out


def custom_count() -> int:
    return len(_custom)


async def save(key: str, value: str) -> None:
    if not known(key):
        return
    _custom[key] = value
    await db.save_custom_text(key, value, EDITABLE[key].description)
    apply()


async def reset(key: str) -> None:
    _custom.pop(key, None)
    await db.delete_custom_text(key)
    apply()


async def reset_all() -> int:
    dropped = await db.wipe_custom_texts()
    _custom.clear()
    apply()
    return dropped
