"""Support's own ban list, applied only where it belongs.

The main bot's middleware taught the lesson this one is built around: it checks
`banned` and `accepted` for every update, group chats included, so a moderator's
plain reply inside a group would be swallowed by the welcome gate before any
handler saw it. Here the block check runs **only for private chats** — the
support chat is where the work happens and must stay untouched.

A ban here is support-local: it silences someone flooding the queue without
touching their access to the main bot.
"""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

import db
import texts
from config import ADMIN_IDS


def _is_private(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        return event.chat.type == ChatType.PRIVATE
    if isinstance(event, CallbackQuery):
        return (
            event.message is not None
            and event.message.chat.type == ChatType.PRIVATE
        )
    return False


class BlockMiddleware(BaseMiddleware):
    """Stops blocked users, and only them."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)

        # Group traffic — cards and moderator replies — passes straight through.
        if not _is_private(event):
            return await handler(event, data)

        # An admin must never lock themselves out of their own panel.
        if tg_user.id in ADMIN_IDS:
            return await handler(event, data)

        if await db.is_blocked(tg_user.id):
            if isinstance(event, CallbackQuery):
                await event.answer(texts.BLOCKED, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(texts.BLOCKED)
            return None

        return await handler(event, data)
