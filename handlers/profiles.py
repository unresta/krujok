"""Author profiles: the shop window and everything sold through it.

A profile is filled in once, moderated like a circle, and then shown to other
users. Two things are for sale — access to the author's circles as they stand at
the moment of purchase, and, if the author opted in, their @username.
"""

import asyncio
import html
import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import settings
import texts
from config import ABOUT_MAX, ADMIN_CHAT_ID, ADMIN_IDS
from keyboards import PRIMARY, DANGER
from handlers.upload import Upload

logger = logging.getLogger(__name__)

router = Router()

CIRCLES_PER_BATCH = 10  # sent per tap, so a big catalogue does not hit the limit
SEND_PAUSE = 0.3


class Review(StatesGroup):
    reason = State()


class Anketa(StatesGroup):
    photo = State()
    about = State()
    gender = State()
    price_content = State()
    contact = State()
    price_contact = State()


# --- filling it in -------------------------------------------------------


@router.message(F.text == kb.BTN_MY_ANKETA)
async def my_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    profile = await db.get_profile(message.from_user.id)
    if profile is None:  # no profile yet — pitch it instead of stating the fact
        await message.answer(texts.PROFILE_INTRO, reply_markup=kb.profile_intro())
        return
    await message.answer_photo(
        profile["photo_id"],
        caption=texts.profile_status(profile),
        reply_markup=kb.my_profile(True),
    )


@router.callback_query(F.data == "pf:edit_menu")
async def edit_menu(call: CallbackQuery, state: FSMContext) -> None:
    """Show menu to edit individual fields or create new profile."""
    await state.clear()
    profile = await db.get_profile(call.from_user.id)
    if profile is None:
        await call.message.answer(texts.PROFILE_INTRO, reply_markup=kb.profile_intro())
    else:
        await call.message.answer_photo(
            profile["photo_id"],
            caption=texts.profile_status(profile),
            reply_markup=kb.profile_edit_menu(profile),
        )
    await call.answer()


@router.callback_query(F.data == "pf:hide")
async def hide_profile(call: CallbackQuery) -> None:
    """User hides their own profile."""
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer("Нечего скрывать.", show_alert=True)
        return
    await db.set_profile_status(call.from_user.id, "rejected")
    await call.answer("Анкета скрыта.")
    profile = await db.get_profile(call.from_user.id)
    await call.message.edit_caption(
        caption=texts.profile_status(profile),
        reply_markup=kb.profile_edit_menu(profile),
    )


@router.callback_query(F.data.startswith("pf:edit:"))
async def edit_field(call: CallbackQuery, state: FSMContext) -> None:
    """Start editing one field."""
    field = call.data.split(":")[2]
    profile = await db.get_profile(call.from_user.id)
    if profile is None:
        await call.answer("Сначала заполни анкету.", show_alert=True)
        return

    await state.update_data(editing_field=field)

    if field == "photo":
        await state.set_state(Anketa.photo)
        await call.message.answer(texts.PROFILE_PHOTO, reply_markup=kb.back())
    elif field == "about":
        await state.set_state(Anketa.about)
        await call.message.answer(texts.profile_about(), reply_markup=kb.back())
    elif field == "gender":
        await state.set_state(Anketa.gender)
        await call.message.answer(texts.PROFILE_GENDER, reply_markup=kb.profile_gender())
    elif field == "price_content":
        await state.set_state(Anketa.price_content)
        await call.message.answer(texts.profile_price_content(), reply_markup=kb.back())
    elif field == "price_contact":
        await state.set_state(Anketa.price_contact)
        has_username = bool(call.from_user.username)
        await call.message.answer(
            texts.PROFILE_CONTACT_ASK if has_username else texts.PROFILE_NO_USERNAME,
            reply_markup=kb.profile_contact_ask(has_username),
        )
    await call.answer()


@router.callback_query(F.data == "pf:edit")
async def edit_profile(call: CallbackQuery, state: FSMContext) -> None:
    """Legacy callback — redirect to edit menu."""
    await edit_menu(call, state)


@router.callback_query(F.data == "pf:start")
async def start_profile(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Anketa.photo)
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(texts.PROFILE_PHOTO, reply_markup=kb.back())
    await call.answer()


@router.message(Anketa.photo, F.photo)
async def got_photo(message: Message, state: FSMContext) -> None:
    photo = message.photo[-1]
    data = await state.get_data()

    if data.get("editing_field") == "photo":
        # Single-field edit: update only photo
        profile = await db.get_profile(message.from_user.id)
        if profile:
            await db.save_profile(
                user_id=message.from_user.id,
                photo_id=photo.file_id,
                photo_unique_id=photo.file_unique_id,
                about=profile["about"],
                gender=profile["gender"],
                price_content=profile["price_content"],
                price_contact=profile["price_contact"],
                contact_ok=profile["contact_ok"],
                username=message.from_user.username,
            )
            await state.clear()
            await message.answer("✅ Фото обновлено.", reply_markup=kb.back())
            profile = await db.get_profile(message.from_user.id)
            await message.answer_photo(
                profile["photo_id"],
                caption=texts.profile_status(profile),
                reply_markup=kb.profile_edit_menu(profile),
            )
            return

    await state.update_data(
        photo_id=photo.file_id, photo_unique_id=photo.file_unique_id
    )
    await state.set_state(Anketa.about)
    await message.answer(texts.profile_about(), reply_markup=kb.back())


@router.message(Anketa.photo, ~F.text.in_(kb.MENU_BUTTONS))
async def not_a_photo(message: Message) -> None:
    await message.answer(texts.PROFILE_NOT_PHOTO, reply_markup=kb.back())


@router.message(Anketa.about, ~F.text.in_(kb.MENU_BUTTONS))
async def got_about(message: Message, state: FSMContext) -> None:
    about = (message.text or "").strip()
    if about == "-":
        about = ""
    if len(about) > ABOUT_MAX:
        await message.answer(texts.profile_about(), reply_markup=kb.back())
        return

    data = await state.get_data()
    if data.get("editing_field") == "about":
        profile = await db.get_profile(message.from_user.id)
        if profile:
            await db.save_profile(
                user_id=message.from_user.id,
                photo_id=profile["photo_id"],
                photo_unique_id=profile["photo_unique_id"],
                about=about,
                gender=profile["gender"],
                price_content=profile["price_content"],
                price_contact=profile["price_contact"],
                contact_ok=profile["contact_ok"],
                username=message.from_user.username,
            )
            await state.clear()
            await message.answer("✅ Описание обновлено.", reply_markup=kb.back())
            profile = await db.get_profile(message.from_user.id)
            await message.answer_photo(
                profile["photo_id"],
                caption=texts.profile_status(profile),
                reply_markup=kb.profile_edit_menu(profile),
            )
            return

    await state.update_data(about=about)
    await state.set_state(Anketa.gender)
    await message.answer(texts.PROFILE_GENDER, reply_markup=kb.profile_gender())


@router.callback_query(Anketa.gender, F.data.startswith("pg:"))
async def got_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":")[1]
    data = await state.get_data()

    if data.get("editing_field") == "gender":
        profile = await db.get_profile(call.from_user.id)
        if profile:
            await db.save_profile(
                user_id=call.from_user.id,
                photo_id=profile["photo_id"],
                photo_unique_id=profile["photo_unique_id"],
                about=profile["about"],
                gender=gender,
                price_content=profile["price_content"],
                price_contact=profile["price_contact"],
                contact_ok=profile["contact_ok"],
                username=call.from_user.username,
            )
            await state.clear()
            await call.answer("✅ Пол обновлён.")
            profile = await db.get_profile(call.from_user.id)
            await call.message.answer_photo(
                profile["photo_id"],
                caption=texts.profile_status(profile),
                reply_markup=kb.profile_edit_menu(profile),
            )
            return

    await state.update_data(gender=gender)
    await state.set_state(Anketa.price_content)
    await call.message.edit_text(texts.profile_price_content())
    await call.answer()


@router.message(Anketa.price_content, ~F.text.in_(kb.MENU_BUTTONS))
async def got_price_content(message: Message, state: FSMContext) -> None:
    price = _price(message.text)
    if price is None:
        await message.answer(texts.profile_bad_price(), reply_markup=kb.back())
        return

    data = await state.get_data()
    if data.get("editing_field") == "price_content":
        profile = await db.get_profile(message.from_user.id)
        if profile:
            await db.save_profile(
                user_id=message.from_user.id,
                photo_id=profile["photo_id"],
                photo_unique_id=profile["photo_unique_id"],
                about=profile["about"],
                gender=profile["gender"],
                price_content=price,
                price_contact=profile["price_contact"],
                contact_ok=profile["contact_ok"],
                username=message.from_user.username,
            )
            await state.clear()
            await message.answer("✅ Цена кружков обновлена.", reply_markup=kb.back())
            profile = await db.get_profile(message.from_user.id)
            await message.answer_photo(
                profile["photo_id"],
                caption=texts.profile_status(profile),
                reply_markup=kb.profile_edit_menu(profile),
            )
            return

    await state.update_data(price_content=price)
    await state.set_state(Anketa.contact)

    has_username = bool(message.from_user.username)
    await message.answer(
        texts.PROFILE_CONTACT_ASK if has_username else texts.PROFILE_NO_USERNAME,
        reply_markup=kb.profile_contact_ask(has_username),
    )


@router.callback_query(Anketa.contact, F.data.startswith("pc:"))
async def got_contact_choice(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":")[1]

    if choice == "recheck":
        # Telegram sends a fresh from_user with every update, so a username set
        # a second ago is already visible here.
        if not call.from_user.username:
            await call.answer(texts.PROFILE_STILL_NO_USERNAME, show_alert=True)
            return
        await call.answer("Вижу 🟢")
        with suppress(TelegramAPIError):
            await call.message.edit_text(
                texts.PROFILE_CONTACT_ASK, reply_markup=kb.profile_contact_ask(True)
            )
        return

    wants = choice == "yes" and bool(call.from_user.username)
    if not wants:
        await state.update_data(contact_ok=False, price_contact=0)
        await call.answer()
        await _submit(call.message, call.from_user, state)
        return

    await state.update_data(contact_ok=True)
    await state.set_state(Anketa.price_contact)
    await call.message.edit_text(texts.profile_price_contact())
    await call.answer()


@router.message(Anketa.price_contact, ~F.text.in_(kb.MENU_BUTTONS))
async def got_price_contact(message: Message, state: FSMContext) -> None:
    price = _price(message.text)
    if price is None:
        await message.answer(texts.profile_bad_price(), reply_markup=kb.back())
        return

    data = await state.get_data()
    if data.get("editing_field") == "price_contact":
        profile = await db.get_profile(message.from_user.id)
        if profile:
            await db.save_profile(
                user_id=message.from_user.id,
                photo_id=profile["photo_id"],
                photo_unique_id=profile["photo_unique_id"],
                about=profile["about"],
                gender=profile["gender"],
                price_content=profile["price_content"],
                price_contact=price,
                contact_ok=True,
                username=message.from_user.username,
            )
            await state.clear()
            await message.answer("✅ Цена контакта обновлена.", reply_markup=kb.back())
            profile = await db.get_profile(message.from_user.id)
            await message.answer_photo(
                profile["photo_id"],
                caption=texts.profile_status(profile),
                reply_markup=kb.profile_edit_menu(profile),
            )
            return

    await state.update_data(price_contact=price)
    await _submit(message, message.from_user, state)


def _price(raw: str | None) -> int | None:
    raw = (raw or "").strip()
    if not raw.isdigit():
        return None
    price = int(raw)
    if not settings.get("price_min") <= price <= settings.get("price_max"):
        return None
    return price


async def _submit(message: Message, author, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()

    previous = await db.get_profile(author.id)  # read before overwriting it
    changes = texts.profile_changes(previous, data)

    await db.save_profile(
        user_id=author.id,
        photo_id=data["photo_id"],
        photo_unique_id=data.get("photo_unique_id"),
        about=data.get("about", ""),
        gender=data["gender"],
        price_content=data["price_content"],
        price_contact=data.get("price_contact", 0),
        contact_ok=data.get("contact_ok", False),
        username=author.username,
    )
    await message.answer(texts.PROFILE_SENT, reply_markup=kb.back())

    chat = settings.profiles_chat()
    try:
        card = await message.bot.send_photo(
            chat,
            data["photo_id"],
            caption=(
                ("#анкета_изменена" if previous else "#анкета")
                + f" от <code>{author.id}</code>"
                f"{' @' + author.username if author.username else ''}\n"
                + (
                    f"♻️ Поменялось: <b>{', '.join(changes)}</b>\n"
                    if changes
                    else "♻️ Прислана заново без правок\n"
                    if previous
                    else ""
                )
                + f"Кто: {kb.PERSON_TITLE(data['gender'])}\n"
                f"Кружочки: {data['price_content']} · "
                f"личка: {data.get('price_contact') or 'нет'}\n\n"
                f"{data.get('about') or 'Без описания'}"
            ),
            reply_markup=kb.profile_review(author.id),
        )
        await db.set_profile_admin_msg(author.id, card.message_id)
    except TelegramAPIError as error:
        # The profile is saved and shows up in the panel's queue regardless —
        # only the card is missing, and silence here is what hides that.
        logger.error(
            "profile card for %s not delivered to %s: %s", author.id, chat, error
        )


# --- moderation ----------------------------------------------------------


@router.callback_query(F.data.startswith("pm:"))
async def review(call: CallbackQuery, state: FSMContext) -> None:
    if not (
        call.from_user.id in ADMIN_IDS
        or call.message.chat.id == ADMIN_CHAT_ID
        or str(call.message.chat.id) == str(settings.profiles_chat())
        or str(call.message.chat.id) == str(settings.reports_chat())
    ):
        await call.answer("Нет прав.", show_alert=True)
        return

    parts = call.data.split(":")
    verdict = parts[1]
    user_id = int(parts[-1])

    if verdict == "no":  # ask why before turning anyone away
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.profile_reasons(user_id)
            )
        await call.answer("За что отклоняем?")
        return

    if verdict == "again":  # a verdict can always be revisited
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.profile_review(user_id)
            )
        await call.answer("Решай заново")
        return

    if verdict == "back":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.profile_review(user_id)
            )
        await call.answer()
        return

    if verdict == "rc":  # a reason typed by hand
        await state.set_state(Review.reason)
        await state.update_data(user_id=user_id, card=call.message.message_id)
        await call.message.answer(
            f"Причина отклонения для <code>{user_id}</code>? "
            "Пришли одним сообщением — автор её увидит."
        )
        await call.answer()
        return

    reason = texts.REJECT_REASONS[parts[2]] if verdict == "r" else ""
    status = "approved" if verdict == "ok" else "rejected"

    if verdict in ("hide", "keep"):  # verdict on a complaint, not on a new profile
        status = "rejected" if verdict == "hide" else "approved"
        await db.set_profile_status(user_id, status)
        await db.clear_profile_reports(user_id)
        if verdict == "hide":
            await db.drop_profile_backup(user_id)  # nothing here is worth restoring
            await _tell_author(call.bot, user_id, "rejected", "жалобы пользователей")
        mark = "🔴 скрыта" if verdict == "hide" else "🟢 оставлена"
        with suppress(TelegramAPIError):
            await call.message.edit_caption(
                caption=f"{call.message.html_text}\n\n<b>{mark}</b>", reply_markup=None
            )
        await call.answer(mark)
        return

    mark = await _decide(call.bot, user_id, status, reason)
    with suppress(TelegramAPIError):
        await call.message.edit_caption(
            caption=f"{call.message.html_text}\n\n<b>{mark}</b>",
            reply_markup=kb.profile_decided(user_id),
        )
    await call.answer(mark)


async def _decide(bot, user_id: int, status: str, reason: str) -> str:
    """Apply a verdict, whatever the profile's current state.

    Turning down an edit restores the version that was approved before it —
    a bad photo today should not cost the author a profile that was fine.
    """
    if status == "approved":
        await db.set_profile_status(user_id, "approved")
        await db.backup_profile(user_id)
        await _tell_author(bot, user_id, "approved")
        return "🟢 одобрена"

    profile = await db.get_profile(user_id)
    pending_edit = profile is not None and profile["status"] == "pending"

    # Only an edit waiting for review rolls back; turning down a live profile
    # means taking it down, not restoring the same thing.
    if pending_edit and await db.restore_profile(user_id):
        await _tell_author(bot, user_id, "reverted", reason)
        mark = "🔴 правки отклонены, вернули прошлую версию"
    else:
        await db.set_profile_status(user_id, "rejected")
        await db.drop_profile_backup(user_id)
        await _tell_author(bot, user_id, "rejected", reason)
        mark = "🔴 отклонена"
    return f"{mark} · {reason}" if reason else mark


async def _tell_author(bot, user_id: int, status: str, reason: str = "") -> None:
    if status == "approved":
        text, markup = texts.PROFILE_APPROVED, None
    elif status == "reverted":
        text, markup = texts.profile_reverted(reason), kb.refill_profile()
    else:
        text, markup = texts.profile_rejected(reason), kb.refill_profile()

    with suppress(TelegramAPIError):
        await bot.send_message(user_id, text, reply_markup=markup)


@router.message(Review.reason, ~F.text.in_(kb.MENU_BUTTONS))
async def got_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if not 3 <= len(reason) <= 200:
        await message.answer("Причина: от 3 до 200 символов.")
        return

    data = await state.get_data()
    await state.clear()
    user_id = data["user_id"]

    mark = await _decide(message.bot, user_id, "rejected", reason)
    with suppress(TelegramAPIError):
        await message.bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=data["card"],
            reply_markup=kb.profile_decided(user_id),
        )
    await message.answer(mark)


# --- browsing and buying -------------------------------------------------


@router.message(F.text == kb.BTN_ANKETAS)
async def browse(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_next(message.bot, message.from_user.id, message)


@router.callback_query(F.data == "pf:next")
async def next_profile(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)
    await _show_next(call.bot, call.from_user.id, call.message)


async def _show_next(bot, viewer_id: int, origin: Message) -> None:
    profile = await db.pick_profile(viewer_id)
    if profile is None:  # everything seen once — start a new lap
        await db.reset_profile_views(viewer_id)
        profile = await db.pick_profile(viewer_id)
    if profile is None:
        # Nothing to show is the best moment to ask for a profile of their own.
        mine = await db.get_profile(viewer_id)
        if mine is None:
            await origin.answer(
                texts.profile_empty_pitch(), reply_markup=kb.my_profile(False)
            )
        else:
            await origin.answer(texts.PROFILE_EMPTY_WAIT, reply_markup=kb.back())
        return

    author = profile["user_id"]
    bought_content = await db.get_purchase(viewer_id, author, "content") is not None
    bought_contact = await db.get_purchase(viewer_id, author, "contact") is not None
    await bot.send_photo(
        chat_id=viewer_id,
        photo=profile["photo_id"],
        caption=texts.profile_card(profile, profile["circles"]),
        reply_markup=kb.profile_card(profile, bought_content, bought_contact),
    )
    await db.mark_profile_seen(viewer_id, author)


@router.callback_query(F.data == "mp:upload")
async def mp_upload(call: CallbackQuery, state: FSMContext) -> None:
    """Redirect to upload flow."""
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        if profile is None:
            await call.message.answer(texts.UPLOAD_NEEDS_PROFILE, reply_markup=kb.my_profile(False))
        else:
            await call.message.answer(texts.upload_profile_pending(profile["status"]))
        await call.answer()
        return

    await state.set_state(Upload.waiting_video)
    await state.update_data(gender=profile["gender"])
    await call.message.answer(texts.upload_ask(profile["gender"]), reply_markup=kb.back())
    await call.answer()


@router.callback_query(F.data == "mp:circles")
async def mp_circles(call: CallbackQuery) -> None:
    """Show user's own uploaded circles."""
    await call.answer()
    stats = await db.user_stats(call.from_user.id)
    total = stats["approved"] + stats["pending"] + stats["rejected"]
    if not total:
        await call.message.answer("Ты ещё ничего не загрузил.")
        return
    text = (
        "📤 <b>Мои загруженные кружки:</b>\n\n"
        f"🟢 Одобрено: {stats['approved']}\n"
        f"🕒 На проверке: {stats['pending']}\n"
        f"🔴 Отклонено: {stats['rejected']}\n\n"
        f"Всего: {total}"
    )
    await call.message.answer(text, reply_markup=kb.back())


@router.callback_query(F.data == "mp:bought")
async def mp_bought(call: CallbackQuery) -> None:
    """Show purchased content."""
    await call.answer()
    purchases = await db.get_user_purchases(call.from_user.id, "content")
    if not purchases:
        await call.message.answer("Ты ещё ничего не купил.")
        return

    text_lines = ["🛒 <b>Купленные кружочки:</b>\n"]
    buttons = []

    for p in purchases:
        circles = await db.author_circles(p["author_id"], p["max_circle_id"])
        count = len(circles)
        text_lines.append(f"• Автор <code>{p['author_id']}</code> — {count} кружков")
        buttons.append(
            InlineKeyboardButton(
                text=f"👤 Автор {p['author_id']} ({count})",
                callback_data=f"pf:show:{p['author_id']}",
                style=PRIMARY,
            )
        )

    text = "\n".join(text_lines)

    b = InlineKeyboardBuilder()
    for btn in buttons:
        b.row(btn)
    b.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="menu", style=DANGER))

    await call.message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("pf:card:"))
async def open_card(call: CallbackQuery) -> None:
    """«Анкета автора» under a circle — the same card as in the feed."""
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None or profile["status"] != "approved":
        await call.answer("У автора нет анкеты.", show_alert=True)
        return
    if author_id == call.from_user.id:
        await call.answer("Это твоя анкета 🙂")
        return

    await call.answer()
    circles = len(await db.author_circles(author_id, await db.total_circles_max_id()))
    await call.bot.send_photo(
        chat_id=call.from_user.id,
        photo=profile["photo_id"],
        caption=texts.profile_card(profile, circles),
        reply_markup=kb.profile_card(
            profile,
            await db.get_purchase(call.from_user.id, author_id, "content") is not None,
            await db.get_purchase(call.from_user.id, author_id, "contact") is not None,
        ),
    )


@router.callback_query(F.data.startswith("pf:buy:"))
async def buy_content(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer("Анкета пропала.", show_alert=True)
        return

    # Selling access to an empty catalogue is just taking coins.
    if not await db.author_circles(author_id, await db.total_circles_max_id()):
        await call.answer(texts.NOTHING_TO_SELL, show_alert=True)
        return

    price = profile["price_content"]
    result, purchase = await db.buy_access(
        call.from_user.id, author_id, "content", price, settings.author_share(price)
    )
    if result == "poor":
        await call.answer("Не хватает монеток.", show_alert=True)
        return
    if result == "already":
        await call.answer(texts.ALREADY_BOUGHT)
    else:
        await _notify_author(call.bot, author_id, "content", purchase["author_share"])
        circles = await db.author_circles(author_id, purchase["max_circle_id"])
        await call.answer("Куплено 🟢")
        await call.message.answer(
            texts.bought_content(len(circles), purchase["author_share"])
        )

    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=kb.profile_card(
                profile,
                True,
                await db.get_purchase(call.from_user.id, author_id, "contact")
                is not None,
            )
        )


@router.callback_query(F.data.startswith("pf:contact:"))
async def buy_contact(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None or not profile["contact_ok"] or not profile["price_contact"]:
        await call.answer(texts.CONTACT_NOT_FOR_SALE, show_alert=True)
        return

    price = profile["price_contact"]
    result, purchase = await db.buy_access(
        call.from_user.id, author_id, "contact", price, settings.author_share(price)
    )
    if result == "poor":
        await call.answer("Не хватает монеток.", show_alert=True)
        return
    if result == "ok":
        await _notify_author(call.bot, author_id, "contact", purchase["author_share"])

    await call.answer()
    await call.message.answer(
        texts.bought_contact(await _fresh_username(call.bot, author_id, profile))
    )
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=kb.profile_card(
                profile,
                await db.get_purchase(call.from_user.id, author_id, "content")
                is not None,
                True,
            )
        )


@router.callback_query(F.data.startswith("pf:show:"))
async def show_circles(call: CallbackQuery) -> None:
    parts = call.data.split(":")
    author_id = int(parts[2])
    offset = int(parts[3]) if len(parts) > 3 else 0
    purchase = await db.get_purchase(call.from_user.id, author_id, "content")
    if purchase is None:
        await call.answer("Сначала купи доступ.", show_alert=True)
        return

    circles = (await db.author_circles(author_id, purchase["max_circle_id"]))[offset:]
    if not circles:
        await call.answer("У автора пока нечего смотреть.", show_alert=True)
        return

    await call.answer(f"Отправляю {min(len(circles), CIRCLES_PER_BATCH)}")
    for circle in circles[:CIRCLES_PER_BATCH]:
        with suppress(TelegramAPIError):
            await call.bot.send_video_note(
                call.from_user.id, circle["file_id"], protect_content=True
            )
        await asyncio.sleep(SEND_PAUSE)  # Telegram throttles bulk sends hard

    rest = circles[CIRCLES_PER_BATCH:]
    if rest:
        await call.message.answer(
            texts.more_circles(len(rest)),
            reply_markup=kb.more_circles(author_id, offset + CIRCLES_PER_BATCH),
        )


@router.callback_query(F.data.startswith("pf:rep:"))
async def report_profile(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer("Анкета пропала.", show_alert=True)
        return

    count = await db.report_profile(call.from_user.id, author_id)
    if count is None:
        await call.answer(texts.REPORT_DOUBLE_PROFILE, show_alert=True)
        return
    await call.answer(texts.REPORT_SENT, show_alert=True)

    hidden = count >= settings.get("reports_to_hide")
    if hidden and profile["status"] == "approved":
        await db.set_profile_status(author_id, "rejected")

    chat = settings.reports_chat()
    try:
        await call.bot.send_photo(
            chat,
            profile["photo_id"],
            caption=(
                f"#жалоба на анкету <code>{author_id}</code> — {count} шт\n"
                f"Статус: {'скрыта автоматически' if hidden else profile['status']}\n"
                f"{html.escape(profile['about'] or 'Без описания')}"
            ),
            reply_markup=kb.profile_report_review(author_id),
        )
    except TelegramAPIError as error:
        logger.error("profile report for %s not delivered: %s", author_id, error)


async def _fresh_username(bot, author_id: int, profile) -> str:
    """The stored username is a snapshot; ask Telegram before selling it."""
    try:
        chat = await bot.get_chat(author_id)
    except TelegramAPIError:
        return profile["username"] or ""
    return chat.username or profile["username"] or ""


async def _notify_author(bot, author_id: int, kind: str, share: int) -> None:
    with suppress(TelegramAPIError):
        await bot.send_message(author_id, texts.sale_note(kind, share))
