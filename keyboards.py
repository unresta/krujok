"""Inline keyboards.

Bot API has no colour field for inline buttons (colours exist only for the Mini
App main button), so the palette is carried by the leading emoji and kept
consistent everywhere:
  🟢 = do the thing / confirm / earn
  🔵 = money, info, navigation
  🔴 = cancel, reject, destructive
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MIN_STARS, REWARD, STAR_PACKS, WATCH_COST

PREF_TITLE = {"f": "♀ женские", "m": "♂ мужские", "any": "🎲 любые"}


def menu(pref: str, has_coins: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f"{'🟢' if has_coins else '🔵'} Смотреть · {WATCH_COST} 🪙",
        callback_data="watch",
    )
    kb.row(
        *[
            InlineKeyboardButton(
                text=("• " + PREF_TITLE[p] + " •") if p == pref else PREF_TITLE[p],
                callback_data=f"pref:{p}",
            )
            for p in ("f", "m", "any")
        ]
    )
    kb.row(
        InlineKeyboardButton(text="🟢 Заработать", callback_data="upload"),
        InlineKeyboardButton(text="🔵 Купить 🪙", callback_data="buy"),
    )
    kb.row(InlineKeyboardButton(text="🔵 Профиль", callback_data="profile"))
    kb.adjust(1, 3, 2, 1)
    return kb.as_markup()


def after_watch(pref: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🟢 Ещё · {WATCH_COST} 🪙", callback_data="watch")
    kb.row(
        InlineKeyboardButton(
            text=f"🔵 {PREF_TITLE[pref]}", callback_data="pref:cycle"
        ),
        InlineKeyboardButton(text="🔴 Хватит", callback_data="menu"),
    )
    return kb.as_markup()


def no_coins() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🟢 Заработать", callback_data="upload"),
        InlineKeyboardButton(text="🔵 Купить 🪙", callback_data="buy"),
    )
    kb.row(InlineKeyboardButton(text="🔴 Назад", callback_data="menu"))
    return kb.as_markup()


def back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔴 Назад", callback_data="menu")
    return kb.as_markup()


def upload_gender() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text=f"♀ Женский · +{REWARD['f']} 🪙", callback_data="ug:f"
        ),
        InlineKeyboardButton(
            text=f"♂ Мужской · +{REWARD['m']} 🪙", callback_data="ug:m"
        ),
    )
    kb.row(InlineKeyboardButton(text="🔴 Отмена", callback_data="menu"))
    return kb.as_markup()


def buy() -> InlineKeyboardMarkup:
    from config import STARS_RATE

    kb = InlineKeyboardBuilder()
    for stars in STAR_PACKS:
        kb.button(
            text=f"🔵 {stars} ⭐ → {stars * STARS_RATE} 🪙",
            callback_data=f"pay:{stars}",
        )
    kb.button(text="✏️ Своя сумма", callback_data="pay:custom")
    kb.button(text="🔴 Назад", callback_data="menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def buy_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔴 Отмена", callback_data="buy")
    return kb.as_markup()


def moderation(circle_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🟢 Одобрить", callback_data=f"mod:ok:{circle_id}"),
        InlineKeyboardButton(text="🔴 Отклонить", callback_data=f"mod:no:{circle_id}"),
    )
    return kb.as_markup()


MIN_STARS_HINT = f"минимум {MIN_STARS} ⭐"
