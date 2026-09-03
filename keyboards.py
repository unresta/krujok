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
from urllib.parse import quote

from aiogram.utils.keyboard import InlineKeyboardBuilder

import emoji
import lang
import settings
from config import STAR_PACKS


def L(ru: str, en_text: str) -> str:
    """A button label in the language of this update.

    Moderator buttons are left in Russian on purpose: they live in the
    moderation chats, where the people reading them are ours.
    """
    return en_text if lang.get() == "en" else ru

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"

GENDER_EMOJI = {"f": emoji.FEMALE, "m": emoji.MALE, "any": emoji.ANY}
PREF_LABEL = {"f": "женские", "m": "мужские", "any": "любые"}
PREF_LABEL_EN = {"f": "female", "m": "male", "any": "any"}
# A profile is a person, so it says «Девушка», not «женские».
PERSON_LABEL = {"f": "Девушка", "m": "Парень"}
PERSON_LABEL_EN = {"f": "Girl", "m": "Guy"}


def pref_word(pref: str) -> str:
    return (PREF_LABEL_EN if lang.get() == "en" else PREF_LABEL)[pref]


def person_word(gender: str) -> str:
    return (PERSON_LABEL_EN if lang.get() == "en" else PERSON_LABEL)[gender]


def PERSON_TITLE(gender: str) -> str:
    """For message text, where HTML is parsed and a custom emoji renders."""
    return f"{emoji.text(GENDER_EMOJI[gender])} {person_word(gender)}"


def PERSON_BUTTON(gender: str) -> str:
    """The same for a button label, where it is not.

    A button carries plain text: put the HTML form on one and the reader gets
    the tag itself, angle brackets and all.
    """
    return f"{emoji.plain(GENDER_EMOJI[gender])} {person_word(gender)}"


def PREF_TITLE(pref: str) -> str:
    """Human name of a preference for message text and toasts."""
    return f"{emoji.text(GENDER_EMOJI[pref])} {pref_word(pref)}"


def _pref_button(pref: str, styled: bool) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=emoji.label(GENDER_EMOJI[pref]) + pref_word(pref),
        callback_data=f"pref:{pref}",
        icon_custom_emoji_id=emoji.icon(GENDER_EMOJI[pref]),
        style=PRIMARY if styled else None,
    )


def _coin_button(text: str, callback_data: str, style: str, icon: str | None = None) -> InlineKeyboardButton:
    emoji_id = icon if icon else emoji.icon(emoji.COIN)
    label_emoji = emoji.COIN if not icon else None
    return InlineKeyboardButton(
        text=(emoji.label(label_emoji) if label_emoji else "") + text,
        callback_data=callback_data,
        icon_custom_emoji_id=emoji_id,
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
BTN_SUBS = "Подписка"
# Only on screen while an auction is running, and red the whole time it is:
# the point of it is that it ends today.
BTN_AUCTION = "🔨 АУКЦИОН"

# The Russian label is the id of a button — it keys the icon, the style and the
# handler that answers it. English is a second label for the same button, and
# `labels()` is what a filter matches on, because a person with an English
# keyboard presses «Watch circles» and means BTN_WATCH.
MENU_EN = {
    BTN_WATCH: "Watch circles",
    BTN_UPLOAD: "Upload a circle",
    BTN_PROFILE: "Profile",
    BTN_FEED: "Feed",
    BTN_REF: "Referrals",
    BTN_RULES: "Rules and FAQ",
    BTN_SHOP: "Shop",
    BTN_ANKETAS: "Browse profiles",
    BTN_SUBS: "Subscription",
    BTN_AUCTION: "🔨 AUCTION",
}


def menu_label(button: str) -> str:
    return MENU_EN.get(button, button) if lang.get() == "en" else button


def labels(button: str) -> frozenset:
    """Every language's label for one button — what a handler filters on."""
    return frozenset({button, MENU_EN.get(button, button)})


MENU_ICONS = {
    BTN_WATCH: emoji.WATCH,
    BTN_ANKETAS: emoji.PROFILE,
    BTN_PROFILE: emoji.PROFILE,
    BTN_FEED: emoji.FEED,
    BTN_REF: emoji.REF,
    BTN_RULES: emoji.RULES,
    BTN_SHOP: emoji.SHOP,
    BTN_SUBS: emoji.SHOP,
}

# Only the two money-making buttons are coloured; the rest stay plain, so the
# green ones read as the actions.
MENU_STYLES = {
    BTN_WATCH: SUCCESS,
    BTN_SHOP: SUCCESS,
    BTN_SUBS: SUCCESS,
    BTN_ANKETAS: None,
    BTN_PROFILE: None,
    BTN_FEED: None,
    BTN_REF: None,
    BTN_RULES: None,
}


def _menu_button(label: str) -> KeyboardButton:
    return KeyboardButton(
        text=menu_label(label),
        icon_custom_emoji_id=emoji.icon(MENU_ICONS[label]),
        style=MENU_STYLES[label],
    )


# Menu presses must never be mistaken for an answer to a prompt — in either
# language, since the keyboard a person has may not be the one we would give
# them today.
_MENU = (
    BTN_AUCTION,
    BTN_WATCH,
    BTN_ANKETAS,
    BTN_PROFILE,
    BTN_FEED,
    BTN_REF,
    BTN_RULES,
    BTN_SHOP,
    BTN_SUBS,
    BTN_UPLOAD,
)
MENU_BUTTONS = frozenset(set(_MENU) | {MENU_EN[b] for b in _MENU})


def main_menu(auction: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [_menu_button(BTN_WATCH)],
        [_menu_button(BTN_ANKETAS)],
        [_menu_button(BTN_PROFILE), _menu_button(BTN_FEED)],
        [_menu_button(BTN_REF), _menu_button(BTN_RULES)],
        [_menu_button(BTN_SHOP), _menu_button(BTN_SUBS)],
    ]
    if auction:
        # Above everything, alone in its row and red: it is the one button here
        # that stops working in two hours.
        rows.insert(0, [KeyboardButton(text=menu_label(BTN_AUCTION), style=DANGER)])
    return ReplyKeyboardMarkup(
        keyboard=rows, resize_keyboard=True, is_persistent=True
    )


def language(current: str = "") -> InlineKeyboardMarkup:
    """Two flags. The one in force is the coloured one, so it is obvious."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🇷🇺 Русский",
            callback_data="lang:ru",
            style=PRIMARY if current == "ru" else None,
        ),
        InlineKeyboardButton(
            text="🇬🇧 English",
            callback_data="lang:en",
            style=PRIMARY if current == "en" else None,
        ),
    )
    return b.as_markup()


def auction_open() -> InlineKeyboardMarkup:
    """Under «тебя перебили»: one tap turns the notice into the live screen."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🔨 Вернуть первое место", "🔨 Take the lead back"), callback_data="auc:open", style=DANGER
        )
    )
    return b.as_markup()


def auction_screen(live: bool = True) -> InlineKeyboardMarkup:
    """Bids first — the whole screen exists to take one."""
    from config import AUCTION_BIDS

    b = InlineKeyboardBuilder()
    if live:
        bids = [
            _coin_button(f"+{amount}", f"auc:bid:{amount}", SUCCESS)
            for amount in AUCTION_BIDS
        ]
        for pair in (bids[:2], bids[2:]):
            if pair:
                b.row(*pair)
        b.row(
            InlineKeyboardButton(
                text=L("✏️ Своя ставка", "✏️ Custom bid"), callback_data="auc:custom", style=PRIMARY
            )
        )
        b.row(_coin_button(L("Пополнить баланс", "Top up the balance"), "buy", SUCCESS))
        b.row(InlineKeyboardButton(text=L("🔄 Обновить", "🔄 Refresh"), callback_data="auc:open"))
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


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
                text=L("Профиль автора", "Author profile"),
                callback_data=f"pf:card:{author_id}",
                icon_custom_emoji_id=emoji.icon(emoji.AUTHOR_PROFILE),
                style=PRIMARY
            )
        )
    elif archive:  # the bot's own seed content: no author to show
        b.row(
            InlineKeyboardButton(text=L("📦 Архив · без автора", "📦 Archive · no author"), callback_data="arch")
        )
    b.row(
        InlineKeyboardButton(
            text=L("Пожаловаться", "Report"),
            callback_data=f"rep:{circle_id}",
            icon_custom_emoji_id=emoji.icon(emoji.REPORT),
            style=DANGER
        )
    )
    b.row(_coin_button(f'Следующий кружок · {settings.get("watch_cost")}', "watch", SUCCESS, icon=emoji.icon(emoji.NEXT_CIRCLE)))
    return b.as_markup()


def push(free: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=(L("👀 Смотреть бесплатно", "👀 Watch for free") if free
             else L("👀 Смотреть кружки", "👀 Watch circles")),
            callback_data="watch",
            style=SUCCESS,
        )
    )
    return b.as_markup()


def feed(pref: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(*[_pref_button(p, p == pref) for p in ("f", "m", "any")])
    return b.as_markup()


def profile(link: str, has_card: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(_coin_button(L("Пополнить баланс", "Top up the balance"), "buy", SUCCESS))
    b.row(
        InlineKeyboardButton(text=L("💸 Вывести заработок", "💸 Withdraw earnings"), callback_data="po:open", style=PRIMARY)
    )
    b.row(InlineKeyboardButton(text="🌐 Язык / Language", callback_data="lang:ask"))
    b.row(
        InlineKeyboardButton(
            text=L("Загрузить кружок", "Upload a circle"),
            callback_data="mp:upload",
            icon_custom_emoji_id=emoji.icon(emoji.UPLOAD),
        ),
        InlineKeyboardButton(
            text=L("Мои кружки", "My circles"),
            callback_data="mp:circles",
            icon_custom_emoji_id=emoji.icon(emoji.MY_CIRCLES),
        ),
    )
    b.row(
        InlineKeyboardButton(
            # «Профиль автора» under a circle opens someone else's card; this one
            # is the user's own shop window, and the two must not share a name.
            text=L("Моя анкета", "My profile"),
            callback_data="pf:edit_menu",
            icon_custom_emoji_id=emoji.icon(emoji.AUTHOR_PROFILE),
        ),
        InlineKeyboardButton(
            text=L("Купленные кружочки", "Circles I bought"),
            callback_data="mp:bought",
            icon_custom_emoji_id=emoji.icon(emoji.SHOP),
        ),
    )
    # The author's own link earns them money, so it sits on the screen they open
    # every day rather than two taps deep inside «Моя анкета».
    if has_card:
        b.row(
            InlineKeyboardButton(
                text=L("🔗 Ссылка на мою анкету", "🔗 Link to my profile"),
                callback_data="pf:link",
                style=PRIMARY,
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("👥 Позвать друга", "👥 Invite a friend"),
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
            text=L("👥 Позвать друга", "👥 Invite a friend"),
            url=f"https://t.me/share/url?url={link}&text="
            "Кружочки без лишних слов",
            style=PRIMARY,
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("📋 Скопировать ссылку", "📋 Copy the link"), copy_text=CopyTextButton(text=link)
        )
    )
    return b.as_markup()


def rules() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text=L("❓ Прочитать FAQ", "❓ Read the FAQ"), callback_data="faq", style=PRIMARY)
    )
    return b.as_markup()


def faq() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("ℹ️ Прочитать Правила", "ℹ️ Read the rules"), callback_data="rules", style=PRIMARY
        )
    )
    return b.as_markup()


# --- author profiles -----------------------------------------------------


def profile_card(
    profile,
    bought_content: bool,
    bought_contact: bool,
    topup: int = 0,
    from_bought: bool = False,
) -> InlineKeyboardMarkup:
    """The buy buttons disappear once the thing is already owned.

    `topup` is what the circles added since the purchase cost, when there are
    enough of them to be worth selling — otherwise nothing is offered.

    `from_bought` means the card replaced «Купленные кружочки», so it carries
    the way back to the list it stands in place of.
    """
    author = profile["user_id"]
    b = InlineKeyboardBuilder()
    if bought_content:
        b.row(
            InlineKeyboardButton(
                text=L("🎬 Кружочки автора", "🎬 Author's circles"), callback_data=f"pf:show:{author}", style=SUCCESS
            )
        )
        if topup:
            b.row(
                _coin_button(
                    f"Докупить новые за {topup}", f"pf:topup:{author}", PRIMARY
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
                "💬 Личка автора" if bought_contact
                else f"Написать в ЛС · {profile['price_contact']}",
                f"pf:contact:{author}",
                PRIMARY,
            )
        )
    # Opened from «Купленные», the card stands where the list was, so the way
    # back is to the list — not on into a feed the reader never asked for.
    if from_bought:
        b.row(
            InlineKeyboardButton(
                text=L("⬅️ К купленным", "⬅️ Back to purchases"), callback_data="mp:bought", style=PRIMARY
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text=L("➡️ Следующая анкета", "➡️ Next profile"), callback_data="pf:next", style=PRIMARY
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("⚠️ Пожаловаться", "⚠️ Report"), callback_data=f"pf:rep:{author}", style=DANGER
        )
    )
    return b.as_markup()


def topup_offer(author_id: int) -> InlineKeyboardMarkup:
    """Goes with the nudge: the card is where the price and the button live."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🎬 Открыть анкету", "🎬 Open the profile"), callback_data=f"pf:card:{author_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def more_circles(author_id: int, offset: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("▶️ Показать ещё", "▶️ Show more"),
            callback_data=f"pf:show:{author_id}:{offset}",
            style=SUCCESS,
        )
    )
    return b.as_markup()


# --- the author's own uploads --------------------------------------------

MY_CIRCLES_TABS = (
    ("approved", "🟢 Одобренные"),
    ("pending", "🕒 На проверке"),
    ("rejected", "🔴 Отклонённые"),
)


def my_circles(stats: dict) -> InlineKeyboardMarkup:
    """The counters, made openable — a status with nothing in it gets no button."""
    b = InlineKeyboardBuilder()
    for status, label in MY_CIRCLES_TABS:
        if stats[status]:
            b.row(
                InlineKeyboardButton(
                    text=f"{label} · {stats[status]}",
                    callback_data=f"mc:{status}:0",
                    style=PRIMARY,
                )
            )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def my_circle(circle_id: int) -> InlineKeyboardMarkup:
    """A video note carries no caption, so the circle's own numbers hide here.

    Deleting lives here too, and nowhere else: a circle is picked out by
    watching it, not by remembering the number it was given on upload.
    """
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("ℹ️ Об этом кружке", "ℹ️ About this circle"), callback_data=f"mc:i:{circle_id}"
        ),
        InlineKeyboardButton(
            text=L("🗑 Удалить", "🗑 Delete"), callback_data=f"mc:del:{circle_id}", style=DANGER
        ),
    )
    return b.as_markup()


def my_circle_confirm(circle_id: int) -> InlineKeyboardMarkup:
    """Deleting cannot be taken back, so it is never the first tap."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🗑 Да, удалить", "🗑 Yes, delete"), callback_data=f"mc:delgo:{circle_id}", style=DANGER
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("⬅️ Оставить", "⬅️ Keep it"), callback_data=f"mc:keep:{circle_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def my_circles_nav(status: str, offset: int | None = None) -> InlineKeyboardMarkup:
    """Closes a batch: more of the same when there is more, the counters always."""
    b = InlineKeyboardBuilder()
    if offset is not None:
        b.row(
            InlineKeyboardButton(
                text=L("▶️ Показать ещё", "▶️ Show more"),
                callback_data=f"mc:{status}:{offset}",
                style=SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("⬅️ К моим кружкам", "⬅️ Back to my circles"), callback_data="mp:circles", style=PRIMARY
        )
    )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
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
            InlineKeyboardButton(text=L("✅ Продавать", "✅ Sell it"), callback_data="pc:yes", style=SUCCESS),
            InlineKeyboardButton(text=L("❌ Не продавать", "❌ Do not sell"), callback_data="pc:no", style=DANGER),
        )
    else:
        b.row(
            InlineKeyboardButton(
                text=L("✅ Добавил(а) юзернейм", "✅ I added a username"), callback_data="pc:recheck", style=SUCCESS
            )
        )
        b.row(
            InlineKeyboardButton(
                text=L("❌ Не продавать личку", "❌ Do not sell my contact"), callback_data="pc:no", style=DANGER
            )
        )
    return b.as_markup()




def profile_edit_menu(profile) -> InlineKeyboardMarkup:
    """Menu for editing individual profile fields."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("📷 Изменить фото", "📷 Change the photo"), callback_data="pf:edit:photo"
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("✏️ Изменить описание", "✏️ Change the description"), callback_data="pf:edit:about"
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("👤 Изменить пол", "👤 Change who you are"), callback_data="pf:edit:gender"
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("💰 Изменить цену кружков", "💰 Change the circles price"),
            callback_data="pf:edit:price_content",
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("💬 Изменить цену контакта", "💬 Change the contact price"),
            callback_data="pf:edit:price_contact",
        )
    )
    if profile and profile["status"] == "approved":
        import db

        b.row(
            InlineKeyboardButton(
                text=L("🚀 Продвижение", "🚀 Promotion")
            + (L(" · идёт", " · running") if db.boost_on(profile) else ""),
                callback_data="pf:boost",
                style=SUCCESS,
            )
        )
        b.row(
            InlineKeyboardButton(
                text=L("🚫 Скрыть анкету", "🚫 Hide my profile"), callback_data="pf:hide"
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("📝 Заполнить заново", "📝 Fill it in again"), callback_data="pf:start"
        )
    )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def profile_link(link: str) -> InlineKeyboardMarkup:
    """Copy it, or hand it straight to a chat — both in one tap."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text=L("📋 Скопировать", "📋 Copy"), copy_text=CopyTextButton(text=link))
    )
    b.row(
        InlineKeyboardButton(
            text=L("📤 Поделиться", "📤 Share"),
            url=f"https://t.me/share/url?url={quote(link)}",
            style=PRIMARY,
        )
    )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def boost_packs() -> InlineKeyboardMarkup:
    """Days, priced off one setting so the packs stay in proportion."""
    from config import BOOST_PACKS

    b = InlineKeyboardBuilder()
    for days, discount in BOOST_PACKS:
        b.row(
            InlineKeyboardButton(
                text=f"{days} {L('дн', 'd')} · {settings.boost_price(days, discount)} "
                f"{emoji.plain(emoji.COIN)}"
                + (f" · −{discount}%" if discount else ""),
                callback_data=f"pf:boost:{days}",
                style=SUCCESS,
            )
        )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def contact_price_edit() -> InlineKeyboardMarkup:
    """Editing the contact price is also the only way to stop selling it."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🚫 Не продавать личку", "🚫 Stop selling my contact"), callback_data="pc:no", style=DANGER
        )
    )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def profile_review(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ Одобрить", callback_data=f"pm:ok:{user_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"pm:no:{user_id}", style=DANGER
        ),
    )
    return b.as_markup()


def profile_decided(user_id: int) -> InlineKeyboardMarkup:
    """A verdict is never final: the card keeps a way back to the buttons."""
    return decided(f"pm:again:{user_id}")


def profile_report_decided(user_id: int) -> InlineKeyboardMarkup:
    """Same, for a card that came from a complaint rather than from the queue."""
    return decided(f"pm:ragain:{user_id}")


def profile_intro() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("✅ Соглашаюсь, настроить профиль", "✅ I agree, set up my profile"),
            callback_data="pf:start",
            style=SUCCESS,
        )
    )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def refill_profile() -> InlineKeyboardMarkup:
    """Goes with a rejection — the fix is one tap away, not a menu hunt."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("📝 Заполнить заново", "📝 Fill it in again"), callback_data="pf:start", style=SUCCESS
        )
    )
    return b.as_markup()


def fix_profile() -> InlineKeyboardMarkup:
    """Goes with a freeze: the anketa is intact, so it opens rather than restarts."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🧾 Моя анкета", "🧾 My profile"), callback_data="pf:edit_menu", style=SUCCESS
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
            text="🚫 Скрыть анкету", callback_data=f"pm:hide:{user_id}", style=DANGER
        ),
        InlineKeyboardButton(
            text="✅ Оставить", callback_data=f"pm:keep:{user_id}", style=SUCCESS
        ),
    )
    return b.as_markup()


# --- payouts -------------------------------------------------------------


def payout(can_request: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_request:
        b.row(
            InlineKeyboardButton(
                text=L("💸 Оформить вывод", "💸 Request a payout"), callback_data="po:new", style=SUCCESS
            )
        )
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def payout_review(payout_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ Выплачено", callback_data=f"pw:paid:{payout_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"pw:no:{payout_id}", style=DANGER
        ),
    )
    return b.as_markup()


def report_reasons(circle_id: int) -> InlineKeyboardMarkup:
    """Replaces the circle's buttons while the complaint is being named."""
    import texts

    b = InlineKeyboardBuilder()
    for key, label in texts.report_reasons().items():
        b.row(
            InlineKeyboardButton(
                text=label, callback_data=f"rep:r:{key}:{circle_id}", style=DANGER
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("⬅️ Отмена", "⬅️ Cancel"), callback_data=f"rep:back:{circle_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def profile_report_reasons(author_id: int) -> InlineKeyboardMarkup:
    import texts

    b = InlineKeyboardBuilder()
    for key, label in texts.profile_report_reasons().items():
        b.row(
            InlineKeyboardButton(
                text=label, callback_data=f"pf:rr:{key}:{author_id}", style=DANGER
            )
        )
    b.row(
        InlineKeyboardButton(
            text=L("⬅️ Отмена", "⬅️ Cancel"), callback_data=f"pf:rback:{author_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def report_review(circle_id: int) -> InlineKeyboardMarkup:
    """Hiding sits between the two verdicts: it is the one that can be undone."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🚫 Скрыть", callback_data=f"rp:hide:{circle_id}", style=DANGER
        ),
        InlineKeyboardButton(
            text="✅ Оставить", callback_data=f"rp:keep:{circle_id}", style=SUCCESS
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="🗑️ Удалить навсегда",
            callback_data=f"rp:del:{circle_id}",
            style=DANGER,
        )
    )
    return b.as_markup()


def decided(callback_data: str) -> InlineKeyboardMarkup:
    """A verdict is never the end of the conversation — except after a delete."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🔄 Изменить решение", callback_data=callback_data, style=PRIMARY
        )
    )
    return b.as_markup()


def no_coins() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # Uploading only pays while there is a reward for it; with rewards off the
    # way to earn is an anketa people buy, and the button has to say so.
    earn = (
        _coin_button("Заработать", "upload", SUCCESS)
        if settings.reward("f") or settings.reward("m")
        else _coin_button("Зарабатывать", "pf:edit_menu", SUCCESS)
    )
    kb.row(earn, _coin_button("Купить", "buy", SUCCESS))
    kb.row(InlineKeyboardButton(text=L("⬅️ Назад", "⬅️ Back"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def empty_feed(pref: str) -> InlineKeyboardMarkup:
    """Nothing left of this type — the fix is the type switch, not the wallet."""
    b = InlineKeyboardBuilder()
    b.row(*[_pref_button(p, p == pref) for p in ("f", "m", "any")])
    b.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return b.as_markup()


def back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def buy() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    # The coin goes last here, so it cannot be the button icon (that slot always
    # renders first) — a plain emoji in the label is the only way round it.
    packs = [
        InlineKeyboardButton(
            text=f'{stars} ⭐ = {settings.coins_for(stars)} {emoji.plain(emoji.COIN)}',
            callback_data=f"pay:{stars}",
            style=SUCCESS,
        )
        for stars in STAR_PACKS
    ]
    kb.row(*packs[:2])
    kb.row(*packs[2:])
    kb.row(
        InlineKeyboardButton(
            text=L("✏️ Своя сумма", "✏️ Custom amount"), callback_data="pay:custom", style=PRIMARY
        )
    )
    kb.row(InlineKeyboardButton(text=L("⬅️ Назад", "⬅️ Back"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def buy_payment_method() -> InlineKeyboardMarkup:
    """Card first, then Stars, then whichever crypto has a key configured."""
    import crypto
    import paritypay

    kb = InlineKeyboardBuilder()
    if paritypay.enabled():
        # The bonus is the reason to press this one, so it goes on the button.
        extra = settings.get("card_bonus")
        kb.row(
            InlineKeyboardButton(
                text=f"{paritypay.ICON} {paritypay.method_label()}"
                + (f" · +{extra}% 🎁" if extra else ""),
                callback_data=f"pay_method:{paritypay.PROVIDER}",
                style=SUCCESS,
            )
        )
    kb.row(
        InlineKeyboardButton(
            text=L("⭐ Telegram Stars", "⭐ Telegram Stars"),
            callback_data="pay_method:stars",
            style=SUCCESS,
        )
    )
    for provider in crypto.available():
        kb.row(
            InlineKeyboardButton(
                text=f"{crypto.ICONS[provider]} {crypto.TITLES[provider]} · "
                f"{L('крипта', 'crypto')}",
                callback_data=f"pay_method:{provider}",
                style=PRIMARY,
            )
        )
    kb.row(InlineKeyboardButton(text=L("❌ Отмена", "❌ Cancel"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def cheque(code: str) -> InlineKeyboardMarkup:
    """A deep link, not a callback: the reader is not in the bot's chat yet."""
    import access

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🎟 Забрать монетки", "🎟 Claim the coins"),
            url=f"https://t.me/{access.bot_username}?start=chq_{code}",
            style=SUCCESS,
        )
    )
    return b.as_markup()


def crypto_invoice(provider: str, invoice_id: str, link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=L("💳 Оплатить", "💳 Pay"), url=link, style=SUCCESS))
    b.row(
        InlineKeyboardButton(
            text=L("🔄 Проверить оплату", "🔄 Check the payment"),
            callback_data=f"inv:check:{provider}:{invoice_id}",
            style=PRIMARY,
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("❌ Отменить счёт", "❌ Cancel the invoice"),
            callback_data=f"inv:drop:{provider}:{invoice_id}",
            style=DANGER,
        )
    )
    return b.as_markup()


def buy_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=L("❌ Отмена", "❌ Cancel"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def tiers_menu(sub_order: str = "") -> InlineKeyboardMarkup:
    """One button per tier, each carrying its own price a day.

    A running auto-renewal gets its off switch on this same screen: the offer
    documents promise cancelling is no harder than starting.
    """
    import tiers

    kb = InlineKeyboardBuilder()
    if sub_order:
        kb.row(
            InlineKeyboardButton(
                text=L("🚫 Отключить автопродление", "🚫 Stop auto-renewal"),
                callback_data=f"tsub:drop:{sub_order}",
                style=DANGER,
            )
        )
    # The price is what the coin belongs to, but a button icon always renders
    # first — so the coin leads the button and the price stays bare. A label
    # cannot hold a premium emoji at all: that field takes no entities.
    for code in tiers.ORDER:
        mark = "⭐ " if code == tiers.PRO else ""
        kb.row(
            _coin_button(
                f"{mark}Подписка {tiers.title(code)} · "
                f"{tiers.price_of(code, 1)}/день",
                f"tier:{code}",
                SUCCESS if code == tiers.PRO else PRIMARY,
            )
        )
    kb.row(InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))
    return kb.as_markup()


def tier_buy(code: str) -> InlineKeyboardMarkup:
    """A day, a week, a month — the same price a day, counted out."""
    import tiers

    kb = InlineKeyboardBuilder()
    for days in tiers.DAYS:
        kb.row(
            _coin_button(
                f"{days} дн · {tiers.price_of(code, days)}",
                f"tier:buy:{code}:{days}",
                SUCCESS,
            )
        )
    kb.row(
        InlineKeyboardButton(text=L("⬅️ К подпискам", "⬅️ Back to subscriptions"), callback_data="tier:list"),
        InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER),
    )
    return kb.as_markup()


def tier_pay(code: str, days: int) -> InlineKeyboardMarkup:
    """How to pay for a chosen tier and length. Auto-renewal leads when it can."""
    import paritypay
    import settings
    import tiers

    kb = InlineKeyboardBuilder()
    if paritypay.recurring_on() and paritypay.interval_of(days):
        kb.row(
            InlineKeyboardButton(
                text=L("🔁 С автопродлением · ", "🔁 Auto-renewing · ")
                + f"{settings.card_rubles(tiers.price_of(code, days))} ₽",
                callback_data=f"tier:sub:{code}:{days}",
                style=SUCCESS,
            )
        )
    kb.row(
        _coin_button(
            f"{L('Монетками', 'In coins')} · {tiers.price_of(code, days)}",
            f"tier:coins:{code}:{days}",
            PRIMARY,
        )
    )
    kb.row(
        InlineKeyboardButton(text=L("⬅️ Назад", "⬅️ Back"), callback_data=f"tier:{code}"),
        InlineKeyboardButton(text=L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER),
    )
    return kb.as_markup()


def tier_sub_invoice(order_id: str, link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=L("💳 Оплатить", "💳 Pay"), url=link, style=SUCCESS))
    b.row(
        InlineKeyboardButton(
            text=L("🔄 Проверить оплату", "🔄 Check the payment"),
            callback_data=f"tsub:check:{order_id}",
            style=PRIMARY,
        )
    )
    b.row(
        InlineKeyboardButton(
            text=L("❌ Отменить", "❌ Cancel"), callback_data=f"tsub:drop:{order_id}", style=DANGER
        )
    )
    return b.as_markup()


def tier_sub_manage(order_id: str) -> InlineKeyboardMarkup:
    """Cancelling has to be as easy as starting — see the offer documents."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=L("🚫 Отключить автопродление", "🚫 Stop auto-renewal"),
            callback_data=f"tsub:drop:{order_id}",
            style=DANGER,
        )
    )
    b.row(InlineKeyboardButton(text=L("⬅️ К подпискам", "⬅️ Back to subscriptions"), callback_data="tier:list"))
    return b.as_markup()


def moderation(circle_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(
            text="✅ Одобрить", callback_data=f"mod:ok:{circle_id}", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"mod:no:{circle_id}", style=DANGER
        ),
    )
    return kb.as_markup()


def circle_reasons(circle_id: int) -> InlineKeyboardMarkup:
    """Why the circle is being turned down — the author gets told."""
    from texts import CIRCLE_REJECT_REASONS

    b = InlineKeyboardBuilder()
    for key, label in CIRCLE_REJECT_REASONS.items():
        b.row(
            InlineKeyboardButton(
                text=label.capitalize(),
                callback_data=f"mod:r:{key}:{circle_id}",
                style=DANGER,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="Своя причина", callback_data=f"mod:rc:{circle_id}", style=PRIMARY
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Назад", callback_data=f"mod:back:{circle_id}", style=SUCCESS
        )
    )
    return b.as_markup()


def circle_decided(circle_id: int) -> InlineKeyboardMarkup:
    return decided(f"mod:again:{circle_id}")


def report_decided(circle_id: int) -> InlineKeyboardMarkup:
    return decided(f"rp:again:{circle_id}")



