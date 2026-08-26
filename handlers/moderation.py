from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery

import db
import texts
import settings
from config import ADMIN_CHAT_ID, ADMIN_IDS

router = Router()


def _is_moderator(call: CallbackQuery) -> bool:
    return call.message.chat.id == ADMIN_CHAT_ID or call.from_user.id in ADMIN_IDS


@router.callback_query(F.data.startswith("mod:"))
async def review(call: CallbackQuery) -> None:
    if not _is_moderator(call):
        await call.answer("Нет прав.", show_alert=True)
        return

    _, verdict, raw_id = call.data.split(":")
    circle_id = int(raw_id)
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок не найден.", show_alert=True)
        return

    status = "approved" if verdict == "ok" else "rejected"
    if not await db.review_circle(circle_id, status, call.from_user.id):
        await call.answer("Уже обработан.", show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)
        return

    uploader = circle["uploader_id"]
    if status == "approved":
        reward = settings.reward(circle["gender"])
        await db.add_coins(uploader, reward)
        balance = (await db.get_user(uploader))["coins"]
        note = texts.approved(reward, balance)
    else:
        note = texts.REJECTED

    with suppress(TelegramAPIError):  # user may have blocked the bot
        await call.bot.send_message(uploader, note)

    mark = "🟢 одобрено" if status == "approved" else "🔴 отклонено"
    who = call.from_user.username and f"@{call.from_user.username}" or call.from_user.id
    with suppress(TelegramAPIError):
        await call.message.edit_text(
            f"{call.message.html_text}\n\n<b>{mark}</b> · {who}",
            reply_markup=None,
        )
    await call.answer(mark)
