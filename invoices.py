"""Watching crypto invoices until they are paid.

The provider is never asked to call us — there is no public endpoint to call —
so an open invoice is checked on a timer, and the payer gets a button that does
the same check on demand. Both paths end in credit(), which is where the coins
are actually handed over, once.
"""

import asyncio
import logging
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import crypto
import db
import keyboards as kb
import texts
from config import INVOICE_POLL, INVOICE_TTL

logger = logging.getLogger(__name__)

# A provider may confirm a payment slightly after the invoice stops being
# payable, so an invoice is watched a little longer than it lives.
GRACE = 600

last_poll: dict = {"at": 0.0, "checked": 0, "paid": 0, "error": ""}


async def credit(bot: Bot, invoice) -> bool:
    """Hand over the coins for a paid invoice. False if it was already done."""
    charge_id = f"{invoice['provider']}:{invoice['invoice_id']}"
    fresh = await db.add_payment(
        charge_id,
        invoice["user_id"],
        stars=0,
        coins=invoice["coins"],
        provider=invoice["provider"],
        asset=invoice["asset"],
        amount=invoice["amount"],
    )
    await db.close_invoice(invoice["provider"], invoice["invoice_id"], "paid")
    if not fresh:  # the poller and the button both got here
        return False

    await db.add_coins(invoice["user_id"], invoice["coins"])
    balance = (await db.get_user(invoice["user_id"]))["coins"]
    note = texts.crypto_paid(
        invoice["amount"], invoice["asset"], invoice["coins"], balance
    )
    with suppress(TelegramAPIError):
        await bot.send_message(invoice["user_id"], note)
    # The card that carried the pay button is stale the moment it is paid.
    if invoice["msg_id"]:
        with suppress(TelegramAPIError):
            await bot.edit_message_reply_markup(
                chat_id=invoice["user_id"],
                message_id=invoice["msg_id"],
                reply_markup=None,
            )
    logger.info(
        "%s invoice %s paid: %s coins to %s",
        invoice["provider"], invoice["invoice_id"], invoice["coins"],
        invoice["user_id"],
    )
    return True


async def check_one(bot: Bot, invoice) -> str:
    """Ask the provider about one invoice and act on the answer."""
    state = await crypto.status(invoice["provider"], invoice["invoice_id"])
    if state == crypto.PAID:
        await credit(bot, invoice)
        return crypto.PAID

    too_old = time.time() - invoice["created_at"] > INVOICE_TTL + GRACE
    if state == crypto.EXPIRED or (state == crypto.UNKNOWN and too_old):
        await db.close_invoice(invoice["provider"], invoice["invoice_id"], "expired")
        return crypto.EXPIRED
    return state


async def sweep(bot: Bot) -> tuple[int, int]:
    """One pass over the open invoices. Returns (checked, paid)."""
    last_poll["at"] = time.time()
    last_poll["error"] = ""
    open_ones = await db.open_invoices()
    paid = 0
    for invoice in open_ones:
        if await check_one(bot, invoice) == crypto.PAID:
            paid += 1
    last_poll["checked"], last_poll["paid"] = len(open_ones), paid
    return len(open_ones), paid


async def run(bot: Bot) -> None:
    """Background loop; a provider being down must not take the bot with it."""
    while True:
        await asyncio.sleep(INVOICE_POLL)
        if not crypto.enabled():
            continue
        try:
            await sweep(bot)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            last_poll["error"] = str(error)
            logger.exception("invoice sweep failed: %s", error)


async def start(bot: Bot, user_id: int, provider: str, coins: int, message) -> None:
    """Create an invoice and put its card in front of the payer."""
    try:
        invoice = await crypto.create(provider, coins, user_id)
    except crypto.CryptoError as error:
        logger.error("%s invoice for %s failed: %s", provider, user_id, error)
        # A rejected key is not a hiccup the payer should retry through — it is
        # a настройка, and the log is where the admin will look for it.
        if str(error).startswith(("401", "403")):
            logger.error(
                "%s: ключ отклонён. %s", provider, crypto.KEY_HINTS[provider]
            )
        await message.answer(texts.CRYPTO_FAILED)
        return

    await db.add_invoice(
        invoice.provider,
        invoice.invoice_id,
        user_id,
        coins,
        invoice.amount,
        invoice.asset,
        invoice.link,
    )
    card = await message.answer(
        texts.crypto_invoice(provider, invoice.amount, invoice.asset, coins),
        reply_markup=kb.crypto_invoice(
            invoice.provider, invoice.invoice_id, invoice.link
        ),
    )
    await db.set_invoice_msg(invoice.provider, invoice.invoice_id, card.message_id)
