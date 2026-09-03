import asyncio
import html
import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import lang
import texts
import settings
from config import ADMIN_CHAT_ID, ADMIN_IDS

router = Router()


async def _in_russian(handler, event, data):
    """The panel and the moderation chats are read by us, not by the users.

    A moderator with an English client would otherwise get half a card in
    English — the half the user's own language decided.
    """
    lang.set("ru")
    return await handler(event, data)


router.message.middleware(_in_russian)
router.callback_query.middleware(_in_russian)

logger = logging.getLogger(__name__)

REASON_MIN, REASON_MAX = 3, 200


class Reject(StatesGroup):
    reason = State()  # a reason typed by hand, when none of the buttons fits


def _is_moderator(call: CallbackQuery) -> bool:
    return (
        call.from_user.id in ADMIN_IDS
        or call.message.chat.id == ADMIN_CHAT_ID
        or str(call.message.chat.id) == str(settings.circles_chat())
    )


@router.callback_query(F.data.startswith("mod:"))
async def review(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_moderator(call):
        await call.answer("Нет прав.", show_alert=True)
        return

    parts = call.data.split(":")
    verdict = parts[1]
    circle_id = int(parts[-1])
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок не найден.", show_alert=True)
        return

    if verdict == "again":  # a verdict can always be revisited
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=kb.moderation(circle_id))
        await call.answer("Решай заново")
        return

    if verdict == "no":  # ask why before turning anyone away
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.circle_reasons(circle_id)
            )
        await call.answer("За что отклоняем?")
        return

    if verdict == "back":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=kb.moderation(circle_id))
        await call.answer()
        return

    if verdict == "rc":  # a reason typed by hand
        await state.set_state(Reject.reason)
        await state.update_data(
            circle_id=circle_id,
            chat=call.message.chat.id,
            card=call.message.message_id,
            body=_card_body(call.message.html_text),
        )
        await call.message.answer(
            f"Причина отклонения кружка #{circle_id}? "
            f"Пришли одним сообщением ({REASON_MIN}–{REASON_MAX} символов) — "
            "автор её увидит."
        )
        await call.answer()
        return

    # The key travels, not the label: the author may read English, and the same
    # key is what «Мои кружки» shows them later.
    key = parts[2] if verdict == "r" else ""
    reason = key if key in texts.CIRCLE_REJECT_REASONS else ""
    status = "approved" if verdict == "ok" else "rejected"
    purge = key in texts.CIRCLE_REJECT_DELETES

    mark = await _decide(call.bot, circle, status, call.from_user.id, reason, purge)
    if mark is None:
        await call.answer("Уже с таким решением.", show_alert=True)
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.circle_decided(circle_id)
            )
        return

    with suppress(TelegramAPIError):
        await call.message.edit_text(
            f"{_card_body(call.message.html_text)}\n\n"
            f"{_verdict_line(mark, reason, call.from_user)}",
            # A deleted circle has nothing left to change one's mind about.
            reply_markup=None if purge else kb.circle_decided(circle_id),
        )
    await call.answer(mark)


@router.message(Reject.reason, ~F.text.in_(kb.MENU_BUTTONS))
async def got_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if not REASON_MIN <= len(reason) <= REASON_MAX:
        await message.answer(f"Причина: от {REASON_MIN} до {REASON_MAX} символов.")
        return

    data = await state.get_data()
    await state.clear()
    circle_id = data["circle_id"]

    circle = await db.get_circle(circle_id)
    if circle is None:
        await message.answer("Кружок не найден.")
        return

    mark = await _decide(
        message.bot, circle, "rejected", message.from_user.id, reason
    )
    if mark is None:
        await message.answer("Уже с таким решением.")
        return

    with suppress(TelegramAPIError):  # the card keeps a way back to the buttons
        await message.bot.edit_message_text(
            chat_id=data["chat"],
            message_id=data["card"],
            text=f"{data['body']}\n\n"
            f"{_verdict_line(mark, reason, message.from_user)}",
            reply_markup=kb.circle_decided(circle_id),
        )
    await message.answer(f"{mark} · {reason}")


async def _decide(
    bot, circle, status: str, admin_id: int, reason: str, purge: bool = False
) -> str | None:
    """Apply the verdict and tell the author. None when nothing moved.

    The reason travels with the verdict: the author reads it in the message and
    finds it again later under the circle in «Мои кружки» — unless the verdict
    was one that removes the circle, and there is no «Мои кружки» left for it.
    """
    if purge:
        # Rejection only hides a circle; this takes it out of the base, along
        # with its views, reactions and complaints.
        if not await db.delete_circle(circle["id"]):
            return None
        logger.warning(
            "кружок #%s удалён при проверке модератором %s: %s",
            circle["id"], admin_id, reason,
        )
        if circle["uploader_id"]:
            with lang.use(await db.lang_of(circle["uploader_id"])):
                note = texts.circle_deleted(reason)
            with suppress(TelegramAPIError):
                await bot.send_message(circle["uploader_id"], note)
        return "🔴 удалён"

    changed, pay = await db.decide_circle(circle["id"], status, admin_id, reason)
    if not changed:
        return None

    uploader = circle["uploader_id"]
    # Everything below is written by a moderator and read by the author: the
    # verdict line is ours, the note is theirs.
    author_lang = await db.lang_of(uploader) if uploader else "ru"
    if status == "approved":
        reward = settings.reward(circle["gender"]) if pay else 0
        if reward:
            await db.add_coins(uploader, reward, earned=True)
        balance = (await db.get_user(uploader))["coins"]
        # Approved a second time the circle simply comes back; the reward for it
        # was already paid, and saying «+0» would read as a mistake.
        with lang.use(author_lang):
            note = (
                texts.approved(reward, balance) if pay else texts.t("CIRCLE_RESTORED")
            )
        mark = "🟢 одобрено"
        # A circle only becomes sellable once it is approved, so this is the
        # moment the author's old buyers have something new to open.
        if uploader:
            asyncio.create_task(_tell_buyers(bot, uploader))
    else:
        with lang.use(author_lang):
            note = texts.rejected(reason)
        mark = "🔴 отклонено"

    if uploader:
        with suppress(TelegramAPIError):  # user may have blocked the bot
            await bot.send_message(uploader, note)
    return mark


async def _tell_buyers(bot, author_id: int) -> None:
    """Runs beside the verdict: a hundred buyers must not hold up the card."""
    from handlers import profiles

    try:
        await profiles.tell_buyers(bot, author_id)
    except Exception as error:  # noqa: BLE001 — a nudge is never worth a crash
        logger.warning("докупка: не позвали покупателей %s: %s", author_id, error)


def _verdict_line(mark: str, reason: str, moderator) -> str:
    reason = texts.circle_reject_reason(reason) if reason else reason
    """The line under the card. The toast gets the mark alone — it holds 200 chars."""
    who = moderator.username and f"@{moderator.username}" or moderator.id
    parts = [f"<b>{mark}</b>"]
    if reason:
        parts.append(html.escape(reason))
    parts.append(str(who))
    return " · ".join(parts)


def _card_body(html_text: str) -> str:
    """The card is re-decided in place, so old verdict lines must not stack up."""
    return html_text.split("\n\n<b>🟢")[0].split("\n\n<b>🔴")[0].rstrip()
