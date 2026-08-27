"""Re-engagement pushes.

A user who watched a few circles and drifted away comes back for a free one.
The sweep runs on a timer, picks people who have been quiet long enough and were
not nudged recently, and hands each a circle on the house — the reminder is
worth sending only if there is something behind the button.

Quiet hours are respected: a bot that pings at four in the morning gets blocked,
not opened.
"""

import asyncio
import logging
import random
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

import db
import keyboards as kb
import settings
import texts

logger = logging.getLogger(__name__)

SEND_PAUSE = 0.05  # ~20 per second, same ceiling as the broadcast


def within_hours() -> bool:
    """True when local time is inside the allowed window."""
    hour = time.gmtime(time.time() + settings.get("push_tz_offset") * 3600).tm_hour
    start, end = settings.get("push_hour_from"), settings.get("push_hour_to")
    return start <= hour <= end if start <= end else hour >= start or hour <= end


async def sweep(bot: Bot) -> tuple[int, int]:
    """One pass. Returns (delivered, failed)."""
    if not settings.get("push_enabled") or not within_hours():
        return 0, 0

    user_ids = await db.idle_users(
        idle=settings.get("push_idle_hours") * 3600,
        cooldown=settings.get("push_cooldown_hours") * 3600,
        limit=settings.get("push_batch"),
    )
    if not user_ids:
        return 0, 0

    free = settings.get("push_free_views")
    sent = failed = 0
    for user_id in user_ids:
        # The stamp goes down before the send: a failure must not queue the
        # same person up again on the next tick.
        await db.mark_pushed(user_id, free)
        try:
            await bot.send_message(
                user_id,
                random.choice(texts.PUSH_TEXTS)(free),
                reply_markup=kb.push(free),
            )
            sent += 1
        except TelegramForbiddenError:  # blocked the bot
            failed += 1
        except TelegramAPIError as error:
            logger.warning("push to %s failed: %s", user_id, error)
            failed += 1
        await asyncio.sleep(SEND_PAUSE)

    logger.info("push sweep: %s delivered, %s failed", sent, failed)
    return sent, failed


async def run(bot: Bot) -> None:
    """Background loop; one crash must not take the polling down with it."""
    from config import PUSH_TICK

    while True:
        await asyncio.sleep(PUSH_TICK)
        with suppress(Exception):
            await sweep(bot)
