"""Crypto checkout through CryptoBot and xRocket.

Both are the same shape: create an invoice, hand the payer its link, and find
out later whether it was paid. Neither is asked to push that news to us —
nothing in this deployment is reachable from the internet, so there is no
webhook endpoint to point them at. The bot polls its own open invoices
instead (see invoices.poll), which costs one request per open invoice and
needs no infrastructure at all.

    CryptoBot  https://pay.crypt.bot/api/<method>, header Crypto-Pay-API-Token
    xRocket    https://pay.xrocket.exchange/tg-invoices, header Rocket-Pay-Key

A provider without a key is simply absent from the checkout.
"""

from __future__ import annotations

import decimal
import logging
from typing import NamedTuple

import aiohttp

import settings
from config import (
    CRYPTOBOT_API,
    CRYPTOBOT_TOKEN,
    INVOICE_TIMEOUT,
    INVOICE_TTL,
    XROCKET_API,
    XROCKET_KEY,
)

logger = logging.getLogger(__name__)

CRYPTOBOT = "cryptobot"
XROCKET = "xrocket"

TITLES = {CRYPTOBOT: "CryptoBot", XROCKET: "xRocket"}
ICONS = {CRYPTOBOT: "🤖", XROCKET: "🚀"}

# What the provider says about an invoice, boiled down to what we act on.
PAID, ACTIVE, EXPIRED, UNKNOWN = "paid", "active", "expired", "unknown"


class Invoice(NamedTuple):
    provider: str
    invoice_id: str
    link: str
    amount: str
    asset: str


class CryptoError(Exception):
    """The provider refused, or could not be reached."""


# A rejected key looks like a broken integration in the log, and the fix is
# never in the code — so the panel says out loud what to go and check.
KEY_HINTS = {
    CRYPTOBOT: (
        "Токен берётся в @CryptoBot → Crypto Pay → My Apps → API Token. "
        "Проверь, что скопирован целиком и что контейнер перезапущен после "
        "правки .env."
    ),
    XROCKET: (
        "Токен берётся в @xRocket → Rocket Pay → приложение → API Token. "
        "Ключ отдаётся один раз при создании — если приложение пересоздавали "
        "или меняли ему API Version, старый ключ перестаёт работать. "
        "Тестовый ключ (@xrocket_testnet_bot) на боевом адресе тоже даёт этот "
        "отказ. И проверь, что контейнер перезапущен после правки .env."
    ),
}


def keys() -> dict[str, str]:
    return {CRYPTOBOT: CRYPTOBOT_TOKEN.strip(), XROCKET: XROCKET_KEY.strip()}


def available() -> list[str]:
    """Providers that have a key — the only ones the checkout offers."""
    return [name for name, key in keys().items() if key]


def enabled() -> bool:
    return bool(available())


def asset() -> str:
    return settings.get_text("crypto_asset").strip().upper() or "USDT"


def price(coins: int) -> str:
    """Coins to a payable amount, rounded up: never charge less than the rate."""
    rate = decimal.Decimal(settings.get("usdt_rate"))
    amount = decimal.Decimal(coins) / rate
    return str(amount.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_UP))


async def _call(
    method: str, url: str, headers: dict, payload: dict | None = None
) -> dict:
    timeout = aiohttp.ClientTimeout(total=INVOICE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method, url, headers=headers, json=payload
            ) as response:
                body = await response.json(content_type=None)
                if response.status >= 400:
                    raise CryptoError(f"{response.status}: {str(body)[:200]}")
                return body
    except aiohttp.ClientError as error:
        raise CryptoError(str(error)) from error
    except Exception as error:  # timeouts, broken json — same thing to the caller
        if isinstance(error, CryptoError):
            raise
        raise CryptoError(str(error)) from error


# --- CryptoBot -----------------------------------------------------------


async def _cryptobot_create(coins: int, amount: str, user_id: int) -> Invoice:
    body = await _call(
        "POST",
        f"{CRYPTOBOT_API.rstrip('/')}/createInvoice",
        {"Crypto-Pay-API-Token": keys()[CRYPTOBOT]},
        {
            "currency_type": "crypto",
            "asset": asset(),
            "amount": amount,
            "description": f"{coins} монеток",
            "payload": f"{user_id}:{coins}",
            "expires_in": INVOICE_TTL,
            "allow_comments": False,
            "allow_anonymous": True,
        },
    )
    if not body.get("ok"):
        raise CryptoError(str(body.get("error") or body)[:200])
    result = body["result"]
    link = result.get("bot_invoice_url") or result.get("pay_url") or ""
    return Invoice(CRYPTOBOT, str(result["invoice_id"]), link, amount, asset())


async def _cryptobot_status(invoice_id: str) -> str:
    body = await _call(
        "GET",
        f"{CRYPTOBOT_API.rstrip('/')}/getInvoices?invoice_ids={invoice_id}",
        {"Crypto-Pay-API-Token": keys()[CRYPTOBOT]},
    )
    if not body.get("ok"):
        raise CryptoError(str(body.get("error") or body)[:200])
    result = body["result"]
    # The docs show a bare list, live responses wrap it in «items» — take both.
    items = result if isinstance(result, list) else result.get("items", [])
    if not items:
        return UNKNOWN
    return items[0].get("status", UNKNOWN)


# --- xRocket -------------------------------------------------------------


async def _xrocket_create(coins: int, amount: str, user_id: int) -> Invoice:
    body = await _call(
        "POST",
        f"{XROCKET_API.rstrip('/')}/tg-invoices",
        {"Rocket-Pay-Key": keys()[XROCKET]},
        {
            "amount": float(amount),
            "numPayments": 1,
            "currency": asset(),
            "description": f"{coins} монеток",
            "payload": f"{user_id}:{coins}",
            "expiredIn": INVOICE_TTL,
            "commentsEnabled": False,
        },
    )
    if not body.get("success", True):
        raise CryptoError(str(body.get("message") or body)[:200])
    data = body["data"]
    return Invoice(XROCKET, str(data["id"]), data.get("link", ""), amount, asset())


async def _xrocket_status(invoice_id: str) -> str:
    body = await _call(
        "GET",
        f"{XROCKET_API.rstrip('/')}/tg-invoices/{invoice_id}",
        {"Rocket-Pay-Key": keys()[XROCKET]},
    )
    if not body.get("success", True):
        raise CryptoError(str(body.get("message") or body)[:200])
    return body.get("data", {}).get("status", UNKNOWN)


# --- what the handlers use -----------------------------------------------

_CREATE = {CRYPTOBOT: _cryptobot_create, XROCKET: _xrocket_create}
_STATUS = {CRYPTOBOT: _cryptobot_status, XROCKET: _xrocket_status}


async def create(provider: str, coins: int, user_id: int) -> Invoice:
    if provider not in _CREATE or not keys().get(provider):
        raise CryptoError(f"провайдер {provider} не настроен")
    invoice = await _CREATE[provider](coins, price(coins), user_id)
    if not invoice.link:
        raise CryptoError("провайдер не вернул ссылку на оплату")
    logger.info(
        "%s invoice %s for %s: %s %s", provider, invoice.invoice_id, user_id,
        invoice.amount, invoice.asset,
    )
    return invoice


async def status(provider: str, invoice_id: str) -> str:
    """paid / active / expired / unknown — never raises for a caller to guess."""
    if provider not in _STATUS or not keys().get(provider):
        return UNKNOWN
    try:
        raw = await _STATUS[provider](invoice_id)
    except CryptoError as error:
        logger.warning("%s status %s failed: %s", provider, invoice_id, error)
        return UNKNOWN
    return {PAID: PAID, ACTIVE: ACTIVE, EXPIRED: EXPIRED}.get(raw, UNKNOWN)


async def _alive(provider: str) -> bool:
    """Is the service itself up? The only call that needs no key."""
    api = CRYPTOBOT_API if provider == CRYPTOBOT else XROCKET_API
    path = "/getMe" if provider == CRYPTOBOT else "/version"
    try:
        await _call("GET", f"{api.rstrip('/')}{path}", {})
    except CryptoError as error:
        # CryptoBot has no unauthenticated endpoint at all: a refusal there
        # still proves the service answered.
        return provider == CRYPTOBOT and str(error).startswith(("401", "403"))
    return True


async def check_key(provider: str) -> str:
    """A line for the panel: is this key actually good for anything."""
    key = keys().get(provider, "")
    if not key:
        return "⚪ ключа нет"
    try:
        if provider == CRYPTOBOT:
            body = await _call(
                "GET",
                f"{CRYPTOBOT_API.rstrip('/')}/getMe",
                {"Crypto-Pay-API-Token": key},
            )
            if not body.get("ok"):
                raise CryptoError(str(body.get("error") or body)[:120])
            name = body["result"].get("name", "")
        else:
            body = await _call(
                "GET",
                f"{XROCKET_API.rstrip('/')}/app/info",
                {"Rocket-Pay-Key": key},
            )
            if not body.get("success", True):
                raise CryptoError(str(body.get("message") or body)[:120])
            name = body.get("data", {}).get("name", "")
    except CryptoError as error:
        text = str(error)
        # «Ключ не работает» and «сервис лежит» are different problems with
        # different fixes, and only one of them is worth touching .env over.
        if text.startswith(("401", "403")):
            return f"🔴 ключ отклонён сервисом.\n{KEY_HINTS[provider]}"
        if not await _alive(provider):
            return f"🟡 сервис не отвечает: {text[:120]}"
        return f"🔴 ключ не работает: {text[:120]}"
    return f"🟢 подключено{f' · {name}' if name else ''}"
