"""One panel per user: edit it in place instead of piling up messages."""

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
from config import WATCH_COST


async def render_menu(event: Message | CallbackQuery, user_id: int) -> None:
    user = await db.get_user(user_id)
    text = texts.menu(user["coins"], user["pref"])
    markup = kb.menu(user["pref"], user["coins"] >= WATCH_COST)

    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        with suppress(TelegramBadRequest):  # "message is not modified"
            await event.message.edit_text(text, reply_markup=markup)
        return

    message = event if isinstance(event, Message) else event.message
    await message.answer(text, reply_markup=markup)


async def edit(call: CallbackQuery, text: str, markup=None) -> None:
    if isinstance(call.message, Message):
        with suppress(TelegramBadRequest):
            await call.message.edit_text(text, reply_markup=markup)
