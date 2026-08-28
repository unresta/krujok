"""Posts the bot shows on its own: welcomes and promos.

An admin forwards a message once; the bot keeps where it lives and copies it
from there, so anything Telegram can send — photo, video, album-less media,
buttons of its own — works without the bot having to understand it.

    welcome — shown to a person once, right after /start
    promo   — comes round again while they use the bot, no more often than
              the «Показ раз в, ч» setting allows

Both are sold to advertisers, so every showing is counted.
"""

import logging
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
import settings

logger = logging.getLogger(__name__)

WELCOME, PROMO = "welcome", "promo"
KINDS = {WELCOME: "Приветка", PROMO: "Показ"}


async def send(bot: Bot, user_id: int, post, promo: bool = False) -> bool:
    """Copy one post to a user and remember that they have seen it."""
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=post["from_chat"],
            message_id=post["msg_id"],
        )
    except TelegramAPIError as error:
        # A deleted original, a bot kicked from the source chat, a blocked user:
        # none of it is worth failing whatever the user was actually doing.
        logger.warning("post %s not shown to %s: %s", post["id"], user_id, error)
        return False
    await db.mark_shown(user_id, post["id"], promo=promo)
    return True


async def show_welcome(bot: Bot, user_id: int) -> int:
    """Every welcome this person has not seen yet. Returns how many landed."""
    shown = 0
    for post in await db.unseen_welcome(user_id):
        if await send(bot, user_id, post):
            shown += 1
    return shown


async def maybe_promo(bot: Bot, user_id: int) -> bool:
    """Called after every handled update; almost always does nothing."""
    hours = settings.get("promo_every_hours")
    if not settings.get("promo_enabled") or not hours:
        return False
    if not await db.promo_due(user_id, hours * 3600):
        return False

    post = await db.pick_promo(user_id)
    if post is None:
        return False
    with suppress(TelegramAPIError):
        return await send(bot, user_id, post, promo=True)
    return False
