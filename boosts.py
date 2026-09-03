"""Telling an author what their paid reach actually bought.

Reach is sold by the day, so nothing in the bot happens when a run ends — and
an author who never learns what it did has no reason to buy a second one. This
loop watches for finished runs and sends the one line that sells the next: how
many people saw the profile, and how many bought.

The report goes out once per run (`profiles.boost_told`), so a restart in the
middle of a sweep cannot send it twice.
"""

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
import lang
import texts

logger = logging.getLogger(__name__)

TICK = 600.0  # seconds between sweeps; a report is not urgent to the minute
FIRST = 90.0  # let the bot finish starting before the first one
SEND_PAUSE = 0.05


async def sweep(bot: Bot) -> int:
    """Report on every run that has ended. Returns how many went out."""
    sent = 0
    for row in await db.finished_boosts():
        # The stamp goes down first: a send that fails must not queue the same
        # report up again on the next tick.
        await db.mark_boost_told(row["user_id"])
        with lang.use(await db.lang_of(row["user_id"])):
            report = texts.boost_report(
                max(0, row["shown"]), max(0, row["sold_during"])
            )
        try:
            await bot.send_message(row["user_id"], report)
            sent += 1
        except TelegramAPIError as error:  # blocked the bot, most likely
            logger.warning("boost report to %s failed: %s", row["user_id"], error)
        await asyncio.sleep(SEND_PAUSE)
    return sent


async def run(bot: Bot) -> None:
    """Background loop; one crash must not take the polling down with it."""
    await asyncio.sleep(FIRST)
    while True:
        try:
            sent = await sweep(bot)
            if sent:
                logger.info("boost reports: %s sent", sent)
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the loop outlives anything
            logger.exception("boost sweep failed: %s", error)
        await asyncio.sleep(TICK)
