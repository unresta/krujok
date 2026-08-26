"""Inline keyboards.

Colours come from the Bot API `style` field (9.4+): 'primary' blue, 'success'
green, 'danger' red. Convention across the bot:
  primary = main action of the screen / current selection
  success = anything that brings coins in, and "approve"
  danger  = cancel, back, reject
Unselected type buttons stay unstyled on purpose — that is what makes the
selected one readable.

Icons are premium custom emoji (`icon_custom_emoji_id`), one per button, always
rendered before the label. See emoji.py for the Fragment/Premium requirement.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import emoji
from config import MIN_STARS, REWARD, STAR_PACKS, STARS_RATE, WATCH_COST

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"

GENDER_EMOJI = {"f": emoji.FEMALE, "m": emoji.MALE, "any": emoji.ANY}
PREF_LABEL = {"f": "женские", "m": "мужские", "any": "любые"}


def PREF_TITLE(pref: str) -> str:
    """Human name of a preference for message text and toasts."""
    return f"{emoji.text(GENDER_EMOJI[pref])} {PREF_LABEL[pref]}"


def _pref_button(pref: str, styled: bool) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=emoji.label(GENDER_EMOJI[pref]) + PREF_LABEL[pref],
        callback_data=f"pref:{pref}",
        icon_custom_emoji_id=emoji.icon(GENDER_EMOJI[pref]),
        style=PRIMARY if styled else None,
    )


def _coin_button(text: str, callback_data: str, style: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=emoji.label(emoji.COIN) + text,
        callback_data=callback_data,
        icon_custom_emoji_id=emoji.icon(emoji.COIN),
        style=style,
    )


def menu(pref: str, has_coins: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Профиль", callback_data="profile", style=PRIMARY)
    )
    kb.row(*[_pref_button(p, p == pref) for p in ("f", "m", "any")])
    kb.row(
        _coin_button("Заработать", "upload", SUCCESS),
        _coin_button("Купить", "buy", SUCCESS),
    )
    kb.row(_coin_button(f"Смотреть · {WATCH_COST}", "watch", PRIMARY))
    return kb.as_markup()


def after_watch(pref: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(_coin_button(f"Ещё · {WATCH_COST}", "watch", PRIMARY))
    kb.row(
        InlineKeyboardButton(
            text=emoji.label(GENDER_EMOJI[pref]) + PREF_LABEL[pref],
            callback_data="pref:cycle",
            icon_custom_emoji_id=emoji.icon(GENDER_EMOJI[pref]),
            style=PRIMARY,
        ),
        InlineKeyboardButton(text="Хватит", callback_data="menu", style=DANGER),
    )
    return kb.as_markup()


def no_coins() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        _coin_button("Заработать", "upload", SUCCESS),
        _coin_button("Купить", "buy", SUCCESS),
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
        *[
            InlineKeyboardButton(
                text=emoji.label(GENDER_EMOJI[g])
                + f"{'Женский' if g == 'f' else 'Мужской'} · +{REWARD[g]}",
                callback_data=f"ug:{g}",
                icon_custom_emoji_id=emoji.icon(GENDER_EMOJI[g]),
                style=SUCCESS,
            )
            for g in ("f", "m")
        ]
    )
    kb.row(InlineKeyboardButton(text="Отмена", callback_data="menu", style=DANGER))
    return kb.as_markup()


def buy() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # The coin goes last here, so it cannot be the button icon (that slot always
    # renders first) — a plain emoji in the label is the only way round it.
    packs = [
        InlineKeyboardButton(
            text=f"{stars} ⭐ = {stars * STARS_RATE} {emoji.plain(emoji.COIN)}",
            callback_data=f"pay:{stars}",
            style=SUCCESS,
        )
        for stars in STAR_PACKS
    ]
    kb.row(*packs[:2])
    kb.row(*packs[2:])
    kb.row(
        InlineKeyboardButton(
            text="✏️ Своя сумма", callback_data="pay:custom", style=PRIMARY
        )
    )
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
