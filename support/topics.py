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
from aiogram.enums import ChatMemberStatus
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
    """True when the operators' chat is a forum and the bot may manage topics.

    Only a positive verdict is cached. A negative one is re-checked every time:
    turning the group into a forum, or granting the right, happens in Telegram
    without telling the bot, and caching "no" would keep topics off until the
    next restart — which is exactly how this looked broken.
    """
    if not chat:
        return False
    key = str(chat)
    if _chat_ok.get(key):
        return True

    ok = False
    try:
        info = await bot.get_chat(chat)
        if not info.is_forum:
            logger.info(
                "chat %s is not a forum — enable Topics in its Telegram settings "
                "to give every ticket a thread; cards go to the general feed",
                chat,
            )
        else:
            member = await bot.get_chat_member(chat, await _self_id(bot))
            # The creator has every right but carries no can_manage_topics field
            # at all, so asking for the flag alone would answer "no".
            ok = member.status == ChatMemberStatus.CREATOR or bool(
                getattr(member, "can_manage_topics", False)
            )
            if not ok:
                logger.warning(
                    "chat %s is a forum but the bot is %s without can_manage_topics "
                    "— grant it «Управление темами»",
                    chat, member.status,
                )
    except TelegramAPIError as error:
        logger.warning("cannot inspect chat %s (%s), assuming no topics", chat, error)

    if ok:  # negatives stay unmemoised on purpose, see the docstring
        _chat_ok[key] = True
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


# --- closing ------------------------------------------------------------


CLOSED_PREFIX = "✅ "


async def close_ticket_topics(bot: Bot, ticket, chat: int | str) -> bool:
    """Wrap up both of a ticket's topics. True when the user's one was deleted.

    The two sides differ because the point of each thread differs. In the
    operators' group the history is the record — a moderator looks a ticket up
    weeks later — so the topic is closed, not deleted: it drops to the bottom of
    the list and nobody keeps typing in it.

    In the user's own chat the thread is clutter once the question is answered,
    and `closeForumTopic` does not exist for private chats anyway. So it is
    deleted outright. That takes the ticket's messages with it, which is why the
    caller must send the closing notice and the rating buttons *after* this runs,
    outside the topic — see cards.close_topics.

    The boolean is what tells the caller whether the topic is really gone; a
    failed delete leaves the thread usable, and the notice should stay in it.
    """
    deleted = await _delete_user_topic(bot, ticket)
    await _close_chat_topic(bot, chat, ticket)
    return deleted


async def _delete_user_topic(bot: Bot, ticket) -> bool:
    """deleteForumTopic works in private chats, and needs no admin rights there.

    Falls back to the ✅ rename when the delete fails, so a closed ticket never
    looks open — the thread is still there, just marked done.
    """
    thread = ticket["user_thread_id"]
    if not thread:
        return False
    try:
        await bot.delete_forum_topic(
            chat_id=ticket["user_id"], message_thread_id=thread
        )
    except TelegramAPIError as error:
        logger.warning(
            "topic %s of #%s not deleted (%s), marking it done instead",
            thread, ticket["id"], error,
        )
        await _rename_closed(bot, ticket["user_id"], thread, ticket)
        return False
    return True


async def _rename_closed(bot: Bot, chat: int | str, thread: int | None, ticket) -> None:
    """editForumTopic works in private chats; closeForumTopic does not."""
    if not thread:
        return
    name = f"{CLOSED_PREFIX}{topic_name(ticket)}"[:128]
    try:
        await bot.edit_forum_topic(
            chat_id=chat, message_thread_id=thread, name=name
        )
    except TelegramAPIError as error:
        # Cosmetic: the ticket is closed regardless of what the topic is called.
        logger.debug("topic %s of #%s not renamed: %s", thread, ticket["id"], error)


async def _close_chat_topic(bot: Bot, chat: int | str, ticket) -> None:
    thread = ticket["chat_thread_id"]
    if not chat or not thread:
        return
    # Renamed first: a closed topic can still be edited, but doing it in this
    # order means the ✅ is already there when it collapses out of view.
    await _rename_closed(bot, chat, thread, ticket)
    try:
        await bot.close_forum_topic(chat_id=chat, message_thread_id=thread)
    except TelegramAPIError as error:
        logger.debug("topic %s of #%s not closed: %s", thread, ticket["id"], error)
