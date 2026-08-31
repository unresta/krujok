from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import access
import db
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

        # Who they are, kept current for the panel — written only when it moved.
        name = " ".join(filter(None, (tg_user.first_name, tg_user.last_name)))
        if (user["name"], user["username"]) != (name, tg_user.username or ""):
            await db.touch_identity(tg_user.id, name, tg_user.username or "")

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

        # They wrote to us, so they have not blocked the bot after all — and a
        # failed reminder had concluded otherwise. Cleared here rather than
        # further down: somebody who is still at the rules never gets past the
        # welcome, and they are exactly who the reminders are for.
        if user["blocked"]:
            await db.unmark_blocked(tg_user.id)

        # A referral is recorded before the gate and paid after it; an ad code
        # is counted here too, or a user who never subscribes stays invisible.
        if isinstance(event, Message) and (event.text or "").startswith("/start "):
            payload = event.text.split(maxsplit=1)[1]
            # One parser decides what the link is, so nothing is counted twice
            # and no kind can be mistaken for another.
            kind, value = access.parse_start(payload)
            if kind == "referral":
                await access.remember_referrer(tg_user.id, payload)
            elif kind == "profile":
                # Waits on the row until the gate and the rules are behind them.
                await db.remember_profile_link(
                    tg_user.id, access.parse_profile(value)
                )
            elif kind == "cheque":
                # The code waits here until the gate lets them through.
                await db.remember_cheque(tg_user.id, value)
            elif kind == "campaign":
                await db.touch_campaign(value, tg_user.id)

        if not self._exempt(event) and not await access.is_subscribed(
            data["bot"], tg_user.id
        ):
            await self._gate(event, data["bot"], tg_user.id)
            return None

        # Past the gate is what a referral is paid for, and the gate is passed
        # here — not in a handler. Hanging the payment off /start, «Согласен»
        # and «Я подписался» left everyone who joined the channel and then
        # tapped anything else uncredited, with no way to notice. The row is
        # already in hand, so this costs nothing until there is someone to pay.
        # Exempt events skipped the check above, so they may not be through yet;
        # their two handlers confirm it themselves.
        if not self._exempt(event) and user["ref_by"] and not user["ref_credited"]:
            await access.credit_referral(data["bot"], tg_user.id)

        # Age and the rules are confirmed once, before anything else is shown.
        if not user["accepted"] and not self._exempt(event):
            await self._welcome(event)
            return None

        await db.touch_seen(tg_user.id)
        data["user"] = user
        # Promos used to ride along here, after any update at all, which put
        # them in the middle of questions the bot had just asked. They hang off
        # a delivered circle now — see posts.after_circle.
        return await handler(event, data)

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
        text = texts.subscribe(
            len(missing), any(c["kind"] == "bot" for c in missing)
        )
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
