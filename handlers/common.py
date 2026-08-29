from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import access
import db
import posts
from handlers import cheques, watch
import keyboards as kb
import settings
import texts
import ui

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    # Getting here means the gate let the user through, so the inviter is due.
    await access.credit_referral(message.bot, message.from_user.id)
    # …and a cheque they opened is now theirs to take: either straight from the
    # link, or the one that waited on their row while they were at the gate.
    payload = message.text.split(maxsplit=1)[1] if " " in (message.text or "") else ""
    kind, value = access.parse_start(payload)
    code = value if kind == "cheque" else await db.take_pending_cheque(
        message.from_user.id
    )
    if code:
        await cheques.redeem(message.bot, message.from_user.id, code, message)
    # A welcome post is shown before the menu and only ever once per person.
    await posts.show_welcome(message.bot, message.from_user.id)
    await ui.render_menu(message, message.from_user.id)


@router.callback_query(F.data == "accept")
async def accept(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    first_time = await db.accept_rules(call.from_user.id)
    await access.credit_referral(call.bot, call.from_user.id)
    await call.answer(texts.ACCEPTED)
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)

    bonus = settings.get("welcome_bonus")
    if first_time and bonus:  # granted once, on the flip from 0 to 1
        await db.add_coins(call.from_user.id, bonus)
        await call.message.answer(texts.welcome_bonus(bonus))

    await ui.render_menu(call.message, call.from_user.id)

    # The first circle comes on its own, and on the house — this is the first
    # moment the bot is allowed to show one, since the age was just confirmed.
    # It goes after the menu so the circle, with its own buttons, stays last.
    if first_time and settings.get("welcome_circle"):
        await db.grant_free_views(call.from_user.id, 1)
        await watch.serve(call.bot, call.from_user.id, call.message, notice=False)


@router.message(Command("menu", "cancel"))
async def menu_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await ui.render_menu(message, message.from_user.id)


@router.callback_query(F.data == "menu")
async def close_screen(call: CallbackQuery, state: FSMContext) -> None:
    """«Назад», «Закрыть», «Отмена» — the screen goes away, nothing replaces it.

    The main menu is a reply keyboard that is always on screen, so answering with
    another message would only add to the pile.
    """
    await state.clear()
    await call.answer()
    try:
        await call.message.delete()
    except TelegramAPIError:  # older than 48h, or already gone
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(reply_markup=None)


@router.message(F.text.startswith("/stat_"))
async def traffer_stats(message: Message) -> None:
    """Read-only report for whoever bought the ad; no money figures at all."""
    token = message.text.removeprefix("/stat_").strip().lower()
    code = await db.campaign_by_token(token)
    if code is None:
        await message.answer(texts.TRAFFER_UNKNOWN)
        return

    stats = await db.campaign_stats(code)
    week = await db.campaign_stats(code, 7 * 86400)
    day = await db.campaign_stats(code, 86400)
    await message.answer(
        texts.traffer_report(stats, week, day, access.campaign_link(code))
    )


# --- feed ----------------------------------------------------------------


@router.message(F.text == kb.BTN_FEED)
async def feed(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await db.get_user(message.from_user.id)
    await message.answer(texts.feed(user["pref"]), reply_markup=kb.feed(user["pref"]))


@router.callback_query(F.data.startswith("pref:"))
async def pref(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    choice = call.data.split(":", 1)[1]
    await db.set_pref(call.from_user.id, choice)
    await ui.edit(call, texts.feed(choice), kb.feed(choice))
    await call.answer(kb.PREF_LABEL[choice])  # toast is plain text, no HTML


# --- profile, referrals, rules -------------------------------------------


@router.message(F.text == kb.BTN_PROFILE)
async def profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    stats = await db.user_stats(user_id)
    earned, likes, dislikes, views = await db.author_earnings(user_id)
    done, _ = await db.referral_counts(user_id)
    sales = await db.sales_stats(user_id)
    available = await db.withdrawable(user_id)
    await message.answer(
        texts.profile(
            user_id,
            user["coins"],
            stats,
            earned,
            likes,
            dislikes,
            views,
            done,
            sales,
            available,
        ),
        reply_markup=kb.profile(access.referral_link(user_id)),
    )


@router.message(F.text == kb.BTN_REF)
async def referrals(message: Message, state: FSMContext) -> None:
    await state.clear()
    done, waiting = await db.referral_counts(message.from_user.id)
    link = access.referral_link(message.from_user.id)
    await message.answer(
        texts.referrals(done, waiting, link), reply_markup=kb.referrals(link)
    )


@router.message(F.text == kb.BTN_RULES)
async def rules(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.rules(), reply_markup=kb.rules())


@router.callback_query(F.data == "rules")
async def rules_cb(call: CallbackQuery) -> None:
    await ui.edit(call, texts.rules(), kb.rules())
    await call.answer()


@router.callback_query(F.data == "faq")
async def faq_cb(call: CallbackQuery) -> None:
    await ui.edit(call, texts.faq(), kb.faq())
    await call.answer()
