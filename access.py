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
from contextlib import suppress

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import settings
import texts
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


async def adopt_legacy_channel() -> None:
    """The gate used to be one channel in the settings; keep it working.

    Called once on startup: whatever was set there becomes the first entry of
    the list, and the setting is cleared so it cannot come back to life later.
    """
    chat = settings.get_text("channel").strip()
    if not chat:
        return
    if await db.add_channel(chat) is not None:
        logger.info("gate: channel %s moved from settings into the list", chat)
    await settings.set_text("channel", "")


async def gate_channels() -> list:
    """The channels the gate demands right now, advertisers' ones included."""
    return await db.channels(active_only=True)


async def gate_on() -> bool:
    return bool(await gate_channels())


async def missing_channels(bot: Bot, user_id: int) -> list:
    """Which of the demanded channels this person is not in.

    A channel the bot cannot see into is not counted as missing: a broken
    setting must never lock the whole bot, and an advertiser who removes the
    bot from their channel should not take the users with them.
    """
    missing = []
    for channel in await gate_channels():
        try:
            member = await bot.get_chat_member(channel["chat"], user_id)
        except TelegramAPIError as error:
            logger.warning(
                "gate: cannot check %s in %s (%s) — not holding it against them",
                user_id, channel["chat"], error,
            )
            continue
        if member.status in MEMBER_STATUSES:
            # What the advertiser is paying for: this person, in their channel.
            await db.mark_join(channel["id"], user_id)
        else:
            missing.append(channel)
    return missing


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    if not await gate_on():
        return True
    if user_id in ADMIN_IDS:  # an admin locked out of the panel cannot fix the gate
        return True
    if _confirmed.get(user_id, 0.0) > time.monotonic():
        return True

    if await missing_channels(bot, user_id):
        _confirmed.pop(user_id, None)
        return False

    _confirmed[user_id] = time.monotonic() + SUB_CACHE
    if await db.mark_subscribed(user_id):  # first confirmation ever
        await _pay_subscription(bot, user_id)
    return True


async def _pay_subscription(bot: Bot, user_id: int) -> None:
    bonus = settings.get("sub_bonus")
    if not bonus:
        return
    await db.add_coins(user_id, bonus)
    with suppress(TelegramAPIError):  # the toast is nice to have, not required
        await bot.send_message(user_id, texts.sub_bonus(bonus))


def forget(user_id: int) -> None:
    """Drop the cached confirmation, so the next check hits Telegram."""
    _confirmed.pop(user_id, None)


async def channel_link(bot: Bot, chat: str) -> str:
    if chat.startswith("@"):
        return f"https://t.me/{chat[1:]}"
    if chat in _link_cache:
        return _link_cache[chat]

    try:  # numeric id: ask Telegram for a username or an invite link
        found = await bot.get_chat(chat)
    except TelegramAPIError as error:
        logger.warning("cannot resolve channel %s: %s", chat, error)
        return ""
    link = (
        f"https://t.me/{found.username}" if found.username else (found.invite_link or "")
    )
    if link:
        _link_cache[chat] = link
    return link


async def describe(bot: Bot, chat: str) -> tuple[str, str]:
    """(title, link) as Telegram knows it — for the panel and the gate."""
    link = await channel_link(bot, chat)
    try:
        found = await bot.get_chat(chat)
    except TelegramAPIError:
        return "", link
    return found.title or "", link


def drop_link_cache() -> None:
    _link_cache.clear()


async def gate_keyboard(bot: Bot, missing: list | None = None) -> InlineKeyboardMarkup:
    """One button per channel still missing, then the «I have joined» check."""
    b = InlineKeyboardBuilder()
    wanted = await gate_channels() if missing is None else missing
    for channel in wanted:
        link = channel["link"] or await channel_link(bot, channel["chat"])
        if not link:
            continue
        title = channel["title"] or channel["chat"]
        b.row(
            InlineKeyboardButton(
                text=f"📢 {title[:28]}", url=link, style=kb.PRIMARY
            )
        )
    b.row(
        InlineKeyboardButton(
            text="✅ Я подписался", callback_data="sub:check", style=kb.SUCCESS
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
        await bot.send_message(referrer, texts.referral_paid(reward, done))
    except TelegramAPIError:  # blocked the bot, nothing to do about it
        pass
