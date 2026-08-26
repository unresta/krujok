import logging
import time
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import settings
import texts
from config import ADMIN_CHAT_ID, ADMIN_IDS, WATCH_COOLDOWN

logger = logging.getLogger(__name__)

router = Router()

_last_tap: dict[int, float] = {}


@router.message(F.text == kb.BTN_WATCH)
async def watch_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await serve(message.bot, message.from_user.id, message)


@router.callback_query(F.data == "watch")
async def watch_callback(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    now = time.monotonic()
    if now - _last_tap.get(call.from_user.id, 0.0) < WATCH_COOLDOWN:
        await call.answer("Не так быстро 🙂")
        return
    _last_tap[call.from_user.id] = now

    await call.answer()
    # The buttons under a watched circle stay, but only the newest one works.
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)
    await serve(call.bot, call.from_user.id, call.message)


async def serve(bot, user_id: int, origin: Message) -> None:
    """Charge, send one circle, pay its author."""
    user = await db.get_user(user_id)
    cost = settings.get("watch_cost")

    if user["coins"] < cost:
        await origin.answer(texts.not_enough(user["coins"]), reply_markup=kb.no_coins())
        return

    circle = await db.pick_circle(user_id, user["pref"])
    if circle is None:
        await origin.answer(texts.EMPTY, reply_markup=kb.no_coins())
        return
    if not await db.try_spend(user_id, cost):  # raced with another tap
        await origin.answer(texts.not_enough(user["coins"]), reply_markup=kb.no_coins())
        return

    try:
        await bot.send_video_note(
            chat_id=user_id,
            video_note=circle["file_id"],
            protect_content=True,  # no forwarding, no saving
            reply_markup=kb.circle(circle["id"], circle["likes"], circle["dislikes"], 0),
        )
    except TelegramAPIError:
        await db.add_coins(user_id, cost)  # nothing delivered, nothing charged
        await origin.answer("Не удалось отправить кружок, монетки вернул.")
        return

    await db.mark_viewed(user_id, circle["id"])
    await _pay_author(bot, circle, settings.get("view_payout"), texts.earned_toast)


async def _pay_author(bot, circle, amount: int, note) -> None:
    author = circle["uploader_id"]
    if not author or not amount:
        return
    await db.pay_author(circle["id"], author, amount)
    with suppress(TelegramAPIError):  # author may have blocked the bot
        await bot.send_message(author, note(amount))


@router.callback_query(F.data.startswith("lk:"))
async def react(call: CallbackQuery) -> None:
    _, raw_id, raw_value = call.data.split(":")
    circle_id, value = int(raw_id), int(raw_value)

    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок удалён.", show_alert=True)
        return
    if circle["uploader_id"] == call.from_user.id:
        await call.answer("Свой кружок оценивать нечестно 🙂")
        return

    vote, likes, dislikes, fresh_like = await db.set_reaction(
        call.from_user.id, circle_id, value
    )
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=kb.circle(circle_id, likes, dislikes, vote)
        )
    await call.answer("👍" if vote == 1 else "👎" if vote == -1 else "Отменил")

    if fresh_like:
        await _pay_author(
            call.bot,
            circle,
            settings.get("like_bonus"),
            lambda amount: f"👍 Твой кружок лайкнули: +{amount}",
        )


@router.callback_query(F.data.startswith("rep:"))
async def report(call: CallbackQuery) -> None:
    circle_id = int(call.data.split(":")[1])
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок уже удалён.", show_alert=True)
        return

    count = await db.add_report(call.from_user.id, circle_id)
    if count is None:
        await call.answer(texts.REPORT_DOUBLE, show_alert=True)
        return
    await call.answer(texts.REPORT_SENT, show_alert=True)

    # Enough complaints and the circle leaves rotation before a human looks.
    hidden = count >= settings.get("reports_to_hide")
    if hidden and circle["status"] == "approved":
        await db.set_status(circle_id, "rejected")

    chat = settings.reports_chat()
    try:
        await call.bot.send_video_note(chat, circle["file_id"])
        await call.bot.send_message(
            chat,
            f"#жалоба на <b>#{circle_id}</b> — {count} шт\n"
            f"Тип: {kb.PREF_TITLE(circle['gender'])} · {circle['duration']} сек\n"
            f"Автор: <code>{circle['uploader_id']}</code>\n"
            f"Статус: {'скрыт автоматически' if hidden else circle['status']}",
            reply_markup=kb.report_review(circle_id),
        )
    except TelegramAPIError as error:
        # The complaint is already in the base; only the card failed to land.
        logger.error("report card for #%s not delivered to %s: %s", circle_id, chat, error)


@router.callback_query(F.data.startswith("rp:"))
async def review_report(call: CallbackQuery) -> None:
    # The verdict buttons live in a group chat, so anyone could otherwise guess
    # the callback data and delete circles from their own chat with the bot.
    if not (
        call.from_user.id in ADMIN_IDS
        or str(call.message.chat.id) == str(settings.reports_chat())
        or call.message.chat.id == ADMIN_CHAT_ID
    ):
        await call.answer("Нет прав.", show_alert=True)
        return

    _, action, raw_id = call.data.split(":")
    circle_id = int(raw_id)
    circle = await db.get_circle(circle_id)
    await db.clear_reports(circle_id)

    if action == "del":
        if circle and circle["uploader_id"]:
            with suppress(TelegramAPIError):
                await call.bot.send_message(
                    circle["uploader_id"], texts.CIRCLE_REMOVED
                )
        await db.delete_circle(circle_id)
        verdict = "🔴 удалён"
    else:
        if circle:
            await db.set_status(circle_id, "approved")
        verdict = "🟢 оставлен"

    with suppress(TelegramAPIError):
        await call.message.edit_text(
            f"{call.message.html_text}\n\n<b>{verdict}</b>", reply_markup=None
        )
    await call.answer(verdict)
