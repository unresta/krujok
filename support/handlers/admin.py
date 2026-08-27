"""Admin panel: /admin in private, one editable message with everything in it.

Answering tickets does not happen here — that is a reply in the support chat.
This is for the work around it: what is queued, how fast we answer, which topics
generate the load, canned replies, and pointing the bot at the right chat.
"""

import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

import cards
import db
import keyboards as kb
import mainbase
import settings
import texts
from config import ADMIN_IDS, LIST_LIMIT

logger = logging.getLogger(__name__)

router = Router()
# The panel is admins-only and private-only; nothing here works from a group.
router.message.filter(F.from_user.id.in_(ADMIN_IDS), F.chat.type == ChatType.PRIVATE)
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class Panel(StatesGroup):
    canned = State()
    user_id = State()
    chat = State()


async def _chat_status(bot: Bot, chat: int | str) -> str:
    if not chat:
        return "🔴 Чат не задан: карточки идут в личку админам."
    try:
        member = await bot.get_chat_member(chat, (await bot.me()).id)
    except TelegramAPIError as error:
        return f"🔴 Бот не может писать туда: {error}"
    if member.status not in {"administrator", "creator", "member"}:
        return "🔴 Бот не состоит в чате."
    return "🟢 Бот на месте, карточки дойдут."


async def panel_text(bot: Bot) -> str:
    return texts.panel(
        await db.stats(),
        str(settings.support_chat() or "—"),
        await _chat_status(bot, settings.support_chat()),
        mainbase.available(),
    )


async def _edit(call: CallbackQuery, text: str, markup) -> None:
    with suppress(TelegramBadRequest):
        await call.message.edit_text(text, reply_markup=markup)


@router.message(Command("admin"))
async def open_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    stats = await db.stats()
    await message.answer(
        await panel_text(message.bot), reply_markup=kb.panel(stats["waiting"])
    )


@router.callback_query(F.data == "p:home")
async def home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    stats = await db.stats()
    await _edit(call, await panel_text(call.bot), kb.panel(stats["waiting"]))
    await call.answer()


@router.callback_query(F.data == "p:close")
async def close_panel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with suppress(TelegramAPIError):
        await call.message.delete()
    await call.answer()


# --- queue and reports ---------------------------------------------------


@router.callback_query(F.data == "p:queue")
async def queue(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.open_tickets(LIST_LIMIT)
    await _edit(call, texts.queue(rows), kb.queue(rows))
    await call.answer()


@router.callback_query(F.data == "p:topics")
async def by_topic(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.by_topic()
    total = sum(r["n"] for r in rows)
    await _edit(call, texts.topics_report(rows, total), kb.panel_back())
    await call.answer()


# --- canned replies ------------------------------------------------------


@router.callback_query(F.data == "p:canned")
async def canned(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.canned_list()
    await _edit(call, texts.canned_screen(rows), kb.canned_manage(rows))
    await call.answer()


@router.callback_query(F.data == "p:canned:new")
async def canned_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.canned)
    await _edit(call, texts.CANNED_ASK, kb.panel_back())
    await call.answer()


@router.message(Panel.canned)
async def got_canned(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if "|" not in raw:
        await message.answer(texts.CANNED_BAD, reply_markup=kb.panel_back())
        return
    title, body = (part.strip() for part in raw.split("|", 1))
    if not title or not body:
        await message.answer(texts.CANNED_BAD, reply_markup=kb.panel_back())
        return

    await state.clear()
    await db.canned_add(title, body)
    rows = await db.canned_list()
    await message.answer(texts.canned_screen(rows), reply_markup=kb.canned_manage(rows))


@router.callback_query(F.data.startswith("p:canned:del:"))
async def canned_delete(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await db.canned_delete(int(call.data.split(":")[3]))
    rows = await db.canned_list()
    await _edit(call, texts.canned_screen(rows), kb.canned_manage(rows))
    await call.answer("Удалён")


# --- one user's history --------------------------------------------------


@router.callback_query(F.data == "p:user")
async def ask_user(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.user_id)
    await _edit(call, texts.ASK_USER_ID, kb.panel_back())
    await call.answer()


@router.message(Panel.user_id)
async def got_user(message: Message, state: FSMContext) -> None:
    """Accepts an id, or a payment charge id pasted from a Telegram receipt.

    A disputed payment is the case where the receipt is all the user has, so
    looking it up by charge id has to work as well as by user id.
    """
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(texts.BAD_USER_ID, reply_markup=kb.panel_back())
        return

    if not raw.isdigit():
        payment = await mainbase.find_payment(raw)
        if payment is None:
            await message.answer(texts.BAD_USER_ID, reply_markup=kb.panel_back())
            return
        await state.clear()
        await message.answer(
            texts.payment_found(payment), reply_markup=kb.panel_back()
        )
        return

    await state.clear()

    user_id = int(raw)
    rows = await db.user_tickets(user_id, LIST_LIMIT)
    extra = await mainbase.profile(user_id)
    unblock = None
    if await db.is_blocked(user_id):
        unblock = [
            InlineKeyboardButton(
                text="Разблокировать в поддержке",
                callback_data=f"p:unblock:{user_id}",
                style=kb.SUCCESS,
            )
        ]
    await message.answer(
        texts.user_tickets_admin(user_id, rows, extra),
        reply_markup=kb.panel_back(unblock),
    )


@router.callback_query(F.data.startswith("p:unblock:"))
async def unblock(call: CallbackQuery) -> None:
    user_id = int(call.data.split(":")[2])
    await db.unblock(user_id)
    await call.answer("Разблокирован")
    with suppress(TelegramBadRequest):
        await call.message.edit_reply_markup(reply_markup=kb.panel_back())


# --- where the cards go --------------------------------------------------


@router.callback_query(F.data == "p:chat")
async def ask_chat(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Panel.chat)
    await _edit(call, texts.ASK_CHAT, kb.panel_back())
    await call.answer()


@router.message(Panel.chat)
async def got_chat(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    elif not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer(texts.BAD_CHAT, reply_markup=kb.panel_back())
        return

    await state.clear()
    await settings.set_text("chat", raw)
    chat = settings.support_chat()
    await message.answer(
        f"Чат поддержки: <code>{chat or '—'}</code>\n"
        f"{await _chat_status(message.bot, chat)}",
        reply_markup=kb.panel_back(),
    )
