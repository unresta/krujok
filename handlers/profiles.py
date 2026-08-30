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
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import keyboards as kb
import outbox
import people
import settings
import texts
from config import ABOUT_MAX, ADMIN_CHAT_ID, ADMIN_IDS, BOOST_PACKS
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


@router.callback_query(F.data == "pf:edit_menu")
async def edit_menu(call: CallbackQuery, state: FSMContext) -> None:
    """Show menu to edit individual fields or create new profile."""
    await state.clear()
    profile = await db.get_profile(call.from_user.id)
    if profile is None:
        await call.message.answer(texts.PROFILE_INTRO, reply_markup=kb.profile_intro())
        await call.answer()
        return

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
        await call.answer(texts.PROFILE_NOTHING_TO_HIDE, show_alert=True)
        return
    await db.set_profile_status(call.from_user.id, "rejected")
    await call.answer(texts.PROFILE_HIDDEN_TOAST)
    profile = await db.get_profile(call.from_user.id)
    await call.message.edit_caption(
        caption=texts.profile_status(profile),
        reply_markup=kb.profile_edit_menu(profile),
    )


@router.callback_query(F.data.startswith("pf:boost:"))
async def buy_boost(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    days = int(call.data.split(":")[2])
    pack = next((p for p in BOOST_PACKS if p[0] == days), None)
    if pack is None:
        await call.answer(texts.STALE_BUTTON, show_alert=True)
        return

    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.BOOST_NEEDS_APPROVED, show_alert=True)
        return

    price = settings.boost_price(*pack)
    until = await db.buy_boost(call.from_user.id, days, price)
    if until is None:
        user = await db.get_user(call.from_user.id)
        await call.answer(texts.boost_poor(price, user["coins"]), show_alert=True)
        return

    await call.answer(texts.BOUGHT_TOAST)
    await call.message.answer(texts.boost_bought(days, price, until))


@router.callback_query(F.data == "pf:boost")
async def boost_menu(call: CallbackQuery, state: FSMContext) -> None:
    """Paid reach: the card is drawn early, not drawn twice."""
    await state.clear()
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.BOOST_NEEDS_APPROVED, show_alert=True)
        return

    user = await db.get_user(call.from_user.id)
    await call.message.answer(
        texts.boost_screen(user["coins"], profile["boost_until"]),
        reply_markup=kb.boost_packs(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("pf:edit:"))
async def edit_field(call: CallbackQuery, state: FSMContext) -> None:
    """Start editing one field."""
    field = call.data.split(":")[2]
    profile = await db.get_profile(call.from_user.id)
    if profile is None:
        await call.answer(texts.NEED_PROFILE_FIRST, show_alert=True)
        return

    # Selling the contact needs a @username; without one there is nothing to
    # price, so the question is not asked at all.
    if field == "price_contact" and not call.from_user.username:
        await call.answer(texts.PROFILE_NO_USERNAME, show_alert=True)
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
        await call.message.answer(
            texts.profile_price_contact(), reply_markup=kb.contact_price_edit()
        )
    await call.answer()


@router.callback_query(F.data == "pf:edit")
async def edit_profile(call: CallbackQuery, state: FSMContext) -> None:
    """Legacy callback — redirect to edit menu."""
    await edit_menu(call, state)


@router.callback_query(F.data == "pf:start")
async def start_profile(call: CallbackQuery, state: FSMContext) -> None:
    # Filling in from scratch, so a half-finished single-field edit must not
    # linger in the data and swallow the first answer.
    await state.clear()
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
        # Single-field edit: update only photo and resubmit for review
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
            await message.answer(
                texts.profile_field_saved("Фото"), reply_markup=kb.back()
            )
            await _resubmit_for_review(message, message.from_user.id, message.bot)
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
    if message.text is None:  # a photo here used to pass as an empty description
        await message.answer(texts.PROFILE_ABOUT_TEXT_ONLY, reply_markup=kb.back())
        return

    about = message.text.strip()
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
            await message.answer(
                texts.profile_field_saved("Описание"), reply_markup=kb.back()
            )
            await _resubmit_for_review(message, message.from_user.id, message.bot)
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
            await call.answer(texts.PROFILE_SAVED_TOAST)
            await call.message.answer(
                texts.profile_field_saved("Пол"), reply_markup=kb.back()
            )
            await _resubmit_for_review(call.message, call.from_user.id, call.bot)
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
            # Prices go live as they are typed: there is nothing in a number for
            # a moderator to check, and sending the profile back for review over
            # one would take it out of the feed for no reason.
            await db.set_profile_prices(
                message.from_user.id,
                price_content=price,
                price_contact=profile["price_contact"],
                contact_ok=bool(profile["contact_ok"]),
            )
            await state.clear()
            await message.answer(
                texts.profile_price_saved("Цена кружков", price),
                reply_markup=kb.back(),
            )
            return

    await state.update_data(price_content=price)
    await state.set_state(Anketa.contact)

    has_username = bool(message.from_user.username)
    await message.answer(
        texts.PROFILE_CONTACT_ASK if has_username else texts.PROFILE_NO_USERNAME,
        reply_markup=kb.profile_contact_ask(has_username),
    )


@router.callback_query(
    StateFilter(Anketa.contact, Anketa.price_contact), F.data.startswith("pc:")
)
async def got_contact_choice(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":")[1]
    data = await state.get_data()

    # Editing the price is the same screen as switching the sale off.
    if data.get("editing_field") == "price_contact":
        if choice != "no":
            await call.answer()
            return
        profile = await db.get_profile(call.from_user.id)
        if profile is None:
            await call.answer(texts.NEED_PROFILE_FIRST, show_alert=True)
            return
        # Taking the contact off sale is the same kind of change as its price.
        await db.set_profile_prices(
            call.from_user.id,
            price_content=profile["price_content"],
            price_contact=0,
            contact_ok=False,
        )
        await state.clear()
        await call.answer(texts.CONTACT_OFF_TOAST)
        await call.message.answer(texts.PROFILE_CONTACT_OFF, reply_markup=kb.back())
        return

    if choice == "recheck":
        # Telegram sends a fresh from_user with every update, so a username set
        # a second ago is already visible here.
        if not call.from_user.username:
            await call.answer(texts.PROFILE_STILL_NO_USERNAME, show_alert=True)
            return
        await call.answer(texts.USERNAME_SEEN)
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
            await db.set_profile_prices(
                message.from_user.id,
                price_content=profile["price_content"],
                price_contact=price,
                contact_ok=True,
            )
            await state.clear()
            await message.answer(
                texts.profile_price_saved("Цена лички", price),
                reply_markup=kb.back(),
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
    caption = (
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
        f"{html.escape(data.get('about') or 'Без описания')}"
    )

    async def deliver() -> None:
        # The profile is saved and shows up in the panel's queue regardless —
        # only the card is missing, and silence here is what hides that.
        card = await outbox.call(
            chat,
            lambda: message.bot.send_photo(
                chat,
                data["photo_id"],
                caption=caption,
                reply_markup=kb.profile_review(author.id),
            ),
            f"анкета {author.id}",
        )
        if card is not None:
            await db.set_profile_admin_msg(author.id, card.message_id)

    outbox.post(chat, deliver, f"анкета {author.id}")


async def _resubmit_for_review(message: Message, user_id: int, bot) -> None:
    """Re-submit profile for review after editing a field."""
    profile = await db.get_profile(user_id)
    if not profile:
        return

    # Set status back to pending
    await db.set_profile_status(user_id, "pending")

    chat = settings.profiles_chat()
    caption = (
        f"#анкета_изменена от {await people.of(user_id)}\n"
        f"♻️ Отредактирована\n"
        f"Кто: {kb.PERSON_TITLE(profile['gender'])}\n"
        f"Кружочки: {profile['price_content']} · "
        f"личка: {profile['price_contact'] or 'нет'}\n\n"
        f"{html.escape(profile['about'] or 'Без описания')}"
    )

    async def deliver() -> None:
        card = await outbox.call(
            chat,
            lambda: bot.send_photo(
                chat,
                profile["photo_id"],
                caption=caption,
                reply_markup=kb.profile_review(user_id),
            ),
            f"анкета {user_id}",
        )
        if card is not None:
            await db.set_profile_admin_msg(user_id, card.message_id)

    outbox.post(chat, deliver, f"анкета {user_id}")


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

    # A verdict can always be revisited — each card comes back to its own pair
    # of buttons: the queue's approve/reject, the complaint's hide/keep.
    if verdict in ("again", "ragain"):
        markup = (
            kb.profile_review(user_id)
            if verdict == "again"
            else kb.profile_report_review(user_id)
        )
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=markup)
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
            f"Причина отклонения для {await people.of(user_id)}? "
            "Пришли одним сообщением — автор её увидит."
        )
        await call.answer()
        return

    reason = texts.REJECT_REASONS[parts[2]] if verdict == "r" else ""
    status = "approved" if verdict == "ok" else "rejected"

    if verdict in ("hide", "keep"):  # verdict on a complaint, not on a new profile
        was = await db.get_profile(user_id)
        status = "rejected" if verdict == "hide" else "approved"
        await db.set_profile_status(user_id, status)
        await db.clear_profile_reports(user_id)
        if verdict == "hide":
            await db.drop_profile_backup(user_id)  # nothing here is worth restoring
            await _tell_author(call.bot, user_id, "rejected", "жалобы пользователей")
        elif was is not None and was["status"] != "approved":
            # Keeping a profile that was already hidden puts it back on screen,
            # and the author has no other way of learning that.
            await _tell_author(call.bot, user_id, "approved")
        mark = "🔴 скрыта" if verdict == "hide" else "🟢 оставлена"
        with suppress(TelegramAPIError):
            await call.message.edit_caption(
                caption=f"{_card_body(call.message.html_text)}\n\n<b>{mark}</b>",
                reply_markup=kb.profile_report_decided(user_id),
            )
        await call.answer(mark)
        return

    mark = await _decide(call.bot, user_id, status, reason)
    with suppress(TelegramAPIError):
        await call.message.edit_caption(
            caption=f"{_card_body(call.message.html_text)}\n\n<b>{mark}</b>",
            reply_markup=kb.profile_decided(user_id),
        )
    await call.answer(mark)


def _card_body(html_text: str) -> str:
    """Re-deciding edits the same card, so verdict lines must not stack up."""
    for mark in ("\n\n<b>🟢", "\n\n<b>🔴"):
        html_text = html_text.split(mark)[0]
    return html_text.rstrip()


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
    with suppress(TelegramAPIError):  # the card keeps a way back to the buttons
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
    profile = await db.pick_profile(viewer_id, settings.get("boost_weight"))
    if profile is None:  # everything seen once — start a new lap
        await db.reset_profile_views(viewer_id)
        profile = await db.pick_profile(viewer_id, settings.get("boost_weight"))
    if profile is None:
        # Nothing to show is the best moment to ask for a profile of their own.
        mine = await db.get_profile(viewer_id)
        if mine is None:
            await origin.answer(
                texts.profile_empty_pitch(), reply_markup=kb.profile_intro()
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
            await call.message.answer(texts.UPLOAD_NEEDS_PROFILE, reply_markup=kb.profile_intro())
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
        await call.message.answer(texts.MY_CIRCLES_EMPTY)
        return
    await call.message.answer(texts.my_circles(stats), reply_markup=kb.back())


@router.callback_query(F.data == "mp:bought")
async def mp_bought(call: CallbackQuery) -> None:
    """Show purchased content."""
    await call.answer()
    purchases = await db.get_user_purchases(call.from_user.id, "content")
    if not purchases:
        await call.message.answer(texts.BOUGHT_EMPTY)
        return

    text_lines = [texts.BOUGHT_HEADER]
    buttons = []

    for index, p in enumerate(purchases, 1):
        author_id = p["author_id"]
        circles = await db.author_circles(author_id, p["max_circle_id"])
        count = len(circles)
        # The buyer bought circles, not the person: an author is «♀️ Девушка»
        # here, and their id stays where it belongs — in the callback.
        profile = await db.get_profile(author_id)
        who = kb.PERSON_TITLE(profile["gender"]) if profile else texts.AUTHOR_NO_PROFILE
        text_lines.append(texts.bought_row(index, who, count))
        buttons.append(
            InlineKeyboardButton(
                text=f"{index}. {who} · {count}",
                callback_data=f"pf:show:{author_id}",
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
        await call.answer(texts.PROFILE_NONE_YET, show_alert=True)
        return
    if author_id == call.from_user.id:
        await call.answer(texts.PROFILE_OWN)
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
        await call.answer(texts.PROFILE_GONE, show_alert=True)
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
        await call.answer(texts.NOT_ENOUGH_COINS_TOAST, show_alert=True)
        return
    if result == "already":
        await call.answer(texts.ALREADY_BOUGHT)
    else:
        await _notify_author(call.bot, author_id, "content", purchase["author_share"])
        circles = await db.author_circles(author_id, purchase["max_circle_id"])
        await call.answer(texts.BOUGHT_TOAST)
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
        await call.answer(texts.NOT_ENOUGH_COINS_TOAST, show_alert=True)
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
        await call.answer(texts.BUY_FIRST, show_alert=True)
        return

    circles = (await db.author_circles(author_id, purchase["max_circle_id"]))[offset:]
    if not circles:
        await call.answer(texts.AUTHOR_EMPTY, show_alert=True)
        return

    await call.answer(texts.sending_circles(min(len(circles), CIRCLES_PER_BATCH)))
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


async def _card_markup(viewer_id: int, profile):
    """The card's own buttons, rebuilt after the reasons menu covered them."""
    author_id = profile["user_id"]
    return kb.profile_card(
        profile,
        await db.get_purchase(viewer_id, author_id, "content") is not None,
        await db.get_purchase(viewer_id, author_id, "contact") is not None,
    )


@router.callback_query(F.data.startswith(("pf:rep:", "pf:rr:", "pf:rback:")))
async def report_profile(call: CallbackQuery) -> None:
    """Two taps: «Пожаловаться» asks what for, the reason files the complaint."""
    parts = call.data.split(":")
    action = parts[1]
    author_id = int(parts[-1])

    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer(texts.PROFILE_GONE, show_alert=True)
        return

    if action == "rback":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=await _card_markup(call.from_user.id, profile)
            )
        await call.answer()
        return

    # Better to say so now than after they picked a reason for nothing.
    if await db.has_reported_profile(call.from_user.id, author_id):
        await call.answer(texts.REPORT_DOUBLE_PROFILE, show_alert=True)
        return

    if action == "rep":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.profile_report_reasons(author_id)
            )
        await call.answer(texts.REPORT_ASK)
        return

    reason = parts[2] if parts[2] in texts.PROFILE_REPORT_REASONS else "other"
    count = await db.report_profile(call.from_user.id, author_id, reason)
    if count is None:  # two taps racing each other
        await call.answer(texts.REPORT_DOUBLE_PROFILE, show_alert=True)
        return
    await call.answer(texts.REPORT_SENT, show_alert=True)
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=await _card_markup(call.from_user.id, profile)
        )

    hidden = count >= settings.get("reports_to_hide")
    if hidden and profile["status"] == "approved":
        await db.set_profile_status(author_id, "rejected")

    breakdown = texts.reasons_summary(
        await db.profile_report_reasons(author_id), texts.PROFILE_REPORT_REASONS
    )
    chat = settings.reports_chat()
    caption = (
        f"#жалоба на анкету {await people.of(author_id)} — {count} шт\n"
        f"Причина: {texts.PROFILE_REPORT_REASONS[reason]}\n"
        f"Статус: {'скрыта автоматически' if hidden else profile['status']}\n"
        f"{html.escape(profile['about'] or 'Без описания')}\n\n"
        f"{breakdown}"
    )
    outbox.post(
        chat,
        lambda: outbox.call(
            chat,
            lambda: call.bot.send_photo(
                chat,
                profile["photo_id"],
                caption=caption,
                reply_markup=kb.profile_report_review(author_id),
            ),
            f"жалоба на анкету {author_id}",
        ),
        f"жалоба на анкету {author_id}",
    )


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
