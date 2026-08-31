"""Whether a person is already inside somebody else's bot.

Two ways to ask, and an advertiser hands over one or the other:

    botmembers — код от @BotMembersRobot, проверяется через BotStat
    token      — токен самого рекламируемого бота, его спрашивают напрямую

The token route asks the advertised bot about the user with getChat: a bot has
a chat with everyone who ever started it and with nobody else, so «chat not
found» is the answer «не запускал».

Nothing here is allowed to say «no» by accident. A service having a bad minute
returns None, and every caller reads that as «не знаем» rather than «не внутри»:
in the gate that lets the person through, in a promo it keeps showing the post.
Guessing the other way would either lock people out or quietly stop an advert
somebody paid for.
"""

from __future__ import annotations

import logging
import re

import aiohttp

import botstat
from config import INVOICE_TIMEOUT

logger = logging.getLogger(__name__)

BOTMEMBERS, TOKEN = "botmembers", "token"
METHODS = {BOTMEMBERS: "BotMembers", TOKEN: "токен бота"}

API = "https://api.telegram.org"

# 123456789:AA… — the shape Telegram issues. Checked before anything is stored,
# so a mistyped BotMembers code is not saved as a token and vice versa.
_TOKEN = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{30,}$")
_CODE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


class SponsorError(Exception):
    """The bot refused, or could not be reached."""


def looks_like_token(text: str) -> bool:
    return bool(_TOKEN.match((text or "").strip()))


def looks_like_code(text: str) -> bool:
    return bool(_CODE.match((text or "").strip())) and not looks_like_token(text)


def guess_method(text: str) -> str:
    """What the admin just pasted. One field, two kinds of credential."""
    if looks_like_token(text):
        return TOKEN
    return BOTMEMBERS if looks_like_code(text) else ""


async def _call(token: str, method: str, params: dict) -> tuple[bool, dict]:
    """(ok, body). Never raises for a network problem — see the module docstring."""
    url = f"{API}/bot{token}/{method}"
    timeout = aiohttp.ClientTimeout(total=INVOICE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as response:
                body = await response.json(content_type=None)
    except Exception as error:  # noqa: BLE001 — any failure is «unknown»
        raise SponsorError(str(error)) from error
    return bool(body.get("ok")), body


async def whoami(token: str) -> str:
    """@username of the bot this token belongs to. Raises if it is not a token."""
    ok, body = await _call(token, "getMe", {})
    if not ok:
        raise SponsorError(str(body.get("description") or body)[:200])
    return "@" + (body.get("result") or {}).get("username", "")


async def _started(token: str, user_id: int) -> bool | None:
    """Has this person ever started that bot? None when the answer is no answer.

    A bot cannot list its users, but it does have a private chat with each one,
    and only with those. «chat not found» is therefore a real «no», while an
    Unauthorized is a broken token and tells us nothing about the person.
    """
    try:
        ok, body = await _call(token, "getChat", {"chat_id": user_id})
    except SponsorError as error:
        logger.warning("спонсорский бот недоступен: %s", error)
        return None
    if ok:
        return True
    description = str(body.get("description") or "").lower()
    if "chat not found" in description or "user not found" in description:
        return False
    logger.warning("спонсорский бот ответил отказом: %s", description[:120])
    return None


async def check(method: str, secret: str, user_id: int) -> bool | None:
    """Is this person inside the sponsor's bot? None when nobody could tell us."""
    if not secret:
        return None
    if method == TOKEN:
        return await _started(secret, user_id)
    return await botstat.check_member(secret, user_id)


async def probe(method: str, secret: str, user_id: int) -> str:
    """A line for the panel: does this credential actually answer anything.

    Tried on the admin themselves, before it goes anywhere near a user — a
    credential nobody answers for would let a gate pass everyone unnoticed, or
    keep showing an advert to people who already converted.
    """
    if method == TOKEN:
        try:
            name = await whoami(secret)
        except SponsorError as error:
            return f"🔴 Токен не работает: {str(error)[:80]}"
        inside = await _started(secret, user_id)
        if inside is None:
            return f"🟡 {name}: токен рабочий, но проверить человека не вышло."
        seen = "запустившего" if inside else "не запустившего"
        return f"🟢 {name}: работает (тебя видит как {seen})."

    inside = await botstat.check_member(secret, user_id)
    if inside is None:
        return "🔴 BotStat не ответил — проверь код."
    seen = "запустившего" if inside else "не запустившего"
    return f"🟢 Код рабочий (тебя он видит как {seen})."
