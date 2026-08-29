"""Message texts.

Every message the user can see is a module-level template here, and every one of
them is editable from the admin panel: text_manager swaps the constant in place.
Functions only gather the values a template asks for — {coins}, {price}, {coin}
and so on — so wording, order and emoji are the admin's business, not the code's.

Emoji are placeholders too: their real form is only known after emoji.resolve()
has run against Telegram, so they are passed in rather than baked in.

A template that an edit broke (unknown {vstavka}, stray brace) falls back to the
shipped one instead of taking the message down — see _fmt.
"""

import html
import logging

import emoji
import settings
from config import ABOUT_MAX
from keyboards import PERSON_TITLE, PREF_TITLE

logger = logging.getLogger(__name__)


def _fmt(key: str, template: str, **values) -> str:
    """Fill a template, falling back to the shipped one if an edit broke it."""
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        import text_manager  # late: text_manager imports this module

        logger.warning("текст %s не собрался, показываю стандартный", key)
        try:
            return text_manager.default(key).format(**values)
        except (KeyError, IndexError, ValueError):
            return template


def coin() -> str:
    return emoji.text(emoji.COIN)


def reward_line() -> str:
    """One rate reads as one number; two rates have to be spelled out."""
    female, male = settings.reward("f"), settings.reward("m")
    if female == male:
        return f"+{female}"
    return f"+{female} за женский, +{male} за мужской"


def circles_word(count: int) -> str:
    """1 кружок, 2 кружка, 5 кружков."""
    tail = count % 100
    if 11 <= tail <= 14:
        return "кружочков"
    return {1: "кружочек", 2: "кружочка", 3: "кружочка", 4: "кружочка"}.get(
        tail % 10, "кружочков"
    )


# --- main menu, feed, rules ----------------------------------------------

MENU = (
    "<b>Кружочки</b>\n\n"
    "{coin} Баланс: <b>{coins}</b>\n"
    "{film} Лента: <b>{pref}</b>\n\n"
    "Кнопки внизу."
)


def menu(coins: int, pref: str) -> str:
    return _fmt(
        "MENU",
        MENU,
        coin=coin(),
        coins=coins,
        film=emoji.text(emoji.FILM),
        pref=PREF_TITLE(pref),
    )


FEED = (
    "<b>Лента</b>\n\n"
    "Сейчас показываю: <b>{pref}</b>\n"
    "Выбери, какие кружочки хочешь смотреть."
)


def feed(pref: str) -> str:
    return _fmt("FEED", FEED, pref=PREF_TITLE(pref))


RULES = (
    "ℹ️ <b>Правила сервиса</b>\n\n"
    "• Запрещены материалы: ЛГБТ, обнажённые видео пользователей до 18 лет, "
    "реклама, спам, оскорбления и незаконный контент\n"
    "• Минимальная длина кружка = {min_duration} секунд\n"
    "• Уважай других пользователей и не злоупотребляй жалобами\n\n"
    "За нарушение правил доступ к боту может быть ограничен без предупреждения."
)


def rules() -> str:
    return _fmt("RULES", RULES, min_duration=settings.get("min_duration"))


FAQ = (
    "❓ <b>FAQ</b>\n\n"
    "<b>Откуда берутся монетки?</b>\n"
    "Купить за ⭐ в «Магазине» или продать свой контент: люди покупают "
    "доступ к твоим кружочкам, и {author_share}% цены достаётся тебе. "
    "Ещё за друга по твоей ссылке дают {ref_reward}.\n\n"
    "<b>Сколько стоит просмотр?</b>\n"
    "{watch_cost} монетки за кружок. "
    "Один и тот же кружок дважды не попадётся, свои — не показываются.\n\n"
    "<b>Как заработать?</b>\n"
    "Только продажей: кто-то покупает доступ ко всем твоим кружочкам или "
    "твою личку — тебе идёт {author_share}% цены. "
    "За саму загрузку кружочков монетки не начисляются.\n\n"
    "<b>Тогда зачем загружать кружочки?</b>\n"
    "Это единственный способ, которым тебя находят: зритель смотрит кружок "
    "и открывает по кнопке твою анкету. Чем больше лайков собирает кружок, "
    "тем большему числу людей его показывают.\n\n"
    "<b>Что такое анкета?</b>\n"
    "Витрина: фото, описание и твои цены. Заполняется в «Профиле» "
    "кнопкой «Моя анкета», проходит проверку, потом её показывают "
    "в «Смотреть анкеты».\n\n"
    "<b>Как вывести заработанное?</b>\n"
    "В «Профиле» кнопка «Вывести заработок»: от {payout_min} монеток, "
    "курс {payout_rate} монетки = 1 ⭐. Выводятся только заработанные "
    "монетки, купленные за ⭐ — нет. Заявку закрывает админ вручную.\n\n"
    "<b>Почему кружок не приняли?</b>\n"
    "Либо он короче минимума, либо такой уже есть в базе, либо модератор "
    "счёл его нарушающим правила.\n\n"
    "<b>Долго ли ждать проверки?</b>\n"
    "Обычно недолго. Пока кружок на проверке, можно загружать следующие — "
    "до {max_pending} штук.\n\n"
    "<b>Можно ли скачать или переслать кружок?</b>\n"
    "Нет: кружочки уходят с защитой от пересылки и сохранения.\n\n"
    "<b>Почему для загрузки нужна анкета?</b>\n"
    "Потому что кружок и автор связаны: под каждым кружком есть кнопка "
    "«Профиль автора», через неё зритель покупает доступ ко всем твоим "
    "кружочкам. Без анкеты этот путь обрывается.\n\n"
    "<b>Кто увидит, кто я?</b>\n"
    "В анкете — только фото и описание, которые ты сам выбрал. Имя и "
    "@username не показываются никогда; @username уходит покупателю только "
    "если ты сам включил продажу лички и он за неё заплатил.\n\n"
    "<b>Что делать с нарушением?</b>\n"
    "Кнопка «Пожаловаться» под кружком. Жалобы уходят модераторам.\n\n"
    "<b>Где почитать оферту и политику конфиденциальности?</b>\n"
    "Кнопками внизу «Магазина» и на экране выбора способа оплаты — "
    "они открываются страницами в Telegram."
)


def faq() -> str:
    return _fmt(
        "FAQ",
        FAQ,
        author_share=settings.get("author_share"),
        ref_reward=settings.get("ref_reward"),
        watch_cost=settings.get("watch_cost"),
        payout_min=settings.get("payout_min"),
        payout_rate=settings.get("payout_rate"),
        max_pending=settings.get("max_pending"),
    )


# --- referrals ------------------------------------------------------------

REFERRALS = (
    "👥 <b>Рефералы</b>\n\n"
    "Приглашено: <b>{done}</b>{waiting}\n"
    "За каждого друга, который подпишется на канал, — "
    "<b>+{ref_reward}</b> {coin}\n\n"
    "Твоя ссылка:\n<code>{link}</code>"
)
REFERRALS_WAITING = " · ждут подписки: {waiting}"


def referrals(done: int, waiting: int, link: str) -> str:
    tail = (
        _fmt("REFERRALS_WAITING", REFERRALS_WAITING, waiting=waiting)
        if waiting
        else ""
    )
    return _fmt(
        "REFERRALS",
        REFERRALS,
        done=done,
        waiting=tail,
        ref_reward=settings.get("ref_reward"),
        coin=coin(),
        link=link,
    )


# --- watching -------------------------------------------------------------

NOT_ENOUGH = "{coin} Баланс: <b>{coins}</b> — на просмотр нужно {watch_cost}.\n\n{earn}"
NOT_ENOUGH_UPLOAD = "Загрузи кружок ({reward}) или купи монетки за ⭐."
NOT_ENOUGH_SELL = (
    "Монетки берутся двумя путями: купить за ⭐ в «Магазине» "
    "или продавать свой контент — заведи анкету, и каждый, кто "
    "купит доступ, принесёт тебе {author_share}% от своей оплаты."
)


def not_enough(coins: int) -> str:
    if settings.reward("f") or settings.reward("m"):
        earn = _fmt("NOT_ENOUGH_UPLOAD", NOT_ENOUGH_UPLOAD, reward=reward_line())
    else:
        earn = _fmt(
            "NOT_ENOUGH_SELL",
            NOT_ENOUGH_SELL,
            author_share=settings.get("author_share"),
        )
    return _fmt(
        "NOT_ENOUGH",
        NOT_ENOUGH,
        coin=coin(),
        coins=coins,
        watch_cost=settings.get("watch_cost"),
        earn=earn,
    )


PUSH_NEW = (
    "<b>В боте пополнились новые кружки! Время смотреть!</b>\n\n"
    "Жми кнопку — {free} {circles} бесплатно 👀"
)
PUSH_MISSED = (
    "<b>Тебя давно не было — а тут уже новые лица.</b>\n\n"
    "Держи {free} {circles} за счёт заведения 👀"
)
PUSH_WAITING = (
    "<b>Кто-то записал кружок, пока тебя не было.</b>\n\n"
    "Первые {free} {circles} — бесплатно, дальше как обычно 👀"
)


def _push_new(free: int) -> str:
    return _fmt("PUSH_NEW", PUSH_NEW, free=free, circles=circles_word(free))


def _push_missed(free: int) -> str:
    return _fmt("PUSH_MISSED", PUSH_MISSED, free=free, circles=circles_word(free))


def _push_waiting(free: int) -> str:
    return _fmt("PUSH_WAITING", PUSH_WAITING, free=free, circles=circles_word(free))


PUSH_TEXTS = (_push_new, _push_missed, _push_waiting)

FREE_VIEW_LEFT = (
    "🎁 Этот кружок — за счёт заведения. Бесплатных осталось: <b>{left}</b>."
)
FREE_VIEW_LAST = (
    "🎁 Это был последний бесплатный кружок — "
    "дальше как обычно, {watch_cost} {coin} за просмотр."
)


def free_view_left(left: int) -> str:
    if left:
        return _fmt("FREE_VIEW_LEFT", FREE_VIEW_LEFT, left=left)
    return _fmt(
        "FREE_VIEW_LAST",
        FREE_VIEW_LAST,
        watch_cost=settings.get("watch_cost"),
        coin=coin(),
    )


EMPTY = (
    "Свежих кружочков этого типа пока нет — ты посмотрел все.\n"
    "Загляни позже или смени тип."
)

ARCHIVE_NOTE = "Это кружок из архива бота — он без автора, анкеты у него нет."

EARNED_TOAST = "Твой кружок посмотрели: +{amount}"


def earned_toast(amount: int) -> str:
    return _fmt("EARNED_TOAST", EARNED_TOAST, amount=amount)


LIKE_BONUS_NOTE = "👍 Твой кружок лайкнули: +{amount}"


def like_bonus_note(amount: int) -> str:
    return _fmt("LIKE_BONUS_NOTE", LIKE_BONUS_NOTE, amount=amount)


# --- uploading ------------------------------------------------------------

UPLOAD_NEEDS_PROFILE = (
    "🎬 Сначала анкета.\n\n"
    "Кружочки показываются вместе с анкетой автора: зритель может её открыть и "
    "купить доступ ко всем твоим кружочкам. Без анкеты продавать нечего."
)
UPLOAD_WAIT_REVIEW = (
    "🕒 Анкета на проверке. Как одобрят — можно будет загружать кружочки."
)
UPLOAD_PROFILE_REJECTED = (
    "🔴 Анкета отклонена. Заполни её заново: «Профиль» → «Моя анкета», "
    "потом загружай."
)


def upload_profile_pending(status: str) -> str:
    if status == "pending":
        return UPLOAD_WAIT_REVIEW
    return UPLOAD_PROFILE_REJECTED


UPLOAD_ASK = "🎥 Пришли {kind} кружок одним сообщением.\n\n• минимум {min_duration} секунд\n{payoff}"
UPLOAD_ASK_PAID = "• <b>+{reward}</b> {coin} после проверки модератором"
UPLOAD_ASK_FREE = (
    "• кружочки не оплачиваются — это витрина твоей анкеты\n"
    "• под каждым есть кнопка «Профиль автора»: так тебя находят и покупают\n"
    "• чем больше лайков, тем большему числу людей тебя показывают"
)


def upload_ask(gender: str) -> str:
    reward = settings.reward(gender)
    payoff = (
        _fmt("UPLOAD_ASK_PAID", UPLOAD_ASK_PAID, reward=reward, coin=coin())
        if reward
        else UPLOAD_ASK_FREE
    )
    return _fmt(
        "UPLOAD_ASK",
        UPLOAD_ASK,
        kind="женский" if gender == "f" else "мужской",
        min_duration=settings.get("min_duration"),
        payoff=payoff,
    )


NOT_A_CIRCLE = "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение."

TOO_SHORT = "Кружок {duration} сек — коротко. Минимальная длина: {min_duration} секунд."


def too_short(duration: int) -> str:
    return _fmt(
        "TOO_SHORT",
        TOO_SHORT,
        duration=duration,
        min_duration=settings.get("min_duration"),
    )


DUPLICATE = "Такой кружок уже есть в базе."
TOO_MANY_PENDING = "У тебя уже несколько кружков на проверке. Дождись решения."

UPLOAD_SENT = "✅ Кружок <b>#{circle_id}</b> отправлен на проверку.\n{tail}"
UPLOAD_SENT_PAID = "После одобрения: <b>+{reward}</b> {coin}"
UPLOAD_SENT_FREE = "После одобрения его начнут показывать вместе с твоей анкетой."


def upload_sent(circle_id: int, reward: int) -> str:
    tail = (
        _fmt("UPLOAD_SENT_PAID", UPLOAD_SENT_PAID, reward=reward, coin=coin())
        if reward
        else UPLOAD_SENT_FREE
    )
    return _fmt("UPLOAD_SENT", UPLOAD_SENT, circle_id=circle_id, tail=tail)


APPROVED_PAID = "🟢 Твой кружок одобрен: <b>+{reward}</b> {coin}\nБаланс: <b>{coins}</b>"
APPROVED_FREE = (
    "🟢 Твой кружок одобрен — его начали показывать.\n"
    "Собирай лайки: чем их больше, тем чаще кружок попадается людям, "
    "и тем чаще открывают твою анкету."
)


def approved(reward: int, coins: int) -> str:
    if reward:
        return _fmt(
            "APPROVED_PAID", APPROVED_PAID, reward=reward, coin=coin(), coins=coins
        )
    return APPROVED_FREE


REJECTED = "🔴 Кружок отклонён модератором."


# --- complaints -----------------------------------------------------------

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


CIRCLE_REMOVED = "🔴 Твой кружок удалён по жалобам."
CIRCLE_HIDDEN = "🚫 Твой кружок сняли с показа — модератор счёл его нарушающим правила."
CIRCLE_RESTORED = "🟢 Твой кружок проверили и вернули в показ."


# --- buying coins ---------------------------------------------------------

BUY = (
    "{coin} Баланс: <b>{coins}</b>\n\n"
    "1 ⭐ = <b>{stars_rate}</b> {coin}, минимум {min_stars} ⭐."
)


def buy(coins: int) -> str:
    return _fmt(
        "BUY",
        BUY,
        coin=coin(),
        coins=coins,
        stars_rate=settings.get("stars_rate"),
        min_stars=settings.get("min_stars"),
    )


BUY_CUSTOM = "Сколько ⭐ спишем? Пришли число (от {min_stars})."


def buy_custom() -> str:
    return _fmt("BUY_CUSTOM", BUY_CUSTOM, min_stars=settings.get("min_stars"))


BUY_CHOOSE_METHOD = (
    "💰 <b>Покупка {coins} монет</b>\n\n"
    "Сумма: <b>{stars} ⭐</b> → <b>{coins}</b> {coin}\n\n"
    "Выбери способ оплаты:"
)


def buy_choose_method(stars: int, coins: int) -> str:
    return _fmt(
        "BUY_CHOOSE_METHOD", BUY_CHOOSE_METHOD, stars=stars, coins=coins, coin=coin()
    )


BUY_PICK_METHOD = "Способ оплаты выбирается кнопкой под сообщением выше."

BUY_BAD_INPUT = "Нужно целое число от {min_stars}."


def buy_bad_input() -> str:
    return _fmt("BUY_BAD_INPUT", BUY_BAD_INPUT, min_stars=settings.get("min_stars"))


CRYPTO_INVOICE = (
    "🧾 <b>Счёт на {amount} {asset}</b>\n\n"
    "Получишь: <b>{coins}</b> {coin}\n"
    "Оплата через {provider}.\n\n"
    "Жми «Оплатить», а после оплаты — «Проверить». "
    "Монетки придут сами в течение минуты.\n"
    "Счёт действует {minutes} минут."
)


def crypto_invoice(provider: str, amount: str, asset: str, coins: int) -> str:
    import crypto
    from config import INVOICE_TTL

    return _fmt(
        "CRYPTO_INVOICE",
        CRYPTO_INVOICE,
        amount=amount,
        asset=asset,
        coins=coins,
        coin=coin(),
        provider=crypto.TITLES.get(provider, provider),
        minutes=INVOICE_TTL // 60,
    )


CRYPTO_PAID = (
    "🟢 Оплачено {amount} {asset} → <b>+{coins}</b> {coin}\nБаланс: <b>{balance}</b>"
)


def crypto_paid(amount: str, asset: str, coins: int, balance: int) -> str:
    return _fmt(
        "CRYPTO_PAID",
        CRYPTO_PAID,
        amount=amount,
        asset=asset,
        coins=coins,
        coin=coin(),
        balance=balance,
    )


CRYPTO_PENDING = "Оплата ещё не пришла. Если только что перевёл — подожди минуту."
CRYPTO_EXPIRED = "Счёт больше не действует. Оформи новый в «Магазине»."
CRYPTO_CANCELLED = "Счёт отменён."
CRYPTO_FAILED = (
    "😕 Не получилось выставить счёт — платёжный сервис не ответил.\n"
    "Попробуй ещё раз или выбери другой способ оплаты."
)
CRYPTO_GONE = "Счёт не найден."

PAID = "🟢 Оплачено {stars} ⭐ → <b>+{added}</b> {coin}\nБаланс: <b>{coins}</b>"


def paid(stars: int, coins_added: int, coins: int) -> str:
    return _fmt("PAID", PAID, stars=stars, added=coins_added, coin=coin(), coins=coins)


# --- the user's own profile screen ---------------------------------------

PROFILE = (
    "{icon_profile} <b>Твой профиль:</b>\n\n"
    "{icon_uploaded} Загружено кружков: <b>{approved}</b>\n"
    "{icon_ratings} Оценки: {icon_like} <b>{likes}</b> | {icon_dislike} <b>{dislikes}</b>\n"
    "{icon_views} Просмотрено кружков: <b>{watched}</b>\n"
    "{icon_balance} Баланс: <b>{coins}</b> {icon_coin}\n\n"
    "{icon_earnings} <b>Хочешь зарабатывать в Krujok — жми «Моя анкета» 👇</b>\n\n"
    "👥 Приглашено пользователей: {ref_done}\n"
    "💸 К выводу: <b>{withdrawable}</b> {coin} (~{stars} ⭐)\n"
    "🛒 Продано: {sold_content} доступов · {sold_contact} контактов\n"
    "👀 Просмотров твоих кружков: {views}"
)


def profile(
    user_id: int,
    coins: int,
    s: dict,
    earned: int,
    likes: int,
    dislikes: int,
    views: int,
    ref_done: int,
    sales: dict | None = None,
    withdrawable: int = 0,
) -> str:
    sales = sales or {"content": 0, "contact": 0, "income": 0}
    return _fmt(
        "PROFILE",
        PROFILE,
        icon_profile=emoji.text(emoji.PROFILE_HEADER),
        icon_uploaded=emoji.text(emoji.UPLOADED_COUNT),
        icon_ratings=emoji.text(emoji.RATINGS_ICON),
        icon_like=emoji.text(emoji.LIKE_EMOJI),
        icon_dislike=emoji.text(emoji.DISLIKE_EMOJI),
        icon_views=emoji.text(emoji.VIEWS_COUNT),
        icon_balance=emoji.text(emoji.BALANCE_ICON),
        icon_coin=emoji.text(emoji.COIN_EMOJI),
        icon_earnings=emoji.text(emoji.EARNINGS_ICON),
        coin=coin(),
        approved=s["approved"],
        watched=s["watched"],
        likes=likes,
        dislikes=dislikes,
        coins=coins,
        earned=earned,
        ref_done=ref_done,
        withdrawable=withdrawable,
        stars=settings.stars_for(withdrawable),
        sold_content=sales["content"],
        sold_contact=sales["contact"],
        views=views,
        user_id=user_id,
    )


MY_CIRCLES = (
    "📤 <b>Мои загруженные кружки:</b>\n\n"
    "🟢 Одобрено: {approved}\n"
    "🕒 На проверке: {pending}\n"
    "🔴 Отклонено: {rejected}\n\n"
    "Всего: {total}"
)


def my_circles(stats: dict) -> str:
    total = stats["approved"] + stats["pending"] + stats["rejected"]
    return _fmt(
        "MY_CIRCLES",
        MY_CIRCLES,
        approved=stats["approved"],
        pending=stats["pending"],
        rejected=stats["rejected"],
        total=total,
    )


MY_CIRCLES_EMPTY = "Ты ещё ничего не загрузил."
BOUGHT_EMPTY = "Ты ещё ничего не купил."
BOUGHT_HEADER = "🛒 <b>Купленные кружочки:</b>\n"


# --- author profile: filling it in ---------------------------------------

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
    "🖼 <b>Моя анкета</b>\n\n"
    "Пришли фото для анкеты — его увидят все, кто листает анкеты.\n"
    "Лицо показывать необязательно."
)

PROFILE_ABOUT = "✍️ Теперь описание — пара строк о себе.\nДо {limit} символов. «-» — оставить пустым."


def profile_about() -> str:
    return _fmt("PROFILE_ABOUT", PROFILE_ABOUT, limit=ABOUT_MAX)


PROFILE_ABOUT_TEXT_ONLY = "Описание — текстом. «-» — оставить пустым."

PROFILE_GENDER = "Кто ты?"

PROFILE_PRICE_CONTENT = (
    "💰 Цена доступа ко <b>всем твоим кружочкам</b> в монетках.\n"
    "От {price_min} до {price_max}.\n\n"
    "Тебе достаётся {author_share}% с каждой покупки."
)


def profile_price_content() -> str:
    return _fmt(
        "PROFILE_PRICE_CONTENT",
        PROFILE_PRICE_CONTENT,
        price_min=settings.get("price_min"),
        price_max=settings.get("price_max"),
        author_share=settings.get("author_share"),
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

PROFILE_PRICE_CONTACT = (
    "💬 Цена за доступ к личке в монетках.\nОт {price_min} до {price_max}."
)


def profile_price_contact() -> str:
    return _fmt(
        "PROFILE_PRICE_CONTACT",
        PROFILE_PRICE_CONTACT,
        price_min=settings.get("price_min"),
        price_max=settings.get("price_max"),
    )


PROFILE_BAD_PRICE = "Нужно число от {price_min} до {price_max}."


def profile_bad_price() -> str:
    return _fmt(
        "PROFILE_BAD_PRICE",
        PROFILE_BAD_PRICE,
        price_min=settings.get("price_min"),
        price_max=settings.get("price_max"),
    )


PROFILE_SENT = (
    "✅ Анкета отправлена на проверку. Как только модератор её одобрит, "
    "её начнут показывать другим."
)
PROFILE_NOT_PHOTO = "Нужно именно фото."
PROFILE_APPROVED = "🟢 Твоя анкета одобрена — её уже показывают."

PROFILE_FIELD_SAVED = "✅ {field} обновлено.\n📬 Анкета отправлена на повторную проверку."
PROFILE_CONTACT_OFF = (
    "✅ Личка снята с продажи.\n📬 Анкета отправлена на повторную проверку."
)


def profile_field_saved(field: str) -> str:
    return _fmt("PROFILE_FIELD_SAVED", PROFILE_FIELD_SAVED, field=field)


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
        changes.append(f"личка {was or 'не продавалась'} → {now or 'не продаётся'}")
    return changes


REJECT_REASONS = {
    "photo": "фото не подходит: чужое, не по теме или без человека",
    "about": "описание не по теме или набор символов",
    "ads": "реклама, ссылки или контакты в анкете",
    "rules": "нарушает правила сервиса",
    "quality": "слишком плохое качество фото",
}

PROFILE_REVERTED = (
    "🔴 Правки в анкете отклонены.{reason}\n\n"
    "Вернули прошлую версию — она снова показывается. "
    "Можешь отредактировать заново."
)
PROFILE_REJECTED = (
    "🔴 Анкета отклонена модератором.{reason}\n\n"
    "Заполни её заново — это займёт минуту. Без анкеты нельзя загружать "
    "кружочки и зарабатывать на них."
)
PROFILE_REASON_TAIL = "\n\nПричина: <b>{reason}</b>"


def _reason_tail(reason: str) -> str:
    if not reason:
        return ""
    return _fmt("PROFILE_REASON_TAIL", PROFILE_REASON_TAIL, reason=reason)


def profile_reverted(reason: str = "") -> str:
    return _fmt("PROFILE_REVERTED", PROFILE_REVERTED, reason=_reason_tail(reason))


def profile_rejected(reason: str = "") -> str:
    return _fmt("PROFILE_REJECTED", PROFILE_REJECTED, reason=_reason_tail(reason))


PROFILE_EMPTY_WAIT = "Анкет пока нет — все просмотрены. Загляни позже."

PROFILE_EMPTY_PITCH = (
    "Анкет пока нет — но ты можешь стать первым.\n\n"
    "Анкета — это твоя витрина: фото, описание и твоя цена. Другие покупают "
    "доступ ко всем твоим кружочкам, и <b>{author_share}%</b> "
    "от каждой покупки достаётся тебе. Заработанное выводится в ⭐ "
    "от {payout_min} монеток.\n\n"
    "Без анкеты кружочки загружать нельзя — с неё всё и начинается."
)


def profile_empty_pitch() -> str:
    return _fmt(
        "PROFILE_EMPTY_PITCH",
        PROFILE_EMPTY_PITCH,
        author_share=settings.get("author_share"),
        payout_min=settings.get("payout_min"),
    )


STATUS_PENDING = "🕒 на проверке"
STATUS_APPROVED = "🟢 показывается"
STATUS_REJECTED = "🔴 отклонена"
CONTACT_NOT_SOLD = "не продаётся"

PROFILE_STATUS = (
    "<b>Моя анкета</b> · {status}\n\n"
    "{about}\n\n"
    "Кружочки: {price_content} {coin}\n"
    "Личка: {contact}\n"
    "Показов: {views} · покупок: {sold}"
)


def _status_label(status: str) -> str:
    return {
        "pending": STATUS_PENDING,
        "approved": STATUS_APPROVED,
        "rejected": STATUS_REJECTED,
    }.get(status, status)


def _contact_line(profile) -> str:
    if profile["contact_ok"] and profile["price_contact"]:
        return f"{profile['price_contact']} {coin()}"
    return CONTACT_NOT_SOLD


def profile_status(profile) -> str:  # noqa: D401 — the author's own view
    return _fmt(
        "PROFILE_STATUS",
        PROFILE_STATUS,
        status=_status_label(profile["status"]),
        about=html.escape(profile["about"] or "Без описания"),
        price_content=profile["price_content"],
        coin=coin(),
        contact=_contact_line(profile),
        views=profile["views"],
        sold=profile["sold"],
    )


PROFILE_CARD = (
    "<b>{who}</b>\n\n"
    "{icon_about} {about}\n\n"
    "{icon_count} Кружочков у автора: <b>{circles}</b>\n"
    "{icon_price} Доступ ко всем: <b>{price_content}</b> {coin}\n"
    "Личка: {contact}\n"
    "{icon_sold} Купили: {sold} раз\n\n"
    "{icon_info} <i>Покупка открывает кружочки, которые есть "
    "у автора прямо сейчас.</i>"
)


def profile_card(profile, circles: int) -> str:
    return _fmt(
        "PROFILE_CARD",
        PROFILE_CARD,
        who=PERSON_TITLE(profile["gender"]),
        icon_about=emoji.text(emoji.ABOUT),
        about=html.escape(profile["about"] or "Без описания"),
        icon_count=emoji.text(emoji.CIRCLE_COUNT),
        circles=circles,
        icon_price=emoji.text(emoji.PRICE),
        price_content=profile["price_content"],
        coin=coin(),
        contact=_contact_line(profile),
        icon_sold=emoji.text(emoji.SOLD),
        sold=profile["sold"],
        icon_info=emoji.text(emoji.INFO),
    )


# --- buying from an author ------------------------------------------------

BOUGHT_CONTENT = (
    "🟢 Доступ открыт: {count} {circles} этого автора теперь бесплатны.\n"
    "Жми «Кружочки автора», чтобы посмотреть."
)


def bought_content(count: int, share: int) -> str:
    return _fmt(
        "BOUGHT_CONTENT",
        BOUGHT_CONTENT,
        count=count,
        circles=circles_word(count),
        share=share,
    )


BOUGHT_CONTACT = "🟢 Личка автора: @{username}\n\nНапиши ему сам."


def bought_contact(username: str) -> str:
    return _fmt("BOUGHT_CONTACT", BOUGHT_CONTACT, username=username)


SALE_NOTE = "💰 Купили {what}: <b>+{share}</b> {coin}"
SALE_KIND_CONTENT = "доступ к твоим кружочкам"
SALE_KIND_CONTACT = "твою личку"


def sale_note(kind: str, share: int) -> str:
    what = SALE_KIND_CONTENT if kind == "content" else SALE_KIND_CONTACT
    return _fmt("SALE_NOTE", SALE_NOTE, what=what, share=share, coin=coin())


MORE_CIRCLES = "Осталось ещё {left} {circles} этого автора."


def more_circles(left: int) -> str:
    return _fmt("MORE_CIRCLES", MORE_CIRCLES, left=left, circles=circles_word(left))


CONTACT_NOT_FOR_SALE = "Автор не продаёт личку."
NOTHING_TO_SELL = "У автора пока нет кружочков — покупать нечего."
ALREADY_BOUGHT = "Уже куплено."


# --- payouts -------------------------------------------------------------

PAYOUT_SCREEN = (
    "💸 <b>Вывод</b>\n\n"
    "Доступно к выводу: <b>{available}</b> {coin} (~{stars} ⭐)\n"
    "Курс: {rate} монетки = 1 ⭐, минимум {low} монеток\n\n"
    "Выводятся только заработанные монетки — купленные за ⭐ нельзя.{pending}"
)
PAYOUT_SCREEN_PENDING = "\n\n🕒 Заявок в работе: {pending}"


def payout_screen(available: int, pending: int) -> str:
    tail = (
        _fmt("PAYOUT_SCREEN_PENDING", PAYOUT_SCREEN_PENDING, pending=pending)
        if pending
        else ""
    )
    return _fmt(
        "PAYOUT_SCREEN",
        PAYOUT_SCREEN,
        available=available,
        coin=coin(),
        stars=settings.stars_for(available),
        rate=settings.get("payout_rate"),
        low=settings.get("payout_min"),
        pending=tail,
    )


PAYOUT_ASK_AMOUNT = "Сколько монеток вывести? Доступно {available}, минимум {low}."


def payout_ask_amount(available: int) -> str:
    return _fmt(
        "PAYOUT_ASK_AMOUNT",
        PAYOUT_ASK_AMOUNT,
        available=available,
        low=settings.get("payout_min"),
    )


PAYOUT_NOT_A_NUMBER = "Нужно число — только цифры, без пробелов и букв."
PAYOUT_OVER_AVAILABLE = "Столько нет: к выводу доступно <b>{available}</b> монеток."
PAYOUT_UNDER_MIN = "Это меньше минимума — выводим от <b>{low}</b> монеток."


def payout_bad_amount(raw: str, available: int) -> str:
    """Says which of the three ways the number was wrong."""
    low = settings.get("payout_min")
    if not raw.isdigit():
        why = PAYOUT_NOT_A_NUMBER
    elif int(raw) > available:
        why = _fmt("PAYOUT_OVER_AVAILABLE", PAYOUT_OVER_AVAILABLE, available=available)
    else:
        why = _fmt("PAYOUT_UNDER_MIN", PAYOUT_UNDER_MIN, low=low)
    return f"{why}\n\n{payout_ask_amount(available)}"


PAYOUT_ASK_DETAILS = (
    "Куда отправить? Пришли адрес кошелька (USDT/TON) или свой @username — "
    "админ свяжется и выплатит."
)

PAYOUT_CREATED = (
    "✅ Заявка <b>#{payout_id}</b> создана: {coins} {coin} → {stars} ⭐.\n"
    "Монетки заморожены. Админ выплатит вручную и отметит заявку."
)


def payout_created(payout_id: int, coins: int, stars: int) -> str:
    return _fmt(
        "PAYOUT_CREATED",
        PAYOUT_CREATED,
        payout_id=payout_id,
        coins=coins,
        coin=coin(),
        stars=stars,
    )


PAYOUT_PAID = "🟢 Заявка #{payout_id} выплачена: {stars} ⭐."


def payout_paid(payout_id: int, stars: int) -> str:
    return _fmt("PAYOUT_PAID", PAYOUT_PAID, payout_id=payout_id, stars=stars)


PAYOUT_REJECTED = "🔴 Заявка #{payout_id} отклонена, {coins} монеток вернулись на баланс."


def payout_rejected(payout_id: int, coins: int) -> str:
    return _fmt("PAYOUT_REJECTED", PAYOUT_REJECTED, payout_id=payout_id, coins=coins)


PAYOUT_SPENT = (
    "На балансе только {balance} монеток, а на вывод нужно {wanted}: "
    "заработанное уже потрачено на просмотры или покупки."
)


def payout_spent(balance: int, wanted: int) -> str:
    return _fmt("PAYOUT_SPENT", PAYOUT_SPENT, balance=balance, wanted=wanted)


PAYOUT_TOO_SMALL = "Минимум для вывода — {low} монеток. Доступно: {available}."


def payout_too_small(available: int) -> str:
    return _fmt(
        "PAYOUT_TOO_SMALL",
        PAYOUT_TOO_SMALL,
        low=settings.get("payout_min"),
        available=available,
    )


# --- cheques --------------------------------------------------------------

CHEQUE_POST = (
    "🎟 <b>Чек на {coins} монеток</b>\n\n"
    "Активаций: <b>{total}</b>\n"
    "Жми кнопку — монетки упадут на баланс."
)


def cheque_post(coins: int, total: int) -> str:
    return _fmt("CHEQUE_POST", CHEQUE_POST, coins=coins, total=total)


CHEQUE_CLAIMED = "🎟 Чек активирован: <b>+{coins}</b> {coin}\nБаланс: <b>{balance}</b>"


def cheque_claimed(coins: int, balance: int) -> str:
    return _fmt(
        "CHEQUE_CLAIMED", CHEQUE_CLAIMED, coins=coins, coin=coin(), balance=balance
    )


CHEQUE_NEEDS_REFS = (
    "🎟 Этот чек — для тех, кто приводит друзей.\n\n"
    "Нужно приглашённых: <b>{need}</b>, у тебя: <b>{have}</b>.\n"
    "Позови друзей по своей ссылке и возвращайся — чек подождёт, "
    "пока не кончатся активации."
)


def cheque_needs_refs(need: int, have: int) -> str:
    return _fmt("CHEQUE_NEEDS_REFS", CHEQUE_NEEDS_REFS, need=need, have=have)


CHEQUE_GONE = "🎟 Такого чека нет — возможно, его удалили."
CHEQUE_TAKEN = "🎟 Этот чек ты уже активировал."
CHEQUE_EMPTY = "🎟 Активации закончились — этот чек уже разобрали."


# --- gate, welcome, subscription -----------------------------------------

WELCOME = (
    "👋 <b>Добро пожаловать</b>\n\n"
    "{rules}{gift}\n\n"
    "Нажимая кнопку ниже, ты подтверждаешь, что тебе есть 18 лет, "
    "и принимаешь правила сервиса."
)
WELCOME_GIFT = "\n\n🎁 За согласие дарим <b>{bonus}</b> монеток на первые просмотры."


def welcome() -> str:
    bonus = settings.get("welcome_bonus")
    gift = _fmt("WELCOME_GIFT", WELCOME_GIFT, bonus=bonus) if bonus else ""
    return _fmt("WELCOME", WELCOME, rules=rules(), gift=gift)


ACCEPTED = "Готово. Приятного просмотра 🙂"

WELCOME_BONUS = (
    "🎁 Держи <b>{amount}</b> {coin} на старт — это {views} {circles} бесплатно.\n\n"
    "Кончатся — запиши свой кружок или загляни в «Магазин»."
)


def welcome_bonus(amount: int) -> str:
    views = amount // settings.get("watch_cost")
    return _fmt(
        "WELCOME_BONUS",
        WELCOME_BONUS,
        amount=amount,
        coin=coin(),
        views=views,
        circles=circles_word(views),
    )


SUBSCRIBE = (
    "📢 Бот работает только для подписчиков.\n\n"
    "Выполни условия по кнопкам ниже — подпишись на {what} — "
    "и нажми «Я подписался».{gift}"
)
SUBSCRIBE_ONE = "канал"
SUBSCRIBE_MANY = "все каналы"
SUBSCRIBE_SPONSORS = "всех спонсоров"
SUBSCRIBE_GIFT = "\n\n🎁 За подписку начислим <b>{bonus}</b> монеток."


def subscribe(missing: int = 1, bots: bool = False) -> str:
    """«Подпишись на канал» stops being true once a sponsor bot is in the list."""
    bonus = settings.get("sub_bonus")
    gift = _fmt("SUBSCRIBE_GIFT", SUBSCRIBE_GIFT, bonus=bonus) if bonus else ""
    if bots:
        what = SUBSCRIBE_SPONSORS
    else:
        what = SUBSCRIBE_ONE if missing <= 1 else SUBSCRIBE_MANY
    return _fmt("SUBSCRIBE", SUBSCRIBE, gift=gift, what=what)


SUB_BONUS = "🎁 Спасибо за подписку: <b>+{amount}</b> {coin}"


def sub_bonus(amount: int) -> str:
    return _fmt("SUB_BONUS", SUB_BONUS, amount=amount, coin=coin())


SUBSCRIBE_MISSING = "Подписки не вижу. Подпишись на канал и нажми ещё раз."
SUBSCRIBE_OK = "Готово 🟢"

REFERRAL_PAID = (
    "🟢 По твоей ссылке пришёл друг: <b>+{reward}</b> монеток.\n"
    "Всего приглашено: {done}"
)


def referral_paid(reward: int, done: int) -> str:
    return _fmt("REFERRAL_PAID", REFERRAL_PAID, reward=reward, done=done)


BANNED = "Доступ закрыт."
MAINTENANCE = "🔧 Бот на техработах. Загляни чуть позже."


# --- ad campaign report (for whoever bought the traffic) ------------------

TRAFFER_UNKNOWN = "Команда не подходит — проверь её у того, кто выдал ссылку."

TRAFFER_REPORT = (
    "📊 <b>{title}</b>\n\n"
    "🕓 <b>За всё время</b>\n"
    "Новых пользователей: <b>{users}</b>\n"
    "Прошли подписку: {subscribed} ({subscribed_pct})\n"
    "Приняли правила: {accepted} ({accepted_pct})\n"
    "Покупали монетки: {payers} ({payers_pct})\n\n"
    "📅 7 дней · людей {week_users}, подписок {week_subscribed}\n"
    "📅 Сутки · людей {day_users}, подписок {day_subscribed}\n\n"
    "<code>{link}</code>"
)


def traffer_report(stats: dict, week: dict, day: dict, link: str) -> str:
    """What the person who bought the ad sees: traffic, not the money behind it."""

    def pct(part: int, whole: int) -> str:
        return f"{part * 100 / whole:.1f}%" if whole else "—"

    return _fmt(
        "TRAFFER_REPORT",
        TRAFFER_REPORT,
        title=stats["title"] or stats["code"],
        users=stats["users"],
        subscribed=stats["subscribed"],
        subscribed_pct=pct(stats["subscribed"], stats["users"]),
        accepted=stats["accepted"],
        accepted_pct=pct(stats["accepted"], stats["users"]),
        payers=stats["payers"],
        payers_pct=pct(stats["payers"], stats["users"]),
        week_users=week["users"],
        week_subscribed=week["subscribed"],
        day_users=day["users"],
        day_subscribed=day["subscribed"],
        link=link,
    )


# --- short answers to a tap ----------------------------------------------

VOTE_LIKE = "👍"
VOTE_DISLIKE = "👎"
VOTE_CANCEL = "Отменил"
PROFILE_NOTHING_TO_HIDE = "Нечего скрывать."
PROFILE_HIDDEN_TOAST = "Анкета скрыта."
PROFILE_SAVED_TOAST = "Готово 🟢"
CONTACT_OFF_TOAST = "Личка больше не продаётся."
USERNAME_SEEN = "Вижу 🟢"
BUY_NO_AMOUNT = "Сумма не выбрана — начни заново."
BUY_CARD_SOON = "⚠️ Оплата картой пока недоступна. Используйте Telegram Stars."

SENDING_CIRCLES = "Отправляю {count}"


def sending_circles(count: int) -> str:
    return _fmt("SENDING_CIRCLES", SENDING_CIRCLES, count=count)


# The author's telegram id has no business here: the buyer paid for circles, and
# an id is enough to look a person up. Only a bought contact opens the username.
AUTHOR_NO_PROFILE = "Автор без анкеты"
BOUGHT_ROW = "{index}. {who} — {count} {circles}"


def bought_row(index: int, who: str, count: int) -> str:
    return _fmt(
        "BOUGHT_ROW",
        BOUGHT_ROW,
        index=index,
        who=who,
        count=count,
        circles=circles_word(count),
    )


# --- what the code says when something is off ----------------------------

CIRCLE_GONE = "Кружок уже удалён."
CIRCLE_NOT_SHOWN = "Этот кружок тебе не показывали."
CIRCLE_OWN_VOTE = "Свой кружок оценивать нечестно 🙂"
PROFILE_GONE = "Анкета пропала."
PROFILE_OWN = "Это твоя анкета 🙂"
PROFILE_NONE_YET = "У автора нет анкеты."
NEED_PROFILE_FIRST = "Сначала заполни анкету."
NOT_SO_FAST = "Не так быстро 🙂"
SEND_FAILED = "Не удалось отправить кружок, монетки вернул."
BUY_FIRST = "Сначала купи доступ."
AUTHOR_EMPTY = "У автора пока нечего смотреть."
NOT_ENOUGH_COINS_TOAST = "Не хватает монеток."
BOUGHT_TOAST = "Куплено 🟢"
STALE_BUTTON = "Кнопка устарела"

