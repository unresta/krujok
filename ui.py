"""One panel per user: edit it in place instead of piling up messages."""

from contextlib import suppress

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts


async def render_menu(event: Message | CallbackQuery, user_id: int) -> None:
    """The main menu is a reply keyboard, so it cannot scroll out of reach."""
    user = await db.get_user(user_id)
    message = event if isinstance(event, Message) else event.message
    await message.answer(
        texts.menu(user["coins"], user["pref"]), reply_markup=kb.main_menu()
    )


async def edit(call: CallbackQuery, text: str, markup=None) -> None:
    if isinstance(call.message, Message):
        with suppress(TelegramBadRequest):
            await call.message.edit_text(text, reply_markup=markup)
