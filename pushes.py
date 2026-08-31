"""Re-engagement pushes.

A user who watched a few circles and drifted away comes back for a free one.
The sweep runs on a timer, picks people who have been quiet long enough and were
not nudged recently, and hands each a circle on the house — the reminder is
worth sending only if there is something behind the button.

Every pass leaves a trace in `last_sweep`: a job that quietly stopped sending
looks exactly like a job that has nobody to send to, and the panel has to be
able to tell the two apart.
"""

import asyncio
import logging
import random
import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

import db
import keyboards as kb
import settings
import texts

logger = logging.getLogger(__name__)

SEND_PAUSE = 0.05  # ~20 per second, same ceiling as the broadcast
FIRST_SWEEP = 60.0  # after a restart, do not make the first batch wait a tick

# Filled in by every pass, read by the admin panel.
last_sweep: dict = {"at": 0.0, "sent": 0, "failed": 0, "skipped": "", "error": ""}


async def sweep(bot: Bot) -> tuple[int, int]:
    """One pass. Returns (delivered, failed)."""
    last_sweep["at"] = time.time()
    last_sweep["error"] = ""
    last_sweep["skipped"] = ""

    if not settings.get("push_enabled"):
        last_sweep["skipped"] = "напоминания выключены"
        last_sweep["sent"] = last_sweep["failed"] = 0
        return 0, 0

    idle = settings.get("push_idle_hours") * 3600
    cooldown = settings.get("push_cooldown_hours") * 3600
    batch = settings.get("push_batch")

    user_ids = await db.idle_users(idle, cooldown, batch)
    # Whatever is left of the batch goes to people who pressed /start, met the
    # rules and never came back. They are half the base and were never written
    # to at all — but they come second, because somebody who took the rules is
    # worth more than somebody who has not yet.
    newcomers = []
    if settings.get("push_unaccepted") and len(user_ids) < batch:
        newcomers = await db.idle_users(
            idle, cooldown, batch - len(user_ids), accepted=0
        )
    if not user_ids and not newcomers:
        last_sweep["skipped"] = "некому: все были в боте недавно"
        last_sweep["sent"] = last_sweep["failed"] = 0
        return 0, 0

    free = settings.get("push_free_views")
    sent = failed = 0
    for user_id, accepted in [(u, True) for u in user_ids] + [
        (u, False) for u in newcomers
    ]:
        # The stamp goes down before the send: a failure must not queue the
        # same person up again on the next tick.
        await db.mark_pushed(user_id, free)
        text = (
            random.choice(texts.PUSH_TEXTS)(free)
            if accepted
            else texts.push_unaccepted(free)
        )
        markup = kb.push(free) if accepted else kb.push_unaccepted()
        if await _deliver(bot, user_id, text, markup):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(SEND_PAUSE)

    last_sweep["sent"], last_sweep["failed"] = sent, failed
    logger.info(
        "push sweep: %s delivered, %s failed (%s из них — не принявшие правила)",
        sent, failed, len(newcomers),
    )
    return sent, failed


async def _deliver(bot: Bot, user_id: int, text: str, markup) -> bool:
    """One reminder. False when it did not land, for whatever reason."""
    try:
        await bot.send_message(user_id, text, reply_markup=markup)
        return True
    except TelegramRetryAfter as error:
        # The gift is already on their account; giving up here would waste it
        # on a limit that passes on its own.
        await asyncio.sleep(error.retry_after + 1)
        try:
            await bot.send_message(user_id, text, reply_markup=markup)
            return True
        except TelegramForbiddenError:
            await db.mark_blocked(user_id)
        except TelegramAPIError:
            pass
        return False
    except TelegramForbiddenError:
        # Blocked the bot, or deleted the account. Written down so the next
        # batch is not spent on them again — a third of every one was.
        await db.mark_blocked(user_id)
        return False
    except TelegramAPIError as error:
        logger.warning("push to %s failed: %s", user_id, error)
        return False


async def run(bot: Bot) -> None:
    """Background loop; one crash must not take the polling down with it."""
    from config import PUSH_TICK

    await asyncio.sleep(FIRST_SWEEP)
    while True:
        try:
            await sweep(bot)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            # Swallowing this silently is what made a broken job look like an
            # empty queue for as long as nobody read the logs.
            last_sweep["error"] = str(error)
            logger.exception("push sweep failed: %s", error)
        await asyncio.sleep(PUSH_TICK)  # cancelled here is how the loop ends
