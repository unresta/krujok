from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

import crypto
import db
import invoices
import keyboards as kb
import texts
import ui
import settings
from config import MAX_STARS

router = Router()


class Buy(StatesGroup):
    waiting_amount = State()
    choose_method = State()


@router.message(F.text == kb.BTN_SHOP)
async def shop(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(message.from_user.id)
    await message.answer(texts.buy(user["coins"]), reply_markup=kb.buy())


@router.callback_query(F.data == "buy")
async def buy_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(call.from_user.id)
    await ui.edit(call, texts.buy(user["coins"]), kb.buy())
    await call.answer()


@router.callback_query(F.data == "pay:custom")
async def ask_amount(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Buy.waiting_amount)
    await ui.edit(call, texts.buy_custom(), kb.buy_cancel())
    await call.answer()


# A circle recorded while this form is open belongs to the uploader, not here:
# letting it fall through is what keeps the recording from being lost.
@router.message(Buy.waiting_amount, ~F.video_note, ~F.text.in_(kb.MENU_BUTTONS))
async def custom_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (settings.get("min_stars") <= int(raw) <= MAX_STARS):
        await message.answer(texts.buy_bad_input(), reply_markup=kb.buy_cancel())
        return
    stars = int(raw)
    await state.update_data(stars=stars)
    await state.set_state(Buy.choose_method)
    coins = stars * settings.get("stars_rate")
    await message.answer(
        texts.buy_choose_method(stars, coins),
        reply_markup=kb.buy_payment_method()
    )


@router.message(Buy.choose_method, ~F.video_note, ~F.text.in_(kb.MENU_BUTTONS))
async def method_hint(message: Message) -> None:
    """Typing at the payment-method step used to get no answer at all."""
    await message.answer(texts.BUY_PICK_METHOD, reply_markup=kb.buy_payment_method())


@router.callback_query(F.data.startswith("pay:"))
async def pay_pack(call: CallbackQuery, state: FSMContext) -> None:
    if call.data == "pay:custom":
        return  # handled by buy_custom

    await state.clear()
    stars = int(call.data.split(":", 1)[1])
    coins = stars * settings.get("stars_rate")
    await state.update_data(stars=stars)
    await state.set_state(Buy.choose_method)
    await call.message.answer(
        texts.buy_choose_method(stars, coins),
        reply_markup=kb.buy_payment_method()
    )
    await call.answer()


@router.callback_query(F.data == "pay_method:stars")
async def pay_with_stars(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    stars = data.get("stars")
    if not stars:
        await call.answer(texts.BUY_NO_AMOUNT, show_alert=True)
        return
    await state.clear()
    await call.answer()
    await send_invoice(call.message, stars)


@router.callback_query(F.data.startswith("doc:"))
async def show_document(call: CallbackQuery) -> None:
    """The offer and the privacy policy, in the chat rather than behind a link."""
    name = call.data.split(":", 1)[1]
    if name not in texts.DOCS:
        await call.answer(texts.STALE_BUTTON)
        return

    await call.answer()
    parts = texts.doc_parts(name)
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        await call.message.answer(part, reply_markup=kb.back() if last else None)


@router.callback_query(F.data.startswith("pay_method:"))
async def pay_with_crypto(call: CallbackQuery, state: FSMContext) -> None:
    """Everything that is not Stars is an invoice at one of the crypto bots."""
    provider = call.data.split(":", 1)[1]
    if provider not in crypto.available():
        await call.answer(texts.BUY_CARD_SOON, show_alert=True)
        return

    stars = (await state.get_data()).get("stars")
    if not stars:
        await call.answer(texts.BUY_NO_AMOUNT, show_alert=True)
        return
    await state.clear()
    await call.answer()
    coins = stars * settings.get("stars_rate")
    await invoices.start(call.bot, call.from_user.id, provider, coins, call.message)


@router.callback_query(F.data.startswith("inv:"))
async def invoice_action(call: CallbackQuery) -> None:
    _, action, provider, invoice_id = call.data.split(":", 3)
    invoice = await db.get_invoice(provider, invoice_id)
    if invoice is None or invoice["user_id"] != call.from_user.id:
        await call.answer(texts.CRYPTO_GONE, show_alert=True)
        return

    if action == "drop":
        await db.close_invoice(provider, invoice_id, "cancelled")
        await call.answer(texts.CRYPTO_CANCELLED)
        with suppress(TelegramAPIError):
            await call.message.delete()
        return

    if invoice["status"] == "paid":  # the poller got there first
        await call.answer(texts.ALREADY_BOUGHT, show_alert=True)
        return

    state = await invoices.check_one(call.bot, invoice)
    if state == crypto.PAID:
        await call.answer("🟢")
        return
    if state == crypto.EXPIRED:
        await call.answer(texts.CRYPTO_EXPIRED, show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)
        return
    await call.answer(texts.CRYPTO_PENDING, show_alert=True)


async def send_invoice(message: Message, stars: int) -> None:
    coins = stars * settings.get("stars_rate")
    await message.answer_invoice(
        title=f"{coins} монеток",
        description=f"{stars} ⭐ → {coins} 🪙 на баланс в боте.",
        payload=f"coins:{stars}",
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label=f"{coins} 🪙", amount=stars)],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, state: FSMContext) -> None:
    await state.clear()
    payment = message.successful_payment
    stars = payment.total_amount
    coins = stars * settings.get("stars_rate")

    fresh = await db.add_payment(
        payment.telegram_payment_charge_id, message.from_user.id, stars, coins
    )
    if fresh:
        await db.add_coins(message.from_user.id, coins)

    user = await db.get_user(message.from_user.id)
    await message.answer(texts.paid(stars, coins, user["coins"]))
    await ui.render_menu(message, message.from_user.id)
