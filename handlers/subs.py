"""Buying a subscription.

Three tiers, priced per day in coins. The screen lists what each one buys, a
tier opens a card with the durations, and the coins are taken only on the last
tap — nothing here charges on the way in.

What a tier then does lives where it applies: the feed reads it in watch.py,
the upload queue in upload.py. This module only sells.
"""

import logging
import uuid
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import invoices
import keyboards as kb
import paritypay
import settings
import texts
import tiers
import ui

logger = logging.getLogger(__name__)

router = Router()


async def _screen(user_id: int) -> tuple[str, object]:
    user = await db.get_user(user_id)
    tier = db.active_tier(user)
    body = texts.tiers_screen(user["coins"], tier, user["tier_until"])
    # A running auto-renewal is the one thing on this screen that keeps taking
    # money, so it is said out loud and switched off from here.
    row = await db.live_tier_sub(user_id)
    if row is not None and row["status"] == "active":
        body += "\n\n" + texts.tier_sub_active(
            row["tier"], row["amount"], row["days"], row["next_at"]
        )
    return body, kb.tiers_menu(row["order_id"] if row is not None else "")


@router.message(F.text == kb.BTN_SUBS)
async def open_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    text, markup = await _screen(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "tier:list")
async def back_to_list(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup = await _screen(call.from_user.id)
    await ui.edit(call, text, markup)
    await call.answer()


def _parse(data: str) -> tuple[str, int] | None:
    """«tier:buy:a+:7» -> ('a+', 7), or None if the button is not ours any more."""
    parts = data.split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        return None
    code, days = parts[2], int(parts[3])
    if tiers.get(code) is None or days not in tiers.DAYS:
        return None
    return code, days


@router.callback_query(F.data.startswith("tier:buy:"))
async def choose_payment(call: CallbackQuery, state: FSMContext) -> None:
    """Length is chosen; now how to pay for it."""
    await state.clear()
    picked = _parse(call.data)
    if picked is None:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return
    code, days = picked
    await ui.edit(call, texts.tier_pay(code, days), kb.tier_pay(code, days))
    await call.answer()


@router.callback_query(F.data.startswith("tier:sub:"))
async def buy_recurring(call: CallbackQuery, state: FSMContext) -> None:
    """Pay at the processor, and keep paying — see invoices.run_subs."""
    await state.clear()
    picked = _parse(call.data)
    if picked is None or not paritypay.recurring_on():
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return
    code, days = picked

    # Two live subscriptions would charge the same person twice for one thing.
    if await db.live_tier_sub(call.from_user.id) is not None:
        await call.answer(texts.TIER_SUB_ALREADY, show_alert=True)
        return

    order_id = uuid.uuid4().hex
    amount = settings.card_rubles(tiers.price_of(code, days))
    try:
        link = await paritypay.create_subscription(
            order_id,
            amount,
            days,
            f"{tiers.title(code)} в {(await call.bot.me()).username}",
            f"{tiers.title(code)} на {texts.day_word(days)}",
        )
    except paritypay.ParityError as error:
        logger.error("подписка для %s не создалась: %s", call.from_user.id, error)
        await call.answer(texts.CRYPTO_FAILED, show_alert=True)
        return

    await db.add_tier_sub(order_id, call.from_user.id, code, days, amount, link)
    await call.answer()
    card = await call.message.answer(
        texts.tier_sub_invoice(code, amount, days),
        reply_markup=kb.tier_sub_invoice(order_id, link),
    )
    await db.set_tier_sub_msg(order_id, card.message_id)


@router.callback_query(F.data.startswith("tsub:"))
async def manage_sub(call: CallbackQuery) -> None:
    _, action, order_id = call.data.split(":", 2)
    row = await db.get_tier_sub(order_id)
    if row is None or row["user_id"] != call.from_user.id:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return

    if action == "drop":
        # An initialization that was never paid needs no cancelling at their
        # end — it fails on its own — but ours must stop being polled either way.
        with suppress(paritypay.ParityError):
            await paritypay.cancel_subscription(order_id)
        await db.touch_tier_sub(order_id, "cancelled")
        await call.answer(texts.TIER_SUB_DROPPED, show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)
        return

    charged = await invoices.check_subscription(call.bot, row)
    if charged == "active":
        await call.answer("🟢")
        return
    await call.answer(texts.TIER_SUB_WAITING, show_alert=True)


@router.callback_query(F.data.startswith("tier:coins:"))
async def buy(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    picked = _parse(call.data)
    if picked is None:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return

    code, days = picked
    price = tiers.price_of(code, days)
    until = await db.buy_tier(call.from_user.id, code, days, price)
    if until is None:
        user = await db.get_user(call.from_user.id)
        await call.answer(texts.tier_poor(price, user["coins"]), show_alert=True)
        return

    await call.answer(texts.BOUGHT_TOAST)
    await call.message.answer(texts.tier_bought(code, days, price, until))
    await ui.render_menu(call.message, call.from_user.id)


@router.callback_query(F.data.startswith("tier:"))
async def show_tier(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    code = call.data.split(":", 1)[1]
    if tiers.get(code) is None:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return

    user = await db.get_user(call.from_user.id)
    current = db.active_tier(user)
    body = texts.tier_card(code, user["coins"])
    # Two subscriptions cannot both be in force, so a switch costs the days that
    # are left. Saying so before the tap is the whole point of this screen.
    if current and current != code:
        body = f"{texts.tier_switch(current, user['tier_until'])}\n\n{body}"

    await ui.edit(call, body, kb.tier_buy(code))
    await call.answer()
