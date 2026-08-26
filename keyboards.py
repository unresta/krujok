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

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import emoji
import settings
from config import STAR_PACKS

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


# --- main menu: a reply keyboard that never scrolls away -----------------

# Labels carry no emoji of their own: the icon is a separate field, and the
# text has to stay byte-identical to what the filters match on.
BTN_WATCH = "Смотреть кружки"
BTN_UPLOAD = "Загрузить кружок"
BTN_PROFILE = "Профиль"
BTN_FEED = "Лента"
BTN_REF = "Рефералы"
BTN_RULES = "Правила и FAQ"
BTN_SHOP = "Магазин"

MENU_ICONS = {
    BTN_WATCH: emoji.WATCH,
    BTN_UPLOAD: emoji.UPLOAD,
    BTN_PROFILE: emoji.PROFILE,
    BTN_FEED: emoji.FEED,
    BTN_REF: emoji.REF,
    BTN_RULES: emoji.RULES,
    BTN_SHOP: emoji.SHOP,
}

MENU_STYLES = {
    BTN_WATCH: SUCCESS,  # the thing people came for
    BTN_SHOP: SUCCESS,  # and the thing that pays for it
    BTN_UPLOAD: PRIMARY,
    BTN_PROFILE: PRIMARY,
    BTN_FEED: PRIMARY,
    BTN_REF: PRIMARY,
    BTN_RULES: None,  # one plain button keeps the rest readable
}


def _menu_button(label: str) -> KeyboardButton:
    return KeyboardButton(
        text=label,
        icon_custom_emoji_id=emoji.icon(MENU_ICONS[label]),
        style=MENU_STYLES[label],
    )


# Menu presses must never be mistaken for an answer to a prompt.
MENU_BUTTONS = frozenset(
    {BTN_WATCH, BTN_UPLOAD, BTN_PROFILE, BTN_FEED, BTN_REF, BTN_RULES, BTN_SHOP}
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [_menu_button(BTN_WATCH)],
            [_menu_button(BTN_UPLOAD), _menu_button(BTN_PROFILE)],
            [_menu_button(BTN_FEED), _menu_button(BTN_REF)],
            [_menu_button(BTN_RULES), _menu_button(BTN_SHOP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def circle(circle_id: int, likes: int, dislikes: int, vote: int) -> InlineKeyboardMarkup:
    """Sits under the circle itself, so reactions travel with the video."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=emoji.label(emoji.LIKE) + str(likes),
            callback_data=f"lk:{circle_id}:1",
            icon_custom_emoji_id=emoji.icon(emoji.LIKE),
            style=SUCCESS if vote == 1 else None,
        ),
        InlineKeyboardButton(
            text=emoji.label(emoji.DISLIKE) + str(dislikes),
            callback_data=f"lk:{circle_id}:-1",
            icon_custom_emoji_id=emoji.icon(emoji.DISLIKE),
            style=DANGER if vote == -1 else None,
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="Пожаловаться", callback_data=f"rep:{circle_id}", style=DANGER
        )
    )
    b.row(_coin_button(f'Следующий · {settings.get("watch_cost")}', "watch", SUCCESS))
    return b.as_markup()


def feed(pref: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[_pref_button(p, p == pref) for p in ("f", "m", "any")])
    return b.as_markup()


def profile(link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_coin_button("Пополнить баланс", "buy", SUCCESS))
    b.row(
        InlineKeyboardButton(
            text="Позвать друга",
            url=f"https://t.me/share/url?url={link}&text="
            "Кружочки без лишних слов",
            style=PRIMARY,
        )
    )
    return b.as_markup()


def referrals(link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Позвать друга",
            url=f"https://t.me/share/url?url={link}&text="
            "Кружочки без лишних слов",
            style=PRIMARY,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Скопировать ссылку", copy_text=CopyTextButton(text=link)
        )
    )
    return b.as_markup()


def rules() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Прочитать FAQ", callback_data="faq", style=PRIMARY)
    )
    return b.as_markup()


def faq() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Прочитать Правила", callback_data="rules", style=PRIMARY
        )
    )
    return b.as_markup()


def report_review(circle_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Удалить кружок", callback_data=f"rp:del:{circle_id}", style=DANGER
        ),
        InlineKeyboardButton(
            text="Оставить", callback_data=f"rp:keep:{circle_id}", style=SUCCESS
        ),
    )
    return b.as_markup()


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
    kb.row(InlineKeyboardButton(text="Закрыть", callback_data="menu", style=DANGER))
    return kb.as_markup()


def upload_gender() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        *[
            InlineKeyboardButton(
                text=emoji.label(GENDER_EMOJI[g])
                + f"{'Женский' if g == 'f' else 'Мужской'} · "
                + f"+{settings.reward(g)}",
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
            text=f'{stars} ⭐ = {stars * settings.get("stars_rate")} {emoji.plain(emoji.COIN)}',
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



