"""Admin panel: /admin opens one editable message with everything in it.

Every screen is a callback on the "a:" prefix and every one of them is gated on
ADMIN_IDS — the panel lives in the admin's private chat, not in the moderation
chat, so a leaked button id is not enough to use it.
"""

import asyncio
import html
import logging
import re
import time
from contextlib import suppress

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
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
import outbox
import people
import posts
import paritypay
import pushes
import sponsors
from handlers import cheques
import keyboards as kb
import settings
import text_manager
import texts
import tiers
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
    dm = State()  # a message to one person, written from the user card
    broadcast = State()
    setting = State()
    circle_id = State()
    channel = State()
    channel_link = State()
    reports_chat = State()
    campaign = State()
    spend = State()
    delete_link = State()
    profiles_chat = State()
    circles_chat = State()
    content_edit = State()  # unified text + emoji editing
    crypto_asset = State()
    gate_bot = State()
    channel_title = State()
    post = State()
    post_sponsor = State()  # чей бот рекламирует показ — код или токен
    botman_folder = State()
    dead_file = State()  # список мёртвых от BotSafe


# --- home ----------------------------------------------------------------


def home_kb(
    maintenance: bool,
    pending: int,
    reports: int,
    anketas: int,
    payouts: int,
) -> InlineKeyboardMarkup:
    """Queues first, everyday tools next, the rest behind three doors.

    Twenty-three buttons in one screen is a wall you read every time instead of
    a panel you use, and the four counters — the reason the admin opened it —
    drowned in it. Everything that is not needed daily moved into sections.
    """
    b = InlineKeyboardBuilder()

    # What waits for a human — the only place colour means urgency.
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

    # Reached for by hand every day, so they stay one tap away.
    b.row(
        InlineKeyboardButton(text="👤 Пользователь", callback_data="a:user"),
        InlineKeyboardButton(text="🎥 Кружок", callback_data="a:circle"),
    )
    b.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="a:cast"),
        InlineKeyboardButton(text="📦 Массовая загрузка", callback_data="a:bulk"),
    )

    b.row(
        InlineKeyboardButton(text="📈 Трафик", callback_data="a:sec:traffic"),
        InlineKeyboardButton(text="📊 Отчёты", callback_data="a:sec:reports"),
    )
    # Maintenance lives in the section now, but «bot is closed» is not something
    # to find out two taps deep — the door itself carries the alarm.
    b.row(
        InlineKeyboardButton(
            text="⚙️ Настройки" + (" · 🔧 техработы" if maintenance else ""),
            callback_data="a:sec:settings",
            style=kb.DANGER if maintenance else None,
        )
    )

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


# --- sections ------------------------------------------------------------

# Three drawers under the panel. Each one only gathers screens that already
# exist — the buttons kept their callbacks, so every old path still works.


def _section_kb(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*row)
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


@router.callback_query(F.data == "a:sec:traffic")
async def cb_sec_traffic(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    channels = len(await db.channels(active_only=True))
    await _edit(
        call,
        "📈 <b>Трафик</b>\n\nОткуда приходят люди и что возвращает их обратно.",
        _section_kb(
            [
                [
                    InlineKeyboardButton(
                        text=f"📢 Подписка · {channels}", callback_data="a:chan"
                    ),
                    InlineKeyboardButton(text="🔗 Ссылки", callback_data="a:links"),
                ],
                [
                    InlineKeyboardButton(text="📰 Посты", callback_data="a:posts"),
                    InlineKeyboardButton(text="🎟 Чеки", callback_data="a:cheques"),
                ],
                [
                    InlineKeyboardButton(text="👥 Рефералы", callback_data="a:refs"),
                    InlineKeyboardButton(
                        text="🔔 Напоминания", callback_data="a:push"
                    ),
                ],
            ]
        ),
    )
    await call.answer()


@router.callback_query(F.data == "a:sec:reports")
async def cb_sec_reports(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _edit(
        call,
        "📊 <b>Отчёты</b>\n\nЦифры по боту и то, что можно унести с собой.",
        _section_kb(
            [
                [
                    InlineKeyboardButton(
                        text="📊 Статистика", callback_data="a:stats"
                    ),
                    InlineKeyboardButton(text="🏆 Топ авторов", callback_data="a:top"),
                ],
                [
                    InlineKeyboardButton(text="💎 Подписки", callback_data="a:tiers"),
                    InlineKeyboardButton(text="🛡 BotStat", callback_data="a:botstat"),
                ],
                [
                    InlineKeyboardButton(text="💾 Бэкап базы", callback_data="a:db"),
                ],
            ]
        ),
    )
    await call.answer()


def _settings_screen() -> tuple[str, InlineKeyboardMarkup]:
    on = settings.maintenance()
    text = (
        "⚙️ <b>Настройки</b>\n\nЦены, платёжные методы и всё, что бот говорит."
        + (
            "\n\n🔧 <b>Техработы включены</b> — бот отвечает всем, кроме админов, "
            "что закрыт."
            if on
            else ""
        )
    )
    return text, _section_kb(
        [
            [
                InlineKeyboardButton(text="💰 Экономика", callback_data="a:econ"),
                InlineKeyboardButton(text="💳 Платежи", callback_data="a:pay"),
            ],
            [InlineKeyboardButton(text="📝 Тексты", callback_data="a:content")],
            [
                InlineKeyboardButton(
                    text=f"🔧 Техработы: {'вкл' if on else 'выкл'}",
                    callback_data="a:maint",
                    style=kb.DANGER if on else None,
                )
            ],
        ]
    )


@router.callback_query(F.data == "a:sec:settings")
async def cb_sec_settings(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text, markup = _settings_screen()
    await _edit(call, text, markup)
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


@router.callback_query(F.data == "a:tiers")
async def cb_tiers(call: CallbackQuery, state: FSMContext) -> None:
    """What the subscriptions are doing: who holds one, and what they took in."""
    await state.clear()
    stats = await db.tier_stats()
    held = {row["tier"]: row["people"] for row in await db.tiers_in_force()}

    lines = []
    for code in tiers.ORDER:
        tier = tiers.get(code)
        lines.append(
            f"<b>{tier.title}</b> · {tier.price} 🪙/день — "
            f"сейчас у {held.get(code, 0)}"
        )

    boost = await db.boost_stats()
    await _edit(
        call,
        "💎 <b>Подписки</b>\n\n"
        f"Действуют сейчас: <b>{stats['active']}</b>\n"
        f"Продаж всего: {stats['sales']} на {stats['coins']} 🪙 "
        f"(за сутки {stats['coins_today']} 🪙)\n\n"
        + "\n".join(lines)
        + "\n\n🚀 <b>Продвижение анкет</b>\n"
        f"Продаж: {boost['sales']} на {boost['coins']} 🪙 "
        f"(за сутки {boost['coins_today']} 🪙)\n"
        f"Куплено дней: {boost['days']} · покупателей: {boost['buyers']}\n"
        f"Идёт сейчас у {boost['running']} анкет"
        + "\n\nЦены и лимиты — в «Экономике».",
        back_kb(
            [
                InlineKeyboardButton(
                    text="⬅️ К отчётам", callback_data="a:sec:reports"
                )
            ]
        ),
    )
    await call.answer()


@router.callback_query(F.data == "a:top")
async def cb_top(call: CallbackQuery) -> None:
    rows = await db.top_uploaders()
    if not rows:
        body = "Пока никто ничего не загрузил."
    else:
        body = "\n".join(
            [
                f"{i}. {await people.of(r['uploader_id'])} — "
                f"{r['approved']} одобрено из {r['total']}"
                for i, r in enumerate(rows, 1)
            ]
        )
    await _edit(call, f"🏆 <b>Топ авторов</b>\n\n{body}", back_kb())
    await call.answer()


# --- sponsor channels ----------------------------------------------------

# Several channels at once: this is the thing sold to advertisers, so each one
# is listed separately with what it actually brought in.


async def _channel_status(
    bot: Bot, chat: str, kind: str = "channel", channel=None
) -> str:
    """The gate is only real if the membership can actually be checked."""
    if kind == "bot":
        method = channel["method"] if channel is not None else sponsors.BOTMEMBERS
        secret = (channel["secret"] or chat) if channel is not None else chat
        if method == sponsors.TOKEN:
            try:
                return f"🟢 спрашиваем сам {await sponsors.whoami(secret)}"
            except sponsors.SponsorError as error:
                return f"🔴 токен не отвечает: {str(error)[:60]}"
        probe = await botstat.check_member(secret, (await bot.me()).id)
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


def _tme_link(raw: str) -> str:
    """A t.me link in whatever shape it was pasted, or '' if it is not one."""
    tail = raw.strip()
    if "://" in tail:
        tail = tail.split("://", 1)[1]
    if not tail.lower().startswith(("t.me/", "telegram.me/")):
        return ""
    return f"https://{tail}"


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
                text=f"{mark}{icon} {title[:22]} · {row['brought']}",
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
    today = sum(r["brought_today"] for r in active)
    invited, confirmed = await db.referral_totals()

    body = (
        f"Каналов в подписке: <b>{len(active)}</b> из {len(rows)}\n"
        f"Привели за сутки: <b>{today}</b>"
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
        "подписку, и такой канал просто не будет никого задерживать.\n\n"
        "Нужна своя ссылка на кнопке — пришли её вторым куском:\n"
        "<code>@channel https://t.me/+AbCdEf</code>\n"
        "Пригодится для закрытого канала, заявки на вступление или ссылки, "
        "по которой рекламодатель считает свой трафик. Telegram её "
        "не перезапишет.",
        back_kb([InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan")]),
    )
    await call.answer()


@router.callback_query(F.data == "a:chan:add:bot")
async def cb_channel_add_bot(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.gate_bot)
    await _edit(
        call,
        "🤖 <b>Бот в подписку</b>\n\n"
        "Пришли <b>код или токен</b> и <b>ссылку на бота</b> в одной строке:\n"
        "<code>abc123 https://t.me/somebot</code>\n"
        "<code>8012345678:AAH… https://t.me/somebot</code>\n\n"
        "Первым куском — одно из двух:\n"
        "• <b>код BotMembers</b> от @BotMembersRobot;\n"
        "• <b>токен самого бота</b> — тогда бот спрашивают напрямую, "
        "посредник не нужен.\n\n"
        "Что именно прислали, бот поймёт сам. Ссылка нужна для кнопки, "
        "по которой пользователь туда пойдёт; название можно добавить "
        "третьим куском.\n\n"
        "⚠️ Токен — это полный доступ к чужому боту. Бери его только у того, "
        "кто сам его отдал, и помни, что он ляжет в базу.",
        back_kb([InlineKeyboardButton(text="⬅️ К каналам", callback_data="a:chan")]),
    )
    await call.answer()


@router.message(Admin.gate_bot, ~F.text.in_(kb.MENU_BUTTONS))
async def got_gate_bot(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Нужен код и ссылка через пробел.")
        return

    secret, link = parts[0].strip(), parts[1].strip()
    title = parts[2].strip() if len(parts) > 2 else ""
    method = sponsors.guess_method(secret)
    if not method:
        await message.answer(
            "Не похоже ни на код BotMembers, ни на токен бота. "
            "Код — латиница, цифры, <code>_</code> и <code>-</code>; "
            "токен — <code>123456789:AA…</code>."
        )
        return
    link = _tme_link(link)
    if not link:
        await message.answer("Ссылка должна вести на t.me/…")
        return
    if not title:
        title = "@" + link.rstrip("/").rsplit("/", 1)[-1]

    # A credential nobody answers for would let everyone through unnoticed, so
    # it is tried once, on the admin, before it goes into the gate.
    verdict = await sponsors.probe(method, secret, message.from_user.id)
    # The token is a secret and must not sit in `chat`, which every screen
    # prints. `chat` keeps the identity, `secret` keeps the credential.
    ident = secret if method == sponsors.BOTMEMBERS else title
    channel_id = await db.add_channel(
        ident, title, link, kind="bot", linked=True, method=method, secret=secret
    )
    if channel_id is None:
        await message.answer("Такой бот уже в списке.")
        return

    await state.clear()
    channel = await db.get_channel(channel_id)
    await message.answer(
        await _channel_card(message.bot, channel) + f"\n\n{verdict}",
        reply_markup=_channel_kb(channel),
    )


@router.message(Admin.channel, ~F.text.in_(kb.MENU_BUTTONS))
async def got_channel(message: Message, state: FSMContext) -> None:
    parts = (message.text or "").strip().split(maxsplit=1)
    raw = parts[0] if parts else ""
    # A second piece is a link for the button: the channel is checked by its
    # username, but a closed one is entered by an invite the admin holds.
    custom = _tme_link(parts[1]) if len(parts) > 1 else ""
    if len(parts) > 1 and not custom:
        await message.answer("Вторым куском — ссылка t.me/…, либо не присылай её.")
        return

    if raw.startswith("https://t.me/"):
        raw = "@" + raw.removeprefix("https://t.me/").strip("/")
    elif raw.startswith("t.me/"):
        raw = "@" + raw.removeprefix("t.me/").strip("/")
    if not (raw.startswith("@") or raw.lstrip("-").isdigit()):
        await message.answer("Нужен @username, ссылка t.me/… или числовой id.")
        return

    title, link = await access.describe(message.bot, raw)
    channel_id = await db.add_channel(
        raw, title, custom or link, linked=bool(custom)
    )
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
    status = await _channel_status(bot, channel["chat"], channel["kind"], channel)
    title = channel["title"] or channel["chat"]
    icon = "🤖" if channel["kind"] == "bot" else "📢"
    what = (
        sponsors.METHODS.get(channel["method"], channel["method"])
        if channel["kind"] == "bot"
        else "канал"
    )
    already = channel["joined"] - channel["brought"]
    # A token is a credential, not an identifier: `chat` never holds one, and
    # the card never prints one either.
    ident = html.escape(channel["chat"]) if channel["kind"] != "bot" else (
        html.escape(channel["chat"])
        if channel["method"] == sponsors.BOTMEMBERS
        else "токен скрыт"
    )
    return (
        f"{icon} <b>{html.escape(title)}</b> · {what}\n"
        f"<code>{ident}</code> · "
        f"{'🟢 в подписке' if channel['active'] else '⚪ выключен'}\n"
        f"Проверка: {status}\n\n"
        # Two different numbers that used to be one, and the smaller of them is
        # the honest one to show an advertiser.
        f"Привели: <b>{channel['brought']}</b> · за сутки "
        f"{channel['brought_today']}\n"
        # «Привели» never goes down; what the sponsor keeps does.
        f"Из них сейчас внутри: <b>{channel['still_in']}</b>"
        + (f" · вышли: {channel['gone']}" if channel["gone"] else "")
        + "\n"
        f"Были там до нас: {already}\n"
        f"Видели внутри всего: {channel['joined']}\n\n"
        f"Ссылка: {channel['link'] or '—'}"
        + (" · своя" if channel["linked"] else "")
        + f"\n\nКнопка у пользователя: <b>{icon} "
        f"{html.escape((channel['title'] or channel['chat'])[:28])}</b>"
        + (" · своё название" if channel["titled"] else "")
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
            text="✏️ Название кнопки", callback_data=f"a:chan:name:{channel['id']}"
        ),
        InlineKeyboardButton(
            text="🔗 Ссылка", callback_data=f"a:chan:link:{channel['id']}"
        ),
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


@router.callback_query(F.data.startswith("a:chan:name:"))
async def cb_channel_name(call: CallbackQuery, state: FSMContext) -> None:
    """The button label is what a user sees, so it is not Telegram's to decide."""
    channel_id = int(call.data.split(":")[3])
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return

    await state.set_state(Admin.channel_title)
    await state.update_data(channel_id=channel_id)
    icon = "🤖" if channel["kind"] == "bot" else "📢"
    await _edit(
        call,
        "✏️ <b>Название кнопки</b>\n\n"
        f"Сейчас: <b>{icon} "
        f"{html.escape((channel['title'] or channel['chat'])[:28])}</b>\n\n"
        "Пришли новое — до 28 знаков, значок бот подставит сам. "
        "Это то, что видит пользователь на экране подписки: "
        "«Наш спонсор», «Розыгрыши», что угодно.\n\n"
        "Своё название переживает «🔄 Обновить данные» — Telegram его "
        "не перезапишет.",
        back_kb(
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"a:chan:{channel_id}"
                )
            ]
        ),
    )
    await call.answer()


@router.message(Admin.channel_title, ~F.text.in_(kb.MENU_BUTTONS))
async def got_channel_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if not 1 <= len(title) <= 28:
        await message.answer("Название — от 1 до 28 знаков.")
        return

    channel_id = (await state.get_data())["channel_id"]
    await state.clear()
    await db.set_channel_title(channel_id, title)
    channel = await db.get_channel(channel_id)
    if channel is None:
        await message.answer("Канала уже нет.", reply_markup=back_kb())
        return
    await message.answer(
        await _channel_card(message.bot, channel), reply_markup=_channel_kb(channel)
    )


@router.callback_query(F.data.startswith("a:chan:link:"))
async def cb_channel_link(call: CallbackQuery, state: FSMContext) -> None:
    """Where the button leads — a closed channel has no link Telegram can give."""
    channel_id = int(call.data.split(":")[3])
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return

    await state.set_state(Admin.channel_link)
    await state.update_data(channel_id=channel_id)
    extra = [
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"a:chan:{channel_id}")
    ]
    if channel["linked"] and channel["kind"] != "bot":
        extra.insert(
            0,
            InlineKeyboardButton(
                text="↩️ Взять из Telegram",
                callback_data=f"a:chan:unlink:{channel_id}",
            ),
        )
    await _edit(
        call,
        "🔗 <b>Ссылка на кнопке</b>\n\n"
        f"Сейчас: {channel['link'] or '—'}"
        + (" · своя" if channel["linked"] else " · из Telegram")
        + "\n\nПришли новую — <code>https://t.me/…</code>. Годится ссылка-"
        "приглашение закрытого канала (<code>t.me/+AbCdEf</code>), заявка "
        "на вступление или ссылка, по которой рекламодатель считает свой "
        "трафик.\n\n"
        "Проверка подписки от этого не меняется: членство всё так же "
        "проверяется по каналу, ссылка — только то, куда ведёт кнопка.",
        back_kb(extra),
    )
    await call.answer()


@router.message(Admin.channel_link, ~F.text.in_(kb.MENU_BUTTONS))
async def got_channel_link(message: Message, state: FSMContext) -> None:
    link = _tme_link(message.text or "")
    if not link:
        await message.answer("Ссылка должна вести на t.me/…")
        return

    channel_id = (await state.get_data())["channel_id"]
    await state.clear()
    await db.set_channel_link(channel_id, link)
    access.drop_link_cache()
    channel = await db.get_channel(channel_id)
    if channel is None:
        await message.answer("Канала уже нет.", reply_markup=back_kb())
        return
    await message.answer(
        await _channel_card(message.bot, channel), reply_markup=_channel_kb(channel)
    )


@router.callback_query(F.data.startswith("a:chan:unlink:"))
async def cb_channel_unlink(call: CallbackQuery, state: FSMContext) -> None:
    """Hand the link back to Telegram — the next refresh fills it in again."""
    await state.clear()
    channel_id = int(call.data.split(":")[3])
    channel = await db.get_channel(channel_id)
    if channel is None:
        await call.answer("Канала уже нет.", show_alert=True)
        return

    _, link = await access.describe(call.bot, channel["chat"])
    await db.set_channel_link(channel_id, "")
    if link:
        await db.set_channel_meta(channel_id, channel["title"], link)
    access.drop_link_cache()
    await call.answer("Ссылка из Telegram")
    await _show_channel(call, channel_id)


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
                f"Автор: {await people.of(circle['uploader_id'])}\n\n"
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
            f"#анкета от {await people.of(profile['user_id'])}\n"
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
                f"Кому: {await people.of(payout['user_id'])}\n"
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
        f"{texts.circles_word(settings.get('push_free_views'))} "
        f"— не копятся, прошлый подарок сгорает\n"
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

    total_users = await db.campaign_reach()
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
    # «Занято» и «не подходит» — разные ошибки, и вторая ничего не объясняет,
    # когда человек взял код, который уже что-то значит.
    reserved = (
        code.lower().startswith(access.RESERVED)
        or access.parse_payload(code) is not None
        or access.parse_profile(code) is not None
    )
    code = access.parse_campaign(code)
    if code is None:
        await message.answer(
            "Код занят: <code>chq_…</code> — это чеки, <code>r123</code> — "
            "реферальные ссылки, <code>p123</code> — ссылки на анкеты. "
            "Возьми другой."
            if reserved
            else "Код не подходит: латиница, цифры, _ и -, до 32 знаков."
        )
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
    # A queue here means the chat is being fed at Telegram's pace, not that
    # anything is broken — but a number that keeps growing is worth seeing.
    queued = outbox.pending(chat)
    await _edit(
        call,
        f"🎬 <b>Кружочки на проверке</b>\n\nЧат: <code>{chat}</code>\n"
        f"{await _chat_status(call.bot, chat)}\n\nЖдут проверки: {waiting}"
        + (f"\nВ очереди на отправку в чат: {queued}" if queued else ""),
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
        f"Автор: {await people.of(circle['uploader_id'])}",
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
        "👤 <b>Найти пользователя</b>\n\n"
        "Пришли <b>@username</b>, имя или его кусок, id числом — "
        "или перешли сюда любое его сообщение.\n\n"
        "Если совпадений будет несколько, покажу списком.",
        back_kb(),
    )
    await call.answer()


@router.message(Admin.user_id, ~F.text.in_(kb.MENU_BUTTONS))
async def got_user_id(message: Message, state: FSMContext) -> None:
    """@username, a name, an id or a forward — whatever the admin has at hand."""
    sender = getattr(message.forward_origin, "sender_user", None)
    if sender is not None:
        await state.clear()
        text, markup = await user_card(sender.id)
        await message.answer(text, reply_markup=markup)
        return

    query = (message.text or "").strip()
    if not query:
        await message.answer("Пришли @username, имя, id или пересланное сообщение.")
        return

    found = await db.find_users(query)
    if not found:
        # A bare id is worth opening even when the person is not in the base yet.
        if query.lstrip("-").isdigit():
            await state.clear()
            text, markup = await user_card(int(query))
            await message.answer(text, reply_markup=markup)
            return
        await message.answer(
            f"Никого не нашёл по «{html.escape(query[:40])}».\n\n"
            "Имя и @username бот запоминает при первом заходе после обновления — "
            "тех, кто с тех пор не заходил, пока видно только по id."
        )
        return

    if len(found) == 1:
        await state.clear()
        text, markup = await user_card(found[0]["id"])
        await message.answer(text, reply_markup=markup)
        return

    b = InlineKeyboardBuilder()
    for row in found:
        b.row(
            InlineKeyboardButton(
                text=f"👤 {people.short(row)}"
                + (f" · {row['name'][:16]}" if row["username"] and row["name"] else ""),
                callback_data=f"a:u:card:{row['id']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await state.clear()
    await message.answer(
        f"Нашёл {len(found)} по «{html.escape(query[:40])}» — выбери:",
        reply_markup=b.as_markup(),
    )


def _tier_line(user) -> str:
    """«A++ до 03.09.2026 12:40 (осталось 5 дней)», or that there is none."""
    code = db.active_tier(user)
    if not code:
        return "нет"
    line = f"<b>{tiers.title(code)}</b> до {texts.when(user['tier_until'])}"
    left = tiers.daily_views(code)
    if left:
        line += f" · сегодня осталось {db.tier_views_left(user, left)} из {left}"
    return line


async def user_card(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await db.get_user(user_id)
    stats = await db.user_stats(user_id)
    ref_done, ref_wait = await db.referral_counts(user_id)
    sales = await db.sales_stats(user_id)
    available = await db.withdrawable(user_id)
    used = await db.spent_earnings(user_id)
    text = (
        f"👤 {people.label(user)}\n"
        f"В боте с {_since(user['created_at'])}"
        + (f" · был {_since(user['last_seen'])}" if user["last_seen"] else "")
        + "\n\n"
        f"🪙 Баланс: <b>{user['coins']}</b>\n"
        f"Тип: {kb.PREF_TITLE(user['pref'])}\n"
        f"Статус: {'🔴 забанен' if user['banned'] else '🟢 активен'}\n"
        f"Подписка: {_tier_line(user)}\n\n"
        f"👀 Просмотрено: {stats['watched']}\n"
        f"📤 Загружено: {stats['approved']} одобрено · {stats['pending']} ждут · "
        f"{stats['rejected']} отказ\n"
        f"👥 Пригласил: {ref_done}"
        + (f" (ждут подписки: {ref_wait})" if ref_wait else "")
        + (f"\nПришёл от: {await people.of(user['ref_by'])}" if user["ref_by"] else "")
        + f"\n💰 Продажи: {sales['content']} контент · {sales['contact']} личка "
        f"(+{sales['income']} 🪙)"
        # Three numbers, because «заработал 300, к выводу 50» is a support
        # ticket until it says where the other 250 went.
        + f"\n💸 Заработано за всё время: {user['earned']} · к выводу: {available}"
        + (f" · потратил в боте: {used}" if used else "")
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
    b.row(
        InlineKeyboardButton(
            text="✉️ Написать", callback_data=f"a:u:dm:{user_id}", style=kb.PRIMARY
        )
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
        call, f"Сколько монеток начислить {await people.of(user_id)}? "
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


@router.callback_query(F.data.startswith("a:u:dm:"))
async def cb_user_dm(call: CallbackQuery, state: FSMContext) -> None:
    """A message to one person, sent by the bot as its own."""
    user_id = int(call.data.split(":")[3])
    await state.set_state(Admin.dm)
    await state.update_data(dm_to=user_id)
    await _edit(
        call,
        f"✉️ <b>Сообщение для {await people.of(user_id)}</b>\n\n"
        "Пришли текст, фото, кружок — что угодно. Уйдёт от имени бота, "
        "без пометки «переслано», как обычное сообщение от него.\n\n"
        "Перед отправкой покажу, что именно уйдёт.",
        back_kb(
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"a:u:card:{user_id}"
                )
            ]
        ),
    )
    await call.answer()


@router.message(Admin.dm, ~F.text.in_(kb.MENU_BUTTONS))
async def got_dm(message: Message, state: FSMContext) -> None:
    """Nothing is sent yet: a person is on the other end, so it is shown first."""
    user_id = (await state.get_data())["dm_to"]
    await state.update_data(from_chat=message.chat.id, message_id=message.message_id)

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="✉️ Отправить", callback_data="a:u:dmgo", style=kb.SUCCESS
        )
    )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data=f"a:u:card:{user_id}", style=kb.DANGER
        )
    )
    await message.answer(
        f"Выше — то, что уйдёт {await people.of(user_id)}. Отправляем?\n\n"
        "Можно прислать другое сообщение — тогда уйдёт оно.",
        reply_markup=b.as_markup(),
    )


@router.callback_query(F.data == "a:u:dmgo")
async def cb_user_dm_go(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if "message_id" not in data or "dm_to" not in data:
        await call.answer("Нечего отправлять.", show_alert=True)
        return

    user_id = data["dm_to"]
    try:
        await call.bot.copy_message(
            chat_id=user_id,
            from_chat_id=data["from_chat"],
            message_id=data["message_id"],
        )
    except TelegramForbiddenError:
        await call.answer("Заблокировал бота", show_alert=True)
        note = "🔴 Не дошло: заблокировал бота или не запускал его."
    except TelegramAPIError as error:
        await call.answer("Не отправилось", show_alert=True)
        note = f"🔴 Не дошло: {html.escape(str(error))[:120]}"
    else:
        await call.answer("Отправлено")
        note = "🟢 Отправлено."

    text, markup = await user_card(user_id)
    await _edit(call, f"{note}\n\n{text}", markup)


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


async def _circle_card(circle) -> str:
    status = CIRCLE_STATUS.get(circle["status"], circle["status"])
    # Why it is off is half the card when it is off: without it a moderator has
    # to guess whether the last verdict was theirs or the complaints'.
    if circle["status"] == "rejected" and circle["reject_reason"]:
        status += f" · {html.escape(circle['reject_reason'])}"
    return (
        f"🎥 <b>Кружок #{circle['id']}</b>\n\n"
        f"Статус: <b>{status}</b>\n"
        f"Тип: {kb.PREF_TITLE(circle['gender'])} · {circle['duration']} сек\n"
        f"👀 {circle['views']} · 👍 {circle['likes']} / 👎 {circle['dislikes']}\n"
        f"Автор: {await people.of(circle['uploader_id']) if circle['uploader_id'] else 'архив бота'}"
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
    await message.answer(
        await _circle_card(circle), reply_markup=_circle_card_kb(circle)
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


@router.callback_query(F.data.startswith("a:c:hide:"))
async def cb_circle_hide(call: CallbackQuery) -> None:
    """Out of rotation, but still in the base — the one verdict that is undoable."""
    circle_id = int(call.data.split(":")[3])
    circle = await db.get_circle(circle_id)
    if circle is None:
        await call.answer("Кружок уже удалён.", show_alert=True)
        return

    await db.set_status(circle_id, "rejected", texts.REASON_HIDDEN)
    if circle["uploader_id"]:
        with suppress(TelegramAPIError):
            await call.bot.send_message(circle["uploader_id"], texts.CIRCLE_HIDDEN)
    await call.answer("Скрыт")
    circle = await db.get_circle(circle_id)
    await _edit(call, await _circle_card(circle), _circle_card_kb(circle))


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
    await _edit(call, await _circle_card(circle), _circle_card_kb(circle))


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
    await _edit(call, await _circle_card(circle), _circle_card_kb(circle))
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
        except TelegramRetryAfter as error:
            # Counting this as «не дошло» skipped a live user over a limit that
            # passes by itself — so wait it out and hand them the message.
            await asyncio.sleep(error.retry_after + 1)
            try:
                await bot.copy_message(
                    chat_id=user_id, from_chat_id=from_chat, message_id=message_id
                )
                sent += 1
            except TelegramAPIError:
                failed += 1
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


async def _payment_line(row) -> str:
    what = (
        f"{row['stars']} ⭐"
        if row["provider"] == "stars"
        else f"{row['amount']} {row['asset']} · {crypto.TITLES.get(row['provider'], row['provider'])}"
    )
    return (
        f"{await people.of(row['user_id'])} — {what} → {row['coins']} 🪙"
        f"{' · возвращён' if row['refunded'] else ''}\n"
        f"<code>{html.escape(row['charge_id'])}</code>"
    )


@router.callback_query(F.data == "a:pay")
async def cb_pay(call: CallbackQuery) -> None:
    rows = await db.recent_payments()
    lines = [await _payment_line(r) for r in rows]
    body = "\n\n".join(lines) if lines else "Платежей пока нет."
    totals = await db.crypto_totals()
    titles = {**crypto.TITLES, paritypay.PROVIDER: paritypay.TITLE}
    crypto_lines = "\n".join(
        f"• {titles.get(t['provider'], t['provider'])}: {t['payments']} шт · "
        f"{t['amount']:.2f} {t['asset']} → {t['coins']} 🪙"
        for t in totals
    )

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="💳 Карта", callback_data="a:card"),
        InlineKeyboardButton(text="🪙 Крипта", callback_data="a:crypto"),
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        f"💳 <b>Последние платежи</b>\n\n{body}\n\n"
        + (f"<b>Крипта за всё время</b>\n{crypto_lines}\n\n" if crypto_lines else "")
        + "Возврат: <code>/refund charge_id</code> — только для ⭐.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:card")
async def cb_card(call: CallbackQuery, state: FSMContext) -> None:
    """Whether the card checkout is actually working, without leaving the panel."""
    await state.clear()
    await call.answer()
    sample = config.STAR_PACKS[0]
    coins = settings.coins_for(sample)
    base = coins * settings.get("card_price")
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=f"💰 Копеек за монетку: {settings.get('card_price')}",
            callback_data="a:econ:k:card_price",
        )
    )
    b.row(
        InlineKeyboardButton(
            text=f"➕ Надбавка: {settings.get('card_fee')}%",
            callback_data="a:econ:k:card_fee",
        )
    )
    on = bool(settings.get("subs_recurring"))
    b.row(
        InlineKeyboardButton(
            text=f"🔁 Автопродление подписок: {'🟢 вкл' if on else '⚪ выкл'}",
            callback_data="a:card:subs",
            style=kb.SUCCESS if on else None,
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ К платежам", callback_data="a:pay"))
    subs = await db.tier_subs_totals()
    await _edit(
        call,
        "💳 <b>Оплата картой</b>\n\n"
        f"ParityPay: {await paritypay.check_key()}\n\n"
        f"🔁 Автопродление: <b>{'включено' if on else 'выключено'}</b> · "
        f"активных {subs['active']}, ждут оплаты {subs['waiting']}\n"
        "Списания идут через СБП — процессинг умеет повторять только их. "
        "Включать только после согласования подписок с менеджером ParityPay: "
        "до этого счёт с подпиской просто не создастся.\n\n"
        f"Цена: {settings.get('card_price')} коп. за монетку "
        f"+ {settings.get('card_fee')}%\n"
        f"{coins} монеток: {base // 100}.{base % 100:02d} ₽ → "
        f"<b>{settings.card_rubles(coins)} ₽</b> к оплате\n"
        f"Счёт живёт {config.INVOICE_TTL // 60} мин, проверка каждые "
        f"{int(config.INVOICE_POLL)} сек\n\n"
        "Надбавка на кнопке у пользователя показана процентом, отдельной "
        "строкой в счёте не расписывается — платёжная форма показывает итог.\n\n"
        "Ключи задаются в <code>.env</code>: <code>PARITYPAY_SHOP_ID</code> "
        "(UUID кассы) и <code>PARITYPAY_SECRET</code> (ключ №1). Без них "
        "способ не показывается покупателю.",
        b.as_markup(),
    )


@router.callback_query(F.data == "a:card:subs")
async def cb_card_subs(call: CallbackQuery, state: FSMContext) -> None:
    """The switch that waits on ParityPay's own approval."""
    on = not settings.get("subs_recurring")
    await settings.set("subs_recurring", int(on))
    logger.warning(
        "автопродление подписок %s (%s)",
        "включено" if on else "выключено",
        call.from_user.id,
    )
    await cb_card(call, state)  # redraws the screen, and answers the tap


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
    parity = settings.crypto_parity()
    if settings.get("usdt_rate") != parity:
        b.row(
            InlineKeyboardButton(
                text=f"⚖️ Выровнять по звёздам: {parity}",
                callback_data="a:crypto:parity",
                style=kb.SUCCESS,
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ К платежам", callback_data="a:pay"))
    await _edit(
        call,
        "🪙 <b>Оплата криптой</b>\n\n"
        + "\n".join(lines)
        + f"\n\nВалюта счетов: <b>{crypto.asset()}</b>\n"
        f"Цена: {settings.get('usdt_rate')} монеток за 1 {crypto.asset()}\n"
        f"{_parity_line()}\n"
        f"Счёт живёт {config.INVOICE_TTL // 60} мин, проверка каждые "
        f"{int(config.INVOICE_POLL)} сек\n\n"
        f"Проверка счетов: {watcher}\n"
        f"Счета: открыто {totals['open']} · оплачено {totals['paid']} · "
        f"просрочено {totals['expired']} · отменено {totals['cancelled']}\n\n"
        "Ключи задаются в <code>.env</code>: <code>CRYPTOBOT_TOKEN</code>, "
        "<code>XROCKET_KEY</code>. Без ключа способ не показывается покупателю.",
        b.as_markup(),
    )


def _parity_line() -> str:
    """The same basket priced both ways, because only the cheaper door gets used."""
    pack = config.STAR_PACKS[0]
    coins = settings.coins_for(pack)
    in_stars = settings.usd_of_stars(pack)
    in_crypto = float(crypto.price(coins))
    gap = settings.crypto_gap()
    if not gap:
        mark = "🔴 курс не задан"
    elif gap < 0.8:
        mark = "🔴 криптой сильно дешевле — за ⭐ покупать никто не станет"
    elif gap > 1.25:
        mark = "🟡 криптой заметно дороже — способом не пользуются"
    else:  # within a fifth either way is close enough
        mark = "🟢 цены сходятся"
    return (
        f"{mark}\n"
        f"{coins} монеток: {pack} ⭐ ≈ ${in_stars:.2f} · "
        f"криптой ${in_crypto:.2f} (курс ⭐: {settings.get('stars_per_usd')} за $1)"
    )


@router.callback_query(F.data == "a:crypto:parity")
async def cb_crypto_parity(call: CallbackQuery, state: FSMContext) -> None:
    """One tap to put the crypto price back where the star price is."""
    await settings.set("usdt_rate", settings.crypto_parity())
    await cb_crypto(call, state)  # redraws the screen, and answers the tap


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
    await state.clear()
    text, markup = _settings_screen()  # the toggle stays where it was pressed
    await _edit(call, text, markup)


# --- commands (kept for muscle memory) -----------------------------------


@router.message(Command("stats"))
async def stats_cmd(message: Message) -> None:
    d = await db.dashboard()
    await message.answer(
        f"👤 {d['users']} · 🎞 {d['approved']}/{d['pending']} · "
        f"👀 {d['views']} · ⭐ {d['stars']}"
    )


async def _who_from(raw: str, message: Message) -> int | None:
    """id or @username in a command; complains to the admin when it is neither."""
    raw = raw.strip()
    if raw.lstrip("-").isdigit():
        return int(raw)
    found = await db.find_users(raw, limit=2)
    if len(found) == 1:
        return found[0]["id"]
    if not found:
        await message.answer(f"Не нашёл «{html.escape(raw[:40])}».")
    else:
        await message.answer(
            f"По «{html.escape(raw[:40])}» подходит несколько — уточни или дай id: "
            + ", ".join(f"<code>{r['id']}</code>" for r in found)
        )
    return None


@router.message(Command("give"))
async def give_cmd(message: Message, command: CommandObject) -> None:
    parts = (command.args or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.answer("/give &lt;id или @username&gt; &lt;coins&gt;")
        return
    user_id = await _who_from(parts[0], message)
    if user_id is None:
        return
    await db.add_coins(user_id, int(parts[1]))
    text, markup = await user_card(user_id)
    await message.answer(text, reply_markup=markup)


@router.message(Command("ban", "unban"))
async def ban_cmd(message: Message, command: CommandObject) -> None:
    if not (command.args or "").strip():
        await message.answer(f"/{command.command} &lt;id или @username&gt;")
        return
    user_id = await _who_from(command.args, message)
    if user_id is None:
        return
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
            text=f"🎬 Показ раз в {settings.get('promo_every_circles')} кружков",
            callback_data="a:econ:k:promo_every_circles",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    return b.as_markup()


async def _posts_home_text() -> str:
    stats = await db.post_stats()
    on = bool(settings.get("promo_enabled"))
    every = settings.get("promo_every_circles")
    watch = await db.watch_sessions()

    # The rate is only guessable from how much people actually watch at a
    # sitting, so the numbers to guess it from sit next to the setting.
    if watch["sessions"]:
        tail = (
            "\n\n📊 <b>Сколько смотрят за раз</b> (7 дней, перерыв 30 мин)\n"
            f"Сессий: <b>{watch['sessions']}</b>\n"
            f"Обычно: <b>{watch['median']}</b> кружков · в среднем {watch['avg']}\n"
            f"Активные (топ 10%): от {watch['p90']} · рекорд {watch['longest']}\n"
            f"Дойдут до показа при {every}: <b>{watch['reach']}%</b> сессий"
        )
    else:
        tail = "\n\n📊 Кружочков за неделю не смотрели — по чему считать, пока нет."

    return (
        "📰 <b>Посты</b>\n\n"
        "<b>👋 Приветка</b> — показывается один раз, сразу после /start.\n"
        f"<b>🔁 Показ</b> — рекламная пауза в ленте: каждый {every}-й кружок, "
        "сразу после него.\n\n"
        f"Активных приветок: <b>{stats['welcome']}</b> · "
        f"показов: <b>{stats['promo']}</b> "
        f"({'🟢 включены' if on else '🔴 выключены'})\n"
        f"Всего показано: {stats['shown']}"
        + tail
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
        f"<b>{posts.PLURALS[kind]}</b>\n\n{what}\n\n"
        + (
            "🟢 — работает, ⚪ — выключено. Цифра — сколько раз показано."
            if rows
            else "Пока пусто."
        ),
        _post_list_kb(kind, rows),
    )


POST_CARD_MAX = 600  # formatted post text the card will show in full


@router.callback_query(F.data.startswith("a:post:add:"))
async def cb_post_add(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.split(":")[3]
    await state.set_state(Admin.post)
    await state.update_data(kind=kind)
    await _edit(
        call,
        f"➕ <b>Новый пост · {posts.KINDS[kind].lower()}</b>\n\n"
        "Пришли сюда сам пост — текстом, фото, видео, кружком, чем угодно. "
        "Можно переслать готовый из канала.\n\n"
        "Бот покажет его пользователям точной копией. Кнопки-ссылки "
        "переносятся вместе с постом; кнопки, которые что-то делают внутри "
        "чужого бота, Telegram при пересылке отбрасывает сам. Сообщение "
        "должно остаться в этом чате — бот копирует его отсюда каждый раз.",
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
    # The formatted title keeps custom emoji looking like themselves; the plain
    # one is what goes on a button, where no markup is rendered anyway.
    rich = ""
    if message.text or message.caption:
        rich = message.html_text.strip().replace("\n", " ")
    post_id = await db.add_post(
        kind,
        message.chat.id,
        message.message_id,
        title[:60] or "без текста",
        markup=posts.keep_markup(message.reply_markup),
        # Kept whole or not at all: cutting formatted text mid-tag would send
        # the card back as «can't parse entities». A post longer than this
        # falls back to the plain title, which is only ever the first line.
        title_html=rich if len(rich) <= POST_CARD_MAX else "",
    )
    post = await db.get_post(post_id)
    if kind == posts.PROMO:
        # Asked right here rather than left to a menu: a promo without it keeps
        # being shown to people who already went where it sends them.
        await state.set_state(Admin.post_sponsor)
        await state.update_data(post_id=post_id)
        await message.answer(
            "✅ Сохранено и уже работает.\n\n" + _post_card(post) + "\n\n"
            + SPONSOR_ASK,
            reply_markup=_sponsor_ask_kb(post_id),
        )
        return
    await message.answer(
        # Neutral on purpose: «Показ сохранена» is what agreeing with one of
        # the two kind names gets you.
        "✅ Сохранено и уже работает.\n\n" + _post_card(post),
        reply_markup=_post_kb(post),
    )


SPONSOR_ASK = (
    "🤖 <b>Чей это бот?</b>\n\n"
    "Пришли <b>код BotMembers</b> или <b>токен рекламируемого бота</b> — "
    "одним сообщением. По нему бот поймёт, что человек уже дошёл до рекламы, "
    "и перестанет показывать ему этот пост.\n\n"
    "Без этого пост будет крутиться всем подряд, включая тех, кто уже "
    "перешёл.\n\n"
    "⚠️ Токен — это полный доступ к чужому боту. Бери его только у того, кто "
    "сам его отдал."
)


def _sponsor_ask_kb(post_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="Пропустить — показывать всем",
            callback_data=f"a:post:one:{post_id}",
        )
    )
    return b.as_markup()


@router.callback_query(F.data.startswith("a:post:spon:"))
async def cb_post_sponsor(call: CallbackQuery, state: FSMContext) -> None:
    """Attach or replace the advertised bot on a post that already exists."""
    post_id = int(call.data.split(":")[3])
    await state.set_state(Admin.post_sponsor)
    await state.update_data(post_id=post_id)
    await _edit(call, SPONSOR_ASK, _sponsor_ask_kb(post_id))
    await call.answer()


@router.callback_query(F.data.startswith("a:post:unspon:"))
async def cb_post_unsponsor(call: CallbackQuery, state: FSMContext) -> None:
    post_id = int(call.data.split(":")[3])
    await state.clear()
    await db.set_post_sponsor(post_id, "", "", "")
    await call.answer("Отвязан")
    await _show_post(call, post_id)


@router.message(Admin.post_sponsor, ~F.text.in_(kb.MENU_BUTTONS))
async def got_post_sponsor(message: Message, state: FSMContext) -> None:
    secret = (message.text or "").strip()
    method = sponsors.guess_method(secret)
    if not method:
        await message.answer(
            "Не похоже ни на код BotMembers, ни на токен бота. "
            "Код — латиница, цифры, <code>_</code> и <code>-</code>; "
            "токен — <code>123456789:AA…</code>."
        )
        return

    post_id = (await state.get_data())["post_id"]
    verdict = await sponsors.probe(method, secret, message.from_user.id)
    name = ""
    if method == sponsors.TOKEN:
        with suppress(sponsors.SponsorError):
            name = await sponsors.whoami(secret)
    await state.clear()
    await db.set_post_sponsor(post_id, method, secret, name)
    post = await db.get_post(post_id)
    await message.answer(
        _post_card(post) + f"\n\n{verdict}", reply_markup=_post_kb(post)
    )


def _sponsor_line(post, converted: int) -> str:
    """Whose bot the promo sends people to, and how many already went.

    A welcome post has nowhere to send anyone, so it says nothing at all.
    """
    if post["kind"] != posts.PROMO:
        return ""
    if not post["sponsor_method"]:
        return "\n⚠️ Бот не привязан — показывается всем, включая перешедших"
    who = post["sponsor_name"] or sponsors.METHODS.get(
        post["sponsor_method"], post["sponsor_method"]
    )
    return (
        f"\n🤖 Реклама: {html.escape(who)} · "
        f"{sponsors.METHODS.get(post['sponsor_method'], '')}\n"
        f"Уже перешли и больше не увидят: <b>{converted}</b>"
    )


def _post_card(post, converted: int = 0) -> str:
    # The formatted title when it was saved whole, the escaped plain one when it
    # had to be cut — a truncated html_text would arrive with a tag sliced open.
    body = post["title_html"] or html.escape(post["title"])
    labels = posts.buttons_of(post)
    if labels:
        buttons = "\n🔘 Кнопки: " + " · ".join(html.escape(t) for t in labels)
    elif post["markup"] == posts.UNRECORDED:
        # Saved back when copies went out button-less. Nothing to restore from,
        # so the only honest thing is to say it and let the admin decide.
        buttons = "\n⚠️ Кнопки этого поста не сохранены — если они были, добавь пост заново"
    else:
        buttons = ""
    return (
        f"{'👋' if post['kind'] == posts.WELCOME else '🔁'} "
        f"<b>{posts.KINDS[post['kind']]} #{post['id']}</b> · "
        f"{'🟢 работает' if post['active'] else '⚪ выключен'}\n\n"
        f"{body}{buttons}\n\n"
        f"Показан: <b>{post['shown']}</b> раз"
        + _sponsor_line(post, converted)
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
    if post["kind"] == posts.PROMO:
        b.row(
            InlineKeyboardButton(
                text=(
                    "🤖 Сменить бота" if post["sponsor_method"] else "🤖 Привязать бота"
                ),
                callback_data=f"a:post:spon:{post['id']}",
                style=None if post["sponsor_method"] else kb.PRIMARY,
            )
        )
        if post["sponsor_method"]:
            b.row(
                InlineKeyboardButton(
                    text="🔓 Отвязать бота",
                    callback_data=f"a:post:unspon:{post['id']}",
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
    await _edit(
        call, _post_card(post, await db.conversions(post_id)), _post_kb(post)
    )


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
            reply_markup=posts.markup_of(post),
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
        "<b>🧹 Чистка по файлу</b> — присылаешь список мёртвых, который отдал "
        "BotSafe, и они уходят из базы.\n\n"
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
    b.row(
        InlineKeyboardButton(
            text="🧹 Чистка по файлу", callback_data="a:bs:dead", style=kb.DANGER
        )
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
        f"Уйдёт <b>{total}</b> Telegram id в @BotSafeRobot. Прогресс и "
        "результат придут тебе в личку от него.\n\n"
        "Одновременно у бота может идти только одна проверка.",
        _confirm_kb("a:bs:safe:go"),
    )
    await call.answer()


@router.callback_query(F.data == "a:bs:safe:go")
async def cb_botsafe_go(call: CallbackQuery) -> None:
    await call.answer("Отправляю…")
    ids = await db.all_user_ids()
    try:
        result = await botstat.to_botsafe(ids, call.from_user.id, hide=False)
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


# --- sweeping out users who blocked the bot ------------------------------

DEAD_MAX_BYTES = 5 * 1024 * 1024  # a list this long is not a list of ids
_ID = re.compile(r"-?\d{5,}")  # a telegram id, whatever else shares its line


def _dead_ids(raw: bytes) -> list[int]:
    """Every id in the file, whatever the columns around it look like.

    BotSafe sends one id per line, but a list that has been through a
    spreadsheet on the way comes back with commas and quotes around it.
    """
    text = raw.decode("utf-8", errors="ignore")
    return [int(found) for found in _ID.findall(text)]


@router.callback_query(F.data == "a:bs:dead")
async def cb_dead_ask(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Admin.dead_file)
    await _edit(
        call,
        "🧹 <b>Чистка по файлу</b>\n\n"
        "Пришли файл со списком мёртвых — тот, что отдаёт @BotSafeRobot. "
        "Годится любой текстовый: id по одному в строке, лишние колонки "
        "бот пропустит сам.\n\n"
        "Сразу ничего не удалится — сначала покажу, что нашлось в базе.",
        back_kb(
            [InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]
        ),
    )
    await call.answer()


@router.message(Admin.dead_file, F.document)
async def got_dead_file(message: Message, state: FSMContext) -> None:
    document = message.document
    if document.file_size and document.file_size > DEAD_MAX_BYTES:
        await message.answer(
            f"Файл больше {DEAD_MAX_BYTES // 1024 // 1024} МБ — это уже не список id."
        )
        return

    try:
        buffer = await message.bot.download(document)
    except TelegramAPIError as error:
        await message.answer(f"Не смог скачать файл: {html.escape(str(error))[:120]}")
        return

    ids = _dead_ids(buffer.read())
    if not ids:
        await message.answer(
            "В файле не нашлось ни одного id. Нужен текстовый список чисел."
        )
        return

    listed = await db.stage_dead(ids)
    found = await db.dead_preview()
    await state.clear()

    if not found["found"]:
        await message.answer(
            f"В файле {listed} id, но в базе из них нет никого — чистить нечего.",
            reply_markup=back_kb(
                [InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]
            ),
        )
        return

    goes = found["found"] - found["keepers"]
    b = InlineKeyboardBuilder()
    if goes:
        b.row(
            InlineKeyboardButton(
                text=f"🧹 Удалить {goes}",
                callback_data="a:bs:dead:go",
                style=kb.DANGER,
            )
        )
    if found["keepers"]:
        b.row(
            InlineKeyboardButton(
                text=f"🗑 Удалить всех {found['found']}, вместе с авторами",
                callback_data="a:bs:dead:all",
                style=kb.DANGER,
            )
        )
    b.row(
        InlineKeyboardButton(
            text="⬅️ Отмена", callback_data="a:botstat", style=kb.PRIMARY
        )
    )

    await message.answer(
        f"🧹 <b>Чистка базы</b>\n\n"
        f"В файле: <b>{listed}</b> id\n"
        f"Из них есть в базе: <b>{found['found']}</b>\n"
        f"Под удаление сейчас: <b>{goes}</b>\n"
        f"Придержу: {found['keepers']}\n\n"
        "Придерживаю тех, у кого есть кружочки, анкета или открытая заявка "
        "на вывод — без их строки контент осиротеет, а деньги потеряют "
        "получателя. Вторая кнопка снимает и это: анкета удаляется, кружочки "
        "снимаются с показа.\n\n"
        f"Сгорит монеток на руках: {found['coins']}"
        + (f"\nСреди них подписок в силе: {found['subs']}" if found["subs"] else "")
        + "\n\nПлатежи, выплаты и покупки остаются — это история, а не мусор. "
        "Отчёты по рекламным ссылкам тоже: приход считается по переходам, "
        "а они никуда не денутся.",
        reply_markup=b.as_markup(),
    )


@router.message(Admin.dead_file, ~F.text.in_(kb.MENU_BUTTONS))
async def dead_not_a_file(message: Message) -> None:
    await message.answer("Нужен файл документом, а не текстом.")


@router.callback_query(F.data.in_({"a:bs:dead:go", "a:bs:dead:all"}))
async def cb_dead_go(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    keep_authors = call.data == "a:bs:dead:go"
    await call.answer("Чищу…")
    result = await db.sweep_dead(keep_authors=keep_authors)
    await _edit(
        call,
        f"🟢 <b>Готово</b>\n\nУдалено: <b>{result['deleted']}</b>\n"
        f"Осталось из списка: {result['kept']}"
        + ("" if keep_authors else "\n\nАнкеты удалены, кружочки сняты с показа."),
        back_kb(
            [InlineKeyboardButton(text="⬅️ К BotStat", callback_data="a:botstat")]
        ),
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

# Referrals are bought traffic like any other, so the screens answer the same
# questions an ad link does — and split by question rather than piling every
# number onto one wall.

REF_WINDOWS = ((0, "всё время"), (86400, "сутки"), (604800, "неделя"), (2592000, "месяц"))
REF_ORDERS = (
    ("confirmed", "дошли"),
    ("invited", "привели"),
    ("alive", "живые"),
)
REF_PAGE = 8


def _pct_of(part: int, whole: int) -> str:
    return f"{part * 100 / whole:.1f}%" if whole else "—"


def _since(stamp: int) -> str:
    if not stamp:
        return "—"
    days = int((time.time() - stamp) // 86400)
    if days > 1:
        return f"{days} дн назад"
    return _ago(stamp)


def _bar(part: int, whole: int, width: int = 10) -> str:
    """A conversion is easier to feel than to read off a percentage."""
    filled = round(part / whole * width) if whole else 0
    return "█" * filled + "░" * (width - filled)


def _refs_nav(active: str) -> list[InlineKeyboardButton]:
    tabs = (("a:refs", "📊 Сводка"), ("a:refs:top:0:confirmed:0", "🏆 Топ"),
            ("a:refs:bad", "⚠️ Накрутка"))
    return [
        InlineKeyboardButton(
            text=("• " + title if data.startswith(active) else title),
            callback_data=data,
        )
        for data, title in tabs
    ]


async def _refs_summary(call: CallbackQuery) -> None:
    d = await db.referral_overview()
    reward = settings.get("ref_reward")
    invited, confirmed = d["invited"], d["confirmed"]

    b = InlineKeyboardBuilder()
    b.row(*_refs_nav("a:refs"))
    b.row(
        InlineKeyboardButton(
            text=f"🎁 Награда за друга: {reward}",
            callback_data="a:econ:k:ref_reward",
        )
    )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))
    await _edit(
        call,
        "👥 <b>Рефералы</b>\n\n"
        f"Пришло по ссылкам: <b>{invited}</b>\n"
        f"Дошли до конца: <b>{confirmed}</b> · {_pct_of(confirmed, invited)}\n"
        f"{_bar(confirmed, invited)}\n"
        f"Застряли на подписке: {d['waiting']}\n"
        f"Роздано наград: ~{confirmed * reward} 🪙 по текущей ставке\n\n"
        "📅 <b>Пришло → дошли</b>\n"
        f"Сутки: <b>{d['day_invited']}</b> → {d['day_confirmed']} "
        f"({_pct_of(d['day_confirmed'], d['day_invited'])})\n"
        f"Неделя: <b>{d['week_invited']}</b> → {d['week_confirmed']} "
        f"({_pct_of(d['week_confirmed'], d['week_invited'])})\n"
        f"Месяц: <b>{d['month_invited']}</b> → {d['month_confirmed']} "
        f"({_pct_of(d['month_confirmed'], d['month_invited'])})\n\n"
        "🧑‍🤝‍🧑 <b>Рефоводы</b>\n"
        f"Всего: <b>{d['referrers']}</b> · привели 3+: {d['with_three']} · "
        f"10+: {d['with_ten']}\n"
        f"Рекорд одного: {d['best']}\n\n"
        "🎯 <b>Качество приведённых</b>\n"
        f"Приняли правила: {d['accepted']} ({_pct_of(d['accepted'], invited)})\n"
        f"Заходили за неделю: {d['alive']} ({_pct_of(d['alive'], invited)})\n"
        f"Платили: {d['payers']} ({_pct_of(d['payers'], invited)})\n"
        f"В бане: {d['banned']} ({_pct_of(d['banned'], invited)})",
        b.as_markup(),
    )


@router.callback_query(F.data == "a:refs")
async def cb_refs(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _refs_summary(call)
    await call.answer()


@router.callback_query(F.data.startswith("a:refs:top:"))
async def cb_refs_top(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, _, raw_window, order, raw_page = call.data.split(":")
    window, page = int(raw_window), int(raw_page)
    rows = await db.top_referrers(
        limit=REF_PAGE, offset=page * REF_PAGE, window=window, order=order
    )
    total = await db.count_referrers(window)
    pages = max(1, -(-total // REF_PAGE))

    b = InlineKeyboardBuilder()
    b.row(*_refs_nav("a:refs:top"))
    # Period and sorting are one tap each, and the active one is marked.
    b.row(
        *[
            InlineKeyboardButton(
                text=("• " + name if seconds == window else name),
                callback_data=f"a:refs:top:{seconds}:{order}:0",
            )
            for seconds, name in REF_WINDOWS
        ]
    )
    b.row(
        *[
            InlineKeyboardButton(
                text=("• " + name if key == order else name),
                callback_data=f"a:refs:top:{window}:{key}:0",
            )
            for key, name in REF_ORDERS
        ]
    )
    for place, row in enumerate(rows, page * REF_PAGE + 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(place, f"{place}.")
        b.row(
            InlineKeyboardButton(
                text=f"{medal} {people.short(row)} · {row['confirmed']}/{row['invited']}",
                callback_data=f"a:refs:u:{row['user_id']}",
            )
        )
    if pages > 1:
        nav = []
        if page:
            nav.append(
                InlineKeyboardButton(
                    text="⬅️", callback_data=f"a:refs:top:{window}:{order}:{page - 1}"
                )
            )
        nav.append(
            InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="a:refs:noop")
        )
        if page + 1 < pages:
            nav.append(
                InlineKeyboardButton(
                    text="➡️", callback_data=f"a:refs:top:{window}:{order}:{page + 1}"
                )
            )
        b.row(*nav)
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))

    lines = []
    for place, row in enumerate(rows, page * REF_PAGE + 1):
        lines.append(
            f"{place}. {people.label(row)}\n"
            f"    дошли <b>{row['confirmed']}</b> из {row['invited']} · "
            f"живых {row['alive']}"
            + (f" · 🔴 {row['banned']}" if row["banned"] else "")
        )
    window_name = dict(REF_WINDOWS)[window]
    order_name = dict(REF_ORDERS)[order]
    await _edit(
        call,
        f"🏆 <b>Топ рефоводов</b> · {window_name} · по «{order_name}»\n\n"
        + ("\n\n".join(lines) if lines else "Пока никто никого не привёл.")
        + f"\n\nВсего рефоводов за период: {total}. "
        "Жми на строку — откроется рефовод.",
        b.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data == "a:refs:noop")
async def cb_refs_noop(call: CallbackQuery) -> None:
    await call.answer()


@router.callback_query(F.data == "a:refs:bad")
async def cb_refs_bad(call: CallbackQuery, state: FSMContext) -> None:
    """Volume without result — what farming looks like from the outside."""
    await state.clear()
    rows = await db.suspect_referrers(10)

    b = InlineKeyboardBuilder()
    b.row(*_refs_nav("a:refs:bad"))
    for row in rows:
        b.row(
            InlineKeyboardButton(
                text=f"⚠️ {people.short(row)} · живых {row['alive']}/{row['invited']}",
                callback_data=f"a:refs:u:{row['user_id']}",
            )
        )
    b.row(InlineKeyboardButton(text="⬅️ В панель", callback_data="a:home"))

    lines = [
        f"• {people.label(row)}\n"
        f"    привёл {row['invited']} · живых {row['alive']} "
        f"({_pct_of(row['alive'], row['invited'])}) · правила приняли "
        f"{row['accepted']}"
        + (f" · 🔴 {row['banned']}" if row["banned"] else "")
        for row in rows
    ]
    await _edit(
        call,
        "⚠️ <b>Похоже на накрутку</b>\n\n"
        + (
            "\n\n".join(lines)
            if lines
            else "Никого подозрительного: у всех рефоводов приведённые живые."
        )
        + "\n\nСюда попадают те, кто привёл 5+ человек, из которых за неделю "
        "заходили меньше четверти. Это не приговор — но повод посмотреть.",
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
        if guest["banned"]:
            mark = "🔴 бан"
        elif not guest["accepted"]:
            mark = "не принял правила"
        elif not guest["ref_credited"]:
            mark = "не прошёл ОП"
        elif guest["last_seen"] > time.time() - 604800:
            mark = "🟢 активен"
        else:
            mark = "молчит"
        lines.append(f"• {people.label(guest)} · {_since(guest['created_at'])} · {mark}")

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text="👤 Карточка пользователя", callback_data=f"a:u:card:{user_id}"
        )
    )
    b.row(
        InlineKeyboardButton(text="⬅️ К топу", callback_data="a:refs:top:0:confirmed:0"),
        InlineKeyboardButton(text="📊 Сводка", callback_data="a:refs"),
    )
    await _edit(
        call,
        f"👤 <b>Рефовод</b>\n{await people.of(user_id)}\n\n"
        f"Привёл: <b>{invited}</b> · дошли: <b>{d['confirmed']}</b> "
        f"({_pct_of(d['confirmed'], invited)})\n"
        f"{_bar(d['confirmed'], invited)}\n"
        f"За сутки: {d['day']} · за неделю: {d['week']}\n"
        f"Первый: {_since(d['first_at'])} · последний: {_since(d['last_at'])}\n\n"
        f"Приняли правила: {d['accepted']} ({_pct_of(d['accepted'], invited)})\n"
        f"Заходили за неделю: {d['alive']} ({_pct_of(d['alive'], invited)}) · "
        f"в бане: {d['banned']}\n\n"
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
