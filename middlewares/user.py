from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import db
import settings
import texts
from config import ADMIN_IDS


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
        is_admin = tg_user.id in ADMIN_IDS

        if user["banned"]:
            await self._refuse(event, texts.BANNED)
            return None
        if settings.maintenance() and not is_admin:
            await self._refuse(event, texts.MAINTENANCE)
            return None

        data["user"] = user
        return await handler(event, data)

    @staticmethod
    async def _refuse(event: TelegramObject, text: str) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
