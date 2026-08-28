"""Message texts.

Everything that shows an emoji is built at call time — placeholders are only
known after emoji.resolve() has run against Telegram.
"""

import html

import emoji
import settings
from config import ABOUT_MAX
from keyboards import PERSON_TITLE, PREF_TITLE


def coin() -> str:
    return emoji.text(emoji.COIN)


def reward_line() -> str:
    """One rate reads as one number; two rates have to be spelled out."""
    female, male = settings.reward("f"), settings.reward("m")
    if female == male:
        return f"+{female}"
    return f"+{female} за женский, +{male} за мужской"


def menu(coins: int, pref: str) -> str:
    return (
        "<b>Кружочки</b>\n\n"
        f"{coin()} Баланс: <b>{coins}</b>\n"
        f"{emoji.text(emoji.FILM)} Лента: <b>{PREF_TITLE(pref)}</b>\n\n"
        "Кнопки внизу."
    )


def feed(pref: str) -> str:
    return (
        "<b>Лента</b>\n\n"
        f"Сейчас показываю: <b>{PREF_TITLE(pref)}</b>\n"
        "Выбери, какие кружочки хочешь смотреть."
    )


def rules() -> str:
    full = settings.get("min_duration")
    return (
        "ℹ️ <b>Правила сервиса</b>\n\n"
        "• Запрещены материалы: ЛГБТ, обнажённые видео пользователей до 18 лет, "
        "реклама, спам, оскорбления и незаконный контент\n"
        f"• Минимальная длина кружка = {full} секунд\n"
        "• Уважай других пользователей и не злоупотребляй жалобами\n\n"
        "За нарушение правил доступ к боту может быть ограничен без предупреждения."
    )


def faq() -> str:
    return (
        "❓ <b>FAQ</b>\n\n"
        "<b>Откуда берутся монетки?</b>\n"
        "Купить за ⭐ в «Магазине» или продать свой контент: люди покупают "
        f"доступ к твоим кружочкам, и {settings.get('author_share')}% цены "
        f"достаётся тебе. Ещё за друга по твоей ссылке дают "
        f"{settings.get('ref_reward')}.\n\n"
        f"<b>Сколько стоит просмотр?</b>\n"
        f"{settings.get('watch_cost')} монетки за кружок. "
        "Один и тот же кружок дважды не попадётся, свои — не показываются.\n\n"
        "<b>Как заработать?</b>\n"
        "Только продажей: кто-то покупает доступ ко всем твоим кружочкам или "
        f"твою личку — тебе идёт {settings.get('author_share')}% цены. "
        "За саму загрузку кружочков монетки не начисляются.\n\n"
        "<b>Тогда зачем загружать кружочки?</b>\n"
        "Это единственный способ, которым тебя находят: зритель смотрит кружок "
        "и открывает по кнопке твою анкету. Чем больше лайков собирает кружок, "
        "тем большему числу людей его показывают.\n\n"
        "<b>Что такое анкета?</b>\n"
        "Витрина: фото, описание и твои цены. Заполняется в «Мой профиль»,"
        "проходит проверку, потом её показывают в «Смотреть анкеты».\n\n"
        "<b>Как вывести заработанное?</b>\n"
        f"В «Профиле» кнопка «Вывести заработок»: от {settings.get('payout_min')} "
        f"монеток, курс {settings.get('payout_rate')} монетки = 1 ⭐. Выводятся "
        "только заработанные монетки, купленные за ⭐ — нет. Заявку закрывает "
        "админ вручную.\n\n"
        "<b>Почему кружок не приняли?</b>\n"
        "Либо он короче минимума, либо такой уже есть в базе, либо модератор "
        "счёл его нарушающим правила.\n\n"
        "<b>Долго ли ждать проверки?</b>\n"
        "Обычно недолго. Пока кружок на проверке, можно загружать следующие — "
        f"до {settings.get('max_pending')} штук.\n\n"
        "<b>Можно ли скачать или переслать кружок?</b>\n"
        "Нет: кружочки уходят с защитой от пересылки и сохранения.\n\n"
        "<b>Почему для загрузки нужна анкета?</b>\n"
        "Потому что кружок и автор связаны: под каждым кружком есть кнопка "
        "«Профиль автора», через неё зритель покупает доступ ко всем твоим"
        "кружочкам. Без анкеты этот путь обрывается.\n\n"
        "<b>Кто увидит, кто я?</b>\n"
        "В анкете — только фото и описание, которые ты сам выбрал. Имя и "
        "@username не показываются никогда; @username уходит покупателю только "
        "если ты сам включил продажу лички и он за неё заплатил.\n\n"
        "<b>Что делать с нарушением?</b>\n"
        "Кнопка «Пожаловаться» под кружком. Жалобы уходят модераторам.\n\n"
        "<b>Где почитать оферту и политику конфиденциальности?</b>\n"
        "Кнопками под этим сообщением, а ещё они есть на экранах согласия и "
        "в «Магазине»."
    )


def referrals(done: int, waiting: int, link: str) -> str:
    return (
        "👥 <b>Рефералы</b>\n\n"
        f"Приглашено: <b>{done}</b>"
        + (f" · ждут подписки: {waiting}\n" if waiting else "\n")
        + f"За каждого друга, который подпишется на канал, — "
        f"<b>+{settings.get('ref_reward')}</b> {coin()}\n\n"
        f"Твоя ссылка:\n<code>{link}</code>"
    )


def not_enough(coins: int) -> str:
    earn = (
        f"Загрузи кружок ({reward_line()}) или купи монетки за ⭐."
        if settings.reward("f") or settings.reward("m")
        else (
            "Монетки берутся двумя путями: купить за ⭐ в «Магазине» "
            "или продавать свой контент — заведи анкету, и каждый, кто "
            f"купит доступ, принесёт тебе {settings.get('author_share')}% "
            "от своей оплаты."
        )
    )
    return (
        f"{coin()} Баланс: <b>{coins}</b> — "
        f'на просмотр нужно {settings.get("watch_cost")}.\n\n' + earn
    )


def _push_new(free: int) -> str:
    return (
        "<b>В боте пополнились новые кружки! Время смотреть!</b>\n\n"
        f"Жми кнопку — {free} {circles_word(free)} бесплатно 👀"
    )


def _push_missed(free: int) -> str:
    return (
        "<b>Тебя давно не было — а тут уже новые лица.</b>\n\n"
        f"Держи {free} {circles_word(free)} за счёт заведения 👀"
    )


def _push_waiting(free: int) -> str:
    return (
        "<b>Кто-то записал кружок, пока тебя не было.</b>\n\n"
        f"Первые {free} {circles_word(free)} — бесплатно, дальше как обычно 👀"
    )


PUSH_TEXTS = (_push_new, _push_missed, _push_waiting)


def free_view_left(left: int) -> str:
    return f"Бесплатный просмотр. Осталось таких: {left}"


EMPTY = (
    "Свежих кружочков этого типа пока нет — ты посмотрел все.\n"
    "Загляни позже или смени тип."
)


UPLOAD_NEEDS_PROFILE = (
    "🎬 Сначала анкета.\n\n"
    "Кружочки показываются вместе с анкетой автора: зритель может её открыть и "
    "купить доступ ко всем твоим кружочкам. Без анкеты продавать нечего."
)


def upload_profile_pending(status: str) -> str:
    if status == "pending":
        return "🕒 Анкета на проверке. Как одобрят — можно будет загружать кружочки."
    return "🔴 Анкета отклонена. Заполни её заново в «Мой профиль», потом загружай."


def upload_ask(gender: str) -> str:
    kind = "женский" if gender == "f" else "мужской"
    reward = settings.reward(gender)
    payoff = (
        f"• <b>+{reward}</b> {coin()} после проверки модератором"
        if reward
        else "• кружочки не оплачиваются — это витрина твоей анкеты\n"
        "• под каждым есть кнопка «Профиль автора»: так тебя находят и покупают\n"
        "• чем больше лайков, тем большему числу людей тебя показывают"
    )
    return (
        f"🎥 Пришли {kind} кружок одним сообщением.\n\n"
        f'• минимум {settings.get("min_duration")} секунд\n' + payoff
    )


NOT_A_CIRCLE = "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение."


def too_short(duration: int) -> str:
    return (
        f"Кружок {duration} сек — коротко. "
        f'Минимальная длина: {settings.get("min_duration")} секунд.'
    )


DUPLICATE = "Такой кружок уже есть в базе."
TOO_MANY_PENDING = "У тебя уже несколько кружков на проверке. Дождись решения."


def upload_sent(circle_id: int, reward: int) -> str:
    tail = (
        f"После одобрения: <b>+{reward}</b> {coin()}"
        if reward
        else "После одобрения его начнут показывать вместе с твоей анкетой."
    )
    return f"✅ Кружок <b>#{circle_id}</b> отправлен на проверку.\n" + tail


def approved(reward: int, coins: int) -> str:
    if reward:
        return (
            f"🟢 Твой кружок одобрен: <b>+{reward}</b> {coin()}\n"
            f"Баланс: <b>{coins}</b>"
        )
    return (
        "🟢 Твой кружок одобрен — его начали показывать.\n"
        "Собирай лайки: чем их больше, тем чаще кружок попадается людям, "
        "и тем чаще открывают твою анкету."
    )


REJECTED = "🔴 Кружок отклонён модератором."
REPORT_SENT = "Жалоба отправлена модераторам."
REPORT_DOUBLE = "Ты уже жаловался на этот кружок."
REPORT_DOUBLE_PROFILE = "Ты уже жаловался на эту анкету."
REPORT_ASK = "За что жалуешься?"

# The keys go into callback data, so they stay short and ascii.
REPORT_REASONS = {
    "minor": "🧒 На видео несовершеннолетний",
    "violence": "🩸 Насилие или жестокость",
    "ads": "📢 Реклама или спам",
    "stolen": "🎭 Чужой кружок, не свой",
    "other": "⚠️ Другое нарушение",
}

PROFILE_REPORT_REASONS = {
    "photo": "🖼 Фото чужое или не по теме",
    "minor": "🧒 На фото несовершеннолетний",
    "ads": "📢 Реклама или ссылки в анкете",
    "scam": "💸 Обман, деньги мимо бота",
    "abuse": "🤬 Оскорбления в описании",
    "other": "⚠️ Другое нарушение",
}

NO_REASON = "причина не указана"


def reasons_summary(rows, labels: dict[str, str]) -> str:
    """What the complaints were about, for the moderator card."""
    lines = [
        f"• {labels.get(row['reason'], NO_REASON)} — {row['count']}" for row in rows
    ]
    return "\n".join(lines)


def circles_word(count: int) -> str:
    """1 кружок, 2 кружка, 5 кружков."""
    tail = count % 100
    if 11 <= tail <= 14:
        return "кружочков"
    return {1: "кружочек", 2: "кружочка", 3: "кружочка", 4: "кружочка"}.get(
        tail % 10, "кружочков"
    )


CIRCLE_REMOVED = "🔴 Твой кружок удалён по жалобам."


ARCHIVE_NOTE = (
    "Это кружок из архива бота — он без автора, анкеты у него нет."
)


def earned_toast(amount: int) -> str:
    return f"Твой кружок посмотрели: +{amount}"


def buy(coins: int) -> str:
    return (
        f"{coin()} Баланс: <b>{coins}</b>\n\n"
        f'1 ⭐ = <b>{settings.get("stars_rate")}</b> {coin()}, '
        f'минимум {settings.get("min_stars")} ⭐.\n\n'
        "Оплата — по условиям публичной оферты."
    )


def buy_custom() -> str:
    return f'Сколько ⭐ спишем? Пришли число (от {settings.get("min_stars")}).'


def buy_choose_method(stars: int, coins: int) -> str:
    return (
        f"💰 <b>Покупка {coins} монет</b>\n\n"
        f"Сумма: <b>{stars} ⭐</b> → <b>{coins}</b> {coin()}\n\n"
        "Выбери способ оплаты:"
    )


def buy_bad_input() -> str:
    return f'Нужно целое число от {settings.get("min_stars")}.'


def paid(stars: int, coins_added: int, coins: int) -> str:
    return (
        f"🟢 Оплачено {stars} ⭐ → <b>+{coins_added}</b> {coin()}\n"
        f"Баланс: <b>{coins}</b>"
    )


def profile(
    user_id: int,
    coins: int,
    s: dict,
    earned: int,
    likes: int,
    views: int,
    ref_done: int,
    sales: dict | None = None,
    withdrawable: int = 0,
) -> str:
    sales = sales or {"content": 0, "contact": 0, "income": 0}
    dislikes = 0  # TODO: implement dislike tracking if needed
    return (
        f"{emoji.text(emoji.PROFILE_HEADER)} <b>Твой профиль:</b>\n\n"
        f"{emoji.text(emoji.UPLOADED_COUNT)} Загружено кружков: <b>{s['approved']}</b>\n"
        f"{emoji.text(emoji.RATINGS_ICON)} Оценки: {emoji.text(emoji.LIKE_EMOJI)} "
        f"<b>{likes}</b> | {emoji.text(emoji.DISLIKE_EMOJI)} <b>{dislikes}</b>\n"
        f"{emoji.text(emoji.VIEWS_COUNT)} Просмотрено кружков: <b>{s['watched']}</b>\n"
        f"{emoji.text(emoji.BALANCE_ICON)} Баланс: <b>{coins}</b> "
        f"{emoji.text(emoji.COIN_EMOJI)}\n\n"
        f"{emoji.text(emoji.EARNINGS_ICON)} <b>Хочешь зарабатывать в Krujok — жми "
        "«Профиль автора» 👇</b>\n\n"
        f"👥 Приглашено пользователей: {ref_done}\n"
        f"💸 К выводу: <b>{withdrawable}</b> {coin()} "
        f"(~{settings.stars_for(withdrawable)} ⭐)\n"
        f"🛒 Продано: {sales['content']} доступов · {sales['contact']} контактов\n"
        f"👀 Просмотров твоих кружков: {views}"
    )


# --- author profiles -----------------------------------------------------

PROFILE_INTRO = (
    "<b>Хотите зарабатывать в Krujok?</b>\n\n"
    "1. 👤 <b>Настройте свой профиль красиво и привлекательно!</b>\n"
    "— Поставьте справедливую цену\n"
    "— Выставите красивую фотографию\n"
    "— Напишите привлекательное описание\n\n"
    "2. 🔞 <b>Загружайте интересные кружки</b>, чтобы привлечь больше людей\n\n"
    "3. ❓ <b>Как всё работает?</b>\n"
    "Пользователям будут показываться ваши кружки, и у них будет доступ к "
    "просмотру вашего профиля. Поэтому сделайте очень привлекательный профиль "
    "и много интересных кружков\n\n"
    "4. 💸 <b>Доступные способы вывода денег:</b>\n"
    "Крипта 💰\n"
    "Тг старс ⭐\n"
    "Перевод на карту 💳\n\n"
    "Нажмите на кнопку соглашения, чтобы начать настройку профиля."
)

PROFILE_PHOTO = (
    "🖼 <b>Профиль автора</b>\n\n"
    "Пришли фото для анкеты — его увидят все, кто листает анкеты.\n"
    "Лицо показывать необязательно."
)


def profile_about() -> str:
    return (
        "✍️ Теперь описание — пара строк о себе.\n"
        f"До {ABOUT_MAX} символов. «-» — оставить пустым."
    )


PROFILE_GENDER = "Кто ты?"


def profile_price_content() -> str:
    return (
        "💰 Цена доступа ко <b>всем твоим кружочкам</b> в монетках.\n"
        f"От {settings.get('price_min')} до {settings.get('price_max')}.\n\n"
        f"Тебе достаётся {settings.get('author_share')}% с каждой покупки."
    )


PROFILE_CONTACT_ASK = (
    "Продавать доступ к личке? Покупатель получит твой @username и сможет "
    "написать напрямую.\n\nЭто снимает анонимность — решай сам."
)
PROFILE_NO_USERNAME = (
    "Для продажи лички нужен @username.\n\n"
    "Настройки Telegram → Имя пользователя. Поставил — жми "
    "«Добавил(а) юзернейм», и продажа лички станет доступна.\n"
    "Не хочешь — продаём только кружочки."
)
PROFILE_STILL_NO_USERNAME = (
    "@username всё ещё не вижу. Поставь его в настройках Telegram и жми ещё раз."
)


def profile_price_contact() -> str:
    return (
        "💬 Цена за доступ к личке в монетках.\n"
        f"От {settings.get('price_min')} до {settings.get('price_max')}."
    )


def profile_bad_price() -> str:
    return (
        f"Нужно число от {settings.get('price_min')} "
        f"до {settings.get('price_max')}."
    )


def profile_changes(old, new: dict) -> list[str]:
    """What the author actually touched — the moderator reads only that."""
    if old is None:
        return []

    changes = []
    if old["photo_unique_id"] != new.get("photo_unique_id"):
        changes.append("фото")
    if (old["about"] or "") != new.get("about", ""):
        changes.append("описание")
    if old["gender"] != new["gender"]:
        changes.append("кто")
    if old["price_content"] != new["price_content"]:
        changes.append(
            f"цена кружочков {old['price_content']} → {new['price_content']}"
        )

    was = old["price_contact"] if old["contact_ok"] else 0
    now = new.get("price_contact", 0) if new.get("contact_ok") else 0
    if was != now:
        changes.append(
            f"личка {was or 'не продавалась'} → {now or 'не продаётся'}"
        )
    return changes


PROFILE_SENT = (
    "✅ Анкета отправлена на проверку. Как только модератор её одобрит, "
    "её начнут показывать другим."
)
PROFILE_NOT_PHOTO = "Нужно именно фото."
PROFILE_APPROVED = "🟢 Твоя анкета одобрена — её уже показывают."
REJECT_REASONS = {
    "photo": "фото не подходит: чужое, не по теме или без человека",
    "about": "описание не по теме или набор символов",
    "ads": "реклама, ссылки или контакты в анкете",
    "rules": "нарушает правила сервиса",
    "quality": "слишком плохое качество фото",
}


def profile_reverted(reason: str = "") -> str:
    tail = f"\n\nПричина: <b>{reason}</b>" if reason else ""
    return (
        "🔴 Правки в анкете отклонены." + tail + "\n\n"
        "Вернули прошлую версию — она снова показывается. "
        "Можешь отредактировать заново."
    )


def profile_rejected(reason: str = "") -> str:
    tail = f"\n\nПричина: <b>{reason}</b>" if reason else ""
    return (
        "🔴 Анкета отклонена модератором." + tail + "\n\n"
        "Заполни её заново — это займёт минуту. Без анкеты нельзя загружать "
        "кружочки и зарабатывать на них."
    )
PROFILE_EMPTY_WAIT = "Анкет пока нет — все просмотрены. Загляни позже."


def profile_empty_pitch() -> str:
    return (
        "Анкет пока нет — но ты можешь стать первым.\n\n"
        "Анкета — это твоя витрина: фото, описание и твоя цена. Другие покупают "
        f"доступ ко всем твоим кружочкам, и <b>{settings.get('author_share')}%</b> "
        "от каждой покупки достаётся тебе. Заработанное выводится в ⭐ "
        f"от {settings.get('payout_min')} монеток.\n\n"
        "Без анкеты кружочки загружать нельзя — с неё всё и начинается."
    )


def profile_status(profile) -> str:  # noqa: D401 — the author's own view
    label = {
        "pending": "🕒 на проверке",
        "approved": "🟢 показывается",
        "rejected": "🔴 отклонена",
    }[profile["status"]]
    contact = (
        f"{profile['price_contact']} {coin()}"
        if profile["contact_ok"] and profile["price_contact"]
        else "не продаётся"
    )
    return (
        f"<b>Мой профиль</b> · {label}\n\n"
        f"{html.escape(profile['about'] or 'Без описания')}\n\n"
        f"Кружочки: {profile['price_content']} {coin()}\n"
        f"Личка: {contact}\n"
        f"Показов: {profile['views']} · покупок: {profile['sold']}"
    )


def profile_card(profile, circles: int) -> str:
    contact = (
        f"{profile['price_contact']} {coin()}"
        if profile["contact_ok"] and profile["price_contact"]
        else "не продаётся"
    )
    return (
        f"<b>{PERSON_TITLE(profile['gender'])}</b>\n\n"
        f"{emoji.text(emoji.ABOUT)} {html.escape(profile['about'] or 'Без описания')}\n\n"
        f"{emoji.text(emoji.CIRCLE_COUNT)} Кружочков у автора: <b>{circles}</b>\n"
        f"{emoji.text(emoji.PRICE)} Доступ ко всем: "
        f"<b>{profile['price_content']}</b> {coin()}\n"
        f"Личка: {contact}\n"
        f"{emoji.text(emoji.SOLD)} Купили: {profile['sold']} раз\n\n"
        f"{emoji.text(emoji.INFO)} <i>Покупка открывает кружочки, которые есть "
        "у автора прямо сейчас.</i>"
    )


def bought_content(count: int, share: int) -> str:
    return (
        f"🟢 Доступ открыт: {count} {circles_word(count)} этого автора теперь "
        "бесплатны.\nЖми «Кружочки автора», чтобы посмотреть."
    )


def bought_contact(username: str) -> str:
    return f"🟢 Личка автора: @{username}\n\nНапиши ему сам."


def sale_note(kind: str, share: int) -> str:
    what = "доступ к твоим кружочкам" if kind == "content" else "твою личку"
    return f"💰 Купили {what}: <b>+{share}</b> {coin()}"


def more_circles(left: int) -> str:
    return f"Осталось ещё {left} {circles_word(left)} этого автора."


CONTACT_NOT_FOR_SALE = "Автор не продаёт личку."
NOTHING_TO_SELL = "У автора пока нет кружочков — покупать нечего."
ALREADY_BOUGHT = "Уже куплено."


# --- payouts -------------------------------------------------------------


def payout_screen(available: int, pending: int) -> str:
    rate = settings.get("payout_rate")
    low = settings.get("payout_min")
    body = (
        f"💸 <b>Вывод</b>\n\n"
        f"Доступно к выводу: <b>{available}</b> {coin()} "
        f"(~{settings.stars_for(available)} ⭐)\n"
        f"Курс: {rate} монетки = 1 ⭐, минимум {low} монеток\n\n"
        "Выводятся только заработанные монетки — купленные за ⭐ нельзя."
    )
    if pending:
        body += f"\n\n🕒 Заявок в работе: {pending}"
    return body


def payout_ask_amount(available: int) -> str:
    return (
        f"Сколько монеток вывести? Доступно {available}, "
        f"минимум {settings.get('payout_min')}."
    )


PAYOUT_ASK_DETAILS = (
    "Куда отправить? Пришли адрес кошелька (USDT/TON) или свой @username — "
    "админ свяжется и выплатит."
)


def payout_created(payout_id: int, coins: int, stars: int) -> str:
    return (
        f"✅ Заявка <b>#{payout_id}</b> создана: {coins} {coin()} → {stars} ⭐.\n"
        "Монетки заморожены. Админ выплатит вручную и отметит заявку."
    )


def payout_paid(payout_id: int, stars: int) -> str:
    return f"🟢 Заявка #{payout_id} выплачена: {stars} ⭐."


def payout_rejected(payout_id: int, coins: int) -> str:
    return f"🔴 Заявка #{payout_id} отклонена, {coins} монеток вернулись на баланс."


def payout_spent(balance: int, wanted: int) -> str:
    return (
        f"На балансе только {balance} монеток, а на вывод нужно {wanted}: "
        "заработанное уже потрачено на просмотры или покупки."
    )


def payout_too_small(available: int) -> str:
    return (
        f"Минимум для вывода — {settings.get('payout_min')} монеток. "
        f"Доступно: {available}."
    )


def welcome() -> str:
    bonus = settings.get("welcome_bonus")
    gift = (
        f"\n\n🎁 За согласие дарим <b>{bonus}</b> монеток на первые просмотры."
        if bonus
        else ""
    )
    return (
        "👋 <b>Добро пожаловать</b>\n\n"
        f"{rules()}{gift}\n\n"
        "Нажимая кнопку ниже, ты подтверждаешь, что тебе есть 18 лет, "
        "и принимаешь правила, <b>публичную оферту</b> и <b>политику "
        "конфиденциальности</b> — они открываются кнопками ниже."
    )


ACCEPTED = "Готово. Приятного просмотра 🙂"


def welcome_bonus(amount: int) -> str:
    return (
        f"🎁 Держи <b>{amount}</b> {coin()} на старт — "
        f"это {amount // settings.get('watch_cost')} "
        f"{circles_word(amount // settings.get('watch_cost'))} бесплатно.\n\n"
        "Кончатся — запиши свой кружок или загляни в «Магазин»."
    )

def traffer_report(stats: dict, week: dict, day: dict, link: str) -> str:
    """What the person who bought the ad sees: traffic, not the money behind it."""
    def pct(part: int, whole: int) -> str:
        return f"{part * 100 / whole:.1f}%" if whole else "—"

    return (
        f"📊 <b>{stats['title'] or stats['code']}</b>\n\n"
        "🕓 <b>За всё время</b>\n"
        f"Новых пользователей: <b>{stats['users']}</b>\n"
        f"Прошли подписку: {stats['subscribed']} "
        f"({pct(stats['subscribed'], stats['users'])})\n"
        f"Приняли правила: {stats['accepted']} "
        f"({pct(stats['accepted'], stats['users'])})\n"
        f"Покупали монетки: {stats['payers']} "
        f"({pct(stats['payers'], stats['users'])})\n\n"
        f"📅 7 дней · людей {week['users']}, подписок {week['subscribed']}\n"
        f"📅 Сутки · людей {day['users']}, подписок {day['subscribed']}\n\n"
        f"<code>{link}</code>"
    )


TRAFFER_UNKNOWN = "Команда не подходит — проверь её у того, кто выдал ссылку."

BANNED = "Доступ закрыт."
MAINTENANCE = "🔧 Бот на техработах. Загляни чуть позже."
def subscribe() -> str:
    bonus = settings.get("sub_bonus")
    gift = (
        f"\n\n🎁 За подписку начислим <b>{bonus}</b> монеток." if bonus else ""
    )
    return (
        "📢 Бот работает только для подписчиков канала.\n\n"
        "Подпишись и нажми «Я подписался»." + gift
    )


def sub_bonus(amount: int) -> str:
    return f"🎁 Спасибо за подписку: <b>+{amount}</b> {coin()}"
SUBSCRIBE_MISSING = "Подписки не вижу. Подпишись на канал и нажми ещё раз."
