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
# A profile is a person, so it says «Девушка», not «женские».
PERSON_LABEL = {"f": "Девушка", "m": "Парень"}


def PERSON_TITLE(gender: str) -> str:
    return f"{emoji.text(GENDER_EMOJI[gender])} {PERSON_LABEL[gender]}"


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
BTN_ANKETAS = "Смотреть анкеты"
BTN_MY_ANKETA = "Моя анкета"

MENU_ICONS = {
    BTN_WATCH: emoji.WATCH,
    BTN_ANKETAS: emoji.PROFILE,
    BTN_MY_ANKETA: emoji.UPLOAD,
    BTN_UPLOAD: emoji.UPLOAD,
    BTN_PROFILE: emoji.PROFILE,
    BTN_FEED: emoji.FEED,
    BTN_REF: emoji.REF,
    BTN_RULES: emoji.RULES,
    BTN_SHOP: emoji.SHOP,
}

# Only the two money-making buttons are coloured; the rest stay plain, so the
# green ones read as the actions.
MENU_STYLES = {
    BTN_WATCH: SUCCESS,
    BTN_SHOP: SUCCESS,
    BTN_ANKETAS: None,
    BTN_MY_ANKETA: None,
    BTN_UPLOAD: None,
    BTN_PROFILE: None,
    BTN_FEED: None,
    BTN_REF: None,
    BTN_RULES: None,
}


def _menu_button(label: str) -> KeyboardButton:
    return KeyboardButton(
        text=label,
        icon_custom_emoji_id=emoji.icon(MENU_ICONS[label]),
        style=MENU_STYLES[label],
    )


# Menu presses must never be mistaken for an answer to a prompt.
MENU_BUTTONS = frozenset(
    {
        BTN_WATCH,
        BTN_ANKETAS,
        BTN_UPLOAD,
        BTN_MY_ANKETA,
        BTN_PROFILE,
        BTN_FEED,
        BTN_REF,
        BTN_RULES,
        BTN_SHOP,
    }
)


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [_menu_button(BTN_WATCH)],
            [_menu_button(BTN_ANKETAS)],
            [_menu_button(BTN_UPLOAD), _menu_button(BTN_MY_ANKETA)],
            [_menu_button(BTN_PROFILE), _menu_button(BTN_FEED)],
            [_menu_button(BTN_REF), _menu_button(BTN_RULES)],
            [_menu_button(BTN_SHOP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def circle(
    circle_id: int,
    likes: int,
    dislikes: int,
    vote: int,
    author_id: int = 0,
    archive: bool = False,
) -> InlineKeyboardMarkup:
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
    if author_id:  # only when that author has a profile to open
        b.row(
            InlineKeyboardButton(
                text="Анкета автора", callback_data=f"pf:card:{author_id}", style=PRIMARY
            )
        )
    elif archive:  # the bot's own seed content: no author to show
        b.row(
            InlineKeyboardButton(text="Архив · без автора", callback_data="arch")
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
        InlineKeyboardButton(text="Вывести заработок", callback_data="po:open", style=PRIMARY)
    )
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


def accept() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Мне есть 18, согласен с правилами",
            callback_data="accept",
            style=SUCCESS,
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


# --- author profiles -----------------------------------------------------


def profile_card(profile, bought_content: bool, bought_contact: bool) -> InlineKeyboardMarkup:
    """The buy buttons disappear once the thing is already owned."""
    author = profile["user_id"]
    b = InlineKeyboardBuilder()
    if bought_content:
        b.row(
            InlineKeyboardButton(
                text="Кружочки автора", callback_data=f"pf:show:{author}", style=SUCCESS
            )
        )
    else:
        b.row(
            _coin_button(
                f"Купить за {profile['price_content']}", f"pf:buy:{author}", SUCCESS
            )
        )
    if profile["contact_ok"] and profile["price_contact"]:
        b.row(
            _coin_button(
                "Личка автора" if bought_contact
                else f"Написать в ЛС · {profile['price_contact']}",
                f"pf:contact:{author}",
                PRIMARY,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="Следующая анкета", callback_data="pf:next", style=PRIMARY
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Пожаловаться", callback_data=f"pf:rep:{author}", style=DANGER
        )
    )
    return b.as_markup()


def more_circles(author_id: int, offset: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Показать ещё",
            callback_data=f"pf:show:{author_id}:{offset}",
            style=SUCCESS,
        )
    )
    return b.as_markup()


def profile_gender() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        *[
            InlineKeyboardButton(
                text=emoji.label(GENDER_EMOJI[g]) + PERSON_LABEL[g],
                callback_data=f"pg:{g}",
                icon_custom_emoji_id=emoji.icon(GENDER_EMOJI[g]),
                style=SUCCESS,
            )
            for g in ("f", "m")
        ]
    )
    return b.as_markup()


def profile_contact_ask(has_username: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_username:
        b.row(
            InlineKeyboardButton(text="Продавать", callback_data="pc:yes", style=SUCCESS),
            InlineKeyboardButton(text="Не продавать", callback_data="pc:no", style=DANGER),
        )
    else:
        b.row(
            InlineKeyboardButton(
                text="Добавил(а) юзернейм", callback_data="pc:recheck", style=SUCCESS
            )
        )
        b.row(
            InlineKeyboardButton(
                text="Не продавать личку", callback_data="pc:no", style=DANGER
            )
        )
    return b.as_markup()


def my_profile(exists: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Изменить анкету" if exists else "Заполнить анкету",
            callback_data="pf:edit",
            style=SUCCESS,
        )
    )
    return b.as_markup()


def profile_review(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Одобрить", callback_data=f"pm:ok:{user_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="Отклонить", callback_data=f"pm:no:{user_id}", style=DANGER
        ),
    )
    return b.as_markup()


def profile_decided(user_id: int) -> InlineKeyboardMarkup:
    """A verdict is never final: the card keeps a way back to the buttons."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Изменить решение",
            callback_data=f"pm:again:{user_id}",
            style=PRIMARY,
        )
    )
    return b.as_markup()


def profile_intro() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Соглашаюсь, настроить профиль",
            callback_data="pf:start",
            style=SUCCESS,
        )
    )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="menu", style=DANGER))
    return b.as_markup()


def refill_profile() -> InlineKeyboardMarkup:
    """Goes with a rejection — the fix is one tap away, not a menu hunt."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Заполнить заново", callback_data="pf:edit", style=SUCCESS
        )
    )
    return b.as_markup()


def profile_reasons(user_id: int) -> InlineKeyboardMarkup:
    """Why the profile is being turned down — the author gets told."""
    from texts import REJECT_REASONS

    b = InlineKeyboardBuilder()
    for key, label in REJECT_REASONS.items():
        b.row(
            InlineKeyboardButton(
                text=label.capitalize(),
                callback_data=f"pm:r:{key}:{user_id}",
                style=DANGER,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="Своя причина", callback_data=f"pm:rc:{user_id}", style=PRIMARY
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Назад", callback_data=f"pm:back:{user_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def profile_report_review(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Скрыть анкету", callback_data=f"pm:hide:{user_id}", style=DANGER
        ),
        InlineKeyboardButton(
            text="Оставить", callback_data=f"pm:keep:{user_id}", style=SUCCESS
        ),
    )
    return b.as_markup()


# --- payouts -------------------------------------------------------------


def payout(can_request: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_request:
        b.row(
            InlineKeyboardButton(
                text="Оформить вывод", callback_data="po:new", style=SUCCESS
            )
        )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="menu", style=DANGER))
    return b.as_markup()


def payout_review(payout_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Выплачено", callback_data=f"pw:paid:{payout_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="Отклонить", callback_data=f"pw:no:{payout_id}", style=DANGER
        ),
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
    kb.row(InlineKeyboardButton(text="Отмена", callback_data="menu", style=DANGER))
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



