import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User

import db
import keyboards as kb
import lang
import outbox
import people
import texts
import tiers
import ui
import settings
router = Router()

logger = logging.getLogger(__name__)


class Upload(StatesGroup):
    waiting_video = State()


async def _may_upload(message: Message, user_id: int | None = None) -> bool:
    """Circles hang off a profile, so there has to be one to hang them on."""
    profile = await db.get_profile(user_id or message.from_user.id)
    if profile is not None and profile["status"] == "approved":
        return True
    if profile is None:
        await message.answer(texts.t("UPLOAD_NEEDS_PROFILE"), reply_markup=kb.profile_intro())
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
    # Premium is sold on a longer queue, so the ceiling is the tier's, not one
    # number for everybody.
    limit = tiers.max_pending(db.active_tier(await db.get_user(message.from_user.id)))
    if await db.pending_count(message.from_user.id) >= limit:
        await message.answer(texts.t("TOO_MANY_PENDING"), reply_markup=kb.back())
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
    await message.answer(texts.t("NOT_A_CIRCLE"), reply_markup=kb.back())


async def _submit(bot, author: User, data: dict, gender: str) -> str:
    """Store the circle and drop it into the moderation chat.

    The chat takes twenty messages a minute and every upload costs two of them,
    so the card is queued rather than sent: the author is told «принято» right
    away, and the moderation chat is fed at a pace it can take.
    """
    circle_id = await db.add_circle(
        file_id=data["file_id"],
        file_unique_id=data["file_unique_id"],
        uploader_id=author.id,
        gender=gender,
        duration=data["duration"],
    )
    if circle_id is None:
        return texts.t("DUPLICATE")

    reward = settings.reward(gender)
    chat = settings.circles_chat()
    # The card is read by moderators, not by the person who sent it:
    # composed in Russian whatever language they are answered in.
    with lang.use("ru"):
        card_text = (
            f"#на_проверку <b>#{circle_id}</b>\n"
            f"Тип: {kb.PREF_TITLE(gender)} (+{reward} {texts.coin()})\n"
            f"Длина: {data['duration']} сек\n"
            f"Автор: {await people.of(author.id)}"
        )

        async def deliver() -> None:
            # The circle is saved and waits in the panel's queue either way; silence
            # here is exactly what made a broken chat look like a broken upload.
            await outbox.call(
                chat,
                lambda: bot.send_video_note(chat, data["file_id"], protect_content=True),
                f"кружок #{circle_id}",
            )
            card = await outbox.call(
                chat,
                lambda: bot.send_message(
                    chat, card_text, reply_markup=kb.moderation(circle_id)
                ),
                f"карточка кружка #{circle_id}",
            )
            if card is not None:
                await db.set_admin_msg(circle_id, card.message_id)

        outbox.post(chat, deliver, f"кружок #{circle_id}")
    return texts.upload_sent(circle_id, reward)
