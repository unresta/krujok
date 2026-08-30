"""BotStat: handing the user base to @BotManRobot and @BotSafeRobot.

Broadcasts do not run from this bot — a base of any size sent from here would
crawl and get the token rate-limited. BotMan does that job, so the bot's part
is to export ids and upload them:

    POST /botman/{bot_token}?owner_id=…        база уезжает в @BotManRobot
    POST /create/{bot_token}/{access_key}      проверка аудитории в @BotSafeRobot
    GET  /get/{username}/{access_key}          что BotStat думает о боте

Both uploads carry telegram ids and nothing else — no names, no messages, no
balances. Nothing here fires on its own: an admin has to press through a screen
that says what leaves and where it goes.
"""

from __future__ import annotations

import logging

import aiohttp

from config import BOTSTAT_API, BOTSTAT_KEY, BOT_TOKEN, INVOICE_TIMEOUT

logger = logging.getLogger(__name__)


class BotStatError(Exception):
    """The service refused, or could not be reached."""


def configured() -> bool:
    return bool(BOTSTAT_KEY.strip())


def base_file(user_ids: list[int]) -> bytes:
    """The upload format both tools take: one telegram id per line."""
    return ("\n".join(str(uid) for uid in user_ids) + "\n").encode()


async def _upload(url: str, ids: list[int], params: dict) -> dict:
    form = aiohttp.FormData()
    form.add_field(
        "file",
        base_file(ids),
        filename="base.txt",
        content_type="text/plain",
    )
    timeout = aiohttp.ClientTimeout(total=max(INVOICE_TIMEOUT, 60))
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, params=params, data=form) as response:
                body = await response.json(content_type=None)
    except aiohttp.ClientError as error:
        raise BotStatError(str(error)) from error
    except Exception as error:
        raise BotStatError(str(error)) from error

    if not body.get("ok"):
        message = (body.get("result") or {}).get("message") or str(body)
        raise BotStatError(str(message)[:200])
    return body.get("result") or {}


async def to_botman(ids: list[int], owner_id: int, folder_id: str = "") -> dict:
    """Upload the base so the owner can broadcast to it from @BotManRobot."""
    params = {"owner_id": str(owner_id)}
    if folder_id:
        params["folder_id"] = folder_id
    result = await _upload(
        f"{BOTSTAT_API.rstrip('/')}/botman/{BOT_TOKEN}", ids, params
    )
    logger.info("botman: %s ids uploaded for %s", len(ids), owner_id)
    return result


async def to_botsafe(ids: list[int], notify_id: int, hide: bool = False) -> dict:
    """Ask @BotSafeRobot how much of that base is alive."""
    if not configured():
        raise BotStatError("нет ключа BOTSTAT_KEY")
    params = {
        "notify_id": str(notify_id),
        "hide": "true" if hide else "false",
        "show_file_result": "true",
    }
    result = await _upload(
        f"{BOTSTAT_API.rstrip('/')}/create/{BOT_TOKEN}/{BOTSTAT_KEY.strip()}",
        ids,
        params,
    )
    logger.info("botsafe: check started for %s ids", len(ids))
    return result


async def check_member(code: str, user_id: int) -> bool | None:
    """Is this person inside that sponsor bot? None when the service is silent.

    The code itself is the credential here — no key, no token. An unknown
    answer must never be read as «not subscribed»: a service having a bad
    minute would otherwise lock everyone out of the bot.
    """
    url = f"{BOTSTAT_API.rstrip('/')}/checksub/{code}/{user_id}"
    timeout = aiohttp.ClientTimeout(total=INVOICE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status >= 400:
                    logger.warning("botmembers %s: HTTP %s", code, response.status)
                    return None
                body = await response.json(content_type=None)
    except Exception as error:  # noqa: BLE001 — any failure is «unknown»
        logger.warning("botmembers %s unreachable: %s", code, error)
        return None
    return bool(body.get("ok"))


async def bot_info(username: str) -> dict:
    """What BotStat already knows about the bot: live, dead, in chats."""
    if not configured():
        raise BotStatError("нет ключа BOTSTAT_KEY")
    url = (
        f"{BOTSTAT_API.rstrip('/')}/get/{username.lstrip('@')}/{BOTSTAT_KEY.strip()}"
    )
    timeout = aiohttp.ClientTimeout(total=INVOICE_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                body = await response.json(content_type=None)
    except Exception as error:
        raise BotStatError(str(error)) from error
    if not body.get("ok"):
        raise BotStatError(str(body.get("result") or body)[:200])
    return body.get("result") or {}
