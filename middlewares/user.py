from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import db
import texts


class UserMiddleware(BaseMiddleware):
    """Makes sure a row exists and hands it to handlers as `user`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        user = await db.get_user(tg_user.id)
        if user["banned"]:
            if isinstance(event, CallbackQuery):
                await event.answer(texts.BANNED, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(texts.BANNED)
            return None

        data["user"] = user
        return await handler(event, data)
