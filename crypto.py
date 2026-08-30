"""Crypto checkout through CryptoBot and xRocket.

Both are the same shape: create an invoice, hand the payer its link, and find
out later whether it was paid. Neither is asked to push that news to us —
nothing in this deployment is reachable from the internet, so there is no
webhook endpoint to point them at. The bot polls its own open invoices
instead (see invoices.poll), which costs one request per open invoice and
needs no infrastructure at all.

    CryptoBot  https://pay.crypt.bot/api/<method>, header Crypto-Pay-API-Token
    xRocket v1 https://pay.xrocket.exchange/tg-invoices, header Rocket-Pay-Key
    xRocket v2 https://pay.api.xrocket.exchange/api/v1/invoices, Bearer token

xRocket has two Pay APIs at once. They are separate services with separate
credentials, and the app's «API Version» in @xRocket decides which token its
owner is given — so a v2 token sent to v1 comes back «Unknown API Key», which
looks exactly like a wrong key. The bot works out which API a key belongs to by
asking both once, and remembers the answer; the admin pastes whatever the bot
gave them and nothing else needs saying.

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
    XROCKET_API_V2,
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
        "Токен берётся в @xRocket → Pay API → приложение → API Token. "
        "Бот сам понимает, от какой версии API ключ, так что переключать "
        "приложение не нужно — но после смены «API Version» токен выдаётся "
        "заново, а новый v2-токен гасит предыдущий v2-токен. Тестовый ключ "
        "(@xrocket_testnet_bot) на боевом адресе даёт такой же отказ. "
        "И проверь, что контейнер перезапущен после правки .env."
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


def _reason(body) -> str:
    """The one line worth reading out of a refusal, whichever shape it came in.

    Three providers, three envelopes: CryptoBot's `error`, xRocket v1's
    `message`, v2's RFC 9457 `detail`. Dumping the whole body instead buries
    the sentence that says what to fix.
    """
    if isinstance(body, dict):
        for key in ("detail", "message", "error", "title"):
            value = body.get(key)
            if value:
                return str(value)[:200]
    return str(body)[:200]


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
                    raise CryptoError(f"{response.status}: {_reason(body)}")
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

V1, V2 = "v1", "v2"
_flavour: str | None = None  # which Pay API this key belongs to, once we know


def _v1_headers() -> dict:
    return {"Rocket-Pay-Key": keys()[XROCKET]}


def _v2_headers() -> dict:
    return {"Authorization": f"Bearer {keys()[XROCKET]}"}


def _v2_error(body: dict) -> str:
    """v2 answers in RFC 9457 problem details — there is no success envelope."""
    return str(body.get("detail") or body.get("title") or body)[:200]


async def _xrocket_flavour() -> str:
    """Which Pay API the key opens. Asked once, then remembered.

    v2 is tried first because it is the one the bot hands out now; v1 is
    deprecated and only still around for apps nobody has migrated.
    """
    global _flavour
    if _flavour:
        return _flavour
    for flavour, url, headers in (
        (V2, f"{XROCKET_API_V2.rstrip('/')}/api/v1/app-info", _v2_headers()),
        (V1, f"{XROCKET_API.rstrip('/')}/app/info", _v1_headers()),
    ):
        try:
            await _call("GET", url, headers)
        except CryptoError:
            continue
        _flavour = flavour
        logger.info("xrocket: ключ опознан как Pay API %s", flavour)
        return flavour
    # Neither answered: say v2, so the error the admin sees names the current
    # API rather than the one on its way out.
    return V2


def forget_flavour() -> None:
    """After a key change the old answer is worthless — see the panel."""
    global _flavour
    _flavour = None


async def _xrocket_v2_create(coins: int, amount: str, user_id: int) -> Invoice:
    body = await _call(
        "POST",
        f"{XROCKET_API_V2.rstrip('/')}/api/v1/invoices",
        _v2_headers(),
        {
            # Every amount is a string in v2; a float here is a 400.
            "priceAmount": amount,
            "priceCurrency": asset(),
            "numPayments": 1,
            "description": f"{coins} монеток",
            # Omitting this does not mean «never» — it means about 41 days.
            "expiresIn": INVOICE_TTL,
            "data": {"userId": str(user_id), "coins": coins},
        },
    )
    links = body.get("links") or {}
    link = (
        links.get("telegramBotLink")
        or links.get("telegramMiniAppLink")
        or links.get("webLink")
        or ""
    )
    return Invoice(XROCKET, str(body["id"]), link, amount, asset())


async def _xrocket_v2_status(invoice_id: str) -> str:
    body = await _call(
        "GET",
        f"{XROCKET_API_V2.rstrip('/')}/api/v1/invoice?invoiceId={invoice_id}",
        _v2_headers(),
    )
    raw = body.get("status", UNKNOWN)
    # «partially_paid» is not paid — the poller must keep waiting, and the
    # invoice must not be closed as though the money arrived.
    return {"cancelled": EXPIRED, "partially_paid": ACTIVE}.get(raw, raw)


async def _xrocket_create(coins: int, amount: str, user_id: int) -> Invoice:
    if await _xrocket_flavour() == V2:
        return await _xrocket_v2_create(coins, amount, user_id)
    return await _xrocket_v1_create(coins, amount, user_id)


async def _xrocket_status(invoice_id: str) -> str:
    if await _xrocket_flavour() == V2:
        return await _xrocket_v2_status(invoice_id)
    return await _xrocket_v1_status(invoice_id)


async def _xrocket_v1_create(coins: int, amount: str, user_id: int) -> Invoice:
    body = await _call(
        "POST",
        f"{XROCKET_API.rstrip('/')}/tg-invoices",
        _v1_headers(),
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


async def _xrocket_v1_status(invoice_id: str) -> str:
    body = await _call(
        "GET",
        f"{XROCKET_API.rstrip('/')}/tg-invoices/{invoice_id}",
        _v1_headers(),
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
    """Is the service itself up? The one call that needs no key."""
    if provider == CRYPTOBOT:
        try:
            await _call("GET", f"{CRYPTOBOT_API.rstrip('/')}/getMe", {})
        except CryptoError as error:
            # CryptoBot has no unauthenticated endpoint at all: a refusal there
            # still proves the service answered.
            return str(error).startswith(("401", "403"))
        return True
    for url in (
        f"{XROCKET_API_V2.rstrip('/')}/health",
        f"{XROCKET_API.rstrip('/')}/version",
    ):
        try:
            await _call("GET", url, {})
            return True
        except CryptoError:
            continue
    return False


async def check_key(provider: str) -> str:
    """A line for the panel: is this key actually good for anything."""
    key = keys().get(provider, "")
    if not key:
        return "⚪ ключа нет"
    note = ""
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
            # Which API this key opens is the whole question here, so the
            # answer is what the panel shows.
            forget_flavour()
            flavour = await _xrocket_flavour()
            note = f" · Pay API {flavour}"
            if flavour == V2:
                body = await _call(
                    "GET",
                    f"{XROCKET_API_V2.rstrip('/')}/api/v1/app-info",
                    _v2_headers(),
                )
                name = body.get("name", "")
            else:
                body = await _call(
                    "GET", f"{XROCKET_API.rstrip('/')}/app/info", _v1_headers()
                )
                if not body.get("success", True):
                    raise CryptoError(_v2_error(body))
                name = body.get("data", {}).get("name", "")
                note += " (устарел, в боте переключи приложение на v2)"
    except CryptoError as error:
        text = str(error)
        # «Ключ не работает» and «сервис лежит» are different problems with
        # different fixes, and only one of them is worth touching .env over.
        if text.startswith(("401", "403")):
            return f"🔴 ключ отклонён сервисом.\n{KEY_HINTS[provider]}"
        if not await _alive(provider):
            return f"🟡 сервис не отвечает: {text[:120]}"
        return f"🔴 ключ не работает: {text[:120]}"
    return f"🟢 подключено{f' · {name}' if name else ''}{note}"
