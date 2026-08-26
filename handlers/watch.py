import time
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
import ui
from config import WATCH_COOLDOWN, WATCH_COST

router = Router()

_last_tap: dict[int, float] = {}


@router.callback_query(F.data == "watch")
async def watch(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = call.from_user.id

    now = time.monotonic()
    if now - _last_tap.get(user_id, 0.0) < WATCH_COOLDOWN:
        await call.answer("Не так быстро 🙂")
        return
    _last_tap[user_id] = now

    user = await db.get_user(user_id)
    if user["coins"] < WATCH_COST:
        await ui.edit(call, texts.not_enough(user["coins"]), kb.no_coins())
        await call.answer()
        return

    circle = await db.pick_circle(user_id, user["pref"])
    if circle is None:
        await ui.edit(call, texts.EMPTY, kb.no_coins())
        await call.answer()
        return

    if not await db.try_spend(user_id, WATCH_COST):  # raced with another tap
        await ui.edit(call, texts.not_enough(user["coins"]), kb.no_coins())
        await call.answer()
        return

    await call.answer()
    if isinstance(call.message, Message):
        with suppress(TelegramAPIError):
            await call.message.delete()  # panel always stays under the circle

    try:
        await call.bot.send_video_note(
            chat_id=user_id,
            video_note=circle["file_id"],
            protect_content=True,  # no forwarding, no saving
        )
    except TelegramAPIError:
        await db.add_coins(user_id, WATCH_COST)  # nothing delivered, nothing charged
        await call.bot.send_message(
            user_id, "Не удалось отправить кружок, монетки вернул.", reply_markup=kb.back()
        )
        return

    await db.mark_viewed(user_id, circle["id"])
    left = (await db.get_user(user_id))["coins"]
    await call.bot.send_message(
        user_id,
        f"{texts.coin()} <b>{left}</b>",
        reply_markup=kb.after_watch(user["pref"]),
    )
