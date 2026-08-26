"""Withdrawal requests.

The Bot API cannot send Stars to a user — a bot may only refund its own charges
or send gifts — so a payout is a request: the coins freeze, a card lands in the
payouts chat, an admin pays outside the bot and marks it done. A rejected
request puts the coins back.
"""

import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import settings
import texts
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

router = Router()


class Payout(StatesGroup):
    amount = State()
    details = State()


@router.callback_query(F.data == "po:open")
async def screen(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    available = await db.withdrawable(call.from_user.id)
    pending = len(
        [p for p in await db.open_payouts(100) if p["user_id"] == call.from_user.id]
    )
    await call.message.answer(
        texts.payout_screen(available, pending),
        reply_markup=kb.payout(available >= settings.get("payout_min")),
    )
    await call.answer()


@router.callback_query(F.data == "po:new")
async def ask_amount(call: CallbackQuery, state: FSMContext) -> None:
    available = await db.withdrawable(call.from_user.id)
    if available < settings.get("payout_min"):
        await call.answer(texts.payout_too_small(available), show_alert=True)
        return
    await state.set_state(Payout.amount)
    await call.message.answer(texts.payout_ask_amount(available), reply_markup=kb.back())
    await call.answer()


@router.message(Payout.amount, ~F.text.in_(kb.MENU_BUTTONS))
async def got_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    available = await db.withdrawable(message.from_user.id)
    if not raw.isdigit() or not (settings.get("payout_min") <= int(raw) <= available):
        await message.answer(texts.payout_ask_amount(available), reply_markup=kb.back())
        return

    await state.update_data(coins=int(raw))
    await state.set_state(Payout.details)
    await message.answer(texts.PAYOUT_ASK_DETAILS, reply_markup=kb.back())


@router.message(Payout.details, ~F.text.in_(kb.MENU_BUTTONS))
async def got_details(message: Message, state: FSMContext) -> None:
    details = (message.text or "").strip()
    if not 3 <= len(details) <= 200:
        await message.answer(texts.PAYOUT_ASK_DETAILS, reply_markup=kb.back())
        return

    coins = (await state.get_data())["coins"]
    await state.clear()
    stars = settings.stars_for(coins)

    payout_id = await db.create_payout(message.from_user.id, coins, stars, details)
    if payout_id is None:  # balance moved while the form was open
        available = await db.withdrawable(message.from_user.id)
        await message.answer(texts.payout_too_small(available), reply_markup=kb.back())
        return

    await message.answer(texts.payout_created(payout_id, coins, stars))

    who = message.from_user.username and f"@{message.from_user.username}" or "—"
    chat = settings.reports_chat()  # payouts share the moderation-side chat
    try:
        card = await message.bot.send_message(
            chat,
            f"#выплата <b>#{payout_id}</b>\n"
            f"{coins} монеток → <b>{stars} ⭐</b>\n"
            f"Кому: <code>{message.from_user.id}</code> {who}\n"
            f"Реквизиты: <code>{details}</code>",
            reply_markup=kb.payout_review(payout_id),
        )
        await db.set_payout_admin_msg(payout_id, card.message_id)
    except TelegramAPIError as error:
        logger.error("payout card #%s not delivered to %s: %s", payout_id, chat, error)


@router.callback_query(F.data.startswith("pw:"))
async def close(call: CallbackQuery) -> None:
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Нет прав.", show_alert=True)
        return

    _, verdict, raw_id = call.data.split(":")
    payout = await db.close_payout(int(raw_id), "paid" if verdict == "paid" else "rejected")
    if payout is None:
        await call.answer("Заявка уже закрыта.", show_alert=True)
        return

    note = (
        texts.payout_paid(payout["id"], payout["stars"])
        if verdict == "paid"
        else texts.payout_rejected(payout["id"], payout["coins"])
    )
    with suppress(TelegramAPIError):
        await call.bot.send_message(payout["user_id"], note)

    mark = "🟢 выплачено" if verdict == "paid" else "🔴 отклонено"
    with suppress(TelegramAPIError):
        await call.message.edit_text(
            f"{call.message.html_text}\n\n<b>{mark}</b>", reply_markup=None
        )
    await call.answer(mark)
