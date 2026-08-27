"""Forum topics, on both sides of a ticket.

A ticket gets a topic in the user's own chat with the bot and a topic in the
operators' group. The conversations stop bleeding into one another: the user sees
one thread per question, and a moderator opens a topic instead of scrolling a
shared feed.

Everything here is optional by construction. Topic mode in private chats is a
BotFather switch on the bot itself — `has_topics_enabled` comes back from getMe
and cannot be turned on from code — and the group has to be a forum with
`can_manage_topics` granted. Any of that missing, every function returns None and
the bot falls back to the flat behaviour it had before. That is why tickets store
the thread ids as nullable columns rather than assuming they exist.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import texts

logger = logging.getLogger(__name__)

# The six colours the API accepts, one per ticket topic — six of each, so a
# moderator learns to read the category from the icon alone.
ICON_COLORS: dict[str, int] = {
    "pay": 16749490,     # 0xFF93B2 pink
    "coins": 16766590,   # 0xFFD67E yellow
    "anketa": 13338331,  # 0xCB86DB purple
    "circle": 7322096,   # 0x6FB9F0 blue
    "payout": 9367192,   # 0x8EEE98 green
    "other": 16478047,   # 0xFB6F5F red
}

# Resolved on startup by probe(); None means "not asked yet".
_private_enabled: bool | None = None
_bot_id: int | None = None  # cached from the same getMe, so checks stay offline
# Cached per chat id, since is_forum and the bot's rights rarely change.
_chat_ok: dict[str, bool] = {}


async def probe(bot: Bot) -> bool:
    """Ask getMe whether this bot has topic mode in private chats.

    Only getMe reports it, and only for the bot itself — there is no way to ask
    about one particular user, and no way to switch it on from here.
    """
    global _private_enabled, _bot_id
    try:
        me = await bot.me()
    except TelegramAPIError as error:
        logger.warning("getMe failed (%s), assuming no topics in private chats", error)
        _private_enabled = False
        return False

    _private_enabled = bool(me.has_topics_enabled)
    _bot_id = me.id
    if _private_enabled:
        logger.info("topic mode is on in private chats")
    else:
        logger.info(
            "topic mode is off in private chats — enable it for this bot in "
            "@BotFather to give every ticket its own thread"
        )
    return _private_enabled


def private_enabled() -> bool:
    return bool(_private_enabled)


async def _self_id(bot: Bot) -> int:
    """The bot's own id, cached — asking Telegram per check is wasteful."""
    global _bot_id
    if _bot_id is None:
        _bot_id = (await bot.me()).id
    return _bot_id


async def chat_supported(bot: Bot, chat: int | str) -> bool:
    """True when the operators' chat is a forum and the bot may manage topics."""
    if not chat:
        return False
    key = str(chat)
    if key in _chat_ok:
        return _chat_ok[key]

    ok = False
    try:
        info = await bot.get_chat(chat)
        if not info.is_forum:
            logger.info("chat %s is not a forum, cards go to the general feed", chat)
        else:
            member = await bot.get_chat_member(chat, await _self_id(bot))
            ok = bool(getattr(member, "can_manage_topics", False))
            if not ok:
                logger.warning(
                    "chat %s is a forum but the bot lacks can_manage_topics", chat
                )
    except TelegramAPIError as error:
        logger.warning("cannot inspect chat %s (%s), assuming no topics", chat, error)

    _chat_ok[key] = ok
    return ok


def forget_chat(chat: int | str | None = None) -> None:
    """Drop the cached verdict — the admin pointed the bot at another chat."""
    if chat is None:
        _chat_ok.clear()
    else:
        _chat_ok.pop(str(chat), None)


def topic_name(ticket) -> str:
    """What the thread is called on both sides: number first, so it sorts."""
    return f"#{ticket['id']} · {texts.topic_label(ticket['topic'])}"


async def _create(bot: Bot, chat: int | str, ticket) -> int | None:
    try:
        topic = await bot.create_forum_topic(
            chat_id=chat,
            name=topic_name(ticket)[:128],  # the API caps the name at 128
            icon_color=ICON_COLORS.get(ticket["topic"], ICON_COLORS["other"]),
        )
    except TelegramAPIError as error:
        # Not fatal anywhere: the caller keeps the ticket and sends flat instead.
        logger.warning("topic for #%s in %s not created: %s", ticket["id"], chat, error)
        return None
    return topic.message_thread_id


async def create_user_topic(bot: Bot, ticket) -> int | None:
    """A thread in the user's own chat. No admin rights involved there."""
    if not private_enabled():
        return None
    return await _create(bot, ticket["user_id"], ticket)


async def create_chat_topic(bot: Bot, chat: int | str, ticket) -> int | None:
    """A thread in the operators' group, if that group is a forum."""
    if not await chat_supported(bot, chat):
        return None
    return await _create(bot, chat, ticket)
