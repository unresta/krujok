"""Admin panel: /admin opens one editable message with everything in it.

Every screen is a callback on the "a:" prefix and every one of them is gated on
ADMIN_IDS — the panel lives in the admin's private chat, not in the moderation
chat, so a leaked button id is not enough to use it.
"""

import asyncio
import html
import logging
import time
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReactionTypeEmoji,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import access
import botstat
import config
import crypto
import db
import invoices
import posts
import pushes
from handlers import cheques
import keyboards as kb
import settings
import text_manager
import texts
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
    campaign = State()
    spend = State()
    delete_link = State()
    profiles_chat = State()
    circles_chat = State()
    content_edit = State()  # unified text + emoji editing
    crypto_asset = State()
    gate_bot = State()
    post = State()
    botman_folder = State()


# --- home ----------------------------------------------------------------


def home_kb(
    maintenance: bool,
    pending: int,
    reports: int,
    anketas: int,
    payouts: int,
    channels: int = 0,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()

    # Moderation section - только здесь используем цвета для важности
    b.row(
        InlineKeyboardButton(
            text=f"⚠️ Жалобы · {reports}",
            callback_data="a:reports",
            style=kb.DANGER if reports else None,
        ),
        InlineKeyboardButton(
            text=f"📋 Анкеты · {anketas}",
            callback_data="a:anketas",
            style=kb.SUCCESS if anketas else None,
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=f"🎬 Очередь · {pending}",
            callback_data="a:queue",
            style=kb.SUCCESS if pending else None,
        ),
        InlineKeyboardButton(
            text=f"💸 Выплаты · {payouts}",
            callback_data="a:payouts",
            style=kb.SUCCESS if payouts else None,
        ),
    )

    # Management section - без цветов
    b.row(
        InlineKeyboardButton(text="👤 Пользователь", callback_data="a:user"),
        InlineKeyboardButton(text="🎥 Кружок", callback_data="a:circle"),
    )
    b.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="a:cast"),
        InlineKeyboardButton(text="📦 Массовая загрузка", callback_data="a:bulk"),
    )
    b.row(
        InlineKeyboardButton(text="💰 Экономика", callback_data="a:econ"),
        InlineKeyboardButton(text="💳 Платежи", callback_data="a:pay"),
    )
    b.row(
        InlineKeyboardButton(text="💾 Бэкап базы", callback_data="a:db"),
        InlineKeyboardButton(text="🛡 BotStat", callback_data="a:botstat"),
    )

    # Traffic section — что продаётся рекламодателям
    b.row(
        InlineKeyboardButton(
            text=f"📢 Подписка · {channels}", callback_data="a:chan"
        ),
        InlineKeyboardButton(text="📰 Посты", callback_data="a:posts"),
    )
    b.row(
        InlineKeyboardButton(text="🔗 Ссылки", callback_data="a:links"),
        InlineKeyboardButton(text="🎟 Чеки", callback_data="a:cheques"),
    )
    b.row(
        InlineKeyboardButton(text="👥 Рефералы", callback_data="a:refs"),
        InlineKeyboardButton(text="🏆 Топ авторов", callback_data="a:top"),
    )
    b.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="a:stats"),
        InlineKeyboardButton(text="📝 Тексты", callback_data="a:content"),
    )

    b.row(
        InlineKeyboardButton(text="🔔 Напоминания", callback_data="a:push"),
        InlineKeyboardButton(
            text=f"🔧 Техработы: {'вкл' if maintenance else 'выкл'}",
            callback_data="a:maint",
            style=kb.DANGER if maintenance else None,
        ),
    )

    # Close button - DANGER только для закрытия
    b.row(InlineKeyboardButton(text="❌ Закрыть", callback_data="a:close", style=kb.DANGER))
    return b.as_markup()


def back_kb(extra: list[InlineKeyboardButton] | None = None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for button in extra or []:
        b.row(button)
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


async def home_text() -> str:
    d = await db.dashboard()
    todo = {
        "жалоб": await db.open_reports(),
        "анкет": await db.pending_profiles(),
        "кружков": d["pending"],
        "выплат": (await db.payout_totals())["open"],
    }
    waiting = ", ".join(f"{count} {what}" for what, count in todo.items() if count)
    # What needs a human comes first; the rest is background.
    head = f"🔔 <b>Ждут решения:</b> {waiting}" if waiting else "🟢 Разобрано, очередей нет"
    return (
        "⚙️ <b>Админ-панель</b>\n\n"
        f"{head}\n"
        + ("🔧 <b>Техработы включены</b>\n" if settings.maintenance() else "")
        + f"\n👤 {d['users']} польз. (+{d['users_today']} за сутки), "
        f"🚫 бан: {d['banned']}\n"
        f"🎞 {d['approved']} в базе · {d['pending']} ждут · {d['rejected']} отказ\n"
        f"👀 {d['views']} просмотров (+{d['views_today']} за сутки)\n"
        f"⭐ {d['stars']} звёзд · 🪙 {d['coins']} монет на руках"
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
            len(await db.channels(active_only=True)),
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
            len(await db.channels(active_only=True)),
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
        "📊 <b>Статистика</b>\n\n"
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
    await _edit(call, f"🏆 <b>Топ авторов</b>\n\n{body}", back_kb())
    await call.answer()# --- sponsor channels ----------------------------------------------------

# Several channels at once: this is the thing sold to advertisers, so each one
# is listed separately with what it actually brought in.


async def _channel_status(bot: Bot, chat: str, kind: str = "channel") -> str:
    """The gate is only real if the membership can actually be checked."""
    if kind == "bot":
        probe = await botstat.check_member(chat, (await bot.me()).id)
        return (
            "🔴 BotStat молчит — код не работает"
            if probe is None
            else "🟢 проверяется через BotMembers"
        )
    try:
        me = await bot.get_chat_member(chat, (await bot.me()).id)
    except TelegramAPIError as error:
        return f"🔴 не вижу канал: {error}"
    if me.status not in {"administrator", "creator"}:
        return "🔴 бот не админ — подписку не проверить"
    return "🟢 проверяется"


def _channels_kb(rows: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="➕ Добавить канал", callback_data="a:chan:add", style=kb.SUCCESS
        )
    )
    for row in rows:
        mark = "🟢" if row["active"] else "⚪"
        icon = "🤖" if row["kind"] == "bot" else "📢"
        title = row["title"] or row["chat"]
        b.row(
            InlineKeyboardButton(
                text=f"{mark}{icon} {title[:22]} · {row['joined']}",
                callback_data=f"a:chan:{row['id']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


@router.callback_query(F.data == "a:chan")
async def cb_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.channels()
    active = [r for r in rows if r["active"]]
    today = sum(r["joined_today"] for r in active)
    invited, confirmed = await db.referral_totals()

    body = (
        f"Каналов в подписке: <b>{len(active)}</b> из {len(rows)}\n"
        f"Пришло через них за сутки: <b>{today}</b>"
        if rows
        else "Каналов нет — бот пускает всех.\n"
        "Добавь канал, и вход будет только через подписку на него."
    )
    await _edit(
        call,
        f"📢 <b>Обязательная подписка</b>\n\n{body}\n\n"
        f"👥 Рефералы: {confirmed} подтверждено из {invited} приглашённых, "
        f"по {settings.get('ref_reward')} монеток за каждого.",
        _channels_kb(rows),
    )
    await call.answer()


@router.callback_query(F.data == "a:chan:add")
async def cb_channel_add(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="📢 Канал", callback_data="a:chan:add:channel", style=kb.PRIMARY
        ),
        InlineKeyboardButton(
            text="🤖 Бот", callback_data="a:chan:add:bot", style=kb.PRIMARY
        ),
    )
    b.row(InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan"))
    await _edit(
        call,
        "➕ <b>Что добавляем в подписку?</b>\n\n"
        "<b>📢 Канал</b> — обычная обязательная подписка, проверяет сам "
        "Telegram. Бот должен быть админом канала.\n\n"
        "<b>🤖 Бот</b> — спонсорский бот через @BotMembersRobot: человек "
        "должен его запустить. Проверку делает BotStat по коду, который "
        "даёт владелец бота.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:chan:add:channel")
async def cb_channel_add_channel(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.channel)
    await _edit(
        call,
        "📢 <b>Новый канал</b>\n\n"
        "Пришли <code>@username</code>, ссылку <code>t.me/…</code> или id вида "
        "<code>-100…</code>.\n\n"
        "Бот должен быть админом в канале — иначе он не сможет проверять "
        "подписку, и такой канал просто не будет никого задерживать.",
        back_kb([InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan")]),
    )
    await call.answer()


@router.callback_query(F.data == "a:chan:add:bot")
async def cb_channel_add_bot(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.gate_bot)
    await _edit(
        call,
        "🤖 <b>Бот в подписку</b>\n\n"
        "Пришли <b>код BotMembers</b> и <b>ссылку на бота</b> в одной строке:\n"
        "<code>abc123 https://t.me/somebot</code>\n\n"
        "Код выдаёт владелец спонсорского бота в @BotMembersRobot — по нему "
        "проверяется, запустил человек этого бота или нет. Ссылка нужна "
        "для кнопки, по которой пользователь туда пойдёт.\n\n"
        "Можно добавить название третьим куском: "
        "<code>abc123 https://t.me/somebot Спонсор</code>",
        back_kb([InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan")]),
    )
    await call.answer()


@router.message(Admin.gate_bot, ~F.text.in_(kb.MENU_BUTTONS))
async def got_gate_bot(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Нужен код и ссылка через пробел.")
        return

    code, link = parts[0].strip(), parts[1].strip()
    title = parts[2].strip() if len(parts) > 2 else ""
    if not code.replace("_", "").replace("-", "").isalnum():
        await message.answer("Код — латиница и цифры.")
        return
    if not link.startswith(("https://t.me/", "http://t.me/", "t.me/")):
        await message.answer("Ссылка должна вести на t.me/…")
        return
    link = link if link.startswith("http") else f"https://{link}"
    if not title:
        title = "@" + link.rstrip("/").rsplit("/", 1)[-1]

    # A code nobody answers for would let everyone through unnoticed, so it is
    # tried once, on the admin, before it goes into the gate.
    probe = await botstat.check_member(code, message.from_user.id)
    channel_id = await db.add_channel(code, title, link, kind="bot")
    if channel_id is None:
        await message.answer("Такой код уже в списке.")
        return

    await state.clear()
    verdict = (
        "🔴 BotStat не ответил — проверь код, иначе бот никого не задержит."
        if probe is None
        else f"🟢 Код рабочий (тебя он видит как {'запустившего' if probe else 'не запустившего'})."
    )
    channel = await db.get_channel(channel_id)
    await message.answer(
        await _channel_card(message.bot, channel) + f"\n\n{verdict}",
        reply_markup=_channel_kb(channel),
    )


@router.message(Admin.channel, ~F.text.in_(kb.MENU_BUTTONS))
async def got_channel(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("https://t.me/"):
        raw = "@" + raw.removeprefix("https://t.me/").strip("/")
    elif raw.startswith("t.me/"):
        raw = "@" + raw.removeprefix("t.me/").strip("/")
    if not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен @username, ссылка t.me/… или числовой id.")
        return

    title, link = await access.describe(message.bot, raw)
    channel_id = await db.add_channel(raw, title, link)
    if channel_id is None:
        await message.answer("Такой канал уже в списке.")
        return

    await state.clear()
    access.drop_link_cache()
    channel = await db.get_channel(channel_id)
    await message.answer(
        await _channel_card(message.bot, channel),
        reply_markup=_channel_kb(channel),
    )


async def _channel_card(bot: Bot, channel) -> str:
    status = await _channel_status(bot, channel["chat"], channel["kind"])
    title = channel["title"] or channel["chat"]
    icon = "🤖" if channel["kind"] == "bot" else "📢"
    what = "код BotMembers" if channel["kind"] == "bot" else "канал"
    return (
        f"{icon} <b>{html.escape(title)}</b> · {what}\n"
        f"<code>{html.escape(channel['chat'])}</code> · "
        f"{'🟢 в подписке' if channel['active'] else '⚪ выключен'}\n"
        f"Проверка: {status}\n\n"
        f"Пришло через него: <b>{channel['joined']}</b>\n"
        f"За сутки: {channel['joined_today']}\n"
        f"Ссылка: {channel['link'] or '—'}"
    )


def _channel_kb(channel) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if channel["active"]:
        b.row(
            InlineKeyboardButton(
                text="⏸ Убрать из подписки",
                callback_data=f"a:chan:off:{channel['id']}",
                style=kb.DANGER,
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text="▶️ Вернуть в подписку",
                callback_data=f"a:chan:on:{channel['id']}",
                style=kb.SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="🔄 Обновить данные", callback_data=f"a:chan:{channel['id']}"
        ),
        InlineKeyboardButton(
            text="🗑 Удалить", callback_data=f"a:chan:del:{channel['id']}"
        ),
    )
    b.row(InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan"))
    return b.as_markup()


async def _show_channel(call: CallbackQuery, channel_id: int) -> None:
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return
    rows = await db.channels()
    channel = next((r for r in rows if r["id"] == channel_id), channel)
    await _edit(call, await _channel_card(call.bot, channel), _channel_kb(channel))


@router.callback_query(F.data.startswith("a:chan:on:"))
async def cb_channel_on(call: CallbackQuery) -> None:
    channel_id = int(call.data.split(":")[3])
    await db.set_channel_active(channel_id, True)
    await call.answer("В подписке")
    await _show_channel(call, channel_id)


@router.callback_query(F.data.startswith("a:chan:off:"))
async def cb_channel_off(call: CallbackQuery) -> None:
    channel_id = int(call.data.split(":")[3])
    await db.set_channel_active(channel_id, False)
    await call.answer("Убрал из подписки")
    await _show_channel(call, channel_id)


@router.callback_query(F.data.startswith("a:chan:del:"))
async def cb_channel_del(call: CallbackQuery) -> None:
    """Dropping a channel throws away what it brought, so it asks first."""
    channel_id = int(call.data.split(":")[3])
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🗑 Да, удалить",
            callback_data=f"a:chan:delgo:{channel_id}",
            style=kb.DANGER,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data=f"a:chan:{channel_id}", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Удалить канал {html.escape(channel['title'] or channel['chat'])}?</b>\n\n"
        "Вместе с ним пропадёт счётчик, сколько людей через него пришло. "
        "Если канал нужно просто временно убрать из подписки — жми «Убрать», "
        "счётчик останется.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:chan:delgo:"))
async def cb_channel_del_go(call: CallbackQuery, state: FSMContext) -> None:
    await db.drop_channel(int(call.data.split(":")[3]))
    access.drop_link_cache()
    await call.answer("Удалён")
    await cb_channel(call, state)


@router.callback_query(F.data.regexp(r"^a:chan:\d+$"))
async def cb_channel_one(call: CallbackQuery) -> None:
    """Opening a channel also refreshes its title and link from Telegram."""
    channel_id = int(call.data.split(":")[2])
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return
    if channel["kind"] != "bot":  # a BotMembers code has nothing to refresh
        title, link = await access.describe(call.bot, channel["chat"])
        if title or link:
            await db.set_channel_meta(channel_id, title or channel["title"], link)
    await call.answer()
    await _show_channel(call, channel_id)


@router.message(Command("gate"))
async def gate_cmd(message: Message) -> None:
    """Why the gate is or is not stopping anyone, without any of the shortcuts."""
    rows = await db.channels(active_only=True)
    if not rows:
        await message.answer(
            "Каналов в подписке нет — бот пускает всех.\n"
            "Добавить: /admin → «Подписка»."
        )
        return

    lines = []
    for channel in rows:
        icon = "🤖" if channel["kind"] == "bot" else "📢"
        line = [
            f"{icon} <b>{html.escape(channel['title'] or channel['chat'])}</b> "
            f"(<code>{html.escape(channel['chat'])}</code>)",
            await _channel_status(message.bot, channel["chat"], channel["kind"]),
        ]
        if channel["kind"] == "bot":
            probe = await botstat.check_member(channel["chat"], message.from_user.id)
            line.append(
                "проверить тебя не вышло"
                if probe is None
                else f"ты там: {'да' if probe else 'нет'}"
            )
        else:
            try:
                member = await message.bot.get_chat_member(
                    channel["chat"], message.from_user.id
                )
                line.append(f"ты там: <code>{member.status}</code>")
            except TelegramAPIError as error:
                line.append(f"🔴 проверить тебя не вышло: {error}")
        lines.append("\n".join(line))
    lines.append(
        "⚠️ Ты в ADMIN_IDS — тебя гейт пропускает всегда, "
        "проверяй на обычном аккаунте."
    )
    await message.answer("\n\n".join(lines))


@router.callback_query(F.data == "a:reports")
async def cb_reports(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.reported_circles()
    chat = settings.reports_chat()
    status = await _chat_status(call.bot, chat)

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="⚙️ Чат жалоб", callback_data="a:reports:chat"
        )
    )
    if rows:
        b.row(
            InlineKeyboardButton(
                text=f"👁 Показать {min(len(rows), 5)}",
                callback_data="a:reports:show",
                style=kb.DANGER,
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        f"⚠️ <b>Жалобы</b>\n\nЧат: <code>{chat}</code>\n{status}\n\n"
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
        breakdown = texts.reasons_summary(
            await db.report_reasons(circle["id"]), texts.REPORT_REASONS
        )
        with suppress(TelegramAPIError):
            await call.bot.send_video_note(
                call.from_user.id, circle["file_id"], protect_content=True
            )
            await call.bot.send_message(
                call.from_user.id,
                f"#жалоба <b>#{circle['id']}</b> — {circle['complaints']} шт\n"
                f"Статус: {circle['status']} · просмотров: {circle['views']} · "
                f"👍 {circle['likes']} / 👎 {circle['dislikes']}\n"
                f"Автор: <code>{circle['uploader_id']}</code>\n\n"
                f"{breakdown}",
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
            text="⚙️ Чат анкет", callback_data="a:anketas:chat"
        )
    )
    if waiting:
        b.row(
            InlineKeyboardButton(
                text="➡️ Показать следующую",
                callback_data="a:anketas:next",
                style=kb.SUCCESS,
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        f"📋 <b>Анкеты</b>\n\nЧат: <code>{chat}</code>\n"
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
            f"{html.escape(profile['about'] or 'Без описания')}"
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
            "💸 <b>Выплаты</b>\n\nОткрытых заявок нет.\n"
            f"Выплачено за всё время: {totals['paid_stars']} ⭐",
            back_kb(),
        )
        await call.answer()
        return

    await _edit(
        call,
        f"💸 <b>Выплаты</b>\n\nОткрыто: {totals['open']} заявок на "
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
                f"Реквизиты: <code>{html.escape(payout['details'])}</code>",
                reply_markup=kb.payout_review(payout["id"]),
            )
    await call.answer()


def _ago(stamp: float) -> str:
    if not stamp:
        return "ещё ни разу"
    seconds = int(time.time() - stamp)
    if seconds < 90:
        return f"{seconds} сек назад"
    if seconds < 5400:
        return f"{seconds // 60} мин назад"
    return f"{seconds // 3600} ч назад"


@router.callback_query(F.data == "a:push")
async def cb_push(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    on = bool(settings.get("push_enabled"))
    pool = await db.push_pool(
        settings.get("push_idle_hours") * 3600,
        settings.get("push_cooldown_hours") * 3600,
    )
    run = pushes.last_sweep
    tick = int(config.PUSH_TICK // 60)

    # A job that quietly died and a job with nobody to nudge look the same from
    # the outside, so the last pass reports itself.
    if run["error"]:
        last = f"🔴 {_ago(run['at'])}, сорвался: {html.escape(run['error'])[:120]}"
    elif run["skipped"]:
        last = f"⚪ {_ago(run['at'])} — {run['skipped']}"
    elif run["at"]:
        last = f"🟢 {_ago(run['at'])} — отправлено {run['sent']}, не дошло {run['failed']}"
    else:
        last = f"⚪ ещё ни разу (первый проход через {int(pushes.FIRST_SWEEP)} сек после старта)"

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"{'❌ Выключить' if on else '✅ Включить'}",
            callback_data="a:push:toggle",
            style=kb.DANGER if on else kb.SUCCESS,
        ),
        InlineKeyboardButton(
            text="▶️ Отправить сейчас", callback_data="a:push:now"
        ),
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        "🔔 <b>Напоминания</b>\n\n"
        f"Статус: {'🟢 включены' if on else '🔴 выключены'}\n"
        f"Последний проход: {last}\n\n"
        f"<b>Ждут напоминания: {pool['ready']}</b>\n"
        f"Не в очереди из {pool['total']} человек:\n"
        f"• были в боте недавно — {pool['still_active']}\n"
        f"• уже получали, ждут паузы — {pool['cooling']}\n"
        f"• не приняли правила — {pool['not_accepted']}\n"
        f"• забанены — {pool['banned']}\n\n"
        f"Молчал дольше: {settings.get('push_idle_hours')} ч · "
        f"не чаще раза в {settings.get('push_cooldown_hours')} ч\n"
        f"За проход: до {settings.get('push_batch')} человек, раз в {tick} мин, "
        f"круглые сутки\n"
        f"В подарок: {settings.get('push_free_views')} "
        f"{texts.circles_word(settings.get('push_free_views'))}\n"
        f"Всего получали напоминания: {pool['ever_pushed']}\n\n"
        "Цифры правятся в «Экономике».",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:push:toggle")
async def cb_push_toggle(call: CallbackQuery, state: FSMContext) -> None:
    await settings.set("push_enabled", 0 if settings.get("push_enabled") else 1)
    await call.answer("Включено" if settings.get("push_enabled") else "Выключено")
    await cb_push(call, state)


@router.callback_query(F.data == "a:push:now")
async def cb_push_now(call: CallbackQuery) -> None:
    await call.answer("Пошла рассылка")
    sent, failed = await pushes.sweep(call.bot)
    await _edit(
        call,
        f"<b>Напоминания отправлены</b>\n\nДоставлено: {sent}\nНе дошло: {failed}"
        + (
            "\n\nПусто: либо напоминания выключены, либо некому — все были "
            "в боте недавно."
            if not sent and not failed
            else ""
        ),
        back_kb(),
    )


# --- ad links ------------------------------------------------------------


@router.callback_query(F.data == "a:links")
async def cb_links(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.campaigns()

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="➕ Новая ссылка", callback_data="a:links:new", style=kb.SUCCESS
        )
    )
    for row in rows[:20]:  # a callback list, not a report — keep it scannable
        b.row(
            InlineKeyboardButton(
                text=f"🔗 {row['title'] or row['code']} · {row['users']} чел",
                callback_data=f"a:link:{row['code']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))

    total_users = sum(row["users"] for row in rows)
    await _edit(
        call,
        "🔗 <b>Рекламные ссылки</b>\n\n"
        f"Ссылок: {len(rows)} · пришло с них: {total_users}\n\n"
        "Каждая ссылка — это <code>?start=код</code>. Первая ссылка, по которой "
        "пришёл человек, закрепляется за ним навсегда.\n"
        "Отчёт по одной: <code>/link_код</code>.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:links:new")
async def cb_link_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.campaign)
    await _edit(
        call,
        "Пришли код ссылки — латиница, цифры, <code>_</code> и <code>-</code>, "
        "до 32 символов.\n"
        "Можно с названием через пробел: <code>tg_ads Реклама в канале X</code>.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.campaign, ~F.text.in_(kb.MENU_BUTTONS))
async def got_campaign(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    code, _, title = raw.partition(" ")
    code = access.parse_campaign(code)
    if code is None:
        await message.answer("Код не подходит: латиница, цифры, _ и -, до 32 знаков.")
        return

    await state.clear()
    fresh = await db.create_campaign(code, title.strip())
    await message.answer(
        ("Ссылка создана." if fresh else "Такая ссылка уже была.")
        + f"\n\n<code>{access.campaign_link(code)}</code>",
        reply_markup=_link_kb(code, access.campaign_link(code)),
    )


def _link_kb(code: str, link: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📋 Скопировать", copy_text=CopyTextButton(text=link))
    )
    b.row(
        InlineKeyboardButton(
            text="💰 Расход", callback_data=f"a:link:spend:{code}"
        ),
        InlineKeyboardButton(
            text="🔄 Обновить", callback_data=f"a:link:{code}"
        ),
    )
    b.row(
        InlineKeyboardButton(
            text="🔑 Команда трафферу", callback_data=f"a:link:token:{code}"
        ),
        InlineKeyboardButton(
            text="🗑 Удалить", callback_data=f"a:link:del:{code}", style=kb.DANGER
        ),
    )
    b.row(InlineKeyboardButton(text="⬅️ К ссылкам", callback_data="a:links"))
    return b.as_markup()


def _pct(part: int, whole: int) -> str:
    return f"{part * 100 / whole:.1f}%" if whole else "—"


async def _link_report(code: str) -> str | None:
    """All time, then the last week and day — a link that died should show it."""
    total = await db.campaign_stats(code)
    if total is None:
        return None
    week = await db.campaign_stats(code, 7 * 86400)
    day = await db.campaign_stats(code, 86400)

    spend = total["spend"]
    revenue = settings.revenue_of(total["stars"])
    per_user = spend // total["users"] if total["users"] else 0
    per_payer = spend // total["payers"] if total["payers"] else 0

    money = [f"Расход: <b>{settings.money(spend)}</b>"] if spend else []
    if spend:
        money += [
            f"Цена пользователя: {settings.money(per_user)}",
            f"Цена платящего: {settings.money(per_payer)}"
            if total["payers"]
            else "Цена платящего: —",
        ]
    money.append(
        f"Выручка: <b>{settings.money(revenue)}</b> ({total['stars']} ⭐)"
        + (f" · {_pct(revenue, spend)} от расхода" if spend else "")
    )

    return (
        f"📊 <b>{total['title'] or code}</b>\n\n"
        "🕓 <b>За всё время</b>\n"
        f"Новых пользователей: <b>{total['users']}</b> · в бане: {total['banned']}\n"
        f"Прошли ОП: {total['subscribed']} "
        f"({_pct(total['subscribed'], total['users'])})\n"
        f"Приняли правила: {total['accepted']} "
        f"({_pct(total['accepted'], total['users'])})\n"
        f"Конверсия в платёж: {_pct(total['payers'], total['users'])} "
        f"({total['payers']} чел)\n\n"
        + "\n".join(money)
        + "\n\n📅 <b>7 дней</b> · людей {}, ОП {}, платили {} на {} ⭐\n".format(
            week["users"], week["subscribed"], week["payers"], week["stars"]
        )
        + "📅 <b>Сутки</b> · людей {}, ОП {}, платили {} на {} ⭐\n\n".format(
            day["users"], day["subscribed"], day["payers"], day["stars"]
        )
        + f"Анкет: {total['profiles']} · кружочков: {total['circles']} · "
        f"просмотров: {total['views']}\n"
        f"Потрачено монеток на анкеты: {total['spent_coins']}"
    )


@router.callback_query(F.data.startswith("a:link:token:"))
async def cb_link_token(call: CallbackQuery) -> None:
    code = call.data.split(":", 3)[3]
    token = await db.campaign_token(code)
    if token is None:
        await call.answer("Ссылки больше нет.", show_alert=True)
        return

    command = f"/stat_{token}"
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Скопировать команду", copy_text=CopyTextButton(text=command)
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Новый токен", callback_data=f"a:link:retoken:{code}", style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(
            text="К ссылке", callback_data=f"a:link:{code}", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Команда для траффера · {code}</b>\n\n"
        f"<code>{command}</code>\n\n"
        "Отдай её тому, кто льёт трафик: он увидит переходы, людей, ОП и "
        "покупки по своей ссылке — без расхода, выручки и остальной кухни.\n"
        "«Новый токен» мгновенно ломает старую команду.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:link:retoken:"))
async def cb_link_retoken(call: CallbackQuery) -> None:
    code = call.data.split(":", 3)[3]
    await db.new_campaign_token(code)
    await call.answer("Токен обновлён")
    await cb_link_token(
        call.model_copy(update={"data": f"a:link:token:{code}"})
    )


@router.callback_query(F.data.startswith("a:link:spend:"))
async def cb_link_spend(call: CallbackQuery, state: FSMContext) -> None:
    code = call.data.split(":", 3)[3]
    await state.set_state(Admin.spend)
    await state.update_data(code=code)
    await _edit(
        call,
        f"Сколько потрачено на <code>{code}</code>? "
        "Пришли сумму, например <code>10737.20</code>.\n"
        "Это общий расход по ссылке, а не добавка к прошлому.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.spend, ~F.text.in_(kb.MENU_BUTTONS))
async def got_spend(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".").replace(" ", "")
    try:
        minor = round(float(raw) * 100)
    except ValueError:
        await message.answer("Нужна сумма числом, например 10737.20")
        return
    if minor < 0:
        await message.answer("Расход не бывает отрицательным.")
        return

    code = (await state.get_data())["code"]
    await state.clear()
    await db.set_campaign_spend(code, minor)
    report = await _link_report(code)
    await message.answer(
        report or "Ссылки больше нет.",
        reply_markup=_link_kb(code, access.campaign_link(code)),
    )


@router.callback_query(F.data.startswith("a:link:del2:"))
async def cb_link_delete_confirm(call: CallbackQuery, state: FSMContext) -> None:
    code = call.data.split(":", 3)[3]
    await state.set_state(Admin.delete_link)
    await state.update_data(code=code)
    await _edit(
        call,
        f"Последний шаг: пришли код <code>{code}</code> сообщением, "
        "чтобы удалить ссылку.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.delete_link, ~F.text.in_(kb.MENU_BUTTONS))
async def got_delete_link(message: Message, state: FSMContext) -> None:
    code = (await state.get_data())["code"]
    if (message.text or "").strip().lower() != code:
        await message.answer(f"Не совпало. Нужно ровно <code>{code}</code>.")
        return

    await state.clear()
    await db.delete_campaign(code)
    await message.answer(
        f"Ссылка <code>{code}</code> удалена. Статистика по ней больше не "
        "собирается, но люди, пришедшие по ней, остаются помеченными.",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data.startswith("a:link:del:"))
async def cb_link_delete(call: CallbackQuery) -> None:
    """First of three steps — deleting a link by a misclick is too easy."""
    code = call.data.split(":", 3)[3]
    stats = await db.campaign_stats(code)
    if stats is None:
        await call.answer("Ссылки уже нет.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Да, удалить", callback_data=f"a:link:del2:{code}", style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(
            text="Отмена", callback_data=f"a:link:{code}", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Удалить ссылку {code}?</b>\n\n"
        f"По ней {stats['hits']} переходов и {stats['users']} человек. "
        "Отчёт исчезнет, метки у людей останутся.\n\n"
        "После подтверждения попрошу набрать код руками.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:link:"))
async def cb_link(call: CallbackQuery) -> None:
    code = call.data.split(":", 2)[2]
    report = await _link_report(code)
    if report is None:
        await call.answer("Ссылки больше нет.", show_alert=True)
        return

    link = access.campaign_link(code)
    await _edit(call, f"{report}\n\n<code>{link}</code>", _link_kb(code, link))
    await call.answer()


@router.message(F.text.startswith("/link_"))
async def link_cmd(message: Message) -> None:
    """/link_код — the report without walking the panel."""
    code = message.text.removeprefix("/link_").strip().lower()
    report = await _link_report(code)
    if report is None:
        await message.answer("Такой ссылки нет.")
        return
    link = access.campaign_link(code)
    await message.answer(
        f"{report}\n\n<code>{link}</code>", reply_markup=_link_kb(code, link)
    )


# --- moderation queue ----------------------------------------------------


@router.callback_query(F.data == "a:queue")
async def cb_queue(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    chat = settings.circles_chat()
    waiting = (await db.dashboard())["pending"]

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="⚙️ Чат кружков", callback_data="a:queue:chat"
        )
    )
    if waiting:
        b.row(
            InlineKeyboardButton(
                text="➡️ Показать следующий",
                callback_data="a:queue:next",
                style=kb.SUCCESS,
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        f"🎬 <b>Кружочки на проверке</b>\n\nЧат: <code>{chat}</code>\n"
        f"{await _chat_status(call.bot, chat)}\n\nЖдут проверки: {waiting}",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:queue:chat")
async def cb_queue_chat(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.circles_chat)
    await _edit(
        call,
        "Пришли id чата для кружков (<code>-100…</code>) или <code>@username</code>.\n"
        "Бот должен быть в этом чате. <code>-</code> — вернуть в чат модерации.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.circles_chat, ~F.text.in_(kb.MENU_BUTTONS))
async def got_circles_chat(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        raw = ""
    elif not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен id, @username или «-».")
        return

    await state.clear()
    await settings.set_text("circles_chat", raw)
    chat = settings.circles_chat()
    await message.answer(
        f"Чат кружков: <code>{chat}</code>\n"
        f"{await _chat_status(message.bot, chat)}",
        reply_markup=back_kb(),
    )


@router.message(Command("where"))
async def where_cmd(message: Message) -> None:
    """All four destinations at once — the fastest way to find a broken one."""
    places = {
        "Кружочки": settings.circles_chat(),
        "Анкеты": settings.profiles_chat(),
        "Жалобы и выплаты": settings.reports_chat(),
    }
    lines = []
    for label, chat in places.items():
        lines.append(
            f"<b>{label}</b>: <code>{chat}</code>\n"
            f"{await _chat_status(message.bot, chat)}"
        )
    await message.answer("\n\n".join(lines))


@router.callback_query(F.data == "a:queue:next")
async def cb_queue_next(call: CallbackQuery) -> None:
    circle = await db.next_pending()
    if circle is None:
        await call.answer("Очередь пуста 🟢", show_alert=True)
        return

    await call.bot.send_video_note(
        call.from_user.id, circle["file_id"], protect_content=True
    )
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
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


@router.callback_query(F.data == "a:bulk")
async def cb_bulk(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(
        call,
        "📦 <b>Массовая загрузка</b>\n\n"
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
        "👤 <b>Пользователь</b>\n\nПришли id числом — или перешли сюда любое "
        "его сообщение.",
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
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
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
    await _edit(
        call,
        f"🎥 <b>Кружок по номеру</b>\n\nВсего в базе: {total}.\n"
        "Пришли номер — <code>12</code> или <code>#12</code>. Оттуда его можно "
        "снять с показа или удалить.",
        back_kb(),
    )
    await call.answer()


CIRCLE_STATUS = {
    "approved": "🟢 показывается",
    "pending": "🕒 ждёт проверки",
    "rejected": "🚫 скрыт",
}


def _circle_card(circle) -> str:
    return (
        f"🎥 <b>Кружок #{circle['id']}</b>\n\n"
        f"Статус: <b>{CIRCLE_STATUS.get(circle['status'], circle['status'])}</b>\n"
        f"Тип: {kb.PREF_TITLE(circle['gender'])} · {circle['duration']} сек\n"
        f"👀 {circle['views']} · 👍 {circle['likes']} / 👎 {circle['dislikes']}\n"
        f"Автор: <code>{circle['uploader_id'] or 'архив бота'}</code>"
    )


def _circle_card_kb(circle) -> InlineKeyboardMarkup:
    """Hiding is the reversible verdict; deleting asks again before it happens."""
    circle_id = circle["id"]
    b = InlineKeyboardBuilder()
    if circle["status"] == "approved":
        b.row(
            InlineKeyboardButton(
                text="🚫 Скрыть с показа",
                callback_data=f"a:c:hide:{circle_id}",
                style=kb.DANGER,
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text="✅ Вернуть в показ",
                callback_data=f"a:c:show:{circle_id}",
                style=kb.SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="🗑 Удалить навсегда", callback_data=f"a:c:del:{circle_id}"
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


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

    await message.answer_video_note(circle["file_id"], protect_content=True)
    await message.answer(_circle_card(circle), reply_markup=_circle_card_kb(circle))


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


@router.callback_query(F.data.startswith("a:c:hide:"))
async def cb_circle_hide(call: CallbackQuery) -> None:
    """Out of rotation, but still in the base — the one verdict that is undoable."""
    circle_id = int(call.data.split(":")[3])
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок уже удалён.", show_alert=True)
        return

    await db.set_status(circle_id, "rejected")
    if circle["uploader_id"]:
        with suppress(TelegramAPIError):
            await call.bot.send_message(circle["uploader_id"], texts.CIRCLE_HIDDEN)
    await call.answer("Скрыт")
    circle = await db.get_circle(circle_id)
    await _edit(call, _circle_card(circle), _circle_card_kb(circle))


@router.callback_query(F.data.startswith("a:c:show:"))
async def cb_circle_show(call: CallbackQuery) -> None:
    circle_id = int(call.data.split(":")[3])
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок уже удалён.", show_alert=True)
        return

    await db.set_status(circle_id, "approved")
    await db.clear_reports(circle_id)  # a circle back in rotation has no open ones
    if circle["uploader_id"]:
        with suppress(TelegramAPIError):
            await call.bot.send_message(circle["uploader_id"], texts.CIRCLE_RESTORED)
    await call.answer("Вернул в показ")
    circle = await db.get_circle(circle_id)
    await _edit(call, _circle_card(circle), _circle_card_kb(circle))


@router.callback_query(F.data.startswith("a:c:del:"))
async def cb_circle_delete(call: CallbackQuery) -> None:
    """Deleting cannot be taken back, so it is never the first tap."""
    circle_id = int(call.data.split(":")[3])
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🗑 Да, удалить",
            callback_data=f"a:c:delgo:{circle_id}",
            style=kb.DANGER,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data=f"a:c:card:{circle_id}", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Удалить кружок #{circle_id}?</b>\n\n"
        "Уйдут сам кружок, его просмотры, оценки и жалобы. Отменить будет "
        "нельзя — если нужно просто убрать из показа, скрой его.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:c:card:"))
async def cb_circle_card(call: CallbackQuery) -> None:
    circle = await db.get_circle(int(call.data.split(":")[3]))
    if circle is None:
        await call.answer("Кружок уже удалён.", show_alert=True)
        return
    await _edit(call, _circle_card(circle), _circle_card_kb(circle))
    await call.answer()


@router.callback_query(F.data.startswith("a:c:delgo:"))
async def cb_circle_delete_go(call: CallbackQuery) -> None:
    circle_id = int(call.data.split(":")[3])
    circle = await db.get_circle(circle_id)
    await db.clear_reports(circle_id)
    deleted = await db.delete_circle(circle_id)
    if deleted and circle and circle["uploader_id"]:
        with suppress(TelegramAPIError):
            await call.bot.send_message(circle["uploader_id"], texts.CIRCLE_REMOVED)
    await call.answer("Удалён" if deleted else "Уже нет", show_alert=True)
    await _edit(call, f"🗑 Кружок #{circle_id} удалён.", back_kb())


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


def _econ_groups() -> list[tuple[str, tuple[str, ...]]]:
    return list(settings.groups().items())


def _econ_changed(keys) -> int:
    return sum(settings.get(key) != settings.default(key) for key in keys)


@router.callback_query(F.data == "a:econ")
async def cb_econ(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    b = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(
            text=f"{name} · {len(keys)}"
            + (f" · ✏️{_econ_changed(keys)}" if _econ_changed(keys) else ""),
            callback_data=f"a:econ:g:{i}",
        )
        for i, (name, keys) in enumerate(_econ_groups())
    ]
    for i in range(0, len(buttons), 2):
        b.row(*buttons[i : i + 2])
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        "💰 <b>Экономика</b>\n\n"
        "Значения живут в базе и переживают перезапуск, ✏️ — изменённые.\n\n"
        "Выбери раздел:",
        b.as_markup(),
    )
    await call.answer()


def _econ_group_text(index: int) -> str:
    name, keys = _econ_groups()[index]
    lines = []
    for key in keys:
        value = settings.get(key)
        mark = "" if value == settings.default(key) else " ✏️"
        lines.append(f"• {settings.TITLES[key]}: <b>{value}</b>{mark}")
    return f"<b>{name}</b>\n\n" + "\n".join(lines) + "\n\nЖми, чтобы поменять:"


def _econ_group_kb(index: int) -> InlineKeyboardMarkup:
    _, keys = _econ_groups()[index]
    b = InlineKeyboardBuilder()
    for key in keys:
        b.row(
            InlineKeyboardButton(
                text=f"{settings.TITLES[key]} · {settings.get(key)}",
                callback_data=f"a:econ:k:{key}",
            )
        )
    b.row(
        InlineKeyboardButton(text="⬅️ К разделам", callback_data="a:econ"),
        InlineKeyboardButton(text="🏠 В панель", callback_data="a:home"),
    )
    return b.as_markup()


@router.callback_query(F.data.startswith("a:econ:g:"))
async def cb_econ_group(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    index = int(call.data.split(":")[3])
    if not 0 <= index < len(_econ_groups()):
        await call.answer("Раздела нет.", show_alert=True)
        return
    await _edit(call, _econ_group_text(index), _econ_group_kb(index))
    await call.answer()


def _group_of(key: str) -> int:
    for i, (_, keys) in enumerate(_econ_groups()):
        if key in keys:
            return i
    return 0


@router.callback_query(F.data.startswith("a:econ:k:"))
async def cb_econ_key(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":")[3]
    if key not in settings.TITLES:
        await call.answer("Такой настройки нет.", show_alert=True)
        return

    low, high = settings.LIMITS[key]
    default = settings.default(key)
    await state.set_state(Admin.setting)
    await state.update_data(key=key)

    b = InlineKeyboardBuilder()
    if settings.get(key) != default:
        b.row(
            InlineKeyboardButton(
                text=f"↩️ Вернуть {default}", callback_data=f"a:econ:d:{key}"
            )
        )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена",
            callback_data=f"a:econ:g:{_group_of(key)}",
            style=kb.DANGER,
        )
    )
    await _edit(
        call,
        f"⚙️ <b>{settings.TITLES[key]}</b>\n\n"
        f"Сейчас: <b>{settings.get(key)}</b> · по умолчанию: {default}\n"
        f"Допустимо: от {low} до {high}\n\n"
        "Пришли новое значение числом.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:econ:d:"))
async def cb_econ_default(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    key = call.data.split(":")[3]
    if key not in settings.TITLES:
        await call.answer("Такой настройки нет.", show_alert=True)
        return
    await settings.set(key, settings.default(key))
    index = _group_of(key)
    await call.answer(f"{settings.TITLES[key]}: {settings.get(key)}")
    await _edit(call, _econ_group_text(index), _econ_group_kb(index))


@router.message(Admin.setting, ~F.text.in_(kb.MENU_BUTTONS))
async def got_setting(message: Message, state: FSMContext) -> None:
    key = (await state.get_data())["key"]
    low, high = settings.LIMITS[key]
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(f"Нужно число от {low} до {high}.")
        return
    if not low <= int(raw) <= high:
        await message.answer(
            f"{raw} вне допустимого: {settings.TITLES[key]} — от {low} до {high}."
        )
        return

    await state.clear()
    await settings.set(key, int(raw))
    index = _group_of(key)
    # Back to the list it came from, with the new value already in it.
    await message.answer(
        f"🟢 {settings.TITLES[key]}: <b>{settings.get(key)}</b>\n\n"
        + _econ_group_text(index),
        reply_markup=_econ_group_kb(index),
    )


# --- payments, backup, maintenance ---------------------------------------


def _payment_line(row) -> str:
    what = (
        f"{row['stars']} ⭐"
        if row["provider"] == "stars"
        else f"{row['amount']} {row['asset']} · {crypto.TITLES.get(row['provider'], row['provider'])}"
    )
    return (
        f"<code>{row['user_id']}</code> — {what} → {row['coins']} 🪙"
        f"{' · возвращён' if row['refunded'] else ''}\n"
        f"<code>{html.escape(row['charge_id'])}</code>"
    )


@router.callback_query(F.data == "a:pay")
async def cb_pay(call: CallbackQuery) -> None:
    rows = await db.recent_payments()
    body = (
        "\n\n".join(_payment_line(r) for r in rows) if rows else "Платежей пока нет."
    )
    totals = await db.crypto_totals()
    crypto_lines = "\n".join(
        f"• {crypto.TITLES.get(t['provider'], t['provider'])}: {t['payments']} шт · "
        f"{t['amount']:.2f} {t['asset']} → {t['coins']} 🪙"
        for t in totals
    )

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🪙 Крипта", callback_data="a:crypto"))
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        f"💳 <b>Последние платежи</b>\n\n{body}\n\n"
        + (f"<b>Крипта за всё время</b>\n{crypto_lines}\n\n" if crypto_lines else "")
        + "Возврат: <code>/refund charge_id</code> — только для ⭐.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:crypto")
async def cb_crypto(call: CallbackQuery, state: FSMContext) -> None:
    """Whether crypto checkout is actually working, without leaving the panel."""
    await state.clear()
    await call.answer()
    totals = await db.invoice_totals()
    poll = invoices.last_poll

    lines = []
    for provider in (crypto.CRYPTOBOT, crypto.XROCKET):
        status = await crypto.check_key(provider)
        lines.append(f"{crypto.ICONS[provider]} <b>{crypto.TITLES[provider]}</b>: {status}")

    if poll["error"]:
        watcher = f"🔴 сорвался: {html.escape(poll['error'])[:120]}"
    elif poll["at"]:
        watcher = f"🟢 {_ago(poll['at'])} — проверено {poll['checked']}, оплачено {poll['paid']}"
    else:
        watcher = "⚪ ещё не запускался"

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💱 Сменить валюту", callback_data="a:crypto:asset")
    )
    b.row(
        InlineKeyboardButton(
            text=f"💰 Монеток за 1 {crypto.asset()}: {settings.get('usdt_rate')}",
            callback_data="a:econ:k:usdt_rate",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ К платежам", callback_data="a:pay"))
    await _edit(
        call,
        "🪙 <b>Оплата криптой</b>\n\n"
        + "\n".join(lines)
        + f"\n\nВалюта счетов: <b>{crypto.asset()}</b>\n"
        f"Цена: {settings.get('usdt_rate')} монеток за 1 {crypto.asset()}\n"
        f"Счёт живёт {config.INVOICE_TTL // 60} мин, проверка каждые "
        f"{int(config.INVOICE_POLL)} сек\n\n"
        f"Проверка счетов: {watcher}\n"
        f"Счета: открыто {totals['open']} · оплачено {totals['paid']} · "
        f"просрочено {totals['expired']} · отменено {totals['cancelled']}\n\n"
        "Ключи задаются в <code>.env</code>: <code>CRYPTOBOT_TOKEN</code>, "
        "<code>XROCKET_KEY</code>. Без ключа способ не показывается покупателю.",
        b.as_markup(),
    )


@router.callback_query(F.data == "a:crypto:asset")
async def cb_crypto_asset(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.crypto_asset)
    await _edit(
        call,
        "💱 <b>Валюта счетов</b>\n\n"
        f"Сейчас: <b>{crypto.asset()}</b>\n\n"
        "Пришли код валюты — <code>USDT</code>, <code>TON</code>, "
        "<code>BTC</code>… Он должен поддерживаться обоими сервисами, иначе "
        "счёт просто не создастся.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.crypto_asset, ~F.text.in_(kb.MENU_BUTTONS))
async def got_crypto_asset(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().upper()
    if not raw.isalnum() or not 2 <= len(raw) <= 10:
        await message.answer("Код валюты — латиница и цифры, 2–10 знаков.")
        return
    await state.clear()
    await settings.set_text("crypto_asset", raw)
    await message.answer(
        f"💱 Валюта счетов: <b>{raw}</b>\n\n"
        "Проверь, что цена за 1 монетку осталась разумной: "
        f"сейчас {settings.get('usdt_rate')} монеток за 1 {raw}.",
        reply_markup=back_kb(),
    )


@router.callback_query(F.data == "a:db")
async def cb_db(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Прислать файл", callback_data="a:db:go", style=kb.DANGER
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        "💾 <b>Бэкап базы</b>\n\nВ файле лежат балансы, платежи и file_id всех "
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
    if payment["provider"] != "stars":
        # Telegram only gives back its own charges. The bot has no business
        # moving crypto on its own either, so it does the bookkeeping half and
        # leaves the transfer to a human.
        await db.mark_refunded(charge_id)
        await db.deduct_clamped(payment["user_id"], payment["coins"])
        name = crypto.TITLES.get(payment["provider"], payment["provider"])
        with suppress(TelegramAPIError):
            await message.bot.send_message(
                payment["user_id"],
                f"Платёж {payment['amount']} {payment['asset']} отменён — "
                f"списал {payment['coins']} 🪙.",
            )
        await message.answer(
            f"Отметил возврат и списал {payment['coins']} 🪙.\n\n"
            f"⚠️ Сами <b>{payment['amount']} {payment['asset']}</b> переведи "
            f"вручную из {name} — бот криптой не распоряжается."
        )
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


# --- editable texts ------------------------------------------------------

# Everything here edits texts.py through text_manager: a saved text is live on
# the next message, so the panel never has to promise a restart.


def _cat_icon(category: str) -> str:
    return text_manager.CATEGORY_ICON.get(category, "📋")


def _content_home_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    buttons = [
        InlineKeyboardButton(
            text=f"{_cat_icon(name)} {name} · {total}"
            + (f" · ✏️{edited}" if edited else ""),
            callback_data=f"a:cnt:c:{name}",
        )
        for name, total, edited in text_manager.categories()
    ]
    for i in range(0, len(buttons), 2):
        b.row(*buttons[i : i + 2])
    if text_manager.custom_count():
        b.row(
            InlineKeyboardButton(
                text="↩️ Вернуть все стандартные", callback_data="a:cnt:rst"
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


def _content_home_text() -> str:
    total = sum(total for _, total, _ in text_manager.categories())
    edited = text_manager.custom_count()
    return (
        "📝 <b>Тексты бота</b>\n\n"
        f"Всего можно править: <b>{total}</b> · изменено: <b>{edited}</b>\n\n"
        "Здесь всё, что видит пользователь. Правка применяется сразу, "
        "перезапускать бота не нужно.\n"
        "Числа и значки подставляются на месте вставок вида "
        "<code>{coins}</code> — их список показан у каждого текста.\n\n"
        "Выбери раздел:"
    )


@router.callback_query(F.data == "a:content")
async def cb_content(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(call, _content_home_text(), _content_home_kb())
    await call.answer()


@router.callback_query(F.data.startswith("a:cnt:c:"))
async def cb_content_category(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    category = call.data.split(":", 3)[3]
    keys = text_manager.keys_in(category)
    if not keys:
        await call.answer("Раздел пуст.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    for key in keys:
        item = text_manager.EDITABLE[key]
        mark = "✏️" if text_manager.is_custom(key) else "▫️"
        b.row(
            InlineKeyboardButton(
                text=f"{mark} {item.description}", callback_data=f"a:cnt:t:{key}"
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ К разделам", callback_data="a:content"))
    await _edit(
        call,
        f"{_cat_icon(category)} <b>{category}</b>\n\n"
        "✏️ — текст изменён, ▫️ — стандартный.\n"
        "Выбери, что открыть:",
        b.as_markup(),
    )
    await call.answer()


def _text_card(key: str, note: str = "") -> str:
    item = text_manager.EDITABLE[key]
    value = text_manager.get(key)
    body = html.escape(value)
    if len(body) > 700:
        body = body[:700] + "…"
    status = "✏️ изменён" if text_manager.is_custom(key) else "▫️ стандартный"
    warning = (
        "\n\n⚠️ Этот текст показывается всплывающим окном: жирный шрифт, ссылки "
        "и премиум-эмодзи в нём не отображаются."
        if item.plain
        else ""
    )
    return (
        f"{_cat_icon(item.category)} <b>{item.description}</b>\n"
        f"<code>{key}</code> · {status}\n\n"
        f"<pre>{body}</pre>\n\n"
        f"{text_manager.vars_hint(key)}{warning}"
        + (f"\n\n{note}" if note else "")
    )


def _text_card_kb(key: str) -> InlineKeyboardMarkup:
    item = text_manager.EDITABLE[key]
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✏️ Изменить", callback_data=f"a:cnt:e:{key}", style=kb.SUCCESS
        ),
        InlineKeyboardButton(text="👁 Как видит юзер", callback_data=f"a:cnt:p:{key}"),
    )
    if text_manager.is_custom(key):
        b.row(
            InlineKeyboardButton(
                text="↩️ Вернуть стандартный", callback_data=f"a:cnt:r:{key}"
            )
        )
    b.row(
        InlineKeyboardButton(
            text=f"⬅️ {item.category}", callback_data=f"a:cnt:c:{item.category}"
        ),
        InlineKeyboardButton(text="🏠 В панель", callback_data="a:home"),
    )
    return b.as_markup()


@router.callback_query(F.data.startswith("a:cnt:t:"))
async def cb_text_card(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    key = call.data.split(":", 3)[3]
    if not text_manager.known(key):
        await call.answer("Такого текста нет.", show_alert=True)
        return
    await _edit(call, _text_card(key), _text_card_kb(key))
    await call.answer()


@router.callback_query(F.data.startswith("a:cnt:p:"))
async def cb_text_preview(call: CallbackQuery) -> None:
    """The text exactly as the bot sends it — the only honest preview."""
    key = call.data.split(":", 3)[3]
    if not text_manager.known(key):
        await call.answer("Такого текста нет.", show_alert=True)
        return

    # Placeholders are filled with their own description: the real numbers are
    # only known when a user opens the screen.
    value = text_manager.sample(key, text_manager.get(key))
    if text_manager.EDITABLE[key].plain:
        await call.answer(value, show_alert=True)  # exactly where it lives
        return
    try:
        await call.message.answer(value)
    except TelegramBadRequest as error:
        await call.answer(f"Телеграм не принял текст: {error}", show_alert=True)
        return
    await call.answer()


@router.callback_query(F.data.startswith("a:cnt:e:"))
async def cb_text_edit(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 3)[3]
    if not text_manager.known(key):
        await call.answer("Такого текста нет.", show_alert=True)
        return

    item = text_manager.EDITABLE[key]
    await state.set_state(Admin.content_edit)
    await state.update_data(key=key)

    how = (
        "Пришли новый текст одним сообщением — <b>только текст</b>, без "
        "форматирования: он показывается всплывашкой."
        if item.plain
        else "Нажми на блок выше, чтобы скопировать, поправь и пришли обратно "
        "одним сообщением — теги вроде <code>&lt;b&gt;жирный&lt;/b&gt;</code> "
        "сработают как надо.\nМожно и просто написать текст, выделив жирным "
        "или курсивом прямо в Telegram, — форматирование сохранится."
    )
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="❌ Отмена", callback_data=f"a:cnt:t:{key}", style=kb.DANGER
        )
    )
    # The block is long on purpose: it is copyable, so editing means copying it,
    # fixing a line and sending it back.
    current = html.escape(text_manager.get(key))
    if len(current) > 2800:
        current = current[:2800] + "…"
    await _edit(
        call,
        f"✏️ <b>{item.description}</b>\n\n"
        f"Сейчас:\n<pre>{current}</pre>\n\n"
        f"{text_manager.vars_hint(key)}\n\n{how}",
        b.as_markup(),
    )
    await call.answer()


@router.message(Admin.content_edit, ~F.text.in_(kb.MENU_BUTTONS))
async def got_content(message: Message, state: FSMContext) -> None:
    key = (await state.get_data()).get("key")
    if not key or not text_manager.known(key):
        await state.clear()
        await message.answer("Текст потерялся, начни заново.", reply_markup=back_kb())
        return

    if not (message.text or "").strip():
        await message.answer("Нужен текст одним сообщением.")
        return

    value, escaped = text_manager.incoming(key, message.text, message.html_text)

    # A template that asks for a value the bot cannot supply would break the
    # screen it belongs to, so it never gets saved.
    complaint = text_manager.check(key, value)
    if complaint:
        await message.answer(f"⚠️ {complaint}\n\nПоправь и пришли ещё раз.")
        return

    # Sending it once before saving is what keeps a text Telegram refuses to
    # parse from reaching users — the bot would fail silently on every send.
    # The second candidate is the same message with «<» left as a symbol, for
    # when it was a «меньше» and not the start of a tag.
    stored, failure, fell_back = None, "", False
    for index, candidate in enumerate((value, escaped)):
        if candidate is None or text_manager.check(key, candidate):
            continue
        try:
            await message.answer(text_manager.sample(key, candidate))
        except TelegramBadRequest as error:
            failure = failure or str(error)
            continue
        stored, fell_back = candidate, index == 1
        break

    if stored is None:
        await message.answer(
            "⚠️ Телеграм не принял этот текст:\n"
            f"<code>{html.escape(failure)}</code>\n\n"
            "Поправь и пришли ещё раз."
        )
        return

    await text_manager.save(key, stored)
    await state.clear()
    note = "🟢 Сохранено и уже работает."
    if fell_back:
        # They wrote tags, but not ones Telegram accepts — so the angle brackets
        # were kept as symbols, and the preview above shows exactly that.
        note = (
            "🟢 Сохранено, но теги не сошлись — оставил их обычными символами.\n"
            "Если нужен жирный, пришли ещё раз с парными "
            "<code>&lt;b&gt;…&lt;/b&gt;</code>."
        )
    await message.answer(_text_card(key, note), reply_markup=_text_card_kb(key))


@router.callback_query(F.data.startswith("a:cnt:r:"))
async def cb_text_reset(call: CallbackQuery) -> None:
    key = call.data.split(":", 3)[3]
    if not text_manager.known(key):
        await call.answer("Такого текста нет.", show_alert=True)
        return
    await text_manager.reset(key)
    await call.answer("Вернул стандартный")
    await _edit(call, _text_card(key), _text_card_kb(key))


@router.callback_query(F.data == "a:cnt:rst")
async def cb_content_reset(call: CallbackQuery) -> None:
    edited = text_manager.custom_count()
    if not edited:
        await call.answer("Изменённых текстов нет.", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"↩️ Да, вернуть {edited}",
            callback_data="a:cnt:rst:go",
            style=kb.DANGER,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data="a:content", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Вернуть стандартные тексты?</b>\n\n"
        f"Изменённых сейчас: {edited}. Все они вернутся к тому, что написано "
        "в коде, — прямо сейчас, без перезапуска.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:cnt:rst:go")
async def cb_content_reset_go(call: CallbackQuery, state: FSMContext) -> None:
    dropped = await text_manager.reset_all()
    logger.info("custom texts reset by %s (%s)", call.from_user.id, dropped)
    await call.answer(f"Вернул стандартные: {dropped}")
    await _edit(call, _content_home_text(), _content_home_kb())


# --- welcome and promo posts ---------------------------------------------

# The admin forwards a message once; the bot keeps where it lives and copies it
# from there, so any kind of post works without the panel knowing what is in it.


def _posts_home_kb(stats: dict) -> InlineKeyboardMarkup:
    on = bool(settings.get("promo_enabled"))
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"👋 Приветки · {stats['welcome']}", callback_data="a:post:k:welcome"
        ),
        InlineKeyboardButton(
            text=f"🔁 Показы · {stats['promo']}", callback_data="a:post:k:promo"
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=f"{'❌ Выключить показы' if on else '✅ Включить показы'}",
            callback_data="a:post:toggle",
            style=kb.DANGER if on else kb.SUCCESS,
        )
    )
    b.row(
        InlineKeyboardButton(
            text=f"⏱ Показ раз в {settings.get('promo_every_hours')} ч",
            callback_data="a:econ:k:promo_every_hours",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


async def _posts_home_text() -> str:
    stats = await db.post_stats()
    on = bool(settings.get("promo_enabled"))
    return (
        "📰 <b>Посты</b>\n\n"
        "<b>👋 Приветка</b> — показывается один раз, сразу после /start.\n"
        "<b>🔁 Показ</b> — попадается снова и снова, пока человек пользуется "
        f"ботом, не чаще раза в {settings.get('promo_every_hours')} ч.\n\n"
        f"Активных приветок: <b>{stats['welcome']}</b> · "
        f"показов: <b>{stats['promo']}</b> "
        f"({'🟢 включены' if on else '🔴 выключены'})\n"
        f"Всего показано: {stats['shown']}"
    )


@router.callback_query(F.data == "a:posts")
async def cb_posts(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(call, await _posts_home_text(), _posts_home_kb(await db.post_stats()))
    await call.answer()


@router.callback_query(F.data == "a:post:toggle")
async def cb_posts_toggle(call: CallbackQuery, state: FSMContext) -> None:
    await settings.set("promo_enabled", 0 if settings.get("promo_enabled") else 1)
    await call.answer("Показы включены" if settings.get("promo_enabled") else "Выключены")
    await cb_posts(call, state)


def _post_list_kb(kind: str, rows: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="➕ Добавить", callback_data=f"a:post:add:{kind}", style=kb.SUCCESS
        )
    )
    for row in rows:
        mark = "🟢" if row["active"] else "⚪"
        b.row(
            InlineKeyboardButton(
                text=f"{mark} {row['title'][:26]} · {row['shown']}",
                callback_data=f"a:post:one:{row['id']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ К постам", callback_data="a:posts"))
    return b.as_markup()


@router.callback_query(F.data.startswith("a:post:k:"))
async def cb_post_list(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _render_post_list(call, call.data.split(":")[3])
    await call.answer()


async def _render_post_list(call: CallbackQuery, kind: str) -> None:
    rows = await db.posts(kind)
    what = (
        "Показывается один раз каждому новому пользователю, сразу после /start."
        if kind == posts.WELCOME
        else "Попадается во время пользования ботом. Если их несколько, "
        "человеку каждый раз достаётся тот, который он видел давнее всех."
    )
    await _edit(
        call,
        f"<b>{posts.KINDS[kind]}и</b>\n\n{what}\n\n"
        + (
            "🟢 — работает, ⚪ — выключен. Цифра — сколько раз показан."
            if rows
            else "Пока пусто."
        ),
        _post_list_kb(kind, rows),
    )


@router.callback_query(F.data.startswith("a:post:add:"))
async def cb_post_add(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[3]
    await state.set_state(Admin.post)
    await state.update_data(kind=kind)
    await _edit(
        call,
        f"➕ <b>Новая {posts.KINDS[kind].lower()}</b>\n\n"
        "Пришли сюда сам пост — текстом, фото, видео, кружком, чем угодно. "
        "Можно переслать готовый из канала.\n\n"
        "Бот покажет его пользователям точной копией, вместе с кнопками, "
        "если они в нём есть. Сообщение должно остаться в этом чате — бот "
        "копирует его отсюда каждый раз.",
        back_kb(
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"a:post:k:{kind}")]
        ),
    )
    await call.answer()


@router.message(Admin.post, ~F.text.in_(kb.MENU_BUTTONS))
async def got_post(message: Message, state: FSMContext) -> None:
    kind = (await state.get_data()).get("kind", posts.PROMO)
    await state.clear()
    title = (message.text or message.caption or "").strip().replace("\n", " ")
    post_id = await db.add_post(
        kind, message.chat.id, message.message_id, title[:60] or "без текста"
    )
    post = await db.get_post(post_id)
    await message.answer(
        f"✅ {posts.KINDS[kind]} сохранена и уже работает.\n\n" + _post_card(post),
        reply_markup=_post_kb(post),
    )


def _post_card(post) -> str:
    return (
        f"{'👋' if post['kind'] == posts.WELCOME else '🔁'} "
        f"<b>{posts.KINDS[post['kind']]} #{post['id']}</b> · "
        f"{'🟢 работает' if post['active'] else '⚪ выключен'}\n\n"
        f"{html.escape(post['title'])}\n\n"
        f"Показан: <b>{post['shown']}</b> раз"
    )


def _post_kb(post) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="👁 Показать мне", callback_data=f"a:post:show:{post['id']}"
        )
    )
    if post["active"]:
        b.row(
            InlineKeyboardButton(
                text="⏸ Выключить",
                callback_data=f"a:post:off:{post['id']}",
                style=kb.DANGER,
            )
        )
    else:
        b.row(
            InlineKeyboardButton(
                text="▶️ Включить",
                callback_data=f"a:post:on:{post['id']}",
                style=kb.SUCCESS,
            )
        )
    b.row(
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"a:post:del:{post['id']}"),
        InlineKeyboardButton(
            text="⬅️ К списку", callback_data=f"a:post:k:{post['kind']}"
        ),
    )
    return b.as_markup()


async def _show_post(call: CallbackQuery, post_id: int) -> None:
    post = await db.get_post(post_id)
    if post is None:
        await call.answer("Поста уже нет.", show_alert=True)
        return
    await _edit(call, _post_card(post), _post_kb(post))


@router.callback_query(F.data.startswith("a:post:one:"))
async def cb_post_one(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await _show_post(call, int(call.data.split(":")[3]))


@router.callback_query(F.data.startswith("a:post:show:"))
async def cb_post_preview(call: CallbackQuery) -> None:
    """Exactly what the user gets, copied the same way."""
    post = await db.get_post(int(call.data.split(":")[3]))
    if post is None:
        await call.answer("Поста уже нет.", show_alert=True)
        return
    try:
        await call.bot.copy_message(
            chat_id=call.from_user.id,
            from_chat_id=post["from_chat"],
            message_id=post["msg_id"],
        )
    except TelegramAPIError as error:
        await call.answer(f"Не копируется: {error}", show_alert=True)
        return
    await call.answer()


@router.callback_query(F.data.startswith("a:post:on:"))
async def cb_post_on(call: CallbackQuery) -> None:
    post_id = int(call.data.split(":")[3])
    await db.set_post_active(post_id, True)
    await call.answer("Включён")
    await _show_post(call, post_id)


@router.callback_query(F.data.startswith("a:post:off:"))
async def cb_post_off(call: CallbackQuery) -> None:
    post_id = int(call.data.split(":")[3])
    await db.set_post_active(post_id, False)
    await call.answer("Выключен")
    await _show_post(call, post_id)


@router.callback_query(F.data.startswith("a:post:del:"))
async def cb_post_del(call: CallbackQuery) -> None:
    post_id = int(call.data.split(":")[3])
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="🗑 Да, удалить",
            callback_data=f"a:post:delgo:{post_id}",
            style=kb.DANGER,
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data=f"a:post:one:{post_id}", style=kb.PRIMARY
        )
    )
    await _edit(
        call,
        f"<b>Удалить пост #{post_id}?</b>\n\n"
        "Пропадёт и счётчик показов, и отметки о том, кто его уже видел — "
        "если добавить такой же заново, он снова покажется всем. "
        "Чтобы просто перестать показывать, хватит «Выключить».",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:post:delgo:"))
async def cb_post_del_go(call: CallbackQuery, state: FSMContext) -> None:
    post_id = int(call.data.split(":")[3])
    post = await db.get_post(post_id)
    kind = post["kind"] if post else posts.PROMO
    await db.drop_post(post_id)
    await state.clear()
    await call.answer("Удалён")
    await _render_post_list(call, kind)


# --- BotStat: broadcasts and audience checks -----------------------------

# The base leaves the bot only from here, only by hand, and only as telegram
# ids — the screen says as much before anything is sent anywhere.


async def _botstat_text() -> str:
    total = len(await db.all_user_ids())
    key = "🟢 задан" if botstat.configured() else "⚪ нет (BOTSTAT_KEY в .env)"
    return (
        "🛡 <b>BotStat</b>\n\n"
        f"Пользователей в базе: <b>{total}</b>\n"
        f"Ключ BotStat: {key}\n\n"
        "<b>📤 В BotMan</b> — база уезжает в @BotManRobot, рассылку делаешь "
        "там: он умеет скорость, паузы, кнопки и отчёты. Бот сам рассылать "
        "такую базу не станет — это часы и риск для токена.\n\n"
        "<b>🛡 В BotSafe</b> — проверка аудитории в @BotSafeRobot: сколько "
        "живых, сколько мёртвых. Результат придёт тебе в личку от бота "
        "проверки.\n\n"
        "Уходят <b>только Telegram id</b> — ни имён, ни сообщений, ни балансов."
    )


def _botstat_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="📤 Отправить базу в BotMan",
            callback_data="a:bs:botman",
            style=kb.PRIMARY,
        )
    )
    if botstat.configured():
        b.row(
            InlineKeyboardButton(
                text="🛡 Проверить базу в BotSafe", callback_data="a:bs:safe"
            )
        )
        b.row(
            InlineKeyboardButton(text="📊 Что знает BotStat", callback_data="a:bs:info")
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


@router.callback_query(F.data == "a:botstat")
async def cb_botstat(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(call, await _botstat_text(), _botstat_kb())
    await call.answer()


def _confirm_kb(action: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✅ Да, отправить", callback_data=action, style=kb.DANGER
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data="a:botstat", style=kb.PRIMARY
        )
    )
    return b.as_markup()


@router.callback_query(F.data == "a:bs:botman")
async def cb_botman_ask(call: CallbackQuery) -> None:
    total = len(await db.all_user_ids())
    await _edit(
        call,
        "📤 <b>Отправить базу в BotMan?</b>\n\n"
        f"Уйдёт <b>{total}</b> Telegram id в @BotManRobot, база закрепится "
        f"за тобой (<code>{call.from_user.id}</code>).\n\n"
        "Это выгрузка на сторонний сервис — дальше рассылка делается там.",
        _confirm_kb("a:bs:botman:go"),
    )
    await call.answer()


@router.callback_query(F.data == "a:bs:botman:go")
async def cb_botman_go(call: CallbackQuery) -> None:
    await call.answer("Отправляю…")
    ids = await db.all_user_ids()
    try:
        await botstat.to_botman(ids, call.from_user.id)
    except botstat.BotStatError as error:
        await _edit(
            call,
            f"🔴 <b>BotMan не принял базу</b>\n\n<code>{html.escape(str(error))}</code>\n\n"
            "Чаще всего это значит, что бот не привязан к твоему аккаунту "
            "в @BotManRobot — открой его и добавь бота, потом повтори.",
            back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
        )
        return
    await _edit(
        call,
        f"🟢 <b>База ушла в BotMan</b>\n\nОтправлено {len(ids)} id.\n"
        "Открой @BotManRobot — база там, рассылка настраивается в нём.",
        back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
    )


@router.callback_query(F.data == "a:bs:safe")
async def cb_botsafe_ask(call: CallbackQuery) -> None:
    total = len(await db.all_user_ids())
    await _edit(
        call,
        "🛡 <b>Проверить базу в BotSafe?</b>\n\n"
        f"Уйдёт <b>{total}</b> Telegram id в @BotSafeRobot. Проверка идёт "
        "приватно, прогресс и результат придут тебе в личку от него.\n\n"
        "Одновременно у бота может идти только одна проверка.",
        _confirm_kb("a:bs:safe:go"),
    )
    await call.answer()


@router.callback_query(F.data == "a:bs:safe:go")
async def cb_botsafe_go(call: CallbackQuery) -> None:
    await call.answer("Отправляю…")
    ids = await db.all_user_ids()
    try:
        result = await botstat.to_botsafe(ids, call.from_user.id)
    except botstat.BotStatError as error:
        await _edit(
            call,
            f"🔴 <b>BotSafe не принял базу</b>\n\n<code>{html.escape(str(error))}</code>",
            back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
        )
        return
    job = result.get("id", "")
    line = f"Задача: <code>{html.escape(str(job))}</code>\n" if job else ""
    await _edit(
        call,
        f"🟢 <b>Проверка запущена</b>\n\nОтправлено {len(ids)} id.\n{line}"
        "Прогресс и результат придут от @BotSafeRobot.",
        back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
    )


@router.callback_query(F.data == "a:bs:info")
async def cb_botstat_info(call: CallbackQuery) -> None:
    await call.answer()
    username = (await call.bot.me()).username
    try:
        info = await botstat.bot_info(username)
    except botstat.BotStatError as error:
        await _edit(
            call,
            f"🔴 <b>BotStat не ответил</b>\n\n<code>{html.escape(str(error))}</code>\n\n"
            "Бот должен быть привязан в личном кабинете botstat.io, "
            "и ключ должен быть от того же аккаунта.",
            back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
        )
        return
    await _edit(
        call,
        f"📊 <b>{html.escape(str(info.get('fullname') or username))}</b>\n\n"
        f"Живых: <b>{info.get('users_live', '—')}</b> · "
        f"мёртвых: {info.get('users_die', '—')}\n"
        f"Групп: {info.get('groups_live', '—')} живых / "
        f"{info.get('groups_die', '—')} мёртвых\n"
        f"В группах людей: {info.get('users_in_groups', '—')}\n"
        f"Данные на: {html.escape(str(info.get('date', '—')))}",
        back_kb([InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]),
    )


# --- cheques -------------------------------------------------------------

# Minting happens in the inline field (handlers/cheques.py); the panel is for
# seeing what is out there and stopping one that went wrong.


@router.callback_query(F.data == "a:cheques")
async def cb_cheques(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    rows = await db.cheques()
    totals = await db.cheque_totals()

    b = InlineKeyboardBuilder()
    for row in rows[:10]:
        left = row["total"] - row["used"]
        mark = "🟢" if row["active"] and left > 0 else "⚪"
        kind = " 👥" if row["kind"] == cheques.REFS else ""
        b.row(
            InlineKeyboardButton(
                text=f"{mark} {row['coins']}🪙{kind} · {row['used']}/{row['total']}",
                callback_data=f"a:chq:{row['code']}",
            )
        )
    b.row(
        InlineKeyboardButton(
            text=f"👥 Рефералов для чека: {settings.get('cheque_min_refs')}",
            callback_data="a:econ:k:cheque_min_refs",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        "🎟 <b>Чеки</b>\n\n"
        "Чек создаётся в поле ввода любого чата:\n"
        f"<code>@{(await call.bot.me()).username} 100 5</code> — "
        "100 монеток, 5 активаций.\n"
        "В списке будет два варианта: обычный и «только от "
        f"{settings.get('cheque_min_refs')} рефералов» — посты у них одинаковые.\n\n"
        f"Живых чеков: <b>{totals['live']}</b>\n"
        f"Активаций всего: {totals['claims']} на {totals['coins']} 🪙\n\n"
        + ("👥 — чек для рефоводов." if rows else "Пока ни одного не выпущено."),
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:chq:"))
async def cb_cheque_one(call: CallbackQuery) -> None:
    await _show_cheque(call, call.data.split(":", 2)[2])
    await call.answer()


async def _show_cheque(call: CallbackQuery, code: str) -> None:
    cheque = await db.get_cheque(code)
    if cheque is None:
        await call.answer("Чека уже нет.", show_alert=True)
        return

    left = cheque["total"] - cheque["used"]
    kind = (
        f"только для тех, кто привёл {cheque['min_refs']}+"
        if cheque["kind"] == cheques.REFS
        else "для всех, кто прошёл подписку"
    )
    b = InlineKeyboardBuilder()
    if cheque["active"] and left > 0:
        b.row(
            InlineKeyboardButton(
                text="⏹ Остановить чек",
                callback_data=f"a:chq:stop:{code}",
                style=kb.DANGER,
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ К чекам", callback_data="a:cheques"))
    await _edit(
        call,
        f"🎟 <b>Чек на {cheque['coins']} монеток</b>\n"
        f"<code>{html.escape(code)}</code>\n\n"
        f"Условие: {kind}\n"
        f"Активаций: <b>{cheque['used']}</b> из {cheque['total']}"
        + (f" · осталось {left}" if left > 0 else " · разобран")
        + ("\nСтатус: ⏹ остановлен" if not cheque["active"] else "")
        + f"\nВыдано монеток: {cheque['used'] * cheque['coins']}",
        b.as_markup(),
    )


@router.callback_query(F.data.startswith("a:chq:stop:"))
async def cb_cheque_stop(call: CallbackQuery) -> None:
    code = call.data.split(":", 3)[3]
    await db.stop_cheque(code)
    await call.answer("Остановлен")
    await _show_cheque(call, code)


# --- referrals -----------------------------------------------------------

# Referrals are bought traffic like any other, so the screen answers the same
# questions: how much came in, how fast, and whether it is worth anything.


def _pct_of(part: int, whole: int) -> str:
    return f"{part * 100 / whole:.1f}%" if whole else "—"


def _since(stamp: int) -> str:
    if not stamp:
        return "—"
    days = int((time.time() - stamp) // 86400)
    if days > 1:
        return f"{days} дн назад"
    return _ago(stamp)


async def _refs_text() -> str:
    d = await db.referral_overview()
    reward = settings.get("ref_reward")
    invited, confirmed = d["invited"], d["confirmed"]
    return (
        "👥 <b>Рефералы</b>\n\n"
        f"Приглашено всего: <b>{invited}</b>\n"
        f"Дошли до конца (прошли ОП): <b>{confirmed}</b> · "
        f"{_pct_of(confirmed, invited)}\n"
        f"Застряли на подписке: {d['waiting']}\n"
        f"Выдано наград: ~{confirmed * reward} 🪙 (по текущей ставке {reward})\n\n"
        "📅 <b>Пришло / из них дошли</b>\n"
        f"Сутки: <b>{d['day_invited']}</b> / {d['day_confirmed']} "
        f"({_pct_of(d['day_confirmed'], d['day_invited'])})\n"
        f"7 дней: <b>{d['week_invited']}</b> / {d['week_confirmed']} "
        f"({_pct_of(d['week_confirmed'], d['week_invited'])})\n"
        f"30 дней: <b>{d['month_invited']}</b> / {d['month_confirmed']} "
        f"({_pct_of(d['month_confirmed'], d['month_invited'])})\n\n"
        "🧑‍🤝‍🧑 <b>Кто приводит</b>\n"
        f"Рефоводов всего: <b>{d['referrers']}</b> · с результатом: {d['with_one']}\n"
        f"Привели 3+: {d['with_three']} · 10+: {d['with_ten']}\n"
        f"Рекорд одного: {d['best']}\n\n"
        "🎯 <b>Что это за люди</b>\n"
        f"Приняли правила: {d['accepted']} ({_pct_of(d['accepted'], invited)})\n"
        f"Заходили за неделю: {d['alive']} ({_pct_of(d['alive'], invited)})\n"
        f"Платили: {d['payers']} ({_pct_of(d['payers'], invited)})\n"
        f"В бане: {d['banned']} ({_pct_of(d['banned'], invited)})\n"
        f"Монеток на руках у них: {d['coins']}"
    )


def _refs_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="🏆 Топ за всё время", callback_data="a:refs:top:0"),
    )
    b.row(
        InlineKeyboardButton(text="📅 За сутки", callback_data="a:refs:top:86400"),
        InlineKeyboardButton(text="📅 За неделю", callback_data="a:refs:top:604800"),
        InlineKeyboardButton(text="📅 За месяц", callback_data="a:refs:top:2592000"),
    )
    b.row(
        InlineKeyboardButton(
            text=f"🎁 Награда за друга: {settings.get('ref_reward')}",
            callback_data="a:econ:k:ref_reward",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


@router.callback_query(F.data == "a:refs")
async def cb_refs(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(call, await _refs_text(), _refs_kb())
    await call.answer()


WINDOW_TITLE = {
    0: "за всё время",
    86400: "за сутки",
    604800: "за неделю",
    2592000: "за месяц",
}


@router.callback_query(F.data.startswith("a:refs:top:"))
async def cb_refs_top(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    window = int(call.data.split(":")[3])
    rows = await db.top_referrers(limit=15, window=window)

    b = InlineKeyboardBuilder()
    lines = []
    for place, row in enumerate(rows, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
        lines.append(
            f"{medal} <code>{row['user_id']}</code> — <b>{row['confirmed']}</b>"
            f" из {row['invited']}"
            + (f" · 🔴{row['banned']}" if row["banned"] else "")
            + f" · живых {row['alive']}"
        )
        b.row(
            InlineKeyboardButton(
                text=f"{medal} {row['user_id']} · {row['confirmed']}",
                callback_data=f"a:refs:u:{row['user_id']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ К рефералам", callback_data="a:refs"))

    body = "\n".join(lines) if lines else "Пока никто никого не привёл."
    await _edit(
        call,
        f"🏆 <b>Топ рефоводов {WINDOW_TITLE.get(window, '')}</b>\n\n{body}\n\n"
        "<b>N из M</b> — дошли до конца из приглашённых, 🔴 — забанены, "
        "живых — заходили за неделю.\n"
        "Жми на строку, чтобы посмотреть рефовода.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:refs:u:"))
async def cb_refs_user(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = int(call.data.split(":")[3])
    d = await db.referrer_detail(user_id)
    invited = d["invited"]
    guests = await db.referred_users(user_id, 10)

    lines = []
    for guest in guests:
        marks = []
        if guest["banned"]:
            marks.append("🔴 бан")
        elif not guest["accepted"]:
            marks.append("не принял правила")
        elif not guest["ref_credited"]:
            marks.append("не прошёл ОП")
        elif guest["last_seen"] > time.time() - 604800:
            marks.append("активен")
        lines.append(
            f"• <code>{guest['id']}</code> · {_since(guest['created_at'])}"
            + (f" · {', '.join(marks)}" if marks else "")
        )

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="👤 Карточка пользователя", callback_data=f"a:u:card:{user_id}"
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ К топу", callback_data="a:refs:top:0"))
    await _edit(
        call,
        f"👤 <b>Рефовод</b> <code>{user_id}</code>\n\n"
        f"Привёл всего: <b>{invited}</b> · дошли: <b>{d['confirmed']}</b> "
        f"({_pct_of(d['confirmed'], invited)})\n"
        f"За сутки: {d['day']} · за неделю: {d['week']}\n"
        f"Первый: {_since(d['first_at'])} · последний: {_since(d['last_at'])}\n\n"
        f"Приняли правила: {d['accepted']} ({_pct_of(d['accepted'], invited)})\n"
        f"Заходили за неделю: {d['alive']} · в бане: {d['banned']}\n\n"
        + ("<b>Последние приглашённые</b>\n" + "\n".join(lines) if lines else ""),
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("a:u:card:"))
async def cb_user_card(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup = await user_card(int(call.data.split(":")[3]))
    await _edit(call, text, markup)
    await call.answer()
