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
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InputMediaPhoto,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import access
import db
import keyboards as kb
import lang
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


async def _send_circles(bot, user_id: int, circles, markup=None) -> int:
    """A batch of circles into one private chat. Returns how many landed.

    Every send used to sit inside `suppress(TelegramAPIError)`, so a batch that
    Telegram refused looked exactly like a batch it delivered: the toast said
    «Отправляю 7», nothing arrived, and no line went anywhere. Two things come
    out of that — a flood limit is waited out instead of thrown away, and
    whatever is still lost is counted, logged and told to the user.
    """
    landed = 0
    for circle in circles:
        try:
            await bot.send_video_note(
                user_id,
                circle["file_id"],
                protect_content=True,
                reply_markup=markup(circle) if markup else None,
            )
            landed += 1
        except TelegramRetryAfter as error:
            # Ten circles in a row is enough to trip the per-chat limit on its
            # own. Waiting it out is the difference between all of them and none.
            await asyncio.sleep(error.retry_after + 1)
            try:
                await bot.send_video_note(
                    user_id,
                    circle["file_id"],
                    protect_content=True,
                    reply_markup=markup(circle) if markup else None,
                )
                landed += 1
            except TelegramAPIError as second:
                logger.warning(
                    "кружок #%s не дошёл до %s: %s", circle["id"], user_id, second
                )
        except TelegramAPIError as error:
            logger.warning(
                "кружок #%s не дошёл до %s: %s", circle["id"], user_id, error
            )
        await asyncio.sleep(SEND_PAUSE)  # Telegram throttles bulk sends hard
    return landed


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
        await call.message.answer(texts.t("PROFILE_INTRO"), reply_markup=kb.profile_intro())
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
        await call.answer(texts.t("PROFILE_NOTHING_TO_HIDE"), show_alert=True)
        return
    await db.set_profile_status(call.from_user.id, "rejected")
    await call.answer(texts.t("PROFILE_HIDDEN_TOAST"))
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
        await call.answer(texts.t("STALE_BUTTON"), show_alert=True)
        return

    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.t("BOOST_NEEDS_APPROVED"), show_alert=True)
        return

    price = settings.boost_price(*pack)
    until = await db.buy_boost(call.from_user.id, days, price)
    if until is None:
        user = await db.get_user(call.from_user.id)
        await call.answer(texts.boost_poor(price, user["coins"]), show_alert=True)
        return

    await call.answer(texts.t("BOUGHT_TOAST"))
    await call.message.answer(texts.boost_bought(days, price, until))


@router.callback_query(F.data == "pf:boost")
async def boost_menu(call: CallbackQuery, state: FSMContext) -> None:
    """Paid reach: the card is drawn early, not drawn twice."""
    await state.clear()
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.t("BOOST_NEEDS_APPROVED"), show_alert=True)
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
        await call.answer(texts.t("NEED_PROFILE_FIRST"), show_alert=True)
        return

    # Selling the contact needs a @username; without one there is nothing to
    # price, so the question is not asked at all.
    if field == "price_contact" and not call.from_user.username:
        await call.answer(texts.t("PROFILE_NO_USERNAME"), show_alert=True)
        return

    await state.update_data(editing_field=field)

    if field == "photo":
        await state.set_state(Anketa.photo)
        await call.message.answer(texts.t("PROFILE_PHOTO"), reply_markup=kb.back())
    elif field == "about":
        await state.set_state(Anketa.about)
        await call.message.answer(texts.profile_about(), reply_markup=kb.back())
    elif field == "gender":
        await state.set_state(Anketa.gender)
        await call.message.answer(texts.t("PROFILE_GENDER"), reply_markup=kb.profile_gender())
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
    await call.message.answer(texts.t("PROFILE_PHOTO"), reply_markup=kb.back())
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
                texts.profile_field_saved(texts.field_name("Фото")), reply_markup=kb.back()
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
    await message.answer(texts.t("PROFILE_NOT_PHOTO"), reply_markup=kb.back())


@router.message(Anketa.about, ~F.text.in_(kb.MENU_BUTTONS))
async def got_about(message: Message, state: FSMContext) -> None:
    if message.text is None:  # a photo here used to pass as an empty description
        await message.answer(texts.t("PROFILE_ABOUT_TEXT_ONLY"), reply_markup=kb.back())
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
                texts.profile_field_saved(texts.field_name("Описание")), reply_markup=kb.back()
            )
            await _resubmit_for_review(message, message.from_user.id, message.bot)
            return

    await state.update_data(about=about)
    await state.set_state(Anketa.gender)
    await message.answer(texts.t("PROFILE_GENDER"), reply_markup=kb.profile_gender())


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
            await call.answer(texts.t("PROFILE_SAVED_TOAST"))
            await call.message.answer(
                texts.profile_field_saved(texts.field_name("Пол")), reply_markup=kb.back()
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
                texts.profile_price_saved(texts.field_name("Цена кружков"), price),
                reply_markup=kb.back(),
            )
            return

    await state.update_data(price_content=price)
    await state.set_state(Anketa.contact)

    has_username = bool(message.from_user.username)
    await message.answer(
        texts.t("PROFILE_CONTACT_ASK") if has_username else texts.t("PROFILE_NO_USERNAME"),
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
            await call.answer(texts.t("NEED_PROFILE_FIRST"), show_alert=True)
            return
        # Taking the contact off sale is the same kind of change as its price.
        await db.set_profile_prices(
            call.from_user.id,
            price_content=profile["price_content"],
            price_contact=0,
            contact_ok=False,
        )
        await state.clear()
        await call.answer(texts.t("CONTACT_OFF_TOAST"))
        await call.message.answer(texts.t("PROFILE_CONTACT_OFF"), reply_markup=kb.back())
        return

    if choice == "recheck":
        # Telegram sends a fresh from_user with every update, so a username set
        # a second ago is already visible here.
        if not call.from_user.username:
            await call.answer(texts.t("PROFILE_STILL_NO_USERNAME"), show_alert=True)
            return
        await call.answer(texts.t("USERNAME_SEEN"))
        with suppress(TelegramAPIError):
            await call.message.edit_text(
                texts.t("PROFILE_CONTACT_ASK"), reply_markup=kb.profile_contact_ask(True)
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
                texts.profile_price_saved(texts.field_name("Цена лички"), price),
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
    await message.answer(texts.t("PROFILE_SENT"), reply_markup=kb.back())

    chat = settings.profiles_chat()
    # The card is read by moderators: Russian whatever the author is answered in.
    with lang.use("ru"):
        caption = (
            ("#анкета_изменена" if previous else "#анкета")
            + f" от <code>{author.id}</code>"
            f"{' @' + author.username if author.username else ''}\n"
            + (
                # The time tells one edit from the next when the card is
                # rewritten in place — and answers «а когда?» besides.
                f"♻️ Поменялось: <b>{', '.join(changes)}</b> · {texts.hhmm()}\n"
                if changes
                else f"♻️ Прислана заново без правок · {texts.hhmm()}\n"
                if previous
                else ""
            )
            + f"Кто: {kb.PERSON_TITLE(data['gender'])}\n"
            f"Кружочки: {data['price_content']} · "
            f"личка: {data.get('price_contact') or 'нет'}\n\n"
            f"{html.escape(data.get('about') or 'Без описания')}"
        )

    await _post_card(
        message.bot, author.id, data["photo_id"], caption, previous
    )


async def _post_card(bot, user_id: int, photo_id: str, caption: str, previous) -> None:
    """Put the profile in front of a moderator — in one card, not in a pile.

    An author who fixes their photo three times before anyone looks used to
    leave three cards in the chat, all but the last one describing a profile
    that no longer exists. Whoever reads the queue then has to work out which
    of them is still true, and the buttons of the stale ones still work.

    So while the last card is undecided (`profiles.admin_msg_id`), the next
    edit rewrites it. A card that already carries a verdict is never touched:
    that verdict is the record of a decision, and the moderator wrote it.
    """
    chat = settings.profiles_chat()
    markup = kb.profile_review(user_id)
    waiting = previous["admin_msg_id"] if previous else None

    async def deliver() -> None:
        if waiting:
            # editMessageMedia carries the caption with it, so the photo and
            # the text move together — two calls could leave them mismatched.
            edited = await outbox.call(
                chat,
                lambda: bot.edit_message_media(
                    chat_id=chat,
                    message_id=waiting,
                    media=InputMediaPhoto(media=photo_id, caption=caption),
                    reply_markup=markup,
                ),
                f"анкета {user_id}",
            )
            if edited is not None:
                return
            # Gone: deleted by hand, or the chat was changed under us. A fresh
            # card is better than an author who waits for one that is not there.
            logger.info("анкета %s: карточка %s не правится, шлю новую", user_id, waiting)
        # The profile is saved and shows up in the panel's queue regardless —
        # only the card is missing, and silence here is what hides that.
        card = await outbox.call(
            chat,
            lambda: bot.send_photo(
                chat, photo_id, caption=caption, reply_markup=markup
            ),
            f"анкета {user_id}",
        )
        if card is not None:
            await db.set_profile_admin_msg(user_id, card.message_id)

    outbox.post(chat, deliver, f"анкета {user_id}")


async def _resubmit_for_review(message: Message, user_id: int, bot) -> None:
    """Re-submit profile for review after editing a field."""
    profile = await db.get_profile(user_id)
    if not profile:
        return

    # Set status back to pending
    await db.set_profile_status(user_id, "pending")

    with lang.use("ru"):  # moderators read it, not the author
        caption = (
            f"#анкета_изменена от {await people.of(user_id)}\n"
            f"♻️ Отредактирована · {texts.hhmm()}\n"
            f"Кто: {kb.PERSON_TITLE(profile['gender'])}\n"
            f"Кружочки: {profile['price_content']} · "
            f"личка: {profile['price_contact'] or 'нет'}\n\n"
            f"{html.escape(profile['about'] or 'Без описания')}"
        )
    # save_profile leaves admin_msg_id alone, so the row read here still points
    # at the card that is waiting — if one is.
    await _post_card(bot, user_id, profile["photo_id"], caption, profile)


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
        if verdict == "again":
            # Undecided again, so an edit that arrives now belongs on this card
            # rather than on a second one. The complaint card lives in another
            # chat and is not the queue's, so it is not claimed here.
            await db.set_profile_admin_msg(user_id, call.message.message_id)
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

    # The key travels rather than the label — the author may read English.
    reason = parts[2] if verdict == "r" and parts[2] in texts.REJECT_REASONS else ""
    status = "approved" if verdict == "ok" else "rejected"

    if verdict in ("hide", "keep"):  # verdict on a complaint, not on a new profile
        was = await db.get_profile(user_id)
        status = "rejected" if verdict == "hide" else "approved"
        # Read before clearing: what people complained about is the one thing
        # the author needs to know, and the complaints are about to be closed.
        complaints = [
            texts.PROFILE_REPORT_REASONS.get(row["reason"], texts.t("NO_REASON"))
            for row in await db.profile_report_reasons(user_id)
        ]
        await db.set_profile_status(user_id, status)
        await db.clear_profile_reports(user_id)
        if verdict == "hide":
            # The anketa itself stays whole — only its rollback snapshot goes,
            # because the version that collected the complaints is not one to
            # come back to if the author's next edit is turned down.
            await db.drop_profile_backup(user_id)
            await _tell_author(call.bot, user_id, "frozen", complaints=complaints)
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
    # Decided: the card now carries a verdict, and the next edit gets a card of
    # its own rather than overwriting what the moderator just wrote.
    await db.set_profile_admin_msg(user_id, None)
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
    return f"{mark} · {texts.profile_reject_reason(reason)}" if reason else mark


async def _tell_author(
    bot, user_id: int, status: str, reason: str = "", complaints: list | None = None
) -> None:
    # Written from inside a moderator's update, and read by the author: the
    # language has to be theirs, not whoever happened to press the button.
    with lang.use(await db.lang_of(user_id)):
        return await _tell_author_now(bot, user_id, status, reason, complaints)


async def _tell_author_now(
    bot, user_id: int, status: str, reason: str = "", complaints: list | None = None
) -> None:
    if status == "approved":
        text, markup = texts.t("PROFILE_APPROVED"), None
    elif status == "reverted":
        text, markup = texts.profile_reverted(reason), kb.refill_profile()
    elif status == "frozen":
        # Taken off display, not taken away: the way back is the edit menu.
        text, markup = texts.profile_frozen(complaints or []), kb.fix_profile()
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


@router.message(F.text.in_(kb.labels(kb.BTN_ANKETAS)))
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


async def author_card(
    viewer_id: int, profile, intro: str = "", from_bought: bool = False
) -> tuple[str, object]:
    """The whole card — caption and buttons — for whoever is looking at it.

    Three screens show an author: the feed, the «Анкета автора» button under a
    circle, and the author's own link. They used to build the card each in their
    own way, so «Докупить новые» appeared on two of them and the third quietly
    went on showing 112 circles to somebody who could open 38.
    """
    have, total, cost = await topup_state(viewer_id, profile)
    bought = await db.get_purchase(viewer_id, profile["user_id"], "content")
    caption = texts.profile_card(profile, total)
    if bought is not None:
        caption += texts.topup_line(have, total, profile["price_content"])
    return (intro + "\n\n" + caption if intro else caption), await _card_markup(
        viewer_id, profile, from_bought
    )


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
            await origin.answer(texts.t("PROFILE_EMPTY_WAIT"), reply_markup=kb.back())
        return

    caption, markup = await author_card(viewer_id, profile)
    await bot.send_photo(
        chat_id=viewer_id, photo=profile["photo_id"], caption=caption,
        reply_markup=markup,
    )
    await db.mark_profile_seen(viewer_id, profile["user_id"])


@router.callback_query(F.data == "mp:upload")
async def mp_upload(call: CallbackQuery, state: FSMContext) -> None:
    """Redirect to upload flow."""
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        if profile is None:
            await call.message.answer(texts.t("UPLOAD_NEEDS_PROFILE"), reply_markup=kb.profile_intro())
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
        await call.message.answer(texts.t("MY_CIRCLES_EMPTY"))
        return
    await call.message.answer(
        texts.my_circles(stats), reply_markup=kb.my_circles(stats)
    )


@router.callback_query(F.data.startswith("mc:i:"))
async def own_circle_info(call: CallbackQuery) -> None:
    """Everything the bot knows about one of the author's own circles."""
    raw_id = call.data.split(":")[2]
    circle = await db.get_circle(int(raw_id)) if raw_id.isdigit() else None
    # Only the author's own: the numbers under a circle are nobody else's.
    if circle is None or circle["uploader_id"] != call.from_user.id:
        await call.answer(texts.t("MY_CIRCLE_GONE"), show_alert=True)
        return
    await call.answer(texts.my_circle_info(circle), show_alert=True)


@router.callback_query(F.data.startswith(("mc:del:", "mc:delgo:", "mc:keep:")))
async def own_circle_delete(call: CallbackQuery) -> None:
    """An author throwing away one of their own circles, in two taps."""
    _, action, raw_id = call.data.split(":", 2)
    circle = await db.get_circle(int(raw_id)) if raw_id.isdigit() else None
    # Their own only: the callback is guessable, the video is not.
    if circle is None or circle["uploader_id"] != call.from_user.id:
        await call.answer(texts.t("MY_CIRCLE_GONE"), show_alert=True)
        return

    if action == "keep":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.my_circle(circle["id"])
            )
        await call.answer()
        return

    if action == "del":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.my_circle_confirm(circle["id"])
            )
        await call.answer(texts.t("MY_CIRCLE_ASK"), show_alert=True)
        return

    await db.delete_circle(circle["id"])
    logger.info("кружок #%s удалён автором %s", circle["id"], call.from_user.id)
    await call.answer(texts.t("MY_CIRCLE_DELETED"), show_alert=True)
    # The video goes with the row; a message left behind would still play it.
    try:
        await call.message.delete()
    except TelegramAPIError:  # older than 48h — then at least take the buttons off
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("mc:"))
async def own_circles(call: CallbackQuery) -> None:
    """The author's own uploads of one status, a batch per tap."""
    parts = call.data.split(":")
    if (
        len(parts) != 3
        or parts[1] not in texts.MY_CIRCLES_STATUS
        or not parts[2].isdigit()
    ):
        await call.answer(texts.t("STALE_BUTTON"))
        return

    status, offset = parts[1], int(parts[2])
    circles = (await db.own_circles(call.from_user.id, status))[offset:]
    if not circles:
        await call.answer(texts.t("MY_CIRCLES_STATUS_EMPTY"), show_alert=True)
        return

    batch = circles[:CIRCLES_PER_BATCH]
    await call.answer(texts.sending_circles(len(batch)))
    if not offset:  # the header belongs to the list, not to every batch of it
        await call.bot.send_message(
            call.from_user.id, texts.MY_CIRCLES_STATUS[status]
        )
    sent = await _send_circles(
        call.bot, call.from_user.id, batch, lambda c: kb.my_circle(c["id"])
    )
    if sent < len(batch):
        await call.bot.send_message(
            call.from_user.id, texts.circles_lost(sent, len(batch))
        )

    rest = circles[CIRCLES_PER_BATCH:]
    await call.bot.send_message(
        call.from_user.id,
        texts.my_circles_more(len(rest)) if rest else texts.t("MY_CIRCLES_DONE"),
        reply_markup=kb.my_circles_nav(
            status, offset + CIRCLES_PER_BATCH if rest else None
        ),
    )


@router.callback_query(F.data == "mp:bought")
async def mp_bought(call: CallbackQuery) -> None:
    """Show purchased content."""
    await call.answer()
    # Coming back from a card that replaced this list: it goes, the list returns.
    if call.message is not None and call.message.photo:
        with suppress(TelegramAPIError):
            await call.message.delete()
    purchases = await db.get_user_purchases(call.from_user.id, "content")
    if not purchases:
        await call.message.answer(texts.t("BOUGHT_EMPTY"))
        return

    text_lines = [texts.t("BOUGHT_HEADER")]
    buttons = []

    for index, p in enumerate(purchases, 1):
        author_id = p["author_id"]
        circles = await db.author_circles(author_id, p["max_circle_id"])
        count = len(circles)
        # The buyer bought circles, not the person: an author is «♀️ Девушка»
        # here, and their id stays where it belongs — in the callback.
        profile = await db.get_profile(author_id)
        who = kb.PERSON_TITLE(profile["gender"]) if profile else texts.t("AUTHOR_NO_PROFILE")
        # The line goes into message text and the button label into a button:
        # the same name, but only one of the two renders HTML.
        on_button = (
            kb.PERSON_BUTTON(profile["gender"]) if profile else texts.t("AUTHOR_NO_PROFILE")
        )
        text_lines.append(texts.bought_row(index, who, count))
        buttons.append(
            InlineKeyboardButton(
                text=f"{index}. {on_button} · {count}",
                callback_data=f"mp:author:{author_id}",
                style=PRIMARY,
            )
        )

    text = "\n".join(text_lines)

    b = InlineKeyboardBuilder()
    for btn in buttons:
        b.row(btn)
    b.row(InlineKeyboardButton(text=kb.L("❌ Закрыть", "❌ Close"), callback_data="menu", style=DANGER))

    await call.message.answer(text, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("mp:author:"))
async def bought_author(call: CallbackQuery) -> None:
    """Open one author out of «Купленные кружочки», in place of the list.

    The list is a text message and the card is a photo, and Telegram will not
    turn one into the other — so the list goes and the card takes its place.
    That is what «отредактировалось в анкету» looks like from the outside.
    """
    author_id = int(call.data.split(":")[2])
    if await db.get_purchase(call.from_user.id, author_id, "content") is None:
        await call.answer(texts.t("BUY_FIRST"), show_alert=True)
        return
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer(texts.t("AUTHOR_NO_PROFILE"), show_alert=True)
        return

    await call.answer()
    caption, markup = await author_card(
        call.from_user.id, profile, from_bought=True
    )
    await call.bot.send_photo(
        chat_id=call.from_user.id,
        photo=profile["photo_id"],
        caption=caption,
        reply_markup=markup,
    )
    with suppress(TelegramAPIError):  # older than 48h, or already gone
        await call.message.delete()


@router.callback_query(F.data.startswith("pf:card:"))
async def open_card(call: CallbackQuery) -> None:
    """«Анкета автора» under a circle — the same card as in the feed."""
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.t("PROFILE_NONE_YET"), show_alert=True)
        return
    if author_id == call.from_user.id:
        await call.answer(texts.t("PROFILE_OWN"))
        return

    await call.answer()
    caption, markup = await author_card(call.from_user.id, profile)
    await call.bot.send_photo(
        chat_id=call.from_user.id,
        photo=profile["photo_id"],
        caption=caption,
        reply_markup=markup,
    )


async def open_by_link(bot, viewer_id: int, author_id: int) -> bool:
    """The card somebody came for, straight from the author's own link.

    Not marked as seen: the visitor was brought here by the author, not by the
    feed, and taking the card out of their lap would cost a second chance to
    sell it. The visit is counted apart, in `link_hits`.
    """
    profile = await db.get_profile(author_id)
    if profile is None or profile["status"] != "approved":
        await bot.send_message(viewer_id, texts.t("PROFILE_LINK_GONE"))
        return False
    if author_id == viewer_id:
        await bot.send_message(viewer_id, texts.t("PROFILE_LINK_OWN"))
        return False

    await db.count_link_hit(author_id)
    caption, markup = await author_card(viewer_id, profile, texts.t("PROFILE_LINK_INTRO"))
    await bot.send_photo(
        chat_id=viewer_id,
        photo=profile["photo_id"],
        caption=caption,
        reply_markup=markup,
    )
    return True


@router.callback_query(F.data == "pf:link")
async def share_link(call: CallbackQuery) -> None:
    """The author's own link, with the button that copies it."""
    profile = await db.get_profile(call.from_user.id)
    if profile is None or profile["status"] != "approved":
        await call.answer(texts.t("PROFILE_LINK_NEEDS_APPROVED"), show_alert=True)
        return

    link = access.profile_link(call.from_user.id)
    await call.answer()
    await call.message.answer(
        texts.profile_link_screen(link, profile["link_hits"]),
        reply_markup=kb.profile_link(link),
    )


@router.callback_query(F.data.startswith("pf:buy:"))
async def buy_content(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer(texts.t("PROFILE_GONE"), show_alert=True)
        return

    # Selling access to an empty catalogue is just taking coins.
    if not await db.author_circles(author_id, await db.total_circles_max_id()):
        await call.answer(texts.t("NOTHING_TO_SELL"), show_alert=True)
        return

    price = profile["price_content"]
    result, purchase = await db.buy_access(
        call.from_user.id, author_id, "content", price, settings.author_share(price)
    )
    if result == "poor":
        await call.answer(texts.t("NOT_ENOUGH_COINS_TOAST"), show_alert=True)
        return
    if result == "already":
        await call.answer(texts.t("ALREADY_BOUGHT"))
    else:
        await _notify_author(call.bot, author_id, "content", purchase["author_share"])
        circles = await db.author_circles(author_id, purchase["max_circle_id"])
        await call.answer(texts.t("BOUGHT_TOAST"))
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


@router.callback_query(F.data.startswith("pf:topup:"))
async def topup_content(call: CallbackQuery) -> None:
    """Move an old purchase up to the catalogue as it stands today."""
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    purchase = await db.get_purchase(call.from_user.id, author_id, "content")
    if profile is None or purchase is None:
        await call.answer(texts.t("BUY_FIRST"), show_alert=True)
        return

    have, total, cost = await topup_state(call.from_user.id, profile)
    if not total - have:
        await call.answer(texts.t("TOPUP_GONE"), show_alert=True)
        return
    if not cost:  # too few new ones to price — see settings.topup_worth_it
        await call.answer(texts.t("TOPUP_SMALL"), show_alert=True)
        return

    new_max = await db.total_circles_max_id()
    ok = await db.topup_access(
        call.from_user.id, author_id, cost, settings.author_share(cost), new_max
    )
    if not ok:
        user = await db.get_user(call.from_user.id)
        await call.answer(texts.not_enough(user["coins"]), show_alert=True)
        return

    await _notify_author(call.bot, author_id, "content", settings.author_share(cost))
    await call.answer(texts.t("BOUGHT_TOAST"))
    await call.message.answer(texts.topup_done(total - have, total))
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=await _card_markup(call.from_user.id, profile)
        )


async def tell_buyers(bot, author_id: int) -> int:
    """Let this author's buyers know there is something new worth opening.

    Told once per batch of new circles, not once per circle: the marker is
    cleared when they top up, so the next batch can knock again. People who
    have nothing to buy yet are left alone — and so are the ones whose share
    of the catalogue is still too small to price.
    """
    profile = await db.get_profile(author_id)
    if profile is None:
        return 0
    total = await db.author_circle_count(author_id)
    sent = 0
    for purchase in await db.topup_candidates(author_id):
        have = await db.author_circle_count(author_id, purchase["max_circle_id"])
        cost = settings.topup_price(profile["price_content"], have, total)
        if not settings.topup_worth_it(cost):
            continue
        await db.mark_topup_told(purchase["buyer_id"], author_id)
        with lang.use(await db.lang_of(purchase["buyer_id"])):
            offer = texts.topup_news(total - have, cost)
            markup = kb.topup_offer(author_id)
        with suppress(TelegramAPIError):  # blocked the bot, nothing to do
            await bot.send_message(purchase["buyer_id"], offer, reply_markup=markup)
            sent += 1
        await asyncio.sleep(SEND_PAUSE)
    if sent:
        logger.info("докупка: позвали %s покупателей автора %s", sent, author_id)
    return sent


@router.callback_query(F.data.startswith("pf:contact:"))
async def buy_contact(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None or not profile["contact_ok"] or not profile["price_contact"]:
        await call.answer(texts.t("CONTACT_NOT_FOR_SALE"), show_alert=True)
        return

    price = profile["price_contact"]
    result, purchase = await db.buy_access(
        call.from_user.id, author_id, "contact", price, settings.author_share(price)
    )
    if result == "poor":
        await call.answer(texts.t("NOT_ENOUGH_COINS_TOAST"), show_alert=True)
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
        await call.answer(texts.t("BUY_FIRST"), show_alert=True)
        return

    circles = (await db.author_circles(author_id, purchase["max_circle_id"]))[offset:]
    if not circles:
        await call.answer(texts.t("AUTHOR_EMPTY"), show_alert=True)
        return

    batch = circles[:CIRCLES_PER_BATCH]
    await call.answer(texts.sending_circles(len(batch)))
    sent = await _send_circles(call.bot, call.from_user.id, batch)
    if sent < len(batch):
        await call.bot.send_message(
            call.from_user.id, texts.circles_lost(sent, len(batch))
        )

    rest = circles[CIRCLES_PER_BATCH:]
    if rest:
        await call.bot.send_message(
            call.from_user.id,
            texts.more_circles(len(rest)),
            reply_markup=kb.more_circles(author_id, offset + CIRCLES_PER_BATCH),
        )


async def topup_state(viewer_id: int, profile) -> tuple[int, int, int]:
    """(open to them, the author has, what the rest costs) for this pair.

    A purchase is frozen at the catalogue of its day, so an author who keeps
    uploading leaves their own buyers behind. This is what the card needs to
    say so, and what the "докупить" button is priced from.
    """
    author_id = profile["user_id"]
    purchase = await db.get_purchase(viewer_id, author_id, "content")
    total = await db.author_circle_count(author_id)
    if purchase is None:
        return 0, total, 0
    have = await db.author_circle_count(author_id, purchase["max_circle_id"])
    cost = settings.topup_price(profile["price_content"], have, total)
    return have, total, cost if settings.topup_worth_it(cost) else 0


async def _card_markup(viewer_id: int, profile, from_bought: bool = False):
    """The card's own buttons, rebuilt after the reasons menu covered them."""
    author_id = profile["user_id"]
    bought = await db.get_purchase(viewer_id, author_id, "content") is not None
    _, _, cost = await topup_state(viewer_id, profile) if bought else (0, 0, 0)
    return kb.profile_card(
        profile,
        bought,
        await db.get_purchase(viewer_id, author_id, "contact") is not None,
        topup=cost,
        from_bought=from_bought,
    )


@router.callback_query(F.data.startswith(("pf:rep:", "pf:rr:", "pf:rback:")))
async def report_profile(call: CallbackQuery) -> None:
    """Two taps: «Пожаловаться» asks what for, the reason files the complaint."""
    parts = call.data.split(":")
    action = parts[1]
    author_id = int(parts[-1])

    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer(texts.t("PROFILE_GONE"), show_alert=True)
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
        await call.answer(texts.t("REPORT_DOUBLE_PROFILE"), show_alert=True)
        return

    if action == "rep":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.profile_report_reasons(author_id)
            )
        await call.answer(texts.t("REPORT_ASK"))
        return

    reason = parts[2] if parts[2] in texts.PROFILE_REPORT_REASONS else "other"
    count = await db.report_profile(call.from_user.id, author_id, reason)
    if count is None:  # two taps racing each other
        await call.answer(texts.t("REPORT_DOUBLE_PROFILE"), show_alert=True)
        return
    await call.answer(texts.t("REPORT_SENT"), show_alert=True)
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
    with lang.use("ru"):  # a moderator's card
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
    # Written while the buyer is being served, read by the seller.
    with lang.use(await db.lang_of(author_id)):
        note = texts.sale_note(kind, share)
    with suppress(TelegramAPIError):
        await bot.send_message(author_id, note)
