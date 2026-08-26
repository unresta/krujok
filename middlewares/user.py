from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import access
import db
import settings
import texts
from config import ADMIN_IDS

# The gate itself has to stay reachable, or the button that opens it is dead.
GATE_EXEMPT_CALLBACKS = {"sub:check"}


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

        # A referral is recorded before the gate and paid after it.
        if isinstance(event, Message) and (event.text or "").startswith("/start "):
            await access.remember_referrer(
                tg_user.id, event.text.split(maxsplit=1)[1]
            )

        if not self._exempt(event) and not await access.is_subscribed(
            data["bot"], tg_user.id
        ):
            await self._gate(event, data["bot"])
            return None

        data["user"] = user
        return await handler(event, data)

    @staticmethod
    def _exempt(event: TelegramObject) -> bool:
        return (
            isinstance(event, CallbackQuery)
            and event.data in GATE_EXEMPT_CALLBACKS
        )

    @staticmethod
    async def _gate(event: TelegramObject, bot) -> None:
        markup = await access.gate_keyboard(bot)
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(texts.SUBSCRIBE, reply_markup=markup)
        elif isinstance(event, Message):
            await event.answer(texts.SUBSCRIBE, reply_markup=markup)

    @staticmethod
    async def _refuse(event: TelegramObject, text: str) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
