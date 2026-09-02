"""The auction: one prize, one window, the biggest pile of coins takes it.

Bids are not promises. Coins leave the balance the moment they are bid, which
is the only thing that makes the number on the board mean anything — a promise
costs nothing to make and nothing to break. When the window closes, everyone
but the winner gets theirs back, down to the split between bought and earned:
a loser who paid with earnings must get earnings back, or the auction quietly
eats what they could have withdrawn.

Ends by itself. The window is short, so the admin who started it is unlikely to
be watching when it runs out — `run()` closes it on a timer, and the panel's
«Завершить сейчас» does exactly the same thing a few minutes early.
"""

import asyncio
import logging
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

import db
import keyboards as kb
import outbox
import people
import settings
import texts

logger = logging.getLogger(__name__)

SEND_PAUSE = 0.05  # ~20 per second, same ceiling as the broadcast

# Filled in by every pass, read by the panel: a job that quietly died and a job
# with nothing to close look the same from the outside.
last_check: dict = {"at": 0.0, "closed": 0, "error": ""}


def seconds_left(auction) -> int:
    return max(0, int(auction["ends_at"] - time.time()))


async def start(prize: str = "") -> object | None:
    """Open the auction. None when one is already running.

    The refund rule is copied onto the row here and read from there ever after:
    what an auction was announced with is what it must end with.
    """
    prize = prize or settings.get_text("auction_prize")
    hours = settings.get("auction_hours")
    refund = bool(settings.get("auction_refund"))
    row = await db.start_auction(prize, hours * 3600, refund)
    if row is not None:
        logger.info(
            "auction %s started: %s, %s ч, возврат %s",
            row["id"], prize, hours, "да" if refund else "нет",
        )
    return row


async def bid(bot: Bot, user_id: int, amount: int) -> tuple[str, int]:
    """Put coins in. Returns (verdict, this person's new total).

    Verdicts: ok | over | poor | small. Money moves here and nowhere else, so
    the checks that keep it from moving twice live here too.
    """
    auction = await db.live_auction()
    if auction is None or not seconds_left(auction):
        return "over", 0
    if amount <= 0:
        return "small", 0

    user = await db.get_user(user_id)
    # Which half is being spent has to be worked out before the spend — after
    # it, the split is gone, and a refund would hand earnings back as bought.
    from_earned = db.earned_share(user, amount)
    if not await db.try_spend(user_id, amount):
        return "poor", 0

    # Who was in front before the money moved: the one this bid pushes off the
    # top is the only person who needs to hear about it.
    was = await db.auction_board(auction["id"], limit=1)
    total = await db.place_bid(auction["id"], user_id, amount, from_earned)
    logger.info(
        "auction %s: %s bid %s, total %s", auction["id"], user_id, amount, total
    )
    await _tell_outbid(bot, auction, was[0] if was else None, user_id, total)
    return "ok", total


async def _tell_outbid(bot: Bot, auction, leader, bidder: int, top: int) -> None:
    """Tell whoever just lost the lead, and nobody else.

    Not sent when the leader raised their own bid — they know — and not on a
    tie: an equal total leaves the one who got there first in front, so nothing
    changed and there is nothing to say.
    """
    if leader is None or leader["user_id"] == bidder or leader["coins"] >= top:
        return
    with suppress(TelegramAPIError):  # they may have blocked the bot
        await bot.send_message(
            leader["user_id"],
            texts.auction_outbid(top, leader["coins"], texts.time_left(seconds_left(auction))),
            reply_markup=kb.auction_open(),
        )


async def announce(bot: Bot, auction) -> tuple[int, int]:
    """Tell everyone it started, and hand out the keyboard with the button on it.

    Without this the auction is visible to whoever happens to open the menu
    next — which is nobody in particular, and an auction nobody knows about
    collects no bids. Returns (доставлено, не дошло).
    """
    text = texts.auction_announce(
        auction["prize"],
        max(1, seconds_left(auction) // 3600),
        refund=bool(auction["refund"]),
    )
    menu = kb.main_menu(True)
    sent = failed = 0
    for user_id in await db.all_user_ids():
        try:
            await bot.send_message(user_id, text, reply_markup=menu)
            sent += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 1)
            try:
                await bot.send_message(user_id, text, reply_markup=menu)
                sent += 1
            except TelegramAPIError:
                failed += 1
        except TelegramForbiddenError:  # blocked the bot, or deleted the account
            await db.mark_blocked(user_id)
            failed += 1
        except TelegramAPIError:
            failed += 1
        await asyncio.sleep(SEND_PAUSE)
    logger.info("auction %s announced: %s delivered, %s failed", auction["id"], sent, failed)
    return sent, failed


async def close(bot: Bot, auction, cancelled: bool = False) -> bool:
    """Hand out the prize and give everyone else their coins back.

    False when it was already closed — the timer and the panel button both end
    up here, and only one of them may pay anything out.
    """
    board = await db.auction_board(auction["id"], limit=1)
    winner = board[0] if board and not cancelled else None
    if not await db.close_auction(
        auction["id"],
        winner_id=winner["user_id"] if winner else 0,
        winner_bid=winner["coins"] if winner else 0,
        status="cancelled" if cancelled else "done",
    ):
        return False

    contact = settings.get_text("auction_contact").strip()
    # A cancelled auction pays everyone back whatever its rule was: it never
    # ran, so there is nothing anyone lost to.
    refund = cancelled or bool(auction["refund"])
    # The red button is on the reply keyboard, and a reply keyboard only changes
    # when a message brings a new one. These are the messages: everyone who bid
    # gets the keyboard back without it, in the same breath as their coins.
    menu = kb.main_menu(False)
    for row in await db.auction_bidders(auction["id"]):
        if winner is not None and row["user_id"] == winner["user_id"]:
            with suppress(TelegramAPIError):
                await bot.send_message(
                    row["user_id"],
                    texts.auction_won(row["coins"], contact),
                    reply_markup=menu,
                )
            continue
        # Each half goes back where it came from, or nowhere at all.
        if refund:
            await db.give_back(row["user_id"], row["coins"], row["earned"])
        with suppress(TelegramAPIError):
            await bot.send_message(
                row["user_id"],
                texts.auction_refund(row["coins"], cancelled, refund),
                reply_markup=menu,
            )
        await asyncio.sleep(SEND_PAUSE)

    await _tell_admins(bot, auction, winner, cancelled)
    logger.warning(
        "auction %s closed: winner %s with %s",
        auction["id"],
        winner["user_id"] if winner else "—",
        winner["coins"] if winner else 0,
    )
    return True


async def _tell_admins(bot: Bot, auction, winner, cancelled: bool) -> None:
    """The card that says who to hand the prize to — nobody may miss it."""
    chat = settings.reports_chat()
    who = await people.of(winner["user_id"]) if winner else "—"
    totals = await db.auction_totals(auction["id"])
    kept = 0 if cancelled or auction["refund"] else totals["coins"] - (
        winner["coins"] if winner else 0
    )
    card = (
        f"🔨 <b>Аукцион закрыт</b> · {auction['prize']}\n\n"
        + ("<b>Отменён, монетки вернулись всем.</b>\n" if cancelled else "")
        + (
            f"🏆 Победитель: {who}\n"
            f"Ставка: <b>{winner['coins']}</b> монеток\n\n"
            "Он придёт за доступом в поддержку."
            if winner
            else "Ставок не было."
        )
        + (f"\n\n💰 Осталось в банке: <b>{kept}</b> монеток" if kept else "")
    )
    async def deliver() -> None:
        await outbox.call(chat, lambda: bot.send_message(chat, card), "итог аукциона")

    outbox.post(chat, deliver, "итог аукциона")


async def run(bot: Bot) -> None:
    """Background loop: the window closes on time whether anyone is here or not."""
    from config import AUCTION_TICK

    while True:
        await asyncio.sleep(AUCTION_TICK)
        last_check["at"] = time.time()
        last_check["error"] = ""
        try:
            auction = await db.live_auction()
            if auction is not None and not seconds_left(auction):
                if await close(bot, auction):
                    last_check["closed"] += 1
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            last_check["error"] = str(error)
            logger.exception("auction sweep failed: %s", error)
