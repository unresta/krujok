from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User

import db
import keyboards as kb
import texts
import ui
import settings
from config import ADMIN_CHAT_ID

router = Router()


class Upload(StatesGroup):
    waiting_video = State()  # type already picked
    waiting_gender = State()  # circle already in hand


@router.message(F.text == kb.BTN_UPLOAD)
async def upload_button(message: Message, state: FSMContext) -> None:
    await state.set_state(Upload.waiting_gender)
    await message.answer(texts.UPLOAD_PICK_GENDER, reply_markup=kb.upload_gender())


@router.callback_query(F.data == "upload")
async def ask_gender(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Upload.waiting_gender)
    await ui.edit(call, texts.UPLOAD_PICK_GENDER, kb.upload_gender())
    await call.answer()


@router.callback_query(F.data.startswith("ug:"))
async def pick_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":", 1)[1]
    data = await state.get_data()

    if "file_id" not in data:  # picked the type first, circle comes next
        await state.set_state(Upload.waiting_video)
        await state.update_data(gender=gender)
        await ui.edit(call, texts.upload_ask(gender), kb.back())
        await call.answer()
        return

    await state.clear()
    text = await _submit(call.bot, call.from_user, data, gender)
    await ui.edit(call, text, kb.back())
    await call.answer()


@router.message(F.video_note)
async def got_video(message: Message, state: FSMContext) -> None:
    """A circle is accepted at any point — the type is asked for if unknown."""
    note = message.video_note

    if await db.pending_count(message.from_user.id) >= settings.get("max_pending"):
        await message.answer(texts.TOO_MANY_PENDING, reply_markup=kb.back())
        return
    if note.duration < settings.get("min_duration"):
        await message.answer(texts.too_short(note.duration), reply_markup=kb.back())
        return

    data = {
        "file_id": note.file_id,
        "file_unique_id": note.file_unique_id,
        "duration": note.duration,
    }
    gender = (await state.get_data()).get("gender")

    if gender is None:  # circle arrived out of the blue
        await state.set_state(Upload.waiting_gender)
        await state.update_data(**data)
        await message.answer(texts.UPLOAD_ASK_GENDER, reply_markup=kb.upload_gender())
        return

    await state.clear()
    text = await _submit(message.bot, message.from_user, data, gender)
    await message.answer(text, reply_markup=kb.back())


@router.message(Upload.waiting_video, ~F.text.in_(kb.MENU_BUTTONS))
async def wrong_content(message: Message) -> None:
    await message.answer(texts.NOT_A_CIRCLE, reply_markup=kb.back())


async def _submit(bot, author: User, data: dict, gender: str) -> str:
    """Store the circle and drop it into the moderation chat."""
    circle_id = await db.add_circle(
        file_id=data["file_id"],
        file_unique_id=data["file_unique_id"],
        uploader_id=author.id,
        gender=gender,
        duration=data["duration"],
    )
    if circle_id is None:
        return texts.DUPLICATE

    reward = settings.reward(gender)
    await bot.send_video_note(ADMIN_CHAT_ID, data["file_id"])
    who = author.username and f"@{author.username}" or "—"
    admin_msg = await bot.send_message(
        ADMIN_CHAT_ID,
        f"#на_проверку <b>#{circle_id}</b>\n"
        f"Тип: {kb.PREF_TITLE(gender)} (+{reward} {texts.coin()})\n"
        f"Длина: {data['duration']} сек\n"
        f"Автор: <code>{author.id}</code> {who}",
        reply_markup=kb.moderation(circle_id),
    )
    await db.set_admin_msg(circle_id, admin_msg.message_id)
    return texts.upload_sent(circle_id, reward)
