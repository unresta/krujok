from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import access
import db
import posts
from handlers import cheques
import keyboards as kb
import settings
import texts
from config import ADMIN_IDS

# The gate itself has to stay reachable, or the button that opens it is dead.
GATE_EXEMPT_CALLBACKS = {"sub:check", "accept"}


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

        # Telegram has already taken the stars: the coins must be credited even
        # for a banned user, during maintenance, and without a subscription.
        # The traffic buyer's report is the same: they are not here to use the bot.
        if isinstance(event, Message) and (
            event.successful_payment is not None
            or (event.text or "").startswith("/stat_")
        ):
            data["user"] = user
            return await handler(event, data)

        if user["banned"]:
            await self._refuse(event, texts.BANNED)
            return None
        if settings.maintenance() and not is_admin:
            await self._refuse(event, texts.MAINTENANCE)
            return None

        # A referral is recorded before the gate and paid after it; an ad code
        # is counted here too, or a user who never subscribes stays invisible.
        if isinstance(event, Message) and (event.text or "").startswith("/start "):
            payload = event.text.split(maxsplit=1)[1]
            await access.remember_referrer(tg_user.id, payload)
            # A cheque link has to survive the gate: the code is put aside now
            # and handed over the moment the subscription checks out.
            cheque = cheques.parse_link(payload)
            if cheque:
                await db.remember_cheque(tg_user.id, cheque)
            code = access.parse_campaign(payload)
            if code and not cheque:
                await db.touch_campaign(code, tg_user.id)

        if not self._exempt(event) and not await access.is_subscribed(
            data["bot"], tg_user.id
        ):
            await self._gate(event, data["bot"], tg_user.id)
            return None

        # Age and the rules are confirmed once, before anything else is shown.
        if not user["accepted"] and not self._exempt(event):
            await self._welcome(event)
            return None

        await db.touch_seen(tg_user.id)
        data["user"] = user
        result = await handler(event, data)
        # A promo post rides along after the bot has answered, never instead of
        # it — and only when this person has not seen one for a while.
        await posts.maybe_promo(data["bot"], tg_user.id)
        return result

    @staticmethod
    def _exempt(event: TelegramObject) -> bool:
        return (
            isinstance(event, CallbackQuery)
            and event.data in GATE_EXEMPT_CALLBACKS
        )

    @staticmethod
    async def _gate(event: TelegramObject, bot, user_id: int) -> None:
        # Only the channels they are actually missing, so a second tap does not
        # send them back to the ones they already joined.
        missing = await access.missing_channels(bot, user_id)
        markup = await access.gate_keyboard(bot, missing)
        text = texts.subscribe(len(missing))
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(text, reply_markup=markup)
        elif isinstance(event, Message):
            await event.answer(text, reply_markup=markup)

    @staticmethod
    async def _welcome(event: TelegramObject) -> None:
        markup = kb.accept()
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(texts.welcome(), reply_markup=markup)
        elif isinstance(event, Message):
            await event.answer(texts.welcome(), reply_markup=markup)

    @staticmethod
    async def _refuse(event: TelegramObject, text: str) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
