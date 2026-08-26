from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import db
import keyboards as kb
import texts
import ui
from config import MAX_STARS, MIN_STARS, STARS_RATE

router = Router()


class Buy(StatesGroup):
    waiting_amount = State()


@router.callback_query(F.data == "buy")
async def buy_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(call.from_user.id)
    await ui.edit(call, texts.buy(user["coins"]), kb.buy())
    await call.answer()


@router.callback_query(F.data == "pay:custom")
async def ask_amount(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Buy.waiting_amount)
    await ui.edit(call, texts.BUY_CUSTOM, kb.buy_cancel())
    await call.answer()


@router.message(Buy.waiting_amount)
async def custom_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (MIN_STARS <= int(raw) <= MAX_STARS):
        await message.answer(texts.BUY_BAD_INPUT, reply_markup=kb.buy_cancel())
        return
    await state.clear()
    await send_invoice(message, int(raw))


@router.callback_query(F.data.startswith("pay:"))
async def pay_pack(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    stars = int(call.data.split(":", 1)[1])
    await call.answer()
    await send_invoice(call.message, stars)


async def send_invoice(message: Message, stars: int) -> None:
    coins = stars * STARS_RATE
    await message.answer_invoice(
        title=f"{coins} монеток",
        description=f"{stars} ⭐ → {coins} 🪙 на баланс в боте.",
        payload=f"coins:{stars}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=f"{coins} 🪙", amount=stars)],
        protect_content=True,
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, state: FSMContext) -> None:
    await state.clear()
    payment = message.successful_payment
    stars = payment.total_amount
    coins = stars * STARS_RATE

    fresh = await db.add_payment(
        payment.telegram_payment_charge_id, message.from_user.id, stars, coins
    )
    if fresh:
        await db.add_coins(message.from_user.id, coins)

    user = await db.get_user(message.from_user.id)
    await message.answer(texts.paid(stars, coins, user["coins"]))
    await ui.render_menu(message, message.from_user.id)
