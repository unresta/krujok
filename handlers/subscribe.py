from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import access
import texts
import ui

router = Router()


@router.callback_query(F.data == "sub:check")
async def check(call: CallbackQuery, state: FSMContext) -> None:
    access.forget(call.from_user.id)  # the cache must not answer for Telegram
    if not await access.is_subscribed(call.bot, call.from_user.id):
        await call.answer(texts.SUBSCRIBE_MISSING, show_alert=True)
        return

    await state.clear()
    await access.credit_referral(call.bot, call.from_user.id)
    await call.answer(texts.SUBSCRIBE_OK)
    with suppress(TelegramAPIError):  # older than 48h, or already gone
        await call.message.delete()
    await ui.render_menu(call.message, call.from_user.id)
