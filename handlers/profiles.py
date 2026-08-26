"""Author profiles: the shop window and everything sold through it.

A profile is filled in once, moderated like a circle, and then shown to other
users. Two things are for sale — access to the author's circles as they stand at
the moment of purchase, and, if the author opted in, their @username.
"""

import logging
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import keyboards as kb
import settings
import texts
from config import ABOUT_MAX, ADMIN_CHAT_ID, ADMIN_IDS

logger = logging.getLogger(__name__)

router = Router()


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
    if profile is None:
        await message.answer(texts.PROFILE_NONE_YET, reply_markup=kb.my_profile(False))
        return
    await message.answer_photo(
        profile["photo_id"],
        caption=texts.profile_status(profile),
        reply_markup=kb.my_profile(True),
    )


@router.callback_query(F.data == "pf:edit")
async def edit_profile(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Anketa.photo)
    await call.message.answer(texts.PROFILE_PHOTO, reply_markup=kb.back())
    await call.answer()


@router.message(Anketa.photo, F.photo)
async def got_photo(message: Message, state: FSMContext) -> None:
    await state.update_data(photo_id=message.photo[-1].file_id)
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
    await state.update_data(about=about)
    await state.set_state(Anketa.gender)
    await message.answer(texts.PROFILE_GENDER, reply_markup=kb.profile_gender())


@router.callback_query(Anketa.gender, F.data.startswith("pg:"))
async def got_gender(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(gender=call.data.split(":")[1])
    await state.set_state(Anketa.price_content)
    await call.message.edit_text(texts.profile_price_content())
    await call.answer()


@router.message(Anketa.price_content, ~F.text.in_(kb.MENU_BUTTONS))
async def got_price_content(message: Message, state: FSMContext) -> None:
    price = _price(message.text)
    if price is None:
        await message.answer(texts.profile_bad_price(), reply_markup=kb.back())
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
    wants = call.data.split(":")[1] == "yes" and bool(call.from_user.username)
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

    await db.save_profile(
        user_id=author.id,
        photo_id=data["photo_id"],
        about=data.get("about", ""),
        gender=data["gender"],
        price_content=data["price_content"],
        price_contact=data.get("price_contact", 0),
        contact_ok=data.get("contact_ok", False),
        username=author.username,
    )
    await message.answer(texts.PROFILE_SENT, reply_markup=kb.back())

    card = await message.bot.send_photo(
        ADMIN_CHAT_ID,
        data["photo_id"],
        caption=(
            f"#анкета от <code>{author.id}</code>"
            f"{' @' + author.username if author.username else ''}\n"
            f"Тип: {kb.PREF_TITLE(data['gender'])}\n"
            f"Кружочки: {data['price_content']} · "
            f"личка: {data.get('price_contact') or 'нет'}\n\n"
            f"{data.get('about') or 'Без описания'}"
        ),
        reply_markup=kb.profile_review(author.id),
    )
    await db.set_profile_admin_msg(author.id, card.message_id)


# --- moderation ----------------------------------------------------------


@router.callback_query(F.data.startswith("pm:"))
async def review(call: CallbackQuery) -> None:
    if not (call.from_user.id in ADMIN_IDS or call.message.chat.id == ADMIN_CHAT_ID):
        await call.answer("Нет прав.", show_alert=True)
        return

    _, verdict, raw_id = call.data.split(":")
    user_id = int(raw_id)

    if verdict in ("hide", "keep"):  # verdict on a complaint, not on a new profile
        status = "rejected" if verdict == "hide" else "approved"
        await db.set_profile_status(user_id, status)
        if verdict == "hide":
            with suppress(TelegramAPIError):
                await call.bot.send_message(user_id, texts.PROFILE_REJECTED)
        mark = "🔴 скрыта" if verdict == "hide" else "🟢 оставлена"
        with suppress(TelegramAPIError):
            await call.message.edit_caption(
                caption=f"{call.message.html_text}\n\n<b>{mark}</b>", reply_markup=None
            )
        await call.answer(mark)
        return

    status = "approved" if verdict == "ok" else "rejected"
    if not await db.review_profile(user_id, status):
        await call.answer("Уже обработана.", show_alert=True)
        return

    with suppress(TelegramAPIError):
        await call.bot.send_message(
            user_id,
            texts.PROFILE_APPROVED if status == "approved" else texts.PROFILE_REJECTED,
        )
    mark = "🟢 одобрена" if status == "approved" else "🔴 отклонена"
    with suppress(TelegramAPIError):
        await call.message.edit_caption(
            caption=f"{call.message.html_text}\n\n<b>{mark}</b>", reply_markup=None
        )
    await call.answer(mark)


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
        await origin.answer(texts.PROFILE_EMPTY, reply_markup=kb.back())
        return

    author = profile["user_id"]
    await db.mark_profile_seen(viewer_id, author)
    bought_content = await db.get_purchase(viewer_id, author, "content") is not None
    bought_contact = await db.get_purchase(viewer_id, author, "contact") is not None
    await bot.send_photo(
        chat_id=viewer_id,
        photo=profile["photo_id"],
        caption=texts.profile_card(profile, profile["circles"]),
        protect_content=True,
        reply_markup=kb.profile_card(profile, bought_content, bought_contact),
    )


@router.callback_query(F.data.startswith("pf:buy:"))
async def buy_content(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer("Анкета пропала.", show_alert=True)
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
    await call.message.answer(texts.bought_contact(profile["username"] or ""))
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
    author_id = int(call.data.split(":")[2])
    purchase = await db.get_purchase(call.from_user.id, author_id, "content")
    if purchase is None:
        await call.answer("Сначала купи доступ.", show_alert=True)
        return

    circles = await db.author_circles(author_id, purchase["max_circle_id"])
    if not circles:
        await call.answer("У автора пока нечего смотреть.", show_alert=True)
        return

    await call.answer(f"Отправляю {len(circles)}")
    for circle in circles:
        with suppress(TelegramAPIError):
            await call.bot.send_video_note(
                call.from_user.id, circle["file_id"], protect_content=True
            )


@router.callback_query(F.data.startswith("pf:rep:"))
async def report_profile(call: CallbackQuery) -> None:
    author_id = int(call.data.split(":")[2])
    profile = await db.get_profile(author_id)
    if profile is None:
        await call.answer("Анкета пропала.", show_alert=True)
        return

    await call.answer(texts.REPORT_SENT, show_alert=True)
    chat = settings.reports_chat()
    try:
        await call.bot.send_photo(
            chat,
            profile["photo_id"],
            caption=(
                f"#жалоба на анкету <code>{author_id}</code>\n"
                f"{profile['about'] or 'Без описания'}"
            ),
            reply_markup=kb.profile_report_review(author_id),
        )
    except TelegramAPIError as error:
        logger.error("profile report for %s not delivered: %s", author_id, error)


async def _notify_author(bot, author_id: int, kind: str, share: int) -> None:
    with suppress(TelegramAPIError):
        await bot.send_message(author_id, texts.sale_note(kind, share))
