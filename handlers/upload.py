from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import texts
import ui
from config import ADMIN_CHAT_ID, MAX_PENDING, MIN_DURATION, REWARD

router = Router()


class Upload(StatesGroup):
    waiting_video = State()
    waiting_gender = State()


@router.callback_query(F.data == "upload")
async def ask_video(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Upload.waiting_video)
    await ui.edit(call, texts.UPLOAD_ASK, kb.back())
    await call.answer()


@router.message(F.video_note)
async def got_video(message: Message, state: FSMContext) -> None:
    """A circle is accepted at any point — no need to press anything first."""
    note = message.video_note

    if await db.pending_count(message.from_user.id) >= MAX_PENDING:
        await message.answer(texts.TOO_MANY_PENDING, reply_markup=kb.back())
        return
    if note.duration < MIN_DURATION:
        await message.answer(texts.too_short(note.duration), reply_markup=kb.back())
        return

    await state.set_state(Upload.waiting_gender)
    await state.update_data(
        file_id=note.file_id,
        file_unique_id=note.file_unique_id,
        duration=note.duration,
    )
    await message.answer(texts.UPLOAD_ASK_GENDER, reply_markup=kb.upload_gender())


@router.message(Upload.waiting_video)
async def wrong_content(message: Message) -> None:
    await message.answer(texts.NOT_A_CIRCLE, reply_markup=kb.back())


@router.callback_query(Upload.waiting_gender, F.data.startswith("ug:"))
async def pick_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()

    circle_id = await db.add_circle(
        file_id=data["file_id"],
        file_unique_id=data["file_unique_id"],
        uploader_id=call.from_user.id,
        gender=gender,
        duration=data["duration"],
    )
    if circle_id is None:
        await ui.edit(call, texts.DUPLICATE, kb.back())
        await call.answer()
        return

    await call.bot.send_video_note(ADMIN_CHAT_ID, data["file_id"])
    who = call.from_user.username and f"@{call.from_user.username}" or "—"
    admin_msg = await call.bot.send_message(
        ADMIN_CHAT_ID,
        f"#на_проверку <b>#{circle_id}</b>\n"
        f"Тип: {kb.PREF_TITLE(gender)} (+{REWARD[gender]} {texts.COIN})\n"
        f"Длина: {data['duration']} сек\n"
        f"Автор: <code>{call.from_user.id}</code> {who}",
        reply_markup=kb.moderation(circle_id),
    )
    await db.set_admin_msg(circle_id, admin_msg.message_id)

    await ui.edit(call, texts.UPLOAD_SENT, kb.back())
    await call.answer("Отправлено 🟢")
