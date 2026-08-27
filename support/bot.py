"""Support bot entry point.

Router order is the contract here: the support chat is handled before the
private-chat router, and the catch-all inside handlers.user is last. Getting this
wrong is how a moderator's reply ends up treated as a user's message.
"""

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

import cards
import db
import mainbase
import settings
import texts
from config import ADMIN_IDS, BOT_TOKEN, SLA_TICK
from handlers import admin, reply, user
from middlewares.user import BlockMiddleware

logger = logging.getLogger(__name__)


async def sla_sweep(bot: Bot) -> int:
    """Ping the chat about tickets nobody answered in time.

    The stamp goes down before the send, so a failure cannot queue the same
    ticket up again on the next tick.
    """
    chat = settings.support_chat()
    if not chat:
        return 0

    overdue = await db.overdue(
        settings.get("sla_hours"), settings.get("sla_repeat_hours")
    )
    sent = 0
    for ticket in overdue:
        await db.mark_pinged(ticket["id"])
        try:
            await bot.send_message(
                chat,
                texts.sla_ping(ticket),
                reply_to_message_id=ticket["admin_msg_id"] or None,
            )
            sent += 1
        except TelegramAPIError as error:
            logger.warning("SLA ping for #%s failed: %s", ticket["id"], error)
    if sent:
        logger.info("SLA: %s tickets nudged", sent)
    return sent


async def sla_loop(bot: Bot) -> None:
    """Background loop; one crash must not take the polling down with it."""
    while True:
        await asyncio.sleep(SLA_TICK)
        with suppress(Exception):
            await sla_sweep(bot)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await db.connect()
    await settings.load()
    await mainbase.connect()  # read-only, optional

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(BlockMiddleware())
    dp.callback_query.middleware(BlockMiddleware())

    # admin first (it owns /admin), then the support chat, then private chats.
    # handlers.user ends with a catch-all, so it has to come last.
    dp.include_routers(admin.router, reply.router, user.router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Поддержка"),
            BotCommand(command="help", description="Частые вопросы"),
        ]
    )
    for admin_id in ADMIN_IDS:  # /admin shows up only in the admins' own chats
        with suppress(TelegramAPIError):
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Поддержка"),
                    BotCommand(command="help", description="Частые вопросы"),
                    BotCommand(command="admin", description="Панель поддержки"),
                ],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )

    if not settings.support_chat():
        logger.warning("support chat is not set — cards will have nowhere to go")

    sla = asyncio.create_task(sla_loop(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        sla.cancel()
        await mainbase.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
