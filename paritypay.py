"""Card checkout through ParityPay.

Same shape as the crypto providers, so invoices.py can drive all three the same
way: create an invoice, hand the payer its link, ask later whether it was paid.

    POST /v2/invoice/create   заголовки X-ShopId и X-SecretKey
    GET  /v2/invoice/status?order_id=…
    GET  /v2/shop/balance     — ничего не меняет, поэтому им и проверяем ключи

ParityPay can call a webhook, and there is nowhere to call: nothing in this
deployment is reachable from the internet. So the bot polls its own open
invoices, exactly as it does for CryptoBot and xRocket — see invoices.poll.
Their key №2 signs webhooks and is therefore not needed at all.

The order id is ours and random: it goes to a third party, and a user id has no
business travelling with a payment. What the invoice is for lives in our own
invoices table, keyed by that same id.
"""

from __future__ import annotations

import logging
import uuid

import aiohttp

import settings
from config import (
    INVOICE_TIMEOUT,
    INVOICE_TTL,
    PARITYPAY_API,
    PARITYPAY_SECRET,
    PARITYPAY_SHOP_ID,
)
from crypto import ACTIVE, EXPIRED, PAID, UNKNOWN, Invoice

logger = logging.getLogger(__name__)

PROVIDER = "paritypay"
TITLE = "Карта"  # for the panel, where it is a heading
ICON = "💳"
# For «Оплата через …» in the payer's invoice card, where a heading would read
# as «Оплата через Карта».
TITLES = {PROVIDER: "карту"}

# NEW is «ждём оплату»; REFUNDED is not a state an unpaid invoice reaches, and
# treating it as paid would credit coins for money that went back.
STATUSES = {
    "NEW": ACTIVE,
    "PAID": PAID,
    "EXPIRED": EXPIRED,
    "ERROR": EXPIRED,
    "REFUNDED": EXPIRED,
}


class ParityError(Exception):
    """The processor refused, or could not be reached."""


def enabled() -> bool:
    return bool(PARITYPAY_SHOP_ID.strip() and PARITYPAY_SECRET.strip())


def _headers() -> dict:
    return {
        "X-ShopId": PARITYPAY_SHOP_ID.strip(),
        "X-SecretKey": PARITYPAY_SECRET.strip(),
        "Content-Type": "application/json",
    }


def price(coins: int) -> str:
    """Roubles the payer is charged for that many coins."""
    return settings.card_rubles(coins)


async def _call(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{PARITYPAY_API.rstrip('/')}{path}"
    timeout = aiohttp.ClientTimeout(total=INVOICE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=_headers(),
                json=payload if method == "POST" else None,
                params=payload if method == "GET" else None,
            ) as response:
                body = await response.json(content_type=None)
                if response.status >= 400 or "error" in body:
                    reason = body.get("error") or body
                    raise ParityError(f"{response.status}: {str(reason)[:200]}")
                return body
    except ParityError:
        raise
    except Exception as error:  # timeouts, broken json — same thing to the caller
        raise ParityError(str(error)) from error


async def create(provider: str, coins: int, user_id: int) -> Invoice:
    """`provider` is ignored — there is only one card processor — but the
    signature matches crypto.create so invoices.py needs no special case."""
    order_id = uuid.uuid4().hex
    amount = price(coins)
    body = await _call(
        "POST",
        "/v2/invoice/create",
        {
            "order_id": order_id,
            "amount": float(amount),
            "comment": f"{coins} монеток",
            # Minutes here, seconds everywhere else in the bot.
            "expire": max(1, INVOICE_TTL // 60),
            "service": "card",
        },
    )
    link = body.get("link") or ""
    if not link:
        raise ParityError("процессинг не вернул ссылку на оплату")
    logger.info("paritypay invoice %s for %s: %s ₽", order_id, user_id, amount)
    return Invoice(PROVIDER, order_id, link, amount, "₽")


async def status(provider: str, invoice_id: str) -> str:
    """paid / active / expired / unknown — never raises for a caller to guess."""
    try:
        body = await _call("GET", "/v2/invoice/status", {"order_id": invoice_id})
    except ParityError as error:
        # A 404 is an invoice the processor has no record of; anything else is
        # a bad minute, and an unknown answer keeps the invoice open.
        if str(error).startswith("404"):
            return EXPIRED
        logger.warning("paritypay status %s failed: %s", invoice_id, error)
        return UNKNOWN
    return STATUSES.get(body.get("status", ""), UNKNOWN)


async def check_key() -> str:
    """A line for the panel: are the shop id and key actually good for anything."""
    if not enabled():
        return "⚪ ключей нет"
    try:
        body = await _call("GET", "/v2/shop/balance")
    except ParityError as error:
        text = str(error)
        if text.startswith(("400", "401", "403")):
            return (
                "🔴 касса не принимает ключи.\n"
                "X-ShopId — это UUID кассы, X-SecretKey — ключ №1 из настроек "
                "кассы в личном кабинете (не ключ №2, он только для вебхуков). "
                "И проверь, что контейнер перезапущен после правки .env."
            )
        return f"🟡 процессинг не отвечает: {text[:120]}"
    return (
        f"🟢 подключено · баланс {body.get('balance', '?')} "
        f"{body.get('currency', '')}"
        + (f" · в заморозке {body['balance_hold']}" if body.get("balance_hold") else "")
    )
