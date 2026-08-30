import html
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
import settings
from config import ADMIN_CHAT_ID, ADMIN_IDS

router = Router()

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

    reason = texts.CIRCLE_REJECT_REASONS.get(parts[2], "") if verdict == "r" else ""
    status = "approved" if verdict == "ok" else "rejected"

    mark = await _decide(call.bot, circle, status, call.from_user.id, reason)
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
            reply_markup=kb.circle_decided(circle_id),
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


async def _decide(bot, circle, status: str, admin_id: int, reason: str) -> str | None:
    """Apply the verdict and tell the author. None when nothing moved.

    The reason travels with the verdict: the author reads it in the message and
    finds it again later under the circle in «Мои кружки».
    """
    changed, pay = await db.decide_circle(circle["id"], status, admin_id, reason)
    if not changed:
        return None

    uploader = circle["uploader_id"]
    if status == "approved":
        reward = settings.reward(circle["gender"]) if pay else 0
        if reward:
            await db.add_coins(uploader, reward, earned=True)
        balance = (await db.get_user(uploader))["coins"]
        # Approved a second time the circle simply comes back; the reward for it
        # was already paid, and saying «+0» would read as a mistake.
        note = texts.approved(reward, balance) if pay else texts.CIRCLE_RESTORED
        mark = "🟢 одобрено"
    else:
        note = texts.rejected(reason)
        mark = "🔴 отклонено"

    if uploader:
        with suppress(TelegramAPIError):  # user may have blocked the bot
            await bot.send_message(uploader, note)
    return mark


def _verdict_line(mark: str, reason: str, moderator) -> str:
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
