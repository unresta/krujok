"""Answering by replying, and the buttons on a card.

This is the whole point of the design: a moderator replies to a ticket card the
way they would reply to a person, and the text reaches the user as a message
from the bot. Nothing to remember, no command syntax, no panel to open.

Two things make it safe. The router only listens inside the configured support
chat, so callback ids leaked elsewhere do nothing. And the ticket is resolved
from the replied-to message id, which means a reply to anything else is simply
not a ticket and is left alone — moderators can talk in that chat normally.
"""

import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

import cards
import db
import keyboards as kb
import settings
import texts
from config import ADMIN_IDS, THREAD_LIMIT

logger = logging.getLogger(__name__)

router = Router()


def _in_support_chat(chat_id: int) -> bool:
    """True when this chat is the configured one. Admin DMs always qualify."""
    chat = settings.support_chat()
    if chat and str(chat_id) == str(chat):
        return True
    return chat_id in ADMIN_IDS


async def _deliver(bot: Bot, user_id: int, text: str) -> bool:
    try:
        await bot.send_message(user_id, text)
        return True
    except TelegramForbiddenError:  # blocked the bot
        return False
    except TelegramAPIError as error:
        logger.warning("reply to %s failed: %s", user_id, error)
        return False


# --- the reply itself ----------------------------------------------------


@router.message(F.reply_to_message)
async def reply_to_card(message: Message) -> None:
    """A reply in the support chat becomes the answer the user receives."""
    if not _in_support_chat(message.chat.id):
        return

    ticket = await db.ticket_by_admin_msg(message.reply_to_message.message_id)
    if ticket is None:
        # Not a card. Moderators chat here too, so this stays silent unless the
        # reply was aimed at the bot's own message and clearly meant for a user.
        if message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
            with suppress(TelegramAPIError):
                await message.reply(texts.NOT_A_TICKET)
        return

    if ticket["status"] == "closed":
        with suppress(TelegramAPIError):
            await message.reply(texts.TICKET_CLOSED_REPLY)
        return

    body = (message.text or message.caption or "").strip()
    file_id, file_type = cards.extract_attachment(message)
    if not body and not file_id:
        return

    await db.add_message(
        ticket["id"],
        message.from_user.id,
        body,
        from_admin=True,
        file_id=file_id,
        file_type=file_type,
    )

    delivered = True
    if body:
        delivered = await _deliver(
            message.bot, ticket["user_id"], texts.admin_reply(ticket["id"], body)
        )
    if file_id and file_type in cards.ATTACHMENT_SENDERS and delivered:
        send = getattr(message.bot, cards.ATTACHMENT_SENDERS[file_type])
        with suppress(TelegramAPIError):
            await send(ticket["user_id"], file_id)

    with suppress(TelegramAPIError):
        await message.reply(texts.REPLY_SENT if delivered else texts.REPLY_BLOCKED)
    await cards.refresh(message.bot, ticket["id"])


# --- buttons on a card ---------------------------------------------------


@router.callback_query(F.data.startswith("a:"))
async def card_action(call: CallbackQuery) -> None:
    """Every card button lands here; the chat check is the only authorisation."""
    if not _in_support_chat(call.message.chat.id):
        await call.answer(texts.NO_RIGHTS, show_alert=True)
        return

    parts = call.data.split(":")
    action, ticket_id = parts[1], int(parts[2])
    ticket = await db.get_ticket(ticket_id)
    if ticket is None:
        await call.answer("Обращение не найдено.", show_alert=True)
        return

    if action == "take":
        await _take(call, ticket_id)
    elif action == "close":
        await _close(call, ticket_id)
    elif action == "thread":
        await _thread(call, ticket_id)
    elif action == "canned":
        await _canned(call, ticket_id)
    elif action == "send":
        await _send_canned(call, ticket_id, int(parts[3]))
    elif action == "block":
        await _block(call, ticket, bool(int(parts[3])))
    elif action == "card":
        await _resend(call, ticket_id)
    else:
        await call.answer()


async def _take(call: CallbackQuery, ticket_id: int) -> None:
    taken = await db.take_ticket(ticket_id, call.from_user.id)
    if taken is None:
        # Somebody got there first — say who, so the second admin backs off.
        current = await db.get_ticket(ticket_id)
        holder = current["taken_by"] if current else "кем-то"
        await call.answer(f"Уже взято: {holder}", show_alert=True)
        await cards.refresh(call.bot, ticket_id)
        return
    await call.answer("Взято в работу 🔵")
    await cards.refresh(call.bot, ticket_id)
    with suppress(TelegramAPIError):
        await call.bot.send_message(taken["user_id"], texts.taken_notice(ticket_id))


async def _close(call: CallbackQuery, ticket_id: int) -> None:
    closed = await db.close_ticket(ticket_id, closed_by=call.from_user.id)
    if closed is None:
        await call.answer("Уже закрыто.", show_alert=True)
        await cards.refresh(call.bot, ticket_id)
        return

    await call.answer("Закрыто ⚪")
    await cards.refresh(call.bot, ticket_id)
    # The rating question is the last thing the user gets, and only once.
    with suppress(TelegramAPIError):
        await call.bot.send_message(
            closed["user_id"],
            texts.closed_notice(ticket_id),
            reply_markup=kb.rate(ticket_id),
        )


async def _thread(call: CallbackQuery, ticket_id: int) -> None:
    ticket = await db.get_ticket(ticket_id)
    messages = await db.thread(ticket_id, THREAD_LIMIT)
    with suppress(TelegramAPIError):
        await call.message.reply(texts.thread_view(ticket, messages))
    await call.answer()


async def _canned(call: CallbackQuery, ticket_id: int) -> None:
    rows = await db.canned_list()
    if not rows:
        await call.answer("Шаблонов нет. Добавь их в /admin.", show_alert=True)
        return
    with suppress(TelegramAPIError):
        await call.message.reply(
            "Какой шаблон отправить?", reply_markup=kb.canned_pick(ticket_id, rows)
        )
    await call.answer()


async def _send_canned(call: CallbackQuery, ticket_id: int, canned_id: int) -> None:
    ticket = await db.get_ticket(ticket_id)
    template = await db.canned_get(canned_id)
    if ticket is None or template is None:
        await call.answer("Шаблон не найден.", show_alert=True)
        return
    if ticket["status"] == "closed":
        await call.answer(texts.TICKET_CLOSED_REPLY, show_alert=True)
        return

    await db.add_message(
        ticket_id, call.from_user.id, template["body"], from_admin=True
    )
    await db.canned_used(canned_id)
    delivered = await _deliver(
        call.bot, ticket["user_id"], texts.admin_reply(ticket_id, template["body"])
    )
    await call.answer(texts.REPLY_SENT if delivered else texts.REPLY_BLOCKED, show_alert=not delivered)
    with suppress(TelegramAPIError):
        await call.message.delete()  # the picker did its job
    await cards.refresh(call.bot, ticket_id)


async def _block(call: CallbackQuery, ticket, block: bool) -> None:
    if block:
        await db.block(ticket["user_id"])
    else:
        await db.unblock(ticket["user_id"])
    await call.answer("Заблокирован" if block else "Разблокирован")
    await cards.refresh(call.bot, ticket["id"])


async def _resend(call: CallbackQuery, ticket_id: int) -> None:
    """Re-post a card, for tickets reached from the queue screen."""
    ticket = await db.get_ticket(ticket_id)
    messages = await db.thread(ticket_id, limit=1)
    body = messages[0]["text"] if messages else ""
    label = None
    if messages and messages[0]["file_type"]:
        label = texts.ATTACHMENT_LABEL.get(
            messages[0]["file_type"], messages[0]["file_type"]
        )
    blocked = await db.is_blocked(ticket["user_id"])
    with suppress(TelegramAPIError):
        card = await call.message.answer(
            await cards.card_text(ticket, body, label),
            reply_markup=kb.card(
                ticket_id, ticket["status"], bool(ticket["taken_by"]), blocked
            ),
        )
        # The newest card becomes the reply anchor, or answers would go nowhere.
        await db.set_admin_msg(ticket_id, card.message_id)
    await call.answer()
