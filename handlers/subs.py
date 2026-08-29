"""Buying a subscription.

Three tiers, priced per day in coins. The screen lists what each one buys, a
tier opens a card with the durations, and the coins are taken only on the last
tap — nothing here charges on the way in.

What a tier then does lives where it applies: the feed reads it in watch.py,
the upload queue in upload.py. This module only sells.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
import tiers
import ui

router = Router()


async def _screen(user_id: int) -> tuple[str, object]:
    user = await db.get_user(user_id)
    tier = db.active_tier(user)
    return (
        texts.tiers_screen(user["coins"], tier, user["tier_until"]),
        kb.tiers_menu(),
    )


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


@router.callback_query(F.data.startswith("tier:buy:"))
async def buy(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, code, raw_days = call.data.split(":")
    tier = tiers.get(code)
    if tier is None or int(raw_days) not in tiers.DAYS:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return

    days = int(raw_days)
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
