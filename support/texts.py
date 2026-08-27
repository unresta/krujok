"""Topics, self-service answers and every message the support bot sends.

The self-service step is the point of the topic screen: half of what arrives
("how long is moderation", "why can't I forward a circle") is already answered
in the main bot's FAQ, and answering it without a human is faster for everyone.
Only after that screen does the form open.
"""

import time

from config import TEXT_MAX

# code -> (button label, card label). The code goes into tickets.topic.
TOPICS: dict[str, tuple[str, str]] = {
    "pay": ("💳 Оплата и звёзды", "💳 Оплата"),
    "coins": ("🪙 Монетки и баланс", "🪙 Монетки"),
    "anketa": ("👤 Анкета", "👤 Анкета"),
    "circle": ("🎞 Кружок", "🎞 Кружок"),
    "payout": ("💸 Вывод заработка", "💸 Вывод"),
    "other": ("❓ Другое", "❓ Другое"),
}

STATUS_LABEL = {
    "open": "🟡 ждёт ответа",
    "taken": "🔵 в работе",
    "answered": "🟢 ответили",
    "closed": "⚪ закрыт",
}


def topic_label(code: str) -> str:
    return TOPICS.get(code, TOPICS["other"])[1]


def status_label(code: str) -> str:
    return STATUS_LABEL.get(code, code)


# --- self-service: what the user reads before writing --------------------

HINTS: dict[str, str] = {
    "pay": (
        "💳 <b>Оплата и звёзды</b>\n\n"
        "• <b>Списались звёзды, а монетки не пришли.</b> Обычно это задержка на "
        "минуту-две. Проверь баланс в «Профиле» — если монеток так и нет, "
        "напиши нам и <b>приложи скриншот чека</b> из Telegram.\n"
        "• <b>Где найти чек.</b> Настройки Telegram → «Мои звёзды» → история. "
        "Оттуда же виден номер платежа.\n"
        "• <b>Можно ли вернуть звёзды.</b> Да, возврат делает админ вручную — "
        "напиши, за какой платёж."
    ),
    "coins": (
        "🪙 <b>Монетки и баланс</b>\n\n"
        "• <b>Куда уходят монетки.</b> Просмотр кружка стоит несколько монеток; "
        "цена показана в «Правилах и FAQ» главного бота.\n"
        "• <b>Как получить бесплатно.</b> Бонус новичку, подписка на канал и "
        "приглашённые друзья по твоей ссылке из раздела «Рефералы».\n"
        "• <b>Не начислили за друга.</b> Реферал считается только после того, "
        "как друг подпишется на канал. Если он подписан, а монеток нет — "
        "напиши и укажи его id."
    ),
    "anketa": (
        "👤 <b>Анкета</b>\n\n"
        "• <b>Сколько ждать проверку.</b> Обычно недолго; анкету смотрит "
        "модератор вручную.\n"
        "• <b>Анкету отклонили.</b> Причину пишут в сообщении. Чаще всего это "
        "чужое фото, нарушение правил или пустое описание — исправь и отправь "
        "заново кнопкой «Заполнить заново».\n"
        "• <b>Кто увидит мои данные.</b> Только фото и описание. Имя и "
        "@username не показываются; @username уходит покупателю лишь если ты "
        "сам включил продажу лички."
    ),
    "circle": (
        "🎞 <b>Кружок</b>\n\n"
        "• <b>Кружок не приняли.</b> Либо короче минимума, либо такой уже есть "
        "в базе, либо модератор счёл его нарушающим правила.\n"
        "• <b>Нужна анкета.</b> Загружать можно только с одобренной анкетой — "
        "через неё зритель тебя находит.\n"
        "• <b>За загрузку не начислили монетки.</b> Так и задумано: платят "
        "продажи доступа, а не сама загрузка."
    ),
    "payout": (
        "💸 <b>Вывод заработка</b>\n\n"
        "• <b>Сколько ждать.</b> Заявку закрывает админ вручную, выплата идёт "
        "вне бота.\n"
        "• <b>Выводится не всё.</b> Только заработанные монетки. Купленные за "
        "звёзды и бонусы вывести нельзя.\n"
        "• <b>Ошибся в реквизитах.</b> Напиши нам номер заявки — отклоним, "
        "монетки вернутся на баланс, и можно создать новую."
    ),
    "other": (
        "❓ <b>Другое</b>\n\n"
        "Опиши проблему своими словами: что делал, что ожидал и что получилось. "
        "Если есть скриншот — приложи, это ускоряет разбор в разы."
    ),
}


def hint(topic: str) -> str:
    return HINTS.get(topic, HINTS["other"])


# --- user side -----------------------------------------------------------

START = (
    "🛠 <b>Поддержка Krujok</b>\n\n"
    "Здесь помогают с оплатой, монетками, анкетой и выводом.\n\n"
    "Опиши проблему — ответит живой человек. Кнопки внизу."
)

CHOOSE_TOPIC = (
    "С чем нужна помощь?\n\n"
    "Выбери тему — так мы ответим быстрее и точнее."
)


def ask_text(topic: str) -> str:
    return (
        f"{topic_label(topic)}\n\n"
        "Опиши, что случилось, одним сообщением.\n"
        f"Можно приложить скриншот, фото или видео — до {TEXT_MAX} символов текста."
    )


TEXT_TOO_LONG = (
    f"Слишком длинно. Уложись в {TEXT_MAX} символов "
    "или пришли главное, детали обсудим в переписке."
)

TEXT_TOO_SHORT = (
    "Слишком коротко — по такому описанию не понять проблему.\n"
    "Напиши, что делал и что пошло не так."
)


def created(ticket_id: int) -> str:
    return (
        f"🟢 <b>Обращение #{ticket_id} принято</b>\n\n"
        "Ответит живой человек — придёт сюда же, в этот чат.\n"
        "Можешь дописать детали: всё, что пришлёшь, попадёт в это обращение."
    )


def added(ticket_id: int) -> str:
    return f"➕ Добавлено к обращению <b>#{ticket_id}</b>."


def already_open(ticket_id: int) -> str:
    return (
        f"У тебя уже открыто обращение <b>#{ticket_id}</b>.\n\n"
        "Просто напиши сюда — сообщение добавится к нему.\n"
        "Если вопрос уже решился, закрой его — и можно создать новое."
    )


def self_closed(ticket_id: int) -> str:
    """Confirmation for a user who closed their own ticket."""
    return (
        f"⚪ Обращение <b>#{ticket_id}</b> закрыто.\n\n"
        "Спасибо, что сказал — теперь мы не будем тратить на него время.\n"
        "Понадобится помощь — создавай новое, лимит освободился."
    )


SELF_CLOSE_ALREADY = "Это обращение уже закрыто."


def thread_closed(ticket_id: int) -> str:
    """The user wrote into the topic of a ticket that is already closed."""
    return (
        f"Обращение <b>#{ticket_id}</b> закрыто, сюда мы уже не смотрим.\n\n"
        "Если вопрос вернулся — нажми «Новое обращение», откроем свежее."
    )


def self_closed_notice(ticket_id: int) -> str:
    """Posted into the support chat, so nobody keeps working on it."""
    return f"✅ Юзер сам закрыл обращение <b>#{ticket_id}</b> — вопрос решился."


BLOCKED = "Доступ к поддержке закрыт."


def admin_reply(ticket_id: int, text: str) -> str:
    return f"💬 <b>Поддержка · обращение #{ticket_id}</b>\n\n{text}"


def taken_notice(ticket_id: int) -> str:
    return f"🔵 Обращение <b>#{ticket_id}</b> взяли в работу."


def closed_notice(ticket_id: int) -> str:
    return (
        f"⚪ Обращение <b>#{ticket_id}</b> закрыто.\n\n"
        "Если вопрос остался — напиши, откроем новое.\n"
        "Оцени, помогли ли мы:"
    )


THANKS_GOOD = "Спасибо! Рады, что помогли 🙂"
THANKS_BAD = "Спасибо за честность — разберёмся, что можно улучшить."
RATED_ALREADY = "Ты уже оценил это обращение."


def my_tickets(rows: list) -> str:
    if not rows:
        return (
            "У тебя пока нет обращений.\n\n"
            "Нажми «Новое обращение», если нужна помощь."
        )
    lines = ["📋 <b>Мои обращения</b>\n"]
    for t in rows:
        rating = ""
        if t["rating"] == 1:
            rating = " 👍"
        elif t["rating"] == -1:
            rating = " 👎"
        lines.append(
            f"<b>#{t['id']}</b> · {topic_label(t['topic'])} · "
            f"{status_label(t['status'])}{rating}\n"
            f"<i>{ago(t['ts'])}</i>"
        )
    lines.append("\nОткрой любое, чтобы посмотреть переписку.")
    return "\n".join(lines)


def thread_view(ticket: dict, messages: list) -> str:
    head = (
        f"<b>Обращение #{ticket['id']}</b> · {topic_label(ticket['topic'])}\n"
        f"Статус: {status_label(ticket['status'])} · {ago(ticket['ts'])}\n"
        f"{'─' * 20}\n"
    )
    if not messages:
        return head + "\n<i>Пока пусто.</i>"
    body = []
    for m in messages:
        who = "🛠 <b>Поддержка</b>" if m["from_admin"] else "👤 <b>Ты</b>"
        text = m["text"] or f"<i>[{m['file_type'] or 'вложение'}]</i>"
        body.append(f"{who}\n{text}")
    return head + "\n\n".join(body)


# --- time ----------------------------------------------------------------


def ago(ts: int) -> str:
    """Human-readable age, used everywhere a timestamp is shown."""
    seconds = max(0, int(time.time()) - int(ts))
    if seconds < 60:
        return "только что"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} дн назад"


def duration(seconds: int | None) -> str:
    """Length of a period, for the SLA figures."""
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч {minutes % 60} мин"
    return f"{hours // 24} дн {hours % 24} ч"


# --- the card a moderator works with ------------------------------------


def card(ticket: dict, text: str, extra: dict | None, attachment: str | None = None) -> str:
    """One screen with everything needed to answer without asking back.

    `extra` is the main bot's data, or None when that base is unreachable — the
    card must stay useful either way, so those lines are simply dropped.
    """
    who = f"@{ticket['username']}" if ticket["username"] else "без юзернейма"
    head = (
        f"#обращение <b>#{ticket['id']}</b> · {status_label(ticket['status'])}\n"
        f"Тема: <b>{topic_label(ticket['topic'])}</b>\n"
        f"От: <code>{ticket['user_id']}</code> {who}\n"
        f"Когда: {ago(ticket['ts'])}"
    )
    if ticket["taken_by"]:
        head += f"\nВзял: <code>{ticket['taken_by']}</code>"
    # Worth stating outright: a moderator who sees this can stop digging.
    if _self_closed(ticket):
        head += "\n<b>✅ Юзер закрыл сам — вопрос решился</b>"

    body = f"\n{'─' * 24}\n{text}" if text else ""
    if attachment:
        body += f"\n\n📎 <i>{attachment}</i>"

    return head + body + _extra_block(extra)


def _self_closed(ticket) -> bool:
    """True when the person who closed it is the person who opened it."""
    closed_by = ticket["closed_by"] if "closed_by" in ticket.keys() else None
    return ticket["status"] == "closed" and closed_by == ticket["user_id"]


def _extra_block(extra: dict | None) -> str:
    """What the main bot knows — the part that answers most tickets outright."""
    if not extra:
        return "\n\n<i>Данных из основного бота нет.</i>"

    lines = [f"\n{'─' * 24}", "<b>В основном боте</b>"]
    flags = " · 🔴 забанен" if extra.get("banned") else ""
    lines.append(f"🪙 Баланс: <b>{extra['coins']}</b> · заработано {extra['earned']}{flags}")

    pay = extra.get("payments")
    if pay and pay["n"]:
        refunded = f", возвратов {pay['refunded']}" if pay["refunded"] else ""
        lines.append(f"⭐ Платежей: {pay['n']} на {pay['stars']} звёзд{refunded}")
        last = extra.get("last_payment")
        if last:
            mark = " · 🔴 возвращён" if last["refunded"] else ""
            lines.append(
                f"   последний: {last['stars']}⭐ → {last['coins']}🪙, "
                f"{ago(last['ts'])}{mark}\n"
                f"   <code>{last['charge_id']}</code>"
            )
    elif pay is not None:
        lines.append("⭐ Платежей не было")

    circles = extra.get("circles")
    if circles and circles["total"]:
        lines.append(
            f"🎞 Кружки: {circles['approved']} одобрено · "
            f"{circles['pending']} ждут · {circles['rejected']} отказ"
        )

    prof = extra.get("profile")
    if prof:
        lines.append(
            f"👤 Анкета: {prof['status']} · цена {prof['price_content']} · "
            f"продано {prof['sold']}"
        )
    else:
        lines.append("👤 Анкеты нет")

    payouts = extra.get("payouts")
    if payouts and payouts["n"]:
        opened = f", открытых {payouts['open']}" if payouts["open"] else ""
        lines.append(f"💸 Выплаты: {payouts['n']}{opened}, выплачено {payouts['paid_stars']}⭐")

    if extra.get("bought"):
        lines.append(f"🛒 Покупок у авторов: {extra['bought']}")

    return "\n".join(lines)


def user_message_added(ticket_id: int, text: str, attachment: str | None) -> str:
    """A follow-up from the user, posted as a reply to their card."""
    body = text or ""
    if attachment:
        body += f"\n\n📎 <i>{attachment}</i>"
    return f"💬 <b>Дополнение к #{ticket_id}</b>\n\n{body}"


def sla_ping(ticket: dict) -> str:
    return (
        f"⏰ <b>Обращение #{ticket['id']}</b> без ответа "
        f"{ago(ticket['ts'])}.\n"
        f"Тема: {topic_label(ticket['topic'])} · "
        f"от <code>{ticket['user_id']}</code>"
    )


ATTACHMENT_LABEL = {
    "photo": "фото",
    "video": "видео",
    "document": "документ",
    "voice": "голосовое",
    "video_note": "кружок",
    "animation": "гифка",
    "audio": "аудио",
    "sticker": "стикер",
}


# --- admin panel ---------------------------------------------------------


def panel(
    s: dict,
    chat: str,
    chat_status: str,
    main_ok: bool,
    topics_private: bool = False,
    topics_chat: bool = False,
) -> str:
    rated = s["good"] + s["bad"]
    share = f"{s['good'] * 100 // rated}% 👍" if rated else "—"
    return (
        "🛠 <b>Панель поддержки</b>\n\n"
        f"🟡 Ждут ответа: <b>{s['waiting']}</b>\n"
        f"🔵 В работе: {s['taken']} · 🟢 Ответили: {s['answered']}\n"
        f"⚪ Закрыто: {s['closed']} из {s['total']}\n\n"
        f"📅 За сутки: {s['today']} обращений\n"
        f"⏱ Среднее время ответа: <b>{duration(s['avg_reply'])}</b>\n"
        f"👍 Оценки: {share} ({s['good']}/{rated or 0})\n\n"
        f"Чат: <code>{chat}</code>\n{chat_status}\n"
        f"Основная база: {'🟢 читается' if main_ok else '🔴 недоступна'}\n"
        f"Топики: у юзера {'🟢' if topics_private else '🔴'} · "
        f"в чате {'🟢' if topics_chat else '🔴'}"
    )


def queue(rows: list) -> str:
    if not rows:
        return "<b>Очередь</b>\n\nПусто — всем ответили 🙂"
    lines = ["<b>Очередь</b>\n", "Сначала те, кто ждёт дольше всех.\n"]
    for t in rows:
        taken = f" · взял <code>{t['taken_by']}</code>" if t["taken_by"] else ""
        lines.append(
            f"<b>#{t['id']}</b> {topic_label(t['topic'])} · "
            f"{status_label(t['status'])}{taken}\n"
            f"<code>{t['user_id']}</code> · {ago(t['ts'])}"
        )
    return "\n".join(lines)


def topics_report(rows: list, total: int) -> str:
    if not rows:
        return "<b>По темам</b>\n\nПока нет обращений."
    lines = ["<b>По темам</b>\n"]
    for r in rows:
        pct = f"{r['n'] * 100 // total}%" if total else "—"
        lines.append(f"{topic_label(r['topic'])} — <b>{r['n']}</b> ({pct})")
    return "\n".join(lines)


def canned_screen(rows: list) -> str:
    if not rows:
        return (
            "<b>Шаблоны</b>\n\n"
            "Пока пусто. Шаблон — готовый ответ на частый вопрос: выбрал в "
            "карточке, и он ушёл юзеру.\n\n"
            "Добавь первый кнопкой ниже."
        )
    lines = ["<b>Шаблоны</b>\n"]
    for c in rows:
        lines.append(f"<b>{c['title']}</b> · использован {c['used']}×\n<i>{c['body'][:80]}</i>")
    return "\n".join(lines)


CANNED_ASK = (
    "Пришли шаблон одним сообщением:\n\n"
    "<code>Название | текст ответа</code>\n\n"
    "Название видит только админ, текст уходит юзеру."
)

CANNED_BAD = "Нужен формат <code>Название | текст</code>."

ASK_USER_ID = (
    "Пришли id пользователя числом — покажу все его обращения.\n"
    "Или номер платежа из чека (<code>ch_…</code>) — найду сам платёж."
)

BAD_USER_ID = "Нужен id числом или номер платежа из чека."


def payment_found(p: dict) -> str:
    """The answer to "my stars vanished": the charge, as the main bot stored it."""
    mark = " · 🔴 возвращён" if p["refunded"] else ""
    return (
        f"<b>Платёж найден</b>{mark}\n\n"
        f"Кто: <code>{p['user_id']}</code>\n"
        f"{p['stars']} ⭐ → {p['coins']} 🪙\n"
        f"Когда: {ago(p['ts'])}\n"
        f"Номер: <code>{p['charge_id']}</code>\n\n"
        "Если монетки не начислены — начисли вручную в основном боте."
    )


def user_tickets_admin(user_id: int, rows: list, extra: dict | None) -> str:
    head = f"<b>Обращения</b> <code>{user_id}</code>\n"
    if not rows:
        return head + "\nОбращений нет." + _extra_block(extra)
    lines = [head]
    for t in rows:
        lines.append(
            f"<b>#{t['id']}</b> {topic_label(t['topic'])} · "
            f"{status_label(t['status'])} · {ago(t['ts'])}"
        )
    return "\n".join(lines) + _extra_block(extra)


ASK_CHAT = (
    "Пришли id чата поддержки (<code>-100…</code>) или <code>@username</code>.\n"
    "Бот должен быть в этом чате.\n"
    "Пришли <code>-</code>, чтобы вернуть карточки в личку админам."
)

BAD_CHAT = "Нужен id, @username или «-»."

NO_CHAT = (
    "🔴 <b>Чат поддержки не настроен.</b>\n\n"
    "Карточки идут в личку админам. Укажи чат в панели: так отвечать удобнее "
    "и видно, кто что взял."
)

NOT_A_TICKET = (
    "Это сообщение не привязано к обращению.\n"
    "Отвечай реплаем на карточку обращения."
)

TICKET_CLOSED_REPLY = "Обращение уже закрыто — ответ не отправлен."
REPLY_SENT = "Отправлено юзеру 🟢"
REPLY_BLOCKED = "🔴 Юзер заблокировал бота — ответ не доставлен."
NO_RIGHTS = "Нет прав."
