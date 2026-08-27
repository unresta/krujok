"""Keyboards.

Same conventions as the main bot: `style` colours the buttons ('primary' blue,
'success' green, 'danger' red), the main menu is a reply keyboard that cannot
scroll away, and every screen keeps a way back.

No custom emoji here — the support bot has no Premium requirement, so labels
carry plain unicode and always render.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from texts import TOPICS

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"

# --- main menu -----------------------------------------------------------

BTN_NEW = "Новое обращение"
BTN_MY = "Мои обращения"
BTN_FAQ = "Частые вопросы"

MENU_BUTTONS = frozenset({BTN_NEW, BTN_MY, BTN_FAQ})


def main_menu() -> ReplyKeyboardMarkup:
    """Three buttons is the whole bot: write, check, read."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW, style=SUCCESS)],
            [KeyboardButton(text=BTN_MY), KeyboardButton(text=BTN_FAQ)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def topics() -> InlineKeyboardMarkup:
    """Two per row, so six topics fit on one screen without scrolling."""
    b = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"t:{code}")
        for code, (label, _) in TOPICS.items()
    ]
    for i in range(0, len(buttons), 2):
        b.row(*buttons[i : i + 2])
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="close", style=DANGER))
    return b.as_markup()


def hint(topic: str) -> InlineKeyboardMarkup:
    """The self-service screen: solved, or straight on to a human."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Не помогло, писать в поддержку",
            callback_data=f"w:{topic}",
            style=SUCCESS,
        )
    )
    b.row(
        InlineKeyboardButton(text="Другая тема", callback_data="new", style=PRIMARY),
        InlineKeyboardButton(text="Решилось", callback_data="solved", style=DANGER),
    )
    return b.as_markup()


def cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Отмена", callback_data="close", style=DANGER))
    return b.as_markup()


def close() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="close", style=DANGER))
    return b.as_markup()


def already_open(ticket_id: int) -> InlineKeyboardMarkup:
    """Shown when a new ticket is refused because one is still open.

    Closing it is what unblocks a new one, so the way out belongs on this very
    screen instead of sending the user hunting through «Мои обращения».
    """
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Открыть переписку", callback_data=f"my:{ticket_id}", style=PRIMARY
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Вопрос решён, закрыть",
            callback_data=f"done:{ticket_id}",
            style=SUCCESS,
        )
    )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="close", style=DANGER))
    return b.as_markup()


def my_tickets(rows: list) -> InlineKeyboardMarkup:
    """One button per ticket — tapping it shows the thread."""
    b = InlineKeyboardBuilder()
    for t in rows:
        b.row(
            InlineKeyboardButton(
                text=f"#{t['id']} · {t['topic']}",
                callback_data=f"my:{t['id']}",
                style=PRIMARY if t["status"] != "closed" else None,
            )
        )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="close", style=DANGER))
    return b.as_markup()


def thread_back(ticket=None) -> InlineKeyboardMarkup:
    """A user looking at their own thread can resolve it from here.

    The button only exists while the ticket is open, and it is not styled
    `danger`: closing your own solved question is a normal, harmless action, not
    a destructive one.
    """
    b = InlineKeyboardBuilder()
    if ticket is not None and ticket["status"] != "closed":
        b.row(
            InlineKeyboardButton(
                text="Вопрос решён, закрыть",
                callback_data=f"done:{ticket['id']}",
                style=SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(text="К списку", callback_data="my", style=PRIMARY),
        InlineKeyboardButton(text="Закрыть", callback_data="close", style=DANGER),
    )
    return b.as_markup()


def rate(ticket_id: int) -> InlineKeyboardMarkup:
    """Asked once, right after closing, while the impression is fresh."""
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="👍 Помогли", callback_data=f"r:{ticket_id}:1", style=SUCCESS
        ),
        InlineKeyboardButton(
            text="👎 Не помогли", callback_data=f"r:{ticket_id}:-1", style=DANGER
        ),
    )
    return b.as_markup()


# --- the card in the support chat ---------------------------------------


def card(ticket_id: int, status: str, taken: bool, blocked: bool = False) -> InlineKeyboardMarkup:
    """Buttons under a ticket card.

    "Взять" disappears once somebody holds it, so two moderators do not answer
    the same person. Everything else stays available until the ticket closes.
    """
    b = InlineKeyboardBuilder()
    row = []
    if not taken and status != "closed":
        row.append(
            InlineKeyboardButton(
                text="Взять", callback_data=f"a:take:{ticket_id}", style=SUCCESS
            )
        )
    if status != "closed":
        row.append(
            InlineKeyboardButton(
                text="Закрыть", callback_data=f"a:close:{ticket_id}", style=DANGER
            )
        )
    if row:
        b.row(*row)

    if status != "closed":
        b.row(
            InlineKeyboardButton(
                text="Шаблон", callback_data=f"a:canned:{ticket_id}", style=PRIMARY
            ),
            InlineKeyboardButton(
                text="Переписка", callback_data=f"a:thread:{ticket_id}", style=PRIMARY
            ),
        )
    else:
        b.row(
            InlineKeyboardButton(
                text="Переписка", callback_data=f"a:thread:{ticket_id}", style=PRIMARY
            )
        )
    b.row(
        InlineKeyboardButton(
            text="Разблокировать" if blocked else "Заблокировать",
            callback_data=f"a:block:{ticket_id}:{0 if blocked else 1}",
            style=SUCCESS if blocked else DANGER,
        )
    )
    return b.as_markup()


def canned_pick(ticket_id: int, rows: list) -> InlineKeyboardMarkup:
    """Templates offered for one ticket; sending one answers the user at once."""
    b = InlineKeyboardBuilder()
    for c in rows:
        b.row(
            InlineKeyboardButton(
                text=c["title"],
                callback_data=f"a:send:{ticket_id}:{c['id']}",
                style=SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="Назад к обращению", callback_data=f"a:card:{ticket_id}", style=DANGER
        )
    )
    return b.as_markup()


# --- admin panel ---------------------------------------------------------


def panel(waiting: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"Очередь · {waiting}",
            callback_data="p:queue",
            style=SUCCESS if waiting else None,
        ),
        InlineKeyboardButton(text="По темам", callback_data="p:topics", style=PRIMARY),
    )
    b.row(
        InlineKeyboardButton(text="Шаблоны", callback_data="p:canned", style=PRIMARY),
        InlineKeyboardButton(text="Пользователь", callback_data="p:user", style=PRIMARY),
    )
    b.row(
        InlineKeyboardButton(text="Чат поддержки", callback_data="p:chat", style=PRIMARY)
    )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="p:close", style=DANGER))
    return b.as_markup()


def panel_back(extra: list[InlineKeyboardButton] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for button in extra or []:
        b.row(button)
    b.row(InlineKeyboardButton(text="В панель", callback_data="p:home", style=DANGER))
    return b.as_markup()


def queue(rows: list) -> InlineKeyboardMarkup:
    """Each queued ticket gets a button that re-sends its card."""
    b = InlineKeyboardBuilder()
    for t in rows:
        b.row(
            InlineKeyboardButton(
                text=f"#{t['id']} · {t['user_id']}",
                callback_data=f"a:card:{t['id']}",
                style=PRIMARY,
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="p:home", style=DANGER))
    return b.as_markup()


def canned_manage(rows: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Добавить", callback_data="p:canned:new", style=SUCCESS)
    )
    for c in rows:
        b.row(
            InlineKeyboardButton(
                text=f"Удалить «{c['title'][:20]}»",
                callback_data=f"p:canned:del:{c['id']}",
                style=DANGER,
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="p:home", style=DANGER))
    return b.as_markup()
