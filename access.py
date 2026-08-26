"""Subscription gate and referrals.

The gate is a setting, not a constant: an admin points the bot at a channel from
the panel and it starts asking everyone to join. A referral counts only once the
invited user is through that gate — that is the whole point of tying the two
together, otherwise a link farm pays out on empty /start calls.

If the channel is misconfigured (bot not an admin, wrong id) getChatMember
fails, and the gate opens rather than locking every user out of the bot.
"""

import logging
import string
import time

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import settings
from config import ADMIN_IDS, SUB_CACHE

logger = logging.getLogger(__name__)

MEMBER_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}

_confirmed: dict[int, float] = {}  # user id -> moment the confirmation expires
_link_cache: dict[str, str] = {}  # channel -> https link

bot_username = ""  # filled in on startup, used to build referral links


def gate_on() -> bool:
    return bool(settings.get_text("channel").strip())


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    channel = settings.get_text("channel").strip()
    if not channel:
        return True
    if user_id in ADMIN_IDS:  # an admin locked out of the panel cannot fix the gate
        return True
    if _confirmed.get(user_id, 0.0) > time.monotonic():
        return True

    try:
        member = await bot.get_chat_member(channel, user_id)
    except TelegramAPIError as error:
        logger.warning(
            "gate: cannot check %s in %s (%s) — letting the user in",
            user_id, channel, error,
        )
        return True  # never lock the bot on a broken setting

    if member.status in MEMBER_STATUSES:
        _confirmed[user_id] = time.monotonic() + SUB_CACHE
        return True
    logger.info("gate: %s is %s in %s, blocked", user_id, member.status, channel)
    _confirmed.pop(user_id, None)
    return False


def forget(user_id: int) -> None:
    """Drop the cached confirmation, so the next check hits Telegram."""
    _confirmed.pop(user_id, None)


async def channel_link(bot: Bot) -> str:
    channel = settings.get_text("channel").strip()
    if not channel:
        return ""
    if channel.startswith("@"):
        return f"https://t.me/{channel[1:]}"
    if channel in _link_cache:
        return _link_cache[channel]

    try:  # numeric id: ask Telegram for a username or an invite link
        chat = await bot.get_chat(channel)
    except TelegramAPIError as error:
        logger.warning("cannot resolve channel %s: %s", channel, error)
        return ""
    link = (
        f"https://t.me/{chat.username}" if chat.username else (chat.invite_link or "")
    )
    if link:
        _link_cache[channel] = link
    return link


def drop_link_cache() -> None:
    _link_cache.clear()


async def gate_keyboard(bot: Bot) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    link = await channel_link(bot)
    if link:
        b.row(
            InlineKeyboardButton(text="Подписаться", url=link, style=kb.PRIMARY)
        )
    b.row(
        InlineKeyboardButton(
            text="Я подписался", callback_data="sub:check", style=kb.SUCCESS
        )
    )
    return b.as_markup()


# --- referrals -----------------------------------------------------------


def referral_link(user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=r{user_id}"


CODE_ALLOWED = set(string.ascii_lowercase + string.digits + "_-")


def parse_payload(payload: str) -> int | None:
    """/start r123456 -> 123456"""
    payload = (payload or "").strip()
    if not payload.startswith("r") or not payload[1:].isdigit():
        return None
    return int(payload[1:])


def parse_campaign(payload: str) -> str | None:
    """Anything that is not a referral link is treated as an ad campaign code."""
    code = (payload or "").strip().lower()
    if not code or parse_payload(code) is not None:
        return None
    if len(code) > 32 or not set(code) <= CODE_ALLOWED:
        return None
    return code


def campaign_link(code: str) -> str:
    return f"https://t.me/{bot_username}?start={code}"


async def remember_referrer(user_id: int, payload: str) -> None:
    referrer = parse_payload(payload)
    if referrer is None or referrer == user_id:
        return
    if await db.set_referrer(user_id, referrer):
        logger.info("referral: %s invited by %s", user_id, referrer)


async def credit_referral(bot: Bot, user_id: int) -> None:
    """Pay the inviter once the invited user is past the gate."""
    referrer = await db.take_referral(user_id)
    if referrer is None:
        return

    reward = settings.get("ref_reward")
    if reward:
        await db.add_coins(referrer, reward)
    logger.info("referral: %s confirmed, %s paid %s", user_id, referrer, reward)

    done, _ = await db.referral_counts(referrer)
    try:
        await bot.send_message(
            referrer,
            f"🟢 По твоей ссылке пришёл друг: <b>+{reward}</b> монеток.\n"
            f"Всего приглашено: {done}",
        )
    except TelegramAPIError:  # blocked the bot, nothing to do about it
        pass
