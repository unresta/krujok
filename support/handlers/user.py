"""The user's side: describe a problem, follow it, rate the answer.

Two ideas shape this file. First, a topic screen that answers the common cases
without a human — most of what arrives is already in the main bot's FAQ. Second,
one open ticket per person: anything the user sends while a ticket is open joins
that thread instead of starting a new one, so a conversation stays a conversation.
"""

import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import cards
import db
import keyboards as kb
import settings
import texts
from config import LIST_LIMIT, TEXT_MAX, THREAD_LIMIT

logger = logging.getLogger(__name__)

router = Router()
# Everything here is a private conversation; the support chat is another router.
router.message.filter(F.chat.type == ChatType.PRIVATE)

MIN_LENGTH = 10  # shorter than this says nothing a moderator can act on


class Ask(StatesGroup):
    text = State()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.START, reply_markup=kb.main_menu())


@router.message(Command("help"))
async def help_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHOOSE_TOPIC, reply_markup=kb.topics())


@router.message(F.text == kb.BTN_FAQ)
async def faq(message: Message, state: FSMContext) -> None:
    """The self-service list, reachable on its own and not only before a ticket."""
    await state.clear()
    await message.answer(texts.CHOOSE_TOPIC, reply_markup=kb.topics())


# --- new ticket ----------------------------------------------------------


@router.message(F.text == kb.BTN_NEW)
async def new_ticket(message: Message, state: FSMContext) -> None:
    await state.clear()
    open_ticket = await db.open_ticket_of(message.from_user.id)
    if open_ticket is not None:
        await message.answer(
            texts.already_open(open_ticket["id"]),
            reply_markup=kb.already_open(open_ticket["id"]),
        )
        return
    if await db.tickets_today(message.from_user.id) >= settings.get("tickets_per_day"):
        await message.answer(texts.too_many(), reply_markup=kb.close())
        return
    await message.answer(texts.CHOOSE_TOPIC, reply_markup=kb.topics())


@router.callback_query(F.data == "new")
async def new_again(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(call, texts.CHOOSE_TOPIC, kb.topics())
    await call.answer()


@router.callback_query(F.data.startswith("t:"))
async def picked_topic(call: CallbackQuery, state: FSMContext) -> None:
    """Topic chosen — show what usually solves it before asking for details."""
    topic = call.data.split(":", 1)[1]
    await state.clear()
    await _edit(call, texts.hint(topic), kb.hint(topic))
    await call.answer()


@router.callback_query(F.data == "solved")
async def solved(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Рады помочь 🙂")
    with suppress(TelegramAPIError):
        await call.message.delete()


@router.callback_query(F.data.startswith("w:"))
async def ask_text(call: CallbackQuery, state: FSMContext) -> None:
    topic = call.data.split(":", 1)[1]
    await state.set_state(Ask.text)
    await state.update_data(topic=topic)
    await _edit(call, texts.ask_text(topic), kb.cancel())
    await call.answer()


@router.message(Ask.text, ~F.text.in_(kb.MENU_BUTTONS))
async def got_text(message: Message, state: FSMContext) -> None:
    """The first message of a ticket: validated, stored, then posted as a card."""
    body = (message.text or message.caption or "").strip()
    file_id, file_type = cards.extract_attachment(message)

    # An attachment says plenty on its own, so it lowers the bar on the text.
    if not body and not file_id:
        await message.answer(texts.TEXT_TOO_SHORT, reply_markup=kb.cancel())
        return
    if len(body) > TEXT_MAX:
        await message.answer(texts.TEXT_TOO_LONG, reply_markup=kb.cancel())
        return
    if not file_id and len(body) < MIN_LENGTH:
        await message.answer(texts.TEXT_TOO_SHORT, reply_markup=kb.cancel())
        return

    topic = (await state.get_data()).get("topic", "other")
    await state.clear()

    # Re-checked here, not only on the button: the form may have sat open a while.
    if await db.tickets_today(message.from_user.id) >= settings.get("tickets_per_day"):
        await message.answer(texts.too_many(), reply_markup=kb.close())
        return
    existing = await db.open_ticket_of(message.from_user.id)
    if existing is not None:
        await _append(message, existing, body, file_id, file_type)
        return

    ticket_id = await db.create_ticket(
        message.from_user.id, message.from_user.username, topic
    )
    await db.add_message(
        ticket_id, message.from_user.id, body, file_id=file_id, file_type=file_type
    )
    await message.answer(texts.created(ticket_id), reply_markup=kb.main_menu())

    ticket = await db.get_ticket(ticket_id)
    await cards.send_card(message.bot, ticket, body, file_id, file_type)


async def _append(message: Message, ticket, body: str, file_id, file_type) -> None:
    """Add to the thread the user already has open."""
    await db.add_message(
        ticket["id"], message.from_user.id, body, file_id=file_id, file_type=file_type
    )
    await message.answer(texts.added(ticket["id"]))
    await cards.post_followup(message.bot, ticket, body, file_id, file_type)


# --- my tickets ----------------------------------------------------------


@router.message(F.text == kb.BTN_MY)
async def my_tickets(message: Message, state: FSMContext) -> None:
    await state.clear()
    rows = await db.user_tickets(message.from_user.id, LIST_LIMIT)
    await message.answer(texts.my_tickets(rows), reply_markup=kb.my_tickets(rows))


@router.callback_query(F.data == "my")
async def my_tickets_cb(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.user_tickets(call.from_user.id, LIST_LIMIT)
    await _edit(call, texts.my_tickets(rows), kb.my_tickets(rows))
    await call.answer()


@router.callback_query(F.data.startswith("my:"))
async def show_thread(call: CallbackQuery) -> None:
    ticket_id = int(call.data.split(":")[1])
    ticket = await db.get_ticket(ticket_id)
    # Ticket ids are sequential, so ownership has to be checked, not assumed.
    if ticket is None or ticket["user_id"] != call.from_user.id:
        await call.answer("Обращение не найдено.", show_alert=True)
        return
    messages = await db.thread(ticket_id, THREAD_LIMIT)
    await _edit(call, texts.thread_view(ticket, messages), kb.thread_back(ticket))
    await call.answer()


@router.callback_query(F.data.startswith("done:"))
async def self_close(call: CallbackQuery, state: FSMContext) -> None:
    """The user resolves their own ticket.

    Worth allowing: a question that answered itself otherwise sits in the queue
    until a moderator reads it, and the one-open-ticket limit keeps the user from
    asking anything else in the meantime. Closing is also the only action here
    that is safe to hand over — it frees the queue, and a new ticket is one tap
    away if the problem comes back.
    """
    await state.clear()
    ticket_id = int(call.data.split(":")[1])
    ticket = await db.get_ticket(ticket_id)
    if ticket is None or ticket["user_id"] != call.from_user.id:
        await call.answer("Обращение не найдено.", show_alert=True)
        return

    closed = await db.close_ticket(ticket_id, closed_by=call.from_user.id)
    if closed is None:  # a moderator closed it a moment earlier
        await call.answer(texts.SELF_CLOSE_ALREADY, show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)
        return

    await call.answer("Закрыто ⚪")
    with suppress(TelegramAPIError):
        await call.message.delete()
    # No rating prompt: nobody answered, so there is nothing to rate.
    await call.message.answer(texts.self_closed(ticket_id), reply_markup=kb.main_menu())
    await cards.refresh(call.bot, ticket_id)
    await cards.post_self_closed(call.bot, closed)


@router.callback_query(F.data.startswith("r:"))
async def rate(call: CallbackQuery) -> None:
    _, raw_id, raw_value = call.data.split(":")
    ticket = await db.get_ticket(int(raw_id))
    if ticket is None or ticket["user_id"] != call.from_user.id:
        await call.answer("Обращение не найдено.", show_alert=True)
        return

    value = 1 if raw_value == "1" else -1
    if not await db.rate_ticket(int(raw_id), value):
        await call.answer(texts.RATED_ALREADY, show_alert=True)
        return

    await call.answer(texts.THANKS_GOOD if value == 1 else texts.THANKS_BAD, show_alert=True)
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data == "close")
async def close_screen(call: CallbackQuery, state: FSMContext) -> None:
    """The menu is a reply keyboard, so a screen just goes away."""
    await state.clear()
    await call.answer()
    try:
        await call.message.delete()
    except TelegramAPIError:  # older than 48h, or already gone
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)


# --- anything else -------------------------------------------------------


@router.message()
async def anything_else(message: Message, state: FSMContext) -> None:
    """No dead ends.

    With a ticket open this is the natural way to keep talking, so the message
    joins that thread. Without one, the panel comes back — same rule as the main
    bot's fallback.
    """
    await state.clear()
    open_ticket = await db.open_ticket_of(message.from_user.id)
    if open_ticket is None:
        await message.answer(texts.START, reply_markup=kb.main_menu())
        return

    body = (message.text or message.caption or "").strip()
    file_id, file_type = cards.extract_attachment(message)
    if not body and not file_id:  # a sticker-only reply carries nothing to relay
        await message.answer(texts.START, reply_markup=kb.main_menu())
        return
    if len(body) > TEXT_MAX:
        await message.answer(texts.TEXT_TOO_LONG)
        return

    await _append(message, open_ticket, body, file_id, file_type)


async def _edit(call: CallbackQuery, text: str, markup=None) -> None:
    with suppress(TelegramAPIError):
        await call.message.edit_text(text, reply_markup=markup)
