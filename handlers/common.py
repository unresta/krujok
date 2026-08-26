from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import access
import db
import keyboards as kb
import texts
import ui

router = Router()

PREF_CYCLE = {"f": "m", "m": "any", "any": "f"}


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    # Getting here means the gate let the user through, so the inviter is due.
    await access.credit_referral(message.bot, message.from_user.id)
    await ui.render_menu(message, message.from_user.id)


@router.message(Command("menu", "cancel"))
async def menu_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()
    await ui.render_menu(message, message.from_user.id)


@router.callback_query(F.data == "menu")
async def menu_cb(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await ui.render_menu(call, call.from_user.id)
    await call.answer()


@router.callback_query(F.data.startswith("pref:"))
async def pref(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    choice = call.data.split(":", 1)[1]
    user = await db.get_user(call.from_user.id)
    pref_value = PREF_CYCLE[user["pref"]] if choice == "cycle" else choice
    await db.set_pref(call.from_user.id, pref_value)

    if choice == "cycle":
        # Called from the post-watch panel — keep that panel, just relabel it.
        await call.message.edit_reply_markup(reply_markup=kb.after_watch(pref_value))
    else:
        await ui.render_menu(call, call.from_user.id)
    await call.answer(kb.PREF_LABEL[pref_value])  # toast is plain text, no HTML


@router.callback_query(F.data == "profile")
async def profile(call: CallbackQuery) -> None:
    user = await db.get_user(call.from_user.id)
    stats = await db.user_stats(call.from_user.id)
    done, waiting = await db.referral_counts(call.from_user.id)
    link = access.referral_link(call.from_user.id)
    await ui.edit(
        call,
        texts.profile(user["coins"], stats, done, waiting, link),
        kb.profile(link),
    )
    await call.answer()
