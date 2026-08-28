import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    Message,
)

import access
import db
import emoji
import invoices
import pushes
import settings
import texts
import ui
from config import ADMIN_IDS, BOT_TOKEN
from handlers import (
    admin,
    common,
    moderation,
    payments,
    payouts,
    profiles,
    subscribe,
    upload,
    watch,
)
from middlewares.user import UserMiddleware

fallback = Router()


@fallback.message(F.chat.type == ChatType.PRIVATE)
async def anything_else(message: Message) -> None:
    """No dead ends: whatever arrives, the panel comes back."""
    await ui.render_menu(message, message.from_user.id)


@fallback.callback_query()
async def stale_button(call: CallbackQuery) -> None:
    """Button from a message whose state is gone — never leave a spinner hanging."""
    await call.answer(texts.STALE_BUTTON)
    with suppress(TelegramAPIError):
        await call.message.delete()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await db.connect()
    await settings.load()

    # Load custom emoji and texts from database
    import emoji_manager
    import text_manager
    await emoji_manager.load_from_db()
    await text_manager.load_from_db()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    await emoji.resolve(bot)  # real placeholders, or plain unicode if unavailable
    await emoji_manager.resolve(bot)  # resolve custom emoji too
    access.bot_username = (await bot.me()).username  # referral links need it

    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_routers(
        admin.router,
        moderation.router,
        subscribe.router,
        common.router,
        payments.router,
        payouts.router,
        profiles.router,
        watch.router,
        upload.router,
        fallback,
    )

    public = [
        BotCommand(command="start", description="Кружочки"),
        BotCommand(command="menu", description="Меню"),
    ]
    await bot.set_my_commands(public)
    for admin_id in ADMIN_IDS:  # /admin shows up only in the admins' own chats
        with suppress(TelegramAPIError):
            await bot.set_my_commands(
                public + [BotCommand(command="admin", description="Админ-панель")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )

    reminders = asyncio.create_task(pushes.run(bot))
    # Crypto invoices are confirmed by asking, not by being told — see crypto.py.
    watcher = asyncio.create_task(invoices.run(bot))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        reminders.cancel()
        watcher.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    with_suppress = (KeyboardInterrupt, SystemExit)
    try:
        asyncio.run(main())
    except with_suppress:
        pass
