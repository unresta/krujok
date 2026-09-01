from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

import access
import db
import posts
import texts
import ui
from handlers import cheques, common

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
    # A gate message people come back to days later is out of reach by then —
    # and going through it anyway left them past the gate with an empty screen.
    message = ui.live(call)
    if message is not None:
        with suppress(TelegramAPIError):  # already gone
            await message.delete()
    await posts.show_welcome(call.bot, call.from_user.id)
    # The cheque that sent them here in the first place.
    code = await db.take_pending_cheque(call.from_user.id)
    if code:
        await cheques.redeem(call.bot, call.from_user.id, code)
    await ui.render_menu(call, call.from_user.id)
    # …or the author whose link they followed.
    await common.open_pending_profile(call.bot, call.from_user.id)
