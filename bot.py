import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, CallbackQuery, Message

import db
import ui
from config import BOT_TOKEN
from handlers import admin, common, moderation, payments, upload, watch
from middlewares.user import UserMiddleware

fallback = Router()


@fallback.message(F.chat.type == ChatType.PRIVATE)
async def anything_else(message: Message) -> None:
    """No dead ends: whatever arrives, the panel comes back."""
    await ui.render_menu(message, message.from_user.id)


@fallback.callback_query()
async def stale_button(call: CallbackQuery) -> None:
    """Button from a message whose state is gone — never leave a spinner hanging."""
    await call.answer("Кнопка устарела")
    await ui.render_menu(call, call.from_user.id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await db.connect()

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(UserMiddleware())
    dp.callback_query.middleware(UserMiddleware())

    dp.include_routers(
        admin.router,
        moderation.router,
        common.router,
        payments.router,
        upload.router,
        watch.router,
        fallback,
    )

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Кружочки"),
            BotCommand(command="menu", description="Меню"),
        ]
    )

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    with_suppress = (KeyboardInterrupt, SystemExit)
    try:
        asyncio.run(main())
    except with_suppress:
        pass
