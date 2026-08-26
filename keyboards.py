"""Inline keyboards.

Colours come from the Bot API `style` field (9.4+): 'primary' blue, 'success'
green, 'danger' red. Convention kept across the whole bot:
  primary = the main action of the screen
  success = anything that adds coins / approves
  danger  = cancel, back, reject
Neutral buttons stay unstyled so the coloured one always reads as the default.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MIN_STARS, REWARD, STAR_PACKS, STARS_RATE, WATCH_COST

PREF_TITLE = {"f": "♀ женские", "m": "♂ мужские", "any": "🎲 любые"}

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"


def menu(pref: str, has_coins: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"Смотреть · {WATCH_COST} 🪙",
            callback_data="watch",
            style=PRIMARY if has_coins else None,
        )
    )
    kb.row(
        *[
            InlineKeyboardButton(
                text=PREF_TITLE[p],
                callback_data=f"pref:{p}",
                style=PRIMARY if p == pref else None,
            )
            for p in ("f", "m", "any")
        ]
    )
    kb.row(
        InlineKeyboardButton(
            text="Заработать 🪙", callback_data="upload", style=SUCCESS
        ),
        InlineKeyboardButton(text="Купить 🪙", callback_data="buy"),
    )
    kb.row(InlineKeyboardButton(text="Профиль", callback_data="profile"))
    return kb.as_markup()


def after_watch(pref: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"Ещё · {WATCH_COST} 🪙", callback_data="watch", style=PRIMARY
        )
    )
    kb.row(
        InlineKeyboardButton(text=PREF_TITLE[pref], callback_data="pref:cycle"),
        InlineKeyboardButton(text="Хватит", callback_data="menu", style=DANGER),
    )
    return kb.as_markup()


def no_coins() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="Заработать 🪙", callback_data="upload", style=SUCCESS
        ),
        InlineKeyboardButton(text="Купить 🪙", callback_data="buy", style=PRIMARY),
    )
    kb.row(InlineKeyboardButton(text="Назад", callback_data="menu", style=DANGER))
    return kb.as_markup()


def back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Назад", callback_data="menu", style=DANGER))
    return kb.as_markup()


def upload_gender() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"♀ Женский · +{REWARD['f']} 🪙",
            callback_data="ug:f",
            style=SUCCESS,
        ),
        InlineKeyboardButton(
            text=f"♂ Мужской · +{REWARD['m']} 🪙",
            callback_data="ug:m",
            style=SUCCESS,
        ),
    )
    kb.row(InlineKeyboardButton(text="Отмена", callback_data="menu", style=DANGER))
    return kb.as_markup()


def buy() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        *[
            InlineKeyboardButton(
                text=f"{stars} ⭐ → {stars * STARS_RATE} 🪙",
                callback_data=f"pay:{stars}",
                style=PRIMARY,
            )
            for stars in STAR_PACKS[:2]
        ]
    )
    kb.row(
        *[
            InlineKeyboardButton(
                text=f"{stars} ⭐ → {stars * STARS_RATE} 🪙",
                callback_data=f"pay:{stars}",
                style=PRIMARY,
            )
            for stars in STAR_PACKS[2:]
        ]
    )
    kb.row(InlineKeyboardButton(text="✏️ Своя сумма", callback_data="pay:custom"))
    kb.row(InlineKeyboardButton(text="Назад", callback_data="menu", style=DANGER))
    return kb.as_markup()


def buy_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Отмена", callback_data="buy", style=DANGER))
    return kb.as_markup()


def moderation(circle_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="Одобрить", callback_data=f"mod:ok:{circle_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="Отклонить", callback_data=f"mod:no:{circle_id}", style=DANGER
        ),
    )
    return kb.as_markup()


MIN_STARS_HINT = f"минимум {MIN_STARS} ⭐"
