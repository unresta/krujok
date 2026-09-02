"""The auction screen: rules, the board, and a bid in one tap.

Every path lands on the same screen redrawn — a bid that went through, a bid
that did not, a refresh. The number on it is the only reason anybody opens it
twice, so it is never stale by more than the tap that showed it.
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import auction
import db
import keyboards as kb
import texts
import ui

router = Router()


class Bid(StatesGroup):
    waiting_amount = State()


async def screen(user_id: int) -> tuple[str, object]:
    """What the auction looks like right now for this person."""
    live = await db.live_auction()
    if live is None:
        return texts.AUCTION_OFF, kb.auction_screen(live=False)

    board = await db.auction_board(live["id"], limit=1)
    totals = await db.auction_totals(live["id"])
    user = await db.get_user(user_id)
    text = texts.auction(
        prize=live["prize"],
        hours=(live["ends_at"] - live["started_at"] + 1800) // 3600,
        left=texts.time_left(auction.seconds_left(live)),
        top=board[0]["coins"] if board else 0,
        mine=await db.bid_of(live["id"], user_id),
        coins=user["coins"],
        bidders=totals["bidders"],
        # The rule this auction actually runs by, not the one set right now.
        refund=bool(live["refund"]),
    )
    return text, kb.auction_screen()


@router.message(F.text == kb.BTN_AUCTION)
async def open_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    if await db.live_auction() is None:
        # Their keyboard still has yesterday's button on it; this is the one
        # moment we know they are looking at it, so it goes away here.
        await message.answer(texts.AUCTION_OFF, reply_markup=kb.main_menu(False))
        return
    text, markup = await screen(message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == "auc:open")
async def refresh(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup = await screen(call.from_user.id)
    await ui.edit(call, text, markup)
    await call.answer()


@router.callback_query(F.data.startswith("auc:bid:"))
async def place(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _bid(call, call.from_user.id, int(call.data.split(":")[2]))


@router.callback_query(F.data == "auc:custom")
async def ask_amount(call: CallbackQuery, state: FSMContext) -> None:
    if await db.live_auction() is None:
        await call.answer(texts.AUCTION_OFF, show_alert=True)
        return
    await state.set_state(Bid.waiting_amount)
    user = await db.get_user(call.from_user.id)
    await ui.edit(call, texts.auction_bid_ask(user["coins"]), kb.buy_cancel())
    await call.answer()


# A circle recorded while this form is open belongs to the uploader, not here.
@router.message(Bid.waiting_amount, ~F.video_note, ~F.text.in_(kb.MENU_BUTTONS))
async def custom_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or not int(raw):
        await message.answer(texts.AUCTION_BID_SMALL)
        return
    await state.clear()
    await _bid(message, message.from_user.id, int(raw))


async def _bid(event: Message | CallbackQuery, user_id: int, amount: int) -> None:
    """One place takes the coins, one place redraws the board."""
    verdict, mine = await auction.bid(user_id, amount)
    user = await db.get_user(user_id)
    note = {
        "ok": texts.auction_bid_ok(mine),
        "over": texts.AUCTION_OFF,
        "small": texts.AUCTION_BID_SMALL,
        "poor": texts.auction_poor(amount, user["coins"]),
    }[verdict]

    text, markup = await screen(user_id)
    if isinstance(event, CallbackQuery):
        # Anything but a taken bid gets an alert: a toast over a screen that
        # did not change is how a bid looks when it silently failed.
        await event.answer(note, show_alert=verdict != "ok")
        await ui.edit(event, text, markup)
        return
    if verdict != "ok":
        await event.answer(note)
    await event.answer(text, reply_markup=markup)
