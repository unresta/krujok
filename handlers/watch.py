import logging
import time
from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import db
import keyboards as kb
import outbox
import people
import posts
import settings
import texts
import tiers
from config import ADMIN_CHAT_ID, ADMIN_IDS, WATCH_COOLDOWN

logger = logging.getLogger(__name__)

router = Router()

LOW_ALLOWANCE = 10  # circles left before the daily count is worth showing

_last_tap: dict[int, float] = {}


@router.message(F.text == kb.BTN_WATCH)
async def watch_button(message: Message, state: FSMContext) -> None:
    await state.clear()
    await serve(message.bot, message.from_user.id, message)


@router.callback_query(F.data == "watch")
async def watch_callback(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    now = time.monotonic()
    if now - _last_tap.get(call.from_user.id, 0.0) < WATCH_COOLDOWN:
        await call.answer(texts.NOT_SO_FAST)
        return
    _last_tap[call.from_user.id] = now

    await call.answer()
    # The buttons under a watched circle stay, but only the newest one works.
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(reply_markup=None)
    await serve(call.bot, call.from_user.id, call.message)


async def serve(bot, user_id: int, origin: Message, notice: bool = True) -> None:
    """Charge, send one circle, pay its author.

    `notice` is what tells a user the circle was on the house — true for the
    reminder's gift, false for the welcome one, where «последний бесплатный»
    would only confuse someone who still has their starting coins.
    """
    user = await db.get_user(user_id)
    cost = settings.get("watch_cost")


    circle = await db.pick_circle(
        user_id, user["pref"], settings.get("like_boost")
    )
    if circle is None:
        # Nothing left of this type is not a money problem: offer the switch the
        # text itself points at.
        await origin.answer(texts.EMPTY, reply_markup=kb.empty_feed(user["pref"]))
        return

    # Buying an author's profile makes their circles free for that viewer, then
    # a subscription, then a reminder's gift; coins are the last resort. The
    # gift comes after the subscription on purpose — it keeps for later instead
    # of being spent on a circle that was free anyway.
    tier = db.active_tier(user)
    limit = tiers.daily_views(tier)
    free = await db.has_content_access(user_id, circle["uploader_id"], circle["id"])
    on_subscription = not free and tier and await db.use_tier_view(user_id, limit)
    if tier and not free and not on_subscription:
        # A+ ran out its allowance for today. The feed still works, it just
        # costs again — and saying why is better than silently charging.
        with suppress(TelegramAPIError):
            await origin.answer(texts.tier_limit_hit(limit))

    on_the_house = (
        not free and not on_subscription and await db.use_free_view(user_id)
    )
    free = free or on_subscription or on_the_house
    if not free and not await db.try_spend(user_id, cost):  # raced with another tap
        await origin.answer(texts.not_enough(user["coins"]), reply_markup=kb.no_coins())
        return

    author = circle["uploader_id"]
    linked = author if author and await db.has_public_profile(author) else 0
    try:
        await bot.send_video_note(
            chat_id=user_id,
            video_note=circle["file_id"],
            # Forwarding and saving are what A++ and Premium are sold on;
            # for everyone else a circle stays inside the bot.
            protect_content=not tiers.savable(tier),
            reply_markup=kb.circle(
                circle["id"],
                circle["likes"],
                circle["dislikes"],
                0,
                linked,
                archive=not author,
            ),
        )
    except TelegramAPIError:
        if on_subscription:
            await db.refund_tier_view(user_id)  # a circle nobody got costs nothing
        elif on_the_house:
            # Give the free circle back without re-stamping the reminder: a
            # failed send must not push the next nudge a whole cooldown away.
            await db.grant_free_views(user_id, 1)
        elif not free:
            await db.add_coins(user_id, cost)  # nothing delivered, nothing charged
        await origin.answer(texts.SEND_FAILED)
        return

    await db.mark_viewed(user_id, circle["id"])
    if on_the_house and notice:
        # A gifted circle looks exactly like a paid one; without this line the
        # reminder's promise of free views is invisible.
        left = (await db.get_user(user_id))["free_views"]
        with suppress(TelegramAPIError):
            await origin.answer(texts.free_view_left(left))
    elif on_subscription and limit and notice:
        # A daily allowance is worth mentioning only as it runs out — a counter
        # under every one of a hundred circles is noise.
        left = db.tier_views_left(await db.get_user(user_id), limit)
        if left <= LOW_ALLOWANCE:
            with suppress(TelegramAPIError):
                await origin.answer(texts.tier_views_left(left))
    if not free:  # a free view was already paid for when the profile was bought
        await _pay_author(bot, circle, settings.get("view_payout"), texts.earned_toast)
    # The ad break comes after the circle it was earned by, never instead of it.
    await posts.after_circle(bot, user_id)


async def _pay_author(bot, circle, amount: int, note) -> None:
    author = circle["uploader_id"]
    if not author or not amount:
        return
    await db.pay_author(circle["id"], author, amount)
    with suppress(TelegramAPIError):  # author may have blocked the bot
        await bot.send_message(author, note(amount))


@router.callback_query(F.data == "arch")
async def archive_note(call: CallbackQuery) -> None:
    await call.answer(texts.ARCHIVE_NOTE, show_alert=True)


@router.callback_query(F.data.startswith("lk:"))
async def react(call: CallbackQuery) -> None:
    _, raw_id, raw_value = call.data.split(":")
    circle_id, value = int(raw_id), int(raw_value)

    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer(texts.CIRCLE_GONE, show_alert=True)
        return
    if circle["uploader_id"] == call.from_user.id:
        await call.answer(texts.CIRCLE_OWN_VOTE)
        return
    # A like pays the author, so it has to come from someone who was shown the
    # circle — not from a guessed callback.
    if not await db.has_viewed(call.from_user.id, circle_id):
        await call.answer(texts.CIRCLE_NOT_SHOWN, show_alert=True)
        return

    vote, likes, dislikes, fresh_like = await db.set_reaction(
        call.from_user.id, circle_id, value
    )
    author = circle["uploader_id"]
    linked = author if author and await db.has_public_profile(author) else 0
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=kb.circle(
                circle_id, likes, dislikes, vote, linked, archive=not author
            )
        )
    await call.answer(
        texts.VOTE_LIKE if vote == 1 else texts.VOTE_DISLIKE if vote == -1 else texts.VOTE_CANCEL
    )

    if fresh_like:
        await _pay_author(
            call.bot,
            circle,
            settings.get("like_bonus"),
            texts.like_bonus_note,
        )


async def _circle_markup(user_id: int, circle) -> InlineKeyboardMarkup:
    """The circle's own buttons, rebuilt after the reasons menu covered them."""
    author = circle["uploader_id"]
    linked = author if author and await db.has_public_profile(author) else 0
    return kb.circle(
        circle["id"],
        circle["likes"],
        circle["dislikes"],
        await db.get_reaction(user_id, circle["id"]),
        linked,
        archive=not author,
    )


@router.callback_query(F.data.startswith("rep:"))
async def report(call: CallbackQuery) -> None:
    """Two taps: «Пожаловаться» asks what for, the reason files the complaint."""
    parts = call.data.split(":")
    action = "" if parts[1].isdigit() else parts[1]
    circle_id = int(parts[-1])

    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer(texts.CIRCLE_GONE, show_alert=True)
        return

    if action == "back":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=await _circle_markup(call.from_user.id, circle)
            )
        await call.answer()
        return

    if not await db.has_viewed(call.from_user.id, circle_id):
        await call.answer(texts.CIRCLE_NOT_SHOWN, show_alert=True)
        return
    # Better to say so now than after they picked a reason for nothing.
    if await db.has_reported(call.from_user.id, circle_id):
        await call.answer(texts.REPORT_DOUBLE, show_alert=True)
        return

    if action != "r":
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.report_reasons(circle_id)
            )
        await call.answer(texts.REPORT_ASK)
        return

    reason = parts[2] if parts[2] in texts.REPORT_REASONS else "other"
    count = await db.add_report(call.from_user.id, circle_id, reason)
    if count is None:  # two taps racing each other
        await call.answer(texts.REPORT_DOUBLE, show_alert=True)
        return
    await call.answer(texts.REPORT_SENT, show_alert=True)
    with suppress(TelegramAPIError):
        await call.message.edit_reply_markup(
            reply_markup=await _circle_markup(call.from_user.id, circle)
        )

    # Enough complaints and the circle leaves rotation before a human looks.
    hidden = count >= settings.get("reports_to_hide")
    if hidden and circle["status"] == "approved":
        await db.set_status(circle_id, "rejected", texts.REASON_REPORTS)

    breakdown = texts.reasons_summary(
        await db.report_reasons(circle_id), texts.REPORT_REASONS
    )
    chat = settings.reports_chat()
    card_text = (
        f"#жалоба на <b>#{circle_id}</b> — {count} шт\n"
        f"Причина: {texts.REPORT_REASONS[reason]}\n"
        f"Тип: {kb.PREF_TITLE(circle['gender'])} · {circle['duration']} сек\n"
        f"Автор: {await people.of(circle['uploader_id'])}\n"
        f"Статус: {'скрыт автоматически' if hidden else circle['status']}\n\n"
        f"{breakdown}"
    )

    async def deliver() -> None:
        # The complaint is already in the base; only the card failed to land.
        await outbox.call(
            chat,
            lambda: call.bot.send_video_note(
                chat, circle["file_id"], protect_content=True
            ),
            f"кружок по жалобе #{circle_id}",
        )
        await outbox.call(
            chat,
            lambda: call.bot.send_message(
                chat, card_text, reply_markup=kb.report_review(circle_id)
            ),
            f"жалоба на #{circle_id}",
        )

    outbox.post(chat, deliver, f"жалоба на #{circle_id}")


@router.callback_query(F.data.startswith("rp:"))
async def review_report(call: CallbackQuery) -> None:
    # The verdict buttons live in a group chat, so anyone could otherwise guess
    # the callback data and delete circles from their own chat with the bot.
    if not (
        call.from_user.id in ADMIN_IDS
        or str(call.message.chat.id) == str(settings.reports_chat())
        or call.message.chat.id == ADMIN_CHAT_ID
    ):
        await call.answer("Нет прав.", show_alert=True)
        return

    _, action, raw_id = call.data.split(":")
    circle_id = int(raw_id)
    circle = await db.get_circle(circle_id)

    if action == "again":  # hiding and keeping are both reversible
        if circle is None:
            await call.answer(texts.CIRCLE_GONE, show_alert=True)
            return
        with suppress(TelegramAPIError):
            await call.message.edit_reply_markup(
                reply_markup=kb.report_review(circle_id)
            )
        await call.answer("Решай заново")
        return

    await db.clear_reports(circle_id)
    author = circle["uploader_id"] if circle else 0
    note = ""

    if action == "del":
        note = texts.CIRCLE_REMOVED
        await db.delete_circle(circle_id)
        verdict = "🔴 удалён"
    elif action == "hide":
        if circle:
            await db.set_status(circle_id, "rejected", texts.REASON_REPORTS)
            note = texts.CIRCLE_HIDDEN
        verdict = "🚫 скрыт"
    else:
        if circle:
            # Only worth telling the author when the circle was actually off.
            if circle["status"] != "approved":
                note = texts.CIRCLE_RESTORED
            await db.set_status(circle_id, "approved")
        verdict = "🟢 оставлен"

    if author and note:
        with suppress(TelegramAPIError):
            await call.bot.send_message(author, note)

    with suppress(TelegramAPIError):
        await call.message.edit_text(
            f"{_card_body(call.message.html_text)}\n\n<b>{verdict}</b>",
            # A deleted circle has nothing left to change one's mind about.
            reply_markup=None if action == "del" else kb.report_decided(circle_id),
        )
    await call.answer(verdict)


def _card_body(html_text: str) -> str:
    """Re-deciding edits the same card, so verdict lines must not stack up."""
    for mark in ("\n\n<b>🟢", "\n\n<b>🔴", "\n\n<b>🚫"):
        html_text = html_text.split(mark)[0]
    return html_text.rstrip()
