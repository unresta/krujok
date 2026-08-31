"""Watching outside invoices until they are paid.

Three processors, one shape: CryptoBot and xRocket take crypto, ParityPay takes
cards. None of them is asked to call us — there is no public endpoint to call —
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
import paritypay
import texts
from config import INVOICE_POLL, INVOICE_TTL, SUBS_BATCH, SUBS_POLL

logger = logging.getLogger(__name__)

# Everything a processor has to answer to is create/status, so which module
# speaks to it is the only thing that ever differs.
FAILED = (crypto.CryptoError, paritypay.ParityError)


def gateway(provider: str):
    return paritypay if provider == paritypay.PROVIDER else crypto


def available() -> list[str]:
    """Processors with keys, card first — it is the one most people reach for."""
    return ([paritypay.PROVIDER] if paritypay.enabled() else []) + crypto.available()

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
    provider = invoice["provider"]
    state = await gateway(provider).status(provider, invoice["invoice_id"])
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
        if not available():
            continue
        try:
            await sweep(bot)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            last_poll["error"] = str(error)
            logger.exception("invoice sweep failed: %s", error)


# --- recurring tier subscriptions ----------------------------------------

last_subs: dict = {"at": 0.0, "checked": 0, "charged": 0, "error": ""}


async def check_subscription(bot: Bot, row) -> str:
    """Ask about one subscription and grant whatever it has paid for since.

    The processor never tells us about a renewal — it just charges the card and
    moves `last_debited_at`. A value we have not seen before is therefore a
    period the user paid for, and the tier is extended by exactly one.
    """
    try:
        data = await paritypay.subscription(row["order_id"])
    except paritypay.ParityError as error:
        logger.warning("подписка %s: %s", row["order_id"], error)
        await db.touch_tier_sub(row["order_id"], row["status"], next_at=row["next_at"])
        return row["status"]

    status = data.get("status", row["status"])
    await db.touch_tier_sub(
        row["order_id"],
        status,
        data.get("id") or "",
        data.get("next_debited_at") or "",
    )

    debited = data.get("last_debited_at") or ""
    if debited and await db.take_tier_charge(row["order_id"], debited):
        until = await db.grant_tier(row["user_id"], row["tier"], row["days"])
        first = row["charges"] == 0
        logger.info(
            "подписка %s: %s период для %s, до %s",
            row["order_id"], "первый" if first else "продлён", row["user_id"], until,
        )
        with suppress(TelegramAPIError):
            await bot.send_message(
                row["user_id"],
                texts.tier_sub_charged(row["tier"], row["amount"], until, first),
            )
        if first and row["msg_id"]:  # the pay button is spent
            with suppress(TelegramAPIError):
                await bot.edit_message_reply_markup(
                    chat_id=row["user_id"], message_id=row["msg_id"], reply_markup=None
                )
        last_subs["charged"] += 1

    if status not in paritypay.SUB_LIVE and status != row["status"]:
        with suppress(TelegramAPIError):
            await bot.send_message(row["user_id"], texts.tier_sub_over(status))
    return status


async def sweep_subs(bot: Bot) -> int:
    last_subs["at"] = time.time()
    last_subs["error"] = ""
    last_subs["charged"] = 0
    rows = await db.due_tier_subs(SUBS_BATCH)
    for row in rows:
        await check_subscription(bot, row)
    last_subs["checked"] = len(rows)
    return len(rows)


async def run_subs(bot: Bot) -> None:
    """Slow loop: a subscription renews once a day at most."""
    while True:
        await asyncio.sleep(SUBS_POLL)
        if not paritypay.enabled():
            continue
        try:
            await sweep_subs(bot)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            last_subs["error"] = str(error)
            logger.exception("проверка подписок сорвалась: %s", error)


async def start(bot: Bot, user_id: int, provider: str, coins: int, message) -> None:
    """Create an invoice and put its card in front of the payer."""
    try:
        invoice = await gateway(provider).create(provider, coins, user_id)
    except FAILED as error:
        logger.error("%s invoice for %s failed: %s", provider, user_id, error)
        # A rejected key is not a hiccup the payer should retry through — it is
        # a настройка, and the log is where the admin will look for it.
        if str(error).startswith(("400", "401", "403")):
            logger.error(
                "%s: ключ отклонён. %s",
                provider,
                crypto.KEY_HINTS.get(provider, "проверь ключи в .env"),
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
