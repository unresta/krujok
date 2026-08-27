"""Where cards go, and how they are built.

One module because both sides need it: the user handler posts a new card, the
admin handler redraws it after every verdict, and the SLA job pings it. Keeping
`send_card` and `refresh` together is what stops the two from drifting apart.
"""

import logging
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

import db
import keyboards as kb
import mainbase
import settings
import texts
import topics

logger = logging.getLogger(__name__)

# What the bot can forward into the chat, mapped to the sender it needs.
ATTACHMENT_SENDERS = {
    "photo": "send_photo",
    "video": "send_video",
    "document": "send_document",
    "voice": "send_voice",
    "video_note": "send_video_note",
    "animation": "send_animation",
    "audio": "send_audio",
    "sticker": "send_sticker",
}


def extract_attachment(message) -> tuple[str | None, str | None]:
    """(file_id, kind) of whatever came with the message, or (None, None).

    Photos arrive as a ladder of sizes; the last one is the largest.
    """
    if message.photo:
        return message.photo[-1].file_id, "photo"
    for kind in ("video", "document", "voice", "video_note", "animation", "audio", "sticker"):
        media = getattr(message, kind, None)
        if media is not None:
            return media.file_id, kind
    return None, None


async def card_text(ticket, body: str, attachment: str | None = None) -> str:
    """The card, enriched from the main base when that base is reachable."""
    extra = await mainbase.profile(ticket["user_id"])
    return texts.card(ticket, body, extra, attachment)


async def open_topics(bot: Bot, ticket):
    """Give a fresh ticket its two topics, and return the ticket with them set.

    Both sides are optional and independent: private-chat topics depend on a
    BotFather switch, the group one on that group being a forum. Whatever fails
    just stays None and the ticket runs flat, so this never blocks a ticket.
    """
    user_thread = await topics.create_user_topic(bot, ticket)
    chat_thread = await topics.create_chat_topic(bot, settings.support_chat(), ticket)
    if user_thread is None and chat_thread is None:
        return ticket
    await db.set_threads(ticket["id"], user_thread, chat_thread)
    return await db.get_ticket(ticket["id"])


def user_thread_of(ticket) -> int | None:
    """The ticket's topic in the user's own chat, or None."""
    keys = ticket.keys() if hasattr(ticket, "keys") else ticket
    return ticket["user_thread_id"] if "user_thread_id" in keys else None


async def to_user(bot: Bot, ticket, text: str, **kwargs) -> bool:
    """Send to the user inside their ticket's topic. False when they blocked us.

    Anything about one ticket belongs in that ticket's thread — a bare
    send_message would land in the general feed and split the conversation.
    """
    try:
        await bot.send_message(
            ticket["user_id"],
            text,
            message_thread_id=user_thread_of(ticket),
            **kwargs,
        )
        return True
    except TelegramForbiddenError:  # blocked the bot
        return False
    except TelegramAPIError as error:
        # A deleted topic must not swallow the message: retry in the main feed.
        if user_thread_of(ticket) is not None:
            logger.warning(
                "topic %s of #%s unusable (%s), falling back to the flat chat",
                user_thread_of(ticket), ticket["id"], error,
            )
            with suppress(TelegramAPIError):
                await bot.send_message(ticket["user_id"], text, **kwargs)
                return True
        logger.warning("message to %s failed: %s", ticket["user_id"], error)
        return False


async def send_card(bot: Bot, ticket, body: str, file_id: str | None, file_type: str | None) -> None:
    """Post a fresh ticket to the support chat and remember its message id.

    The id is the anchor every later reply resolves through, so a failure to
    store it would orphan the ticket — hence it is saved before the attachment
    is sent, and the attachment failing does not undo the card.
    """
    chat = settings.support_chat()
    if not chat:
        logger.error("ticket #%s has nowhere to go: support chat is not set", ticket["id"])
        return

    label = texts.ATTACHMENT_LABEL.get(file_type or "", file_type)
    blocked = await db.is_blocked(ticket["user_id"])
    thread = _thread_of(ticket)
    try:
        card = await bot.send_message(
            chat,
            await card_text(ticket, body, label),
            reply_markup=kb.card(ticket["id"], ticket["status"], bool(ticket["taken_by"]), blocked),
            message_thread_id=thread,
        )
    except TelegramAPIError as error:
        logger.error("card for #%s not delivered to %s: %s", ticket["id"], chat, error)
        return

    await db.set_admin_msg(ticket["id"], card.message_id)

    if file_id and file_type in ATTACHMENT_SENDERS:
        await _send_attachment(bot, chat, file_id, file_type, card.message_id, thread)


def _thread_of(ticket) -> int | None:
    """The ticket's topic in the operators' chat, or None on a flat setup."""
    keys = ticket.keys() if hasattr(ticket, "keys") else ticket
    return ticket["chat_thread_id"] if "chat_thread_id" in keys else None


async def _send_attachment(
    bot: Bot,
    chat,
    file_id: str,
    file_type: str,
    reply_to: int,
    thread: int | None = None,
) -> None:
    """Attached as a reply to the card, so the two stay together in the chat."""
    send = getattr(bot, ATTACHMENT_SENDERS[file_type])
    try:
        await send(
            chat, file_id, reply_to_message_id=reply_to, message_thread_id=thread
        )
    except TelegramAPIError as error:
        logger.warning("attachment (%s) for card %s failed: %s", file_type, reply_to, error)


async def post_followup(bot: Bot, ticket, body: str, file_id: str | None, file_type: str | None) -> None:
    """A later message from the user, hung under the original card."""
    chat = settings.support_chat()
    if not chat or not ticket["admin_msg_id"]:
        return
    label = texts.ATTACHMENT_LABEL.get(file_type or "", file_type)
    thread = _thread_of(ticket)
    try:
        note = await bot.send_message(
            chat,
            texts.user_message_added(ticket["id"], body, label),
            # Inside a topic the thread already groups it; the reply would only
            # add noise. Without one, the reply is the sole link to the ticket.
            reply_to_message_id=None if thread else ticket["admin_msg_id"],
            message_thread_id=thread,
        )
    except TelegramAPIError as error:
        logger.warning("follow-up for #%s not delivered: %s", ticket["id"], error)
        return
    if file_id and file_type in ATTACHMENT_SENDERS:
        await _send_attachment(bot, chat, file_id, file_type, note.message_id, thread)


async def post_self_closed(bot: Bot, ticket) -> None:
    """Tell the chat the user closed it themselves.

    The redrawn card already says so, but a moderator who is mid-reply is
    looking at the chat, not re-reading the card — so this lands as a reply
    under it, where they will actually see it.
    """
    chat = settings.support_chat()
    if not chat or not ticket["admin_msg_id"]:
        return
    thread = _thread_of(ticket)
    with suppress(TelegramAPIError):
        await bot.send_message(
            chat,
            texts.self_closed_notice(ticket["id"]),
            reply_to_message_id=None if thread else ticket["admin_msg_id"],
            message_thread_id=thread,
        )


async def refresh(bot: Bot, ticket_id: int) -> None:
    ticket = await db.get_ticket(ticket_id)
    if ticket is None or not ticket["admin_msg_id"]:
        return
    chat = settings.support_chat()
    if not chat:
        return

    messages = await db.thread(ticket_id, limit=1)
    body = messages[0]["text"] if messages else ""
    label = texts.ATTACHMENT_LABEL.get(
        messages[0]["file_type"] or "", messages[0]["file_type"]
    ) if messages else None
    blocked = await db.is_blocked(ticket["user_id"])

    try:
        await bot.edit_message_text(
            await card_text(ticket, body, label),
            chat_id=chat,
            message_id=ticket["admin_msg_id"],
            reply_markup=kb.card(
                ticket_id, ticket["status"], bool(ticket["taken_by"]), blocked
            ),
        )
    except TelegramAPIError as error:  # unchanged text, or too old to edit
        logger.debug("card #%s not redrawn: %s", ticket_id, error)
