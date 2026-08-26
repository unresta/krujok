"""Admin panel: /admin opens one editable message with everything in it.

Every screen is a callback on the "a:" prefix and every one of them is gated on
ADMIN_IDS — the panel lives in the admin's private chat, not in the moderation
chat, so a leaked button id is not enough to use it.
"""

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import access
import db
import keyboards as kb
import settings
from config import ADMIN_IDS, DB_PATH

logger = logging.getLogger(__name__)

router = Router()
# The whole panel is admins-only; nothing here is reachable without the filter.
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

BROADCAST_PAUSE = 0.05  # ~20 messages per second, below Telegram's limit
BROADCAST_PROGRESS_EVERY = 25
BULK_EDIT_EVERY = 2.0  # seconds; Telegram rate-limits edits of one message
BULK_SETTLE = 1.5  # redraw this long after the last circle of a burst


class Admin(StatesGroup):
    bulk = State()
    user_id = State()
    give = State()
    broadcast = State()
    setting = State()
    circle_id = State()
    channel = State()
    reports_chat = State()
    profiles_chat = State()


# --- home ----------------------------------------------------------------


def home_kb(
    maintenance: bool, pending: int, reports: int, anketas: int, payouts: int
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="Статистика", callback_data="a:stats", style=kb.PRIMARY),
        InlineKeyboardButton(
            text=f"Очередь · {pending}",
            callback_data="a:queue",
            style=kb.SUCCESS if pending else None,
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="Массовая загрузка", callback_data="a:bulk", style=kb.SUCCESS
        )
    )
    b.row(
        InlineKeyboardButton(text="Пользователь", callback_data="a:user", style=kb.PRIMARY),
        InlineKeyboardButton(text="Кружок", callback_data="a:circle", style=kb.PRIMARY),
    )
    b.row(
        InlineKeyboardButton(text="Рассылка", callback_data="a:cast", style=kb.PRIMARY),
        InlineKeyboardButton(text="Экономика", callback_data="a:econ", style=kb.PRIMARY),
    )
    b.row(
        InlineKeyboardButton(text="Платежи", callback_data="a:pay", style=kb.PRIMARY),
        InlineKeyboardButton(text="Топ авторов", callback_data="a:top", style=kb.PRIMARY),
    )
    b.row(
        InlineKeyboardButton(
            text=f"Жалобы · {reports}",
            callback_data="a:reports",
            style=kb.DANGER if reports else None,
        ),
        InlineKeyboardButton(
            text=f"Анкеты · {anketas}",
            callback_data="a:anketas",
            style=kb.SUCCESS if anketas else None,
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=f"Выплаты · {payouts}",
            callback_data="a:payouts",
            style=kb.SUCCESS if payouts else None,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Подписка на канал", callback_data="a:chan", style=kb.PRIMARY
        )
    )
    b.row(
        InlineKeyboardButton(text="Бэкап базы", callback_data="a:db", style=kb.PRIMARY),
        InlineKeyboardButton(
            text="Техработы: вкл" if maintenance else "Техработы: выкл",
            callback_data="a:maint",
            style=kb.DANGER if maintenance else None,
        ),
    )
    b.row(InlineKeyboardButton(text="Закрыть", callback_data="a:close", style=kb.DANGER))
    return b.as_markup()


def back_kb(extra: list[InlineKeyboardButton] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for button in extra or []:
        b.row(button)
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    return b.as_markup()


async def home_text() -> str:
    d = await db.dashboard()
    return (
        "<b>Админ-панель</b>\n\n"
        f"👤 {d['users']} польз. (+{d['users_today']} за сутки), "
        f"бан: {d['banned']}\n"
        f"🎞 {d['approved']} в базе · {d['pending']} ждут · {d['rejected']} отказ\n"
        f"👀 {d['views']} просмотров (+{d['views_today']} за сутки)\n"
        f"⭐ {d['stars']} звёзд · 🪙 {d['coins']} на руках"
    )


async def show_home(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    d = await db.dashboard()
    await _edit(call, await home_text(), home_kb(
            settings.maintenance(),
            d["pending"],
            await db.open_reports(),
            await db.pending_profiles(),
            (await db.payout_totals())["open"],
        ))


@router.message(Command("admin"))
async def open_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    d = await db.dashboard()
    await message.answer(
        await home_text(), reply_markup=home_kb(
            settings.maintenance(),
            d["pending"],
            await db.open_reports(),
            await db.pending_profiles(),
            (await db.payout_totals())["open"],
        )
    )


async def _edit(call: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    with suppress(TelegramBadRequest):
        await call.message.edit_text(text, reply_markup=markup)


@router.callback_query(F.data == "a:home")
async def cb_home(call: CallbackQuery, state: FSMContext) -> None:
    await show_home(call, state)
    await call.answer()


@router.callback_query(F.data == "a:close")
async def cb_close(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    with suppress(TelegramAPIError):
        await call.message.delete()
    await call.answer()


# --- stats ---------------------------------------------------------------


@router.callback_query(F.data == "a:stats")
async def cb_stats(call: CallbackQuery) -> None:
    d = await db.dashboard()
    invited, confirmed = await db.referral_totals()
    house = d["circles"] - d["approved"] - d["pending"] - d["rejected"]
    await _edit(
        call,
        "<b>Статистика</b>\n\n"
        f"Пользователи: {d['users']} (за сутки +{d['users_today']}, "
        f"забанено {d['banned']})\n"
        f"Монеток на руках: {d['coins']}\n\n"
        f"Кружки: {d['circles']} всего "
        f"(из них залито админом: {await db.house_circles()})\n"
        f"• одобрено {d['approved']} — ♀ {d['female']} / ♂ {d['male']}\n"
        f"• на проверке {d['pending']}, отклонено {d['rejected']}"
        + (f", прочее {house}\n" if house else "\n")
        + f"\nПросмотры: {d['views']} (за сутки +{d['views_today']})\n"
        f"Платежи: {d['payments']} шт, {d['stars']} ⭐\n"
        f"Рефералы: {confirmed} подтверждено из {invited}",
        back_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "a:top")
async def cb_top(call: CallbackQuery) -> None:
    rows = await db.top_uploaders()
    if not rows:
        body = "Пока никто ничего не загрузил."
    else:
        body = "\n".join(
            f"{i}. <code>{r['uploader_id']}</code> — "
            f"{r['approved']} одобрено из {r['total']}"
            for i, r in enumerate(rows, 1)
        )
    await _edit(call, f"<b>Топ авторов</b>\n\n{body}", back_kb())
    await call.answer()


# --- forced subscription -------------------------------------------------


@router.callback_query(F.data == "a:chan")
async def cb_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    channel = settings.get_text("channel").strip()
    invited, confirmed = await db.referral_totals()

    if channel:
        status = await _channel_status(call.bot, channel)
        body = f"Канал: <code>{channel}</code>\n{status}"
    else:
        body = "Подписка выключена — бот пускает всех."

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Изменить канал", callback_data="a:chan:set", style=kb.PRIMARY
        )
    )
    if channel:
        b.row(
            InlineKeyboardButton(
                text="Выключить подписку", callback_data="a:chan:off", style=kb.DANGER
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    await _edit(
        call,
        f"<b>Обязательная подписка</b>\n\n{body}\n\n"
        f"👥 Рефералы: {confirmed} подтверждено из {invited} приглашённых, "
        f"по {settings.get('ref_reward')} монеток за каждого "
        "(меняется в «Экономике»).",
        b.as_markup(),
    )
    await call.answer()


async def _channel_status(bot: Bot, channel: str) -> str:
    """The gate is only real if the bot can see the member list."""
    try:
        me = await bot.get_chat_member(channel, (await bot.me()).id)
    except TelegramAPIError as error:
        return f"🔴 Бот не видит канал: {error}\nПодписка не проверяется."
    if me.status not in {"administrator", "creator"}:
        return "🔴 Бот не админ канала — проверить подписку он не сможет."
    return "🟢 Бот админ канала, подписка проверяется."


@router.message(Command("gate"))
async def gate_cmd(message: Message) -> None:
    """Why the gate is or is not stopping anyone, without any of the shortcuts."""
    channel = settings.get_text("channel").strip()
    if not channel:
        await message.answer(
            "Канал не задан — подписка выключена, бот пускает всех.\n"
            "Задать: /admin → «Подписка на канал»."
        )
        return

    lines = [f"Канал: <code>{channel}</code>", await _channel_status(message.bot, channel)]
    try:
        member = await message.bot.get_chat_member(channel, message.from_user.id)
        lines.append(f"Твой статус в канале: <code>{member.status}</code>")
    except TelegramAPIError as error:
        lines.append(f"🔴 Проверить тебя не вышло: {error}")
    lines.append(
        "⚠️ Ты в ADMIN_IDS — тебя гейт пропускает всегда, "
        "проверяй на обычном аккаунте."
    )
    await message.answer("\n".join(lines))


@router.callback_query(F.data == "a:chan:set")
async def cb_channel_set(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.channel)
    await _edit(
        call,
        "Пришли <code>@username</code> канала или его id вида "
        "<code>-100…</code>.\nБот должен быть админом там.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.channel, ~F.text.in_(kb.MENU_BUTTONS))
async def got_channel(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("https://t.me/"):
        raw = "@" + raw.removeprefix("https://t.me/").strip("/")
    if not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен @username или числовой id.")
        return

    await state.clear()
    await settings.set_text("channel", raw)
    access.drop_link_cache()
    await message.answer(
        f"Канал: <code>{raw}</code>\n{await _channel_status(message.bot, raw)}",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == "a:chan:off")
async def cb_channel_off(call: CallbackQuery, state: FSMContext) -> None:
    await settings.set_text("channel", "")
    access.drop_link_cache()
    await call.answer("Подписка выключена")
    await cb_channel(call, state)


@router.callback_query(F.data == "a:reports")
async def cb_reports(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.reported_circles()
    chat = settings.reports_chat()
    status = await _chat_status(call.bot, chat)

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Чат жалоб", callback_data="a:reports:chat", style=kb.PRIMARY
        )
    )
    if rows:
        b.row(
            InlineKeyboardButton(
                text=f"Показать {min(len(rows), 5)}",
                callback_data="a:reports:show",
                style=kb.DANGER,
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    await _edit(
        call,
        f"<b>Жалобы</b>\n\nЧат: <code>{chat}</code>\n{status}\n\n"
        f"Открытых жалоб: {len(rows)}",
        b.as_markup(),
    )
    await call.answer()


async def _chat_status(bot: Bot, chat: int | str) -> str:
    try:
        member = await bot.get_chat_member(chat, (await bot.me()).id)
    except TelegramAPIError as error:
        return f"🔴 Бот не может писать туда: {error}"
    if member.status not in {"administrator", "creator", "member"}:
        return "🔴 Бот не состоит в чате."
    return "🟢 Бот на месте, карточки жалоб дойдут."


@router.callback_query(F.data == "a:reports:chat")
async def cb_reports_chat(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.reports_chat)
    await _edit(
        call,
        "Пришли id чата жалоб (<code>-100…</code>) или <code>@username</code>.\n"
        "Бот должен быть в этом чате. Пустая строка — вернуть жалобы в "
        "чат модерации: пришли <code>-</code>.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.reports_chat, ~F.text.in_(kb.MENU_BUTTONS))
async def got_reports_chat(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    elif not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен id, @username или «-».")
        return

    await state.clear()
    await settings.set_text("reports_chat", raw)
    chat = settings.reports_chat()
    await message.answer(
        f"Чат жалоб: <code>{chat}</code>\n{await _chat_status(message.bot, chat)}",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == "a:reports:show")
async def cb_reports_show(call: CallbackQuery) -> None:
    rows = await db.reported_circles()
    if not rows:
        await call.answer("Жалоб нет 🟢", show_alert=True)
        return

    for circle in rows[:5]:  # a screenful, the rest stay in the queue
        with suppress(TelegramAPIError):
            await call.bot.send_video_note(call.from_user.id, circle["file_id"])
            await call.bot.send_message(
                call.from_user.id,
                f"#жалоба <b>#{circle['id']}</b> — {circle['complaints']} шт\n"
                f"Статус: {circle['status']} · просмотров: {circle['views']} · "
                f"👍 {circle['likes']} / 👎 {circle['dislikes']}\n"
                f"Автор: <code>{circle['uploader_id']}</code>",
                reply_markup=kb.report_review(circle["id"]),
            )
    await call.answer()


@router.callback_query(F.data == "a:anketas")
async def cb_anketas(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chat = settings.profiles_chat()
    waiting = await db.pending_profiles()

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Чат анкет", callback_data="a:anketas:chat", style=kb.PRIMARY
        )
    )
    if waiting:
        b.row(
            InlineKeyboardButton(
                text="Показать следующую",
                callback_data="a:anketas:next",
                style=kb.SUCCESS,
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    await _edit(
        call,
        f"<b>Анкеты</b>\n\nЧат: <code>{chat}</code>\n"
        f"{await _chat_status(call.bot, chat)}\n\n"
        f"На проверке: {waiting}",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:anketas:chat")
async def cb_anketas_chat(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.profiles_chat)
    await _edit(
        call,
        "Пришли id чата для анкет (<code>-100…</code>) или <code>@username</code>.\n"
        "Бот должен быть в этом чате. <code>-</code> — вернуть анкеты в чат "
        "модерации.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.profiles_chat, ~F.text.in_(kb.MENU_BUTTONS))
async def got_profiles_chat(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    elif not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен id, @username или «-».")
        return

    await state.clear()
    await settings.set_text("profiles_chat", raw)
    chat = settings.profiles_chat()
    await message.answer(
        f"Чат анкет: <code>{chat}</code>\n{await _chat_status(message.bot, chat)}",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == "a:anketas:next")
async def cb_anketas_next(call: CallbackQuery) -> None:
    profile = await db.next_pending_profile()
    if profile is None:
        await call.answer("Анкет на проверке нет 🟢", show_alert=True)
        return

    await call.bot.send_photo(
        call.from_user.id,
        profile["photo_id"],
        caption=(
            f"#анкета от <code>{profile['user_id']}</code>"
            f"{' @' + profile['username'] if profile['username'] else ''}\n"
            f"Кто: {kb.PERSON_TITLE(profile['gender'])}\n"
            f"Кружочки: {profile['price_content']} · "
            f"личка: {profile['price_contact'] or 'нет'}\n\n"
            f"{profile['about'] or 'Без описания'}"
        ),
        reply_markup=kb.profile_review(profile["user_id"]),
    )
    await call.answer()


@router.callback_query(F.data == "a:payouts")
async def cb_payouts(call: CallbackQuery) -> None:
    totals = await db.payout_totals()
    rows = await db.open_payouts()
    if not rows:
        await _edit(
            call,
            "<b>Выплаты</b>\n\nОткрытых заявок нет.\n"
            f"Выплачено за всё время: {totals['paid_stars']} ⭐",
            back_kb(),
        )
        await call.answer()
        return

    await _edit(
        call,
        f"<b>Выплаты</b>\n\nОткрыто: {totals['open']} заявок на "
        f"{totals['open_coins']} монеток\n"
        f"Выплачено за всё время: {totals['paid_stars']} ⭐\n\n"
        "Карточки ниже.",
        back_kb(),
    )
    for payout in rows:
        with suppress(TelegramAPIError):
            await call.bot.send_message(
                call.from_user.id,
                f"#выплата <b>#{payout['id']}</b>\n"
                f"{payout['coins']} монеток → <b>{payout['stars']} ⭐</b>\n"
                f"Кому: <code>{payout['user_id']}</code>\n"
                f"Реквизиты: <code>{payout['details']}</code>",
                reply_markup=kb.payout_review(payout["id"]),
            )
    await call.answer()


# --- moderation queue ----------------------------------------------------


@router.callback_query(F.data == "a:queue")
async def cb_queue(call: CallbackQuery) -> None:
    circle = await db.next_pending()
    if circle is None:
        await call.answer("Очередь пуста 🟢", show_alert=True)
        return

    await call.bot.send_video_note(call.from_user.id, circle["file_id"])
    await call.bot.send_message(
        call.from_user.id,
        f"<b>#{circle['id']}</b> · {kb.PREF_TITLE(circle['gender'])} · "
        f"{circle['duration']} сек\n"
        f"Автор: <code>{circle['uploader_id']}</code>",
        reply_markup=kb.moderation(circle["id"]),
    )
    await call.answer()


# --- bulk upload ---------------------------------------------------------


def bulk_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="♀ Женские", callback_data="a:bulk:f", style=kb.SUCCESS
        ),
        InlineKeyboardButton(
            text="♂ Мужские", callback_data="a:bulk:m", style=kb.SUCCESS
        ),
    )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    return b.as_markup()


@router.callback_query(F.data == "a:bulk")
async def cb_bulk(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(
        call,
        "<b>Массовая загрузка</b>\n\n"
        "Выбери тип — дальше просто шли кружочки подряд, каждый уходит в базу "
        "сразу одобренным, без модерации и без начисления монеток.",
        bulk_kb(),
    )
    await call.answer()


class BulkSession:
    """Counters for one bulk run.

    They cannot live in FSM state: aiogram handles updates concurrently, so a
    read-modify-write of state data loses increments under a flood of circles.
    One lock per session serialises both the counting and the inserts, and the
    added count is taken from the table rather than from arithmetic.
    """

    def __init__(self, gender: str, panel_chat: int, panel_id: int, start: int):
        self.gender = gender
        self.panel_chat = panel_chat
        self.panel_id = panel_id
        self.start_total = start
        self.received = 0
        self.added = 0
        self.lock = asyncio.Lock()
        self.last_edit = 0.0
        self.settle: asyncio.Task | None = None


_sessions: dict[int, BulkSession] = {}


@router.callback_query(F.data.startswith("a:bulk:"))
async def cb_bulk_gender(call: CallbackQuery, state: FSMContext) -> None:
    gender = call.data.split(":")[2]
    if gender == "done":
        await cb_bulk_done(call, state)
        return

    await state.set_state(Admin.bulk)
    _sessions[call.from_user.id] = BulkSession(
        gender=gender,
        panel_chat=call.message.chat.id,
        panel_id=call.message.message_id,
        start=await db.total_circles(),
    )
    await _edit(call, _bulk_text(gender, 0, 0), _bulk_done_kb())
    with suppress(TelegramAPIError):  # keeps «Готово» one tap away under a flood
        await call.bot.pin_chat_message(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            disable_notification=True,
        )
    await call.answer()


def _bulk_done_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Готово", callback_data="a:bulk:done", style=kb.DANGER
        )
    )
    return b.as_markup()


def _bulk_text(gender: str, added: int, dupes: int) -> str:
    return (
        f"<b>Массовая загрузка · {kb.PREF_TITLE(gender)}</b>\n\n"
        f"Загружено: <b>{added}</b>\n"
        f"Пропущено дублей: {dupes}\n\n"
        "Шли кружочки подряд. «Готово» — закончить."
    )


@router.message(Admin.bulk, F.video_note)
async def bulk_receive(message: Message, state: FSMContext) -> None:
    session = _sessions.get(message.from_user.id)
    if session is None:  # bot restarted mid-run
        await state.clear()
        await message.answer("Сессия загрузки потерялась, открой /admin заново.")
        return

    note = message.video_note
    async with session.lock:
        circle_id = await db.add_circle(
            file_id=note.file_id,
            file_unique_id=note.file_unique_id,
            uploader_id=0,  # house-owned
            gender=session.gender,
            duration=note.duration,
            status="approved",
        )
        session.received += 1
        session.added = await db.total_circles() - session.start_total
        original = None
        if circle_id is None:
            original = await db.circle_by_unique(note.file_unique_id)
            logger.info("bulk: duplicate %s skipped", note.file_unique_id)

        now = asyncio.get_running_loop().time()
        stale = now - session.last_edit > BULK_EDIT_EVERY
        if stale:  # Telegram rate-limits edits, so the panel refreshes on a timer
            session.last_edit = now

    if stale:
        await _bulk_refresh(message.bot, session)
    _schedule_settle(message.bot, session)  # a flood can outrun every timed edit
    with suppress(TelegramAPIError):  # a tick per circle, so the flood stays readable
        await message.react([ReactionTypeEmoji(emoji="👍" if circle_id else "🤔")])
    if circle_id is None:  # marked on the message itself, findable after the run
        with suppress(TelegramAPIError):
            await message.reply(
                f"🤔 Дубль — уже в базе как <b>#{original['id']}</b>"
                if original
                else "🤔 Дубль — такой кружок уже есть."
            )


def _schedule_settle(bot: Bot, session: BulkSession) -> None:
    """Redraw once the circles stop coming, so the last number is never stale."""
    if session.settle is not None:
        session.settle.cancel()
    session.settle = asyncio.create_task(_settle(bot, session))


async def _settle(bot: Bot, session: BulkSession) -> None:
    with suppress(asyncio.CancelledError):
        await asyncio.sleep(BULK_SETTLE)
        async with session.lock:
            session.added = await db.total_circles() - session.start_total
            session.last_edit = asyncio.get_running_loop().time()
        await _bulk_refresh(bot, session)


async def _bulk_refresh(bot: Bot, session: BulkSession) -> None:
    with suppress(TelegramAPIError):
        await bot.edit_message_text(
            chat_id=session.panel_chat,
            message_id=session.panel_id,
            text=_bulk_text(
                session.gender, session.added, session.received - session.added
            ),
            reply_markup=_bulk_done_kb(),
        )


@router.callback_query(F.data == "a:bulk:done")
async def cb_bulk_done(call: CallbackQuery, state: FSMContext) -> None:
    session = _sessions.pop(call.from_user.id, None)
    await state.clear()
    if session is not None and session.settle is not None:
        session.settle.cancel()
    if session is None:
        await show_home(call, state)
        await call.answer()
        return

    async with session.lock:  # let the last circles land before counting
        session.added = await db.total_circles() - session.start_total
    total = await db.total_circles()
    with suppress(TelegramAPIError):
        await call.bot.unpin_chat_message(
            chat_id=session.panel_chat, message_id=session.panel_id
        )
    await _edit(
        call,
        f"<b>Загрузка закончена</b>\n\n"
        f"Прислано: {session.received}\n"
        f"Добавлено: <b>{session.added}</b>\n"
        f"Дублей пропущено: {session.received - session.added}\n\n"
        f"Всего в базе: {total}",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.bulk, ~F.text.in_(kb.MENU_BUTTONS))
async def bulk_other(message: Message) -> None:
    await message.answer("Жду кружочки. «Готово» в панели — закончить.")


# --- user card -----------------------------------------------------------


@router.callback_query(F.data == "a:user")
async def cb_user(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.user_id)
    await _edit(
        call,
        "Пришли id пользователя числом — или перешли сюда его сообщение.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.user_id, ~F.text.in_(kb.MENU_BUTTONS))
async def got_user_id(message: Message, state: FSMContext) -> None:
    origin = message.forward_origin
    sender = getattr(origin, "sender_user", None)
    raw = (message.text or "").strip()
    if sender is not None:
        user_id = sender.id
    elif raw.lstrip("-").isdigit():
        user_id = int(raw)
    else:
        await message.answer(
            "Нужен id числом или пересланное сообщение "
            "(у скрытых аккаунтов id не видно)."
        )
        return

    await state.clear()
    text, markup = await user_card(user_id)
    await message.answer(text, reply_markup=markup)


async def user_card(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await db.get_user(user_id)
    stats = await db.user_stats(user_id)
    ref_done, ref_wait = await db.referral_counts(user_id)
    sales = await db.sales_stats(user_id)
    available = await db.withdrawable(user_id)
    text = (
        f"<b>Пользователь</b> <code>{user_id}</code>\n\n"
        f"🪙 Баланс: <b>{user['coins']}</b>\n"
        f"Тип: {kb.PREF_TITLE(user['pref'])}\n"
        f"Статус: {'🔴 забанен' if user['banned'] else '🟢 активен'}\n\n"
        f"👀 Просмотрено: {stats['watched']}\n"
        f"📤 Загружено: {stats['approved']} одобрено · {stats['pending']} ждут · "
        f"{stats['rejected']} отказ\n"
        f"👥 Пригласил: {ref_done}"
        + (f" (ждут подписки: {ref_wait})" if ref_wait else "")
        + (f"\nПришёл от: <code>{user['ref_by']}</code>" if user["ref_by"] else "")
        + f"\n💰 Продажи: {sales['content']} контент · {sales['contact']} личка "
        f"(+{sales['income']} 🪙)"
        + f"\n💸 Заработано {user['earned']}, к выводу {available}"
    )
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="+10 🪙", callback_data=f"a:u:add:{user_id}:10", style=kb.SUCCESS
        ),
        InlineKeyboardButton(
            text="+50 🪙", callback_data=f"a:u:add:{user_id}:50", style=kb.SUCCESS
        ),
        InlineKeyboardButton(
            text="−10 🪙", callback_data=f"a:u:add:{user_id}:-10", style=kb.DANGER
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="Своя сумма", callback_data=f"a:u:give:{user_id}", style=kb.PRIMARY
        ),
        InlineKeyboardButton(
            text="Разбанить" if user["banned"] else "Забанить",
            callback_data=f"a:u:ban:{user_id}:{0 if user['banned'] else 1}",
            style=kb.SUCCESS if user["banned"] else kb.DANGER,
        ),
    )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    return text, b.as_markup()


@router.callback_query(F.data.startswith("a:u:add:"))
async def cb_user_add(call: CallbackQuery) -> None:
    _, _, _, raw_id, raw_amount = call.data.split(":")
    await db.add_coins(int(raw_id), int(raw_amount))
    text, markup = await user_card(int(raw_id))
    await _edit(call, text, markup)
    await call.answer(f"{raw_amount} 🪙")


@router.callback_query(F.data.startswith("a:u:give:"))
async def cb_user_give(call: CallbackQuery, state: FSMContext) -> None:
    user_id = int(call.data.split(":")[3])
    await state.set_state(Admin.give)
    await state.update_data(user_id=user_id)
    await _edit(
        call, f"Сколько монеток начислить <code>{user_id}</code>? "
        "Можно отрицательное число.", back_kb()
    )
    await call.answer()


@router.message(Admin.give, ~F.text.in_(kb.MENU_BUTTONS))
async def got_give(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("Нужно число.")
        return
    user_id = (await state.get_data())["user_id"]
    await state.clear()
    await db.add_coins(user_id, int(raw))
    text, markup = await user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("a:u:ban:"))
async def cb_user_ban(call: CallbackQuery) -> None:
    _, _, _, raw_id, raw_flag = call.data.split(":")
    await db.set_banned(int(raw_id), bool(int(raw_flag)))
    text, markup = await user_card(int(raw_id))
    await _edit(call, text, markup)
    await call.answer("Забанен" if int(raw_flag) else "Разбанен")


# --- circle card ---------------------------------------------------------


@router.callback_query(F.data == "a:circle")
async def cb_circle(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.circle_id)
    total = await db.total_circles()
    await _edit(call, f"Пришли номер кружка (всего в базе: {total}).", back_kb())
    await call.answer()


@router.message(Admin.circle_id, ~F.text.in_(kb.MENU_BUTTONS))
async def got_circle_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").lstrip("#").strip()
    if not raw.isdigit():
        await message.answer("Нужен номер числом.")
        return
    await state.clear()

    circle = await db.get_circle(int(raw))
    if circle is None:
        await message.answer("Нет такого кружка.", reply_markup=back_kb())
        return

    await message.answer_video_note(circle["file_id"])
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Удалить", callback_data=f"a:c:del:{circle['id']}", style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.PRIMARY)
    )
    await message.answer(
        f"<b>#{circle['id']}</b> · {kb.PREF_TITLE(circle['gender'])} · "
        f"{circle['duration']} сек\n"
        f"Статус: {circle['status']} · просмотров: {circle['views']}\n"
        f"Автор: <code>{circle['uploader_id']}</code>",
        reply_markup=b.as_markup(),
    )


@router.message(Command("wipe_circles"))
async def wipe_cmd(message: Message) -> None:
    """Nukes the circle base. Two steps on purpose — there is no undo."""
    d = await db.dashboard()
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Да, удалить всё", callback_data="a:wipe:go", style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(text="Отмена", callback_data="a:home", style=kb.PRIMARY)
    )
    await message.answer(
        "<b>Удалить все кружочки?</b>\n\n"
        f"Под нож пойдут {d['circles']} кружков и {d['views']} просмотров, "
        "нумерация начнётся с #1.\n"
        "Балансы, платежи и пользователи останутся.\n\n"
        "Отменить будет нельзя.",
        reply_markup=b.as_markup(),
    )


@router.message(Command("wipe_house"))
async def wipe_house_cmd(message: Message) -> None:
    """Drops only the seed circles the admin bulk-loaded (uploader_id = 0)."""
    house = await db.house_circles()
    if not house:
        await message.answer("Загруженных админом кружков в базе нет.")
        return

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"Удалить {house}", callback_data="a:wipehouse:go", style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(text="Отмена", callback_data="a:home", style=kb.PRIMARY)
    )
    await message.answer(
        f"<b>Удалить кружочки, залитые админом?</b>\n\n"
        f"Под нож пойдут {house} шт — те, что попали в базу через «Массовую "
        "загрузку». Кружочки пользователей и всё остальное останутся.\n\n"
        "Отменить будет нельзя.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "a:wipehouse:go")
async def cb_wipe_house(call: CallbackQuery) -> None:
    total = await db.wipe_house_circles()
    logger.warning("house circles wiped by %s (%s)", call.from_user.id, total)
    await call.answer("Готово", show_alert=True)
    await _edit(call, f"Удалено кружочков дома: <b>{total}</b>.", back_kb())


@router.callback_query(F.data == "a:wipe:go")
async def cb_wipe(call: CallbackQuery) -> None:
    total = await db.wipe_circles()
    logger.warning("circle base wiped by %s (%s circles)", call.from_user.id, total)
    await call.answer("Готово", show_alert=True)
    await _edit(call, f"Удалено кружков: <b>{total}</b>. База пуста.", back_kb())


@router.callback_query(F.data.startswith("a:c:del:"))
async def cb_circle_delete(call: CallbackQuery) -> None:
    circle_id = int(call.data.split(":")[3])
    await db.clear_reports(circle_id)
    deleted = await db.delete_circle(circle_id)
    await call.answer("Удалён" if deleted else "Уже нет", show_alert=True)
    await _edit(call, f"Кружок #{circle_id} удалён.", back_kb())


# --- broadcast -----------------------------------------------------------


@router.callback_query(F.data == "a:cast")
async def cb_cast(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.broadcast)
    await _edit(
        call,
        "Пришли сообщение для рассылки — текст, фото, кружок, что угодно. "
        "Оно уйдёт копией, без пометки «переслано».",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.broadcast, ~F.text.in_(kb.MENU_BUTTONS))
async def got_cast(message: Message, state: FSMContext) -> None:
    await state.update_data(from_chat=message.chat.id, message_id=message.message_id)
    total = len(await db.all_user_ids())
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"Отправить {total}", callback_data="a:cast:go", style=kb.SUCCESS
        )
    )
    b.row(
        InlineKeyboardButton(text="Отмена", callback_data="a:home", style=kb.DANGER)
    )
    await message.answer(
        f"Выше — то, что уйдёт {total} пользователям. Отправляем?",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "a:cast:go")
async def cb_cast_go(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if "message_id" not in data:
        await call.answer("Нечего отправлять.", show_alert=True)
        return

    await call.answer("Пошла рассылка")
    await _edit(call, "Рассылка идёт…", back_kb())
    sent, failed = await _broadcast(
        call.bot, data["from_chat"], data["message_id"], call.message
    )
    await _edit(
        call,
        f"<b>Рассылка закончена</b>\n\nДоставлено: {sent}\nНе дошло: {failed}",
        back_kb(),
    )


async def _broadcast(
    bot: Bot, from_chat: int, message_id: int, panel: Message
) -> tuple[int, int]:
    user_ids = await db.all_user_ids()
    sent = failed = 0
    for i, user_id in enumerate(user_ids, 1):
        try:
            await bot.copy_message(
                chat_id=user_id, from_chat_id=from_chat, message_id=message_id
            )
            sent += 1
        except TelegramAPIError:  # blocked, deleted, never started the bot
            failed += 1
        if i % BROADCAST_PROGRESS_EVERY == 0:
            with suppress(TelegramAPIError):
                await panel.edit_text(
                    f"Рассылка: {i}/{len(user_ids)} · "
                    f"доставлено {sent}, не дошло {failed}"
                )
        await asyncio.sleep(BROADCAST_PAUSE)
    return sent, failed


# --- economy -------------------------------------------------------------


@router.callback_query(F.data == "a:econ")
async def cb_econ(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    b = InlineKeyboardBuilder()
    for key, title in settings.TITLES.items():
        b.row(
            InlineKeyboardButton(
                text=f"{title}: {settings.get(key)}",
                callback_data=f"a:econ:{key}",
                style=kb.PRIMARY,
            )
        )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.DANGER))
    await _edit(
        call,
        "<b>Экономика</b>\n\nЖми на параметр, чтобы поменять. "
        "Значения живут в базе и переживают перезапуск.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:econ:"))
async def cb_econ_key(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[2]
    low, high = settings.LIMITS[key]
    await state.set_state(Admin.setting)
    await state.update_data(key=key)
    await _edit(
        call,
        f"<b>{settings.TITLES[key]}</b>\nСейчас: {settings.get(key)}\n\n"
        f"Пришли новое значение ({low}–{high}).",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.setting, ~F.text.in_(kb.MENU_BUTTONS))
async def got_setting(message: Message, state: FSMContext) -> None:
    key = (await state.get_data())["key"]
    low, high = settings.LIMITS[key]
    raw = (message.text or "").strip()
    if not raw.isdigit() or not (low <= int(raw) <= high):
        await message.answer(f"Нужно число от {low} до {high}.")
        return
    await state.clear()
    await settings.set(key, int(raw))
    await message.answer(
        f"{settings.TITLES[key]}: <b>{settings.get(key)}</b>",
        reply_markup=back_kb(),
    )


# --- payments, backup, maintenance ---------------------------------------


@router.callback_query(F.data == "a:pay")
async def cb_pay(call: CallbackQuery) -> None:
    rows = await db.recent_payments()
    if not rows:
        body = "Платежей пока нет."
    else:
        body = "\n\n".join(
            f"<code>{r['user_id']}</code> — {r['stars']} ⭐ → {r['coins']} 🪙"
            f"{' · возвращён' if r['refunded'] else ''}\n"
            f"<code>{r['charge_id']}</code>"
            for r in rows
        )
    await _edit(
        call,
        f"<b>Последние платежи</b>\n\n{body}\n\n"
        "Возврат: <code>/refund charge_id</code>",
        back_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "a:db")
async def cb_db(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Прислать файл", callback_data="a:db:go", style=kb.DANGER
        )
    )
    b.row(InlineKeyboardButton(text="В панель", callback_data="a:home", style=kb.PRIMARY))
    await _edit(
        call,
        "<b>Бэкап базы</b>\n\nВ файле лежат балансы, платежи и file_id всех "
        "кружочков. Прислать его сюда?",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:db:go")
async def cb_db_go(call: CallbackQuery) -> None:
    await call.answer("Отправляю")
    try:
        await call.bot.send_document(
            call.from_user.id, FSInputFile(DB_PATH), disable_content_type_detection=True
        )
    except (TelegramAPIError, OSError) as error:
        await _edit(call, f"Не вышло: {error}", back_kb())
        return
    await _edit(call, "Файл отправлен.", back_kb())


@router.callback_query(F.data == "a:maint")
async def cb_maint(call: CallbackQuery, state: FSMContext) -> None:
    await settings.set("maintenance", 0 if settings.maintenance() else 1)
    await call.answer("Техработы включены" if settings.maintenance() else "Выключены")
    await show_home(call, state)


# --- commands (kept for muscle memory) -----------------------------------


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    d = await db.dashboard()
    await message.answer(
        f"👤 {d['users']} · 🎞 {d['approved']}/{d['pending']} · "
        f"👀 {d['views']} · ⭐ {d['stars']}"
    )


@router.message(Command("give"))
async def give_cmd(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[0].isdigit():
        await message.answer("/give &lt;user_id&gt; &lt;coins&gt;")
        return
    await db.add_coins(int(parts[0]), int(parts[1]))
    text, markup = await user_card(int(parts[0]))
    await message.answer(text, reply_markup=markup)


@router.message(Command("ban", "unban"))
async def ban_cmd(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip().isdigit():
        await message.answer(f"/{command.command} &lt;user_id&gt;")
        return
    user_id = int(command.args.strip())
    await db.set_banned(user_id, command.command == "ban")
    text, markup = await user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.message(Command("refund"))
async def refund_cmd(message: Message, command: CommandObject) -> None:
    """/refund <telegram_payment_charge_id> — returns Stars to the buyer."""
    charge_id = (command.args or "").strip()
    if not charge_id:
        await message.answer("/refund &lt;charge_id&gt;")
        return

    payment = await db.get_payment(charge_id)
    if payment is None:
        await message.answer("Платёж не найден.")
        return
    if payment["refunded"]:
        await message.answer("Уже возвращён.")
        return

    try:
        await message.bot.refund_star_payment(
            user_id=payment["user_id"], telegram_payment_charge_id=charge_id
        )
    except TelegramAPIError as error:
        await message.answer(f"Telegram отказал: {error}")
        return

    await db.mark_refunded(charge_id)
    await db.deduct_clamped(payment["user_id"], payment["coins"])
    with suppress(TelegramAPIError):
        await message.bot.send_message(
            payment["user_id"],
            f"⭐ Возврат {payment['stars']} — списал {payment['coins']} 🪙.",
        )
    await message.answer(f"Возвращено {payment['stars']} ⭐.")
