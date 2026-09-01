"""One panel per user: edit it in place instead of piling up messages."""

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts


def live(event: Message | CallbackQuery) -> Message | None:
    """The message we may still write through, or None if Telegram closed it.

    A callback on a message older than two days comes back with an
    `InaccessibleMessage` in place of the message: it carries an id and a chat
    and none of the methods. Reaching for `answer` or `delete` on one raises
    `AttributeError`, which no `suppress(TelegramAPIError)` around it catches —
    that is how a tap on an old button killed the handler halfway through, after
    the toast had already gone out and before anything was sent.
    """
    message = event if isinstance(event, Message) else event.message
    return message if isinstance(message, Message) else None


async def render_menu(event: Message | CallbackQuery, user_id: int) -> None:
    """The main menu is a reply keyboard, so it cannot scroll out of reach."""
    user = await db.get_user(user_id)
    text = texts.menu(user["coins"], user["pref"])
    message = live(event)
    if message is not None:
        await message.answer(text, reply_markup=kb.main_menu())
    else:
        await event.bot.send_message(user_id, text, reply_markup=kb.main_menu())


async def edit(call: CallbackQuery, text: str, markup=None) -> None:
    if isinstance(call.message, Message):
        with suppress(TelegramBadRequest):
            await call.message.edit_text(text, reply_markup=markup)
