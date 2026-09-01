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


# What to pin the payment form to. Empty is the processor's own default and the
# right one to ship: it offers whatever the shop actually has switched on.
# Naming a service the shop does not have leaves the form with no methods at
# all — the invoice is created, the page loads, and there is nothing to press.
SERVICES = {"": "любой", "card": "только карта", "sbp": "только СБП"}


def service() -> str:
    raw = settings.get_text("card_service").strip().lower()
    return raw if raw in SERVICES else ""


def method_label() -> str:
    """The button in the bot has to promise what the form will actually show."""
    return {"card": "Картой", "sbp": "СБП"}.get(service(), "Картой или СБП")


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
    amount = price(coins)  # the bonus is a gift, so it is not priced
    payload = {
        "order_id": order_id,
        "amount": float(amount),
        "comment": f"{settings.card_total(coins)} монеток",
        # Minutes here, seconds everywhere else in the bot.
        "expire": max(1, INVOICE_TTL // 60),
    }
    if service():  # left out entirely means «пусть выбирает плательщик»
        payload["service"] = service()
    body = await _call("POST", "/v2/invoice/create", payload)
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


# --- recurring subscriptions ---------------------------------------------

# Their side supports 1d/1w/1m/1y; the bot sells 1, 7 and 30 days.
INTERVALS = {1: "1d", 7: "1w", 30: "1m"}
INTERVAL_WORDS = {"1d": "каждый день", "1w": "каждую неделю", "1m": "каждый месяц"}

SUB_LIVE = ("initialization", "active")


def interval_of(days: int) -> str:
    """'' when the bot sells a length the processor cannot repeat."""
    return INTERVALS.get(days, "")


def recurring_on() -> bool:
    """Subscriptions need the processor's own approval, so they are a switch.

    Off until an admin turns it on — sending a `subscription` block before that
    approval simply fails, and it would fail in front of a paying user.
    """
    return enabled() and bool(settings.get("subs_recurring"))


async def create_subscription(
    order_id: str, amount: str, days: int, title: str, comment: str
) -> str:
    """First invoice of a subscription. Returns the payment link.

    Recurring charges only run over SBP at this processor — `service` is not a
    choice here, and a card-only payer has to use the coins route instead.
    """
    interval = interval_of(days)
    if not interval:
        raise ParityError(f"{days} дней нельзя повторять — нет такого интервала")
    body = await _call(
        "POST",
        "/v2/invoice/create",
        {
            "order_id": order_id,
            "amount": float(amount),
            "service": "sbp",
            "comment": comment,
            "expire": max(1, INVOICE_TTL // 60),
            "subscription": {
                "interval": interval,
                "description": title,
            },
        },
    )
    link = body.get("link") or ""
    if not link:
        raise ParityError("процессинг не вернул ссылку на оплату")
    logger.info("paritypay subscription %s: %s ₽ / %s", order_id, amount, interval)
    return link


async def subscription(order_id: str) -> dict:
    """What the processor knows about it: status, and when it last took money."""
    return await _call(
        "GET", "/v2/subscription/status", {"shop_subscription_id": order_id}
    )


async def cancel_subscription(order_id: str) -> None:
    """Stop the charges. Only an active subscription can be cancelled."""
    await _call("POST", "/v2/subscription/cancel", {"shop_subscription_id": order_id})
    logger.info("paritypay subscription %s cancelled", order_id)


async def balance() -> dict:
    """Available and held funds. The one call that proves the keys work too."""
    return await _call("GET", "/v2/shop/balance")


KEY_PROBLEM = (
    "🔴 касса не принимает ключи.\n"
    "X-ShopId — это UUID кассы, X-SecretKey — ключ №1 из настроек кассы в "
    "личном кабинете (не ключ №2, он только для вебхуков). И проверь, что "
    "контейнер перезапущен после правки .env."
)


def money(value) -> str:
    """«154300.25» -> «154 300.25». Long numbers are read, not counted."""
    try:
        whole, _, cents = f"{float(value):.2f}".partition(".")
    except (TypeError, ValueError):
        return str(value)
    groups = []
    while len(whole) > 3:
        whole, tail = whole[:-3], whole[-3:]
        groups.insert(0, tail)
    groups.insert(0, whole)
    return f"{' '.join(groups)}.{cents}"


async def shop_state() -> tuple[str, dict | None]:
    """(verdict for the panel, balance) — one request answers both questions."""
    if not enabled():
        return "⚪ ключей нет", None
    try:
        body = await balance()
    except ParityError as error:
        text = str(error)
        if text.startswith(("400", "401", "403")):
            return KEY_PROBLEM, None
        return f"🟡 процессинг не отвечает: {text[:120]}", None
    return "🟢 подключено", body


async def check_key() -> str:
    """Just the verdict, for callers that do not show the money."""
    return (await shop_state())[0]
