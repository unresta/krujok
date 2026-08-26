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
    waiting_video = State()


@router.message(F.text == kb.BTN_UPLOAD)
async def upload_button(message: Message, state: FSMContext) -> None:
    if not await _may_upload(message):
        return
    profile = await db.get_profile(message.from_user.id)
    await state.set_state(Upload.waiting_video)
    await state.update_data(gender=profile["gender"])
    await message.answer(texts.upload_ask(profile["gender"]), reply_markup=kb.back())


async def _may_upload(message: Message, user_id: int | None = None) -> bool:
    """Circles hang off a profile, so there has to be one to hang them on."""
    profile = await db.get_profile(user_id or message.from_user.id)
    if profile is not None and profile["status"] == "approved":
        return True
    if profile is None:
        await message.answer(texts.UPLOAD_NEEDS_PROFILE, reply_markup=kb.my_profile(False))
    else:
        await message.answer(texts.upload_profile_pending(profile["status"]))
    return False


@router.callback_query(F.data == "upload")
async def ask_video(call: CallbackQuery, state: FSMContext) -> None:
    if not await _may_upload(call.message, call.from_user.id):
        await call.answer()
        return
    profile = await db.get_profile(call.from_user.id)
    await state.set_state(Upload.waiting_video)
    await state.update_data(gender=profile["gender"])
    await ui.edit(call, texts.upload_ask(profile["gender"]), kb.back())
    await call.answer()


@router.message(F.video_note)
async def got_video(message: Message, state: FSMContext) -> None:
    """A circle is accepted at any point; its type comes from the profile."""
    note = message.video_note

    if not await _may_upload(message):
        return
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
    # The type comes from the profile: an author does not change sex per circle.
    gender = (await state.get_data()).get("gender")
    if gender is None:
        profile = await db.get_profile(message.from_user.id)
        gender = profile["gender"]

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
