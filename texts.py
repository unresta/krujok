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
import time

import emoji
import settings
from config import ABOUT_MAX, MSK_OFFSET
from keyboards import PERSON_TITLE, PREF_TITLE

logger = logging.getLogger(__name__)


def _fmt(key: str, template: str, **values) -> str:
    """Fill a template, falling back to the shipped one if an edit broke it.

    {coin} is filled in for every text, whether or not the caller passed it: the
    coin is the one insert that makes sense in any message about money, and an
    admin who adds it to a text in the panel should not have to wait for a
    release for it to work. Anything a caller passes wins, so a text that fills
    {coin} itself is untouched.
    """
    values.setdefault("coin", coin())
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
    "По умолчанию нет: кружочки уходят с защитой от пересылки и сохранения. "
    "Защита снимается подпиской A++ или Premium — они в «Подписке».\n\n"
    "<b>Можно ли привести людей на свою анкету со стороны?</b>\n"
    "Да. «Профиль» → «🔗 Ссылка на мою анкету»: ставь её в свой канал или "
    "куда угодно ещё. Кто перейдёт — сразу увидит твою анкету и сможет "
    "купить доступ к кружочкам. Сколько людей пришло, видно там же.\n\n"
    "<b>Как получить больше просмотров анкеты?</b>\n"
    "Кнопка «🚀 Продвижение» в «Моей анкете»: пока оплачено, твоя анкета "
    "идёт в начале выдачи, и её видит намного больше людей. Когда срок "
    "кончится, бот пришлёт, сколько человек её увидело.\n\n"
    "<b>Что дают подписки?</b>\n"
    "Просмотр кружочков перестаёт стоить монетки: A+ даёт бесплатный лимит "
    "в день, A++ и Premium — без лимита, плюс пересылка и скачивание. "
    "Premium ещё поднимает потолок кружочков на проверке. "
    "Платятся монетками за день, кнопка «Подписка» в меню.\n\n"
    "<b>Почему для загрузки нужна анкета?</b>\n"
    "Потому что кружок и автор связаны: под каждым кружком есть кнопка "
    "«Профиль автора», через неё зритель покупает доступ ко всем твоим "
    "кружочкам. Без анкеты этот путь обрывается.\n\n"
    "<b>Кто увидит, кто я?</b>\n"
    "В анкете — только фото и описание, которые ты сам выбрал. Имя и "
    "@username не показываются никогда; @username уходит покупателю только "
    "если ты сам включил продажу лички и он за неё заплатил.\n\n"
    "<b>Что делать с нарушением?</b>\n"
    "Кнопка «Пожаловаться» под кружком. Жалобы уходят модераторам."
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

# For the half of the base that pressed /start, met the rules that used to
# stand there and stopped. They have never seen a single circle, so the pitch is
# «начни», not «вернись» — and there is nothing left to confirm any more.
PUSH_UNACCEPTED = (
    "<b>Ты так и не начал 🙈</b>\n\n"
    "Ничего подтверждать не нужно: {free} {circles} бесплатно уже на счету — "
    "жми и смотри."
)


def push_unaccepted(free: int) -> str:
    return _fmt(
        "PUSH_UNACCEPTED", PUSH_UNACCEPTED, free=free, circles=circles_word(free)
    )

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


# The trial says nothing about itself while it is being spent: a newcomer is
# watching circles, not counting free ones. This is the only place it is ever
# mentioned — five minutes of silence after the circle they never asked for,
# where saying what is left is the whole reason to write at all.
TRIAL_PUSH = (
    "🎁 <b>У тебя ещё {left} {circles} бесплатно!</b>\n\n"
    "Платить ничего не нужно — просто жми кнопку."
)


def trial_push(left: int) -> str:
    return _fmt("TRIAL_PUSH", TRIAL_PUSH, left=left, circles=circles_word(left))


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


REJECTED = "🔴 Кружок отклонён модератором.{reason}"
CIRCLE_REASON_TAIL = "\n\nПричина: <b>{reason}</b>"

# What a moderator turns a circle down for. The keys go into callback data, so
# they stay short and ascii; the labels are what the author reads.
# The child one leads: it is the verdict that has to be one tap away, and the
# same key «minor» the complaint list already uses for it.
CIRCLE_REJECT_REASONS = {
    "minor": "на кружочке ребёнок",
    "quality": "плохое качество: темно, размыто или ничего не видно",
    "short": "почти пустой кружок: ничего не происходит",
    "face": "лица нет или снято не то, что нужно",
    "ads": "реклама, ссылки или контакты в кадре",
    "stolen": "чужой кружок, не свой",
    "rules": "нарушает правила сервиса",
    "unfit": "не подходит",
}

# Reasons that take the circle out of the base rather than off the shelf. A
# rejected circle is only hidden — the file stays, and a changed mind brings it
# back. There is nothing here worth keeping or changing one's mind about.
CIRCLE_REJECT_DELETES = {"minor"}
CIRCLE_DELETED = "🔴 Твой кружок удалён.{reason}"


def circle_deleted(reason: str = "") -> str:
    return _fmt("CIRCLE_DELETED", CIRCLE_DELETED, reason=circle_reason_tail(reason))

# Circles also leave rotation without a moderation card — by complaints, or from
# the panel. Those verdicts get a reason too, or «Мои кружки» would show a circle
# as rejected with nothing said about why.
REASON_REPORTS = "жалобы пользователей"
REASON_HIDDEN = "снят с показа модератором"


def circle_reason_tail(reason: str) -> str:
    """A moderator types this one by hand, so it is escaped where it is shown."""
    if not reason:
        return ""
    return _fmt("CIRCLE_REASON_TAIL", CIRCLE_REASON_TAIL, reason=html.escape(reason))


def rejected(reason: str = "") -> str:
    return _fmt("REJECTED", REJECTED, reason=circle_reason_tail(reason))


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
    "1 {coin} = <b>{star_cost}</b> ⭐, минимум {min_stars} ⭐."
)


def buy(coins: int) -> str:
    return _fmt(
        "BUY",
        BUY,
        coin=coin(),
        coins=coins,
        star_cost=settings.get("star_cost"),
        min_stars=settings.get("min_stars"),
    )


BUY_CUSTOM = "Сколько ⭐ спишем? Пришли число (от {min_stars})."


def buy_custom() -> str:
    return _fmt("BUY_CUSTOM", BUY_CUSTOM, min_stars=settings.get("min_stars"))


BUY_CHOOSE_METHOD = (
    "💰 <b>Покупка {coins} монет</b>\n\n"
    "Сумма: <b>{stars} ⭐</b> → <b>{coins}</b> {coin}{bonus}\n\n"
    "Выбери способ оплаты:"
)

BUY_CARD_BONUS = "\n💳 Картой: <b>{total}</b> {coin} — на {percent}% больше"


def buy_card_bonus(coins: int) -> str:
    """The card line on the method screen; empty when there is nothing to add."""
    import paritypay

    if not paritypay.enabled() or not settings.card_bonus(coins):
        return ""
    return BUY_CARD_BONUS.format(
        total=settings.card_total(coins),
        coin=coin(),
        percent=settings.get("card_bonus"),
    )


def buy_choose_method(stars: int, coins: int) -> str:
    return _fmt(
        "BUY_CHOOSE_METHOD",
        BUY_CHOOSE_METHOD,
        stars=stars,
        coins=coins,
        coin=coin(),
        bonus=buy_card_bonus(coins),
    )


BUY_PICK_METHOD = "Способ оплаты выбирается кнопкой под сообщением выше."

BUY_BAD_INPUT = "Нужно целое число от {min_stars}."


def buy_bad_input() -> str:
    return _fmt("BUY_BAD_INPUT", BUY_BAD_INPUT, min_stars=settings.get("min_stars"))


CRYPTO_INVOICE = (
    "🧾 <b>Счёт на {amount} {asset}</b>\n\n"
    "Получишь: <b>{coins}</b> {coin}{bonus}\n"
    "Оплата через {provider}.\n\n"
    "Жми «Оплатить», а после оплаты — «Проверить». "
    "Монетки придут сами в течение минуты.\n"
    "Счёт действует {minutes} минут."
)

INVOICE_BONUS = "\n🎁 Из них <b>+{bonus}</b> {coin} бонусом за оплату картой"


def crypto_invoice(
    provider: str, amount: str, asset: str, coins: int, bonus: int = 0
) -> str:
    import crypto
    import paritypay
    from config import INVOICE_TTL

    titles = {**crypto.TITLES, **paritypay.TITLES}
    return _fmt(
        "CRYPTO_INVOICE",
        CRYPTO_INVOICE,
        amount=amount,
        asset=asset,
        coins=coins,
        coin=coin(),
        provider=titles.get(provider, provider),
        minutes=INVOICE_TTL // 60,
        bonus=INVOICE_BONUS.format(bonus=bonus, coin=coin()) if bonus else "",
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
    "{icon_balance} Баланс: <b>{coins}</b> {icon_coin}{withdraw}\n\n"
    "{icon_earnings} <b>Хочешь зарабатывать в Krujok — жми «Моя анкета» 👇</b>\n\n"
    "👥 Приглашено пользователей: {ref_done}\n"
    "🛒 Продано: {sold_content} доступов · {sold_contact} контактов\n"
    "👀 Просмотров твоих кружков: {views}"
)

# Right under the balance and worded as a part of it: two numbers a screen apart
# read as two wallets, and that is exactly the question this line answers.
PROFILE_WITHDRAW = "\n💸 Из них можно вывести: <b>{withdrawable}</b> (~{stars} ⭐)"


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
    ever_earned: bool = False,
) -> str:
    sales = sales or {"content": 0, "contact": 0, "income": 0}
    # Nothing ever earned means nothing to explain — a lone «вывести: 0» under
    # the balance of someone who only watches is a question, not an answer.
    withdraw = (
        _fmt(
            "PROFILE_WITHDRAW",
            PROFILE_WITHDRAW,
            withdrawable=withdrawable,
            stars=settings.stars_for(withdrawable),
            coin=coin(),
        )
        if ever_earned or withdrawable
        else ""
    )
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
        withdraw=withdraw,
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

# Own uploads, opened from the counters above. A status the author has none of
# gets no button, so every one of these screens has something on it.
MY_CIRCLES_STATUS = {
    "approved": "🟢 <b>Одобренные кружки</b> — их показывают людям.",
    "pending": "🕒 <b>Кружки на проверке</b> — модератор ещё не решил.",
    "rejected": "🔴 <b>Отклонённые кружки</b> — их не показывают.",
}
MY_CIRCLE_GONE = "Этого кружка больше нет."
MY_CIRCLE_ASK = (
    "Удалить этот кружок? Он пропадёт совсем — вместе с просмотрами и лайками, "
    "и у тех, кто купил доступ, тоже. Отменить будет нельзя."
)
MY_CIRCLE_DELETED = "Кружок удалён."
MY_CIRCLES_STATUS_EMPTY = "Здесь пусто."
MY_CIRCLES_DONE = "Это всё."
MY_CIRCLES_MORE = "Осталось ещё {left} {circles}."

MY_CIRCLE_INFO = (
    "Кружок #{circle_id}\n"
    "Загружен: {date}\n"
    "Длина: {duration} сек\n"
    "Просмотров: {views}\n"
    "Лайков: {likes} · дизлайков: {dislikes}\n"
    "Заработано: {earned}"
)
MY_CIRCLE_INFO_REASON = "\n\nПричина отказа: {reason}"

ALERT_MAX = 200  # Telegram refuses a callback alert longer than this


def my_circles_more(left: int) -> str:
    return _fmt("MY_CIRCLES_MORE", MY_CIRCLES_MORE, left=left, circles=circles_word(left))


def my_circle_info(circle) -> str:
    """The alert under an own circle — plain text, Telegram renders no HTML there."""
    text = _fmt(
        "MY_CIRCLE_INFO",
        MY_CIRCLE_INFO,
        circle_id=circle["id"],
        date=when(circle["created_at"]),
        duration=circle["duration"],
        views=circle["views"],
        likes=circle["likes"],
        dislikes=circle["dislikes"],
        earned=circle["earned"],
    )
    reason = circle["reject_reason"]
    if circle["status"] == "rejected" and reason:
        text += _fmt("MY_CIRCLE_INFO_REASON", MY_CIRCLE_INFO_REASON, reason=reason)
    # A reason is typed by hand and can run to 200 characters on its own, which
    # is the whole alert — cut it here rather than lose the alert to an error.
    if len(text) > ALERT_MAX:
        return text[: ALERT_MAX - 1] + "…"
    return text


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
# Prices are the author's own to set, so they change on the spot — and the
# message has to say so, or «обновлено» reads like «ушло на проверку».
PROFILE_PRICE_SAVED = "✅ {field}: <b>{price}</b> {coin}.\nИзменения уже в силе."
PROFILE_CONTACT_OFF = "✅ Личка снята с продажи. Изменение уже в силе."


def profile_field_saved(field: str) -> str:
    return _fmt("PROFILE_FIELD_SAVED", PROFILE_FIELD_SAVED, field=field)


def profile_price_saved(field: str, price: int) -> str:
    return _fmt(
        "PROFILE_PRICE_SAVED", PROFILE_PRICE_SAVED, field=field, price=price, coin=coin()
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


# Hidden by complaints is not the same as turned down: the anketa is still
# there, whole, and the author fixes it themselves rather than starting over.
PROFILE_FROZEN = (
    "🚫 <b>Твоя анкета снята с показа по жалобам.</b>{reason}\n\n"
    "Она никуда не делась. Открой «Моя анкета», поправь то, на что жалуются, — "
    "и она сама уйдёт на проверку. Кружочки и монетки остаются при тебе."
)
PROFILE_FROZEN_REASONS = "\n\nНа что жаловались:\n{list}"


def profile_frozen(reasons: list[str]) -> str:
    tail = (
        _fmt(
            "PROFILE_FROZEN_REASONS",
            PROFILE_FROZEN_REASONS,
            list="\n".join(f"• {r}" for r in reasons),
        )
        if reasons
        else ""
    )
    return _fmt("PROFILE_FROZEN", PROFILE_FROZEN, reason=tail)


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
    "Показов: {views} · покупок: {sold}{boost}"
)
PROFILE_STATUS_BOOST = "\n🚀 Продвижение до {left}"


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
    import db  # late: db does not import texts, but texts is imported very early

    left = when(profile["boost_until"]) if db.boost_on(profile) else ""
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
        boost=(
            _fmt("PROFILE_STATUS_BOOST", PROFILE_STATUS_BOOST, left=left)
            if left
            else ""
        ),
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

# --- topping an old purchase up to today's catalogue ----------------------

# The line under a bought card. It is on screen every time, so it says where the
# person stands even when there is nothing to buy — «открыто 38 из 112» with no
# way forward was the whole complaint.
TOPUP_OPEN = "\n\n🎬 Открыто {have} из {total} — можно докупить {missing} за {cost} {coin}"
TOPUP_SOON = (
    "\n\n🎬 Открыто {have} из {total}. Автор выложил новые — докупить можно "
    "будет, когда наберётся ещё {left} {circles}"
)
TOPUP_ALL = "\n\n🎬 Открыто всё, что есть у автора: {have}"


def topup_line(have: int, total: int, price: int) -> str:
    """Where this buyer stands with this author, in one line."""
    missing = max(0, total - have)
    if not missing:
        return _fmt("TOPUP_ALL", TOPUP_ALL, have=have)
    cost = settings.topup_price(price, have, total)
    if settings.topup_worth_it(cost):
        return _fmt(
            "TOPUP_OPEN",
            TOPUP_OPEN,
            have=have, total=total, missing=missing, cost=cost, coin=coin(),
        )
    # How many more circles until the price clears the floor, so the wait has a
    # number on it instead of being «когда-нибудь».
    left = 1
    while total + left > 0 and not settings.topup_worth_it(
        settings.topup_price(price, have, total + left)
    ):
        left += 1
        if left > 1000:  # a price so low it never clears; say nothing rather than lie
            return _fmt("TOPUP_ALL", TOPUP_ALL, have=have)
    return _fmt(
        "TOPUP_SOON",
        TOPUP_SOON,
        have=have, total=total, left=left, circles=circles_word(left),
    )


TOPUP_DONE = (
    "🟢 Докуплено: открылись ещё {added} {circles}.\n"
    "Теперь доступно {total} — жми «Кружочки автора»."
)


def topup_done(added: int, total: int) -> str:
    return _fmt(
        "TOPUP_DONE", TOPUP_DONE, added=added, circles=circles_word(added), total=total
    )


TOPUP_NEWS = (
    "🎬 У автора, чьи кружочки ты покупал, появились новые: "
    "<b>{missing}</b> {circles}.\n"
    "Открыть их — <b>{cost}</b> {coin}."
)


def topup_news(missing: int, cost: int) -> str:
    return _fmt(
        "TOPUP_NEWS",
        TOPUP_NEWS,
        missing=missing, circles=circles_word(missing), cost=cost, coin=coin(),
    )


TOPUP_GONE = "Новых кружочков у автора пока нет."
TOPUP_SMALL = "Новых пока слишком мало — докупить можно будет позже."


# --- payouts -------------------------------------------------------------

PAYOUT_SCREEN = (
    "💸 <b>Вывод</b>\n\n"
    "Доступно к выводу: <b>{available}</b> {coin} (~{stars} ⭐)\n"
    "Курс: {rate} монетки = 1 ⭐, минимум {low} монеток\n\n"
    "Выводятся только заработанные монетки — купленные за ⭐ нельзя. "
    "Внутри бота сначала тратятся купленные, так что заработок остаётся "
    "целым.{spent}{pending}"
)
# Why the number here is smaller than everything they ever made. Without this
# line the only explanation is «бот посчитал неправильно».
PAYOUT_SCREEN_SPENT = "\n\n{coin} Ещё {spent} заработанных ты потратил внутри бота."
PAYOUT_SCREEN_PENDING = "\n\n🕒 Заявок в работе: {pending}"


def payout_screen(available: int, pending: int, spent: int = 0) -> str:
    tail = (
        _fmt("PAYOUT_SCREEN_PENDING", PAYOUT_SCREEN_PENDING, pending=pending)
        if pending
        else ""
    )
    used = (
        _fmt("PAYOUT_SCREEN_SPENT", PAYOUT_SCREEN_SPENT, spent=spent) if spent else ""
    )
    return _fmt(
        "PAYOUT_SCREEN",
        PAYOUT_SCREEN,
        available=available,
        coin=coin(),
        stars=settings.stars_for(available),
        rate=settings.get("payout_rate"),
        low=settings.get("payout_min"),
        spent=used,
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


# --- gate, subscription ---------------------------------------------------

# There is no welcome message any more. The age notice and the rules live in
# the bot's description, where they are read before /start rather than scrolled
# past after it, and the starting coins are simply on the balance the menu
# shows. What a newcomer gets is the menu and a circle.

ACCEPTED = "Готово. Приятного просмотра 🙂"


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
    "Дошли до бота: {accepted} ({accepted_pct})\n"
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
BUY_CARD_SOON = "⚠️ Этот способ оплаты сейчас недоступен. Выбери другой."

SENDING_CIRCLES = "Отправляю {count}"


def sending_circles(count: int) -> str:
    return _fmt("SENDING_CIRCLES", SENDING_CIRCLES, count=count)


# «Отправляю 7» and then nothing is the worst thing this screen can do: the
# promise was made in a toast that disappears, so the shortfall has to be said
# out loud, with the button to try again.
CIRCLES_LOST = (
    "⚠️ Дошло {sent} из {total}.\n\n"
    "Остальные Telegram не пропустил — жми кнопку ещё раз через минуту."
)


def circles_lost(sent: int, total: int) -> str:
    return _fmt("CIRCLES_LOST", CIRCLES_LOST, sent=sent, total=total)


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



# --- paid subscriptions ---------------------------------------------------

TIERS_HEADER = "⭐ <b>Выберите тип подписки:</b>"
TIERS_ACTIVE = "🟢 Сейчас у тебя <b>{tier}</b> — до {until} ({left})."
TIERS_BALANCE = "{coin} Баланс: <b>{coins}</b>"


def tiers_screen(coins: int, tier: str, until: int) -> str:
    import tiers

    blocks = [TIERS_HEADER]
    if tier:
        blocks.append(
            _fmt(
                "TIERS_ACTIVE",
                TIERS_ACTIVE,
                tier=tiers.title(tier),
                until=when(until),
                left=days_left(until),
            )
        )
    for code in tiers.ORDER:
        lines = "\n".join(f"   -<i>{perk}</i>" for perk in tiers.perks(code))
        mark = "⭐ " if code == tiers.PRO else ""
        blocks.append(f"<b>{mark}{tiers.title(code)}</b>\n{lines}")
    blocks.append(_fmt("TIERS_BALANCE", TIERS_BALANCE, coin=coin(), coins=coins))
    return "\n\n".join(blocks)


TIER_CARD = (
    "<b>{tier}</b> · {price} {coin}/день\n\n"
    "{perks}\n\n"
    "{coin} Баланс: <b>{coins}</b>\n"
    "Выбери, на сколько берёшь:"
)


def tier_card(code: str, coins: int) -> str:
    import tiers

    return _fmt(
        "TIER_CARD",
        TIER_CARD,
        tier=tiers.title(code),
        price=tiers.price_of(code, 1),
        coin=coin(),
        perks="\n".join(f"• {perk}" for perk in tiers.perks(code)),
        coins=coins,
    )


TIER_SWITCH = (
    "⚠️ Сейчас работает <b>{current}</b>, и до конца {left}.\n"
    "Другая подписка встанет на её место — оставшиеся дни сгорят."
)


def tier_switch(current: str, until: int) -> str:
    import tiers

    return _fmt(
        "TIER_SWITCH", TIER_SWITCH, current=tiers.title(current), left=days_left(until)
    )


TIER_BOUGHT = (
    "🟢 <b>{tier}</b> на {days} — списано {price} {coin}.\n"
    "Работает до <b>{until}</b>."
)


def tier_bought(code: str, days: int, price: int, until: int) -> str:
    import tiers

    return _fmt(
        "TIER_BOUGHT",
        TIER_BOUGHT,
        tier=tiers.title(code),
        days=day_word(days),
        price=price,
        coin=coin(),
        until=when(until),
    )


# --- paying for a tier ----------------------------------------------------

TIER_PAY = (
    "<b>{tier}</b> на {days}\n\n"
    "{coin} Монетками: <b>{price}</b> — разово, продлевать вручную.\n"
    "{recurring}"
)
TIER_PAY_RECURRING = (
    "🔁 С автопродлением: <b>{rubles} ₽</b> {every} через СБП — "
    "доступ не кончится сам, отключить можно в любой момент."
)
TIER_PAY_COINS_ONLY = "Оплата — монетками с баланса."


def tier_pay(code: str, days: int) -> str:
    import paritypay
    import tiers

    price = tiers.price_of(code, days)
    interval = paritypay.interval_of(days)
    tail = TIER_PAY_COINS_ONLY
    if paritypay.recurring_on() and interval:
        tail = _fmt(
            "TIER_PAY_RECURRING",
            TIER_PAY_RECURRING,
            rubles=settings.card_rubles(price),
            every=paritypay.INTERVAL_WORDS.get(interval, ""),
        )
    return _fmt(
        "TIER_PAY",
        TIER_PAY,
        tier=tiers.title(code),
        days=day_word(days),
        coin=coin(),
        price=price,
        recurring=tail,
    )


TIER_SUB_INVOICE = (
    "🧾 <b>Счёт на {amount} ₽</b>\n\n"
    "<b>{tier}</b>, списание {every}.\n"
    "Оплата через СБП. После первой оплаты доступ включится сам, "
    "дальше он будет продлеваться без твоего участия.\n\n"
    "Отключить можно в любой момент в «Подписке».\n"
    "Счёт действует {minutes} минут."
)


def tier_sub_invoice(code: str, amount: str, days: int) -> str:
    import paritypay
    import tiers
    from config import INVOICE_TTL

    return _fmt(
        "TIER_SUB_INVOICE",
        TIER_SUB_INVOICE,
        amount=amount,
        tier=tiers.title(code),
        every=paritypay.INTERVAL_WORDS.get(paritypay.interval_of(days), ""),
        minutes=INVOICE_TTL // 60,
    )


TIER_SUB_CHARGED = "🟢 <b>{tier}</b> оплачен: {amount} ₽.\nРаботает до <b>{until}</b>."
TIER_SUB_RENEWED = "🔁 <b>{tier}</b> продлён: списано {amount} ₽.\nДо <b>{until}</b>."


def tier_sub_charged(code: str, amount: str, until: int, first: bool) -> str:
    import tiers

    key = "TIER_SUB_CHARGED" if first else "TIER_SUB_RENEWED"
    return _fmt(
        key,
        TIER_SUB_CHARGED if first else TIER_SUB_RENEWED,
        tier=tiers.title(code),
        amount=amount,
        until=when(until),
    )


TIER_SUB_OVER = (
    "🔁 Автопродление отключено — новых списаний не будет. "
    "Уже оплаченный срок доработает до конца."
)
TIER_SUB_FAILED = (
    "🔁 Автопродление остановлено: списание не прошло. "
    "Оплаченный срок доработает, а продлить можно заново в «Подписке»."
)


def tier_sub_over(status: str) -> str:
    return TIER_SUB_FAILED if status == "failed" else TIER_SUB_OVER


TIER_SUB_ACTIVE = (
    "🔁 <b>Автопродление включено</b>\n\n"
    "{tier} · {amount} ₽ {every}\n"
    "Следующее списание: <b>{next}</b>"
)
TIER_SUB_WAITING = "🕒 Счёт выставлен, но ещё не оплачен."
TIER_SUB_NONE = "Автопродления нет."
TIER_SUB_DROPPED = "Автопродление отключено."
TIER_SUB_ALREADY = "У тебя уже есть автопродление — сначала отключи его."


def tier_sub_active(code: str, amount: str, days: int, next_at: str) -> str:
    import paritypay
    import tiers

    return _fmt(
        "TIER_SUB_ACTIVE",
        TIER_SUB_ACTIVE,
        tier=tiers.title(code),
        amount=amount,
        every=paritypay.INTERVAL_WORDS.get(paritypay.interval_of(days), ""),
        next=next_at or "—",
    )


TIER_POOR = "Не хватает монеток: нужно {price}, на балансе {coins}."


def tier_poor(price: int, coins: int) -> str:
    return _fmt("TIER_POOR", TIER_POOR, price=price, coins=coins)


TIER_LIMIT_HIT = (
    "Бесплатные {views} {circles} на сегодня кончились — дальше как обычно, "
    "{watch_cost} {coin} за просмотр. Лимит обнулится в полночь по Москве, "
    "а на A++ и Premium его нет вовсе."
)


def tier_limit_hit(views: int) -> str:
    return _fmt(
        "TIER_LIMIT_HIT",
        TIER_LIMIT_HIT,
        views=views,
        circles=circles_word(views),
        watch_cost=settings.get("watch_cost"),
        coin=coin(),
    )


TIER_VIEWS_LEFT = "🎁 По подписке. Бесплатных сегодня осталось: <b>{left}</b>."


def tier_views_left(left: int) -> str:
    return _fmt("TIER_VIEWS_LEFT", TIER_VIEWS_LEFT, left=left)


def day_word(days: int) -> str:
    tail = days % 100
    if 11 <= tail <= 14:
        return f"{days} дней"
    return f"{days} " + ("день" if tail % 10 == 1 else
                         "дня" if 2 <= tail % 10 <= 4 else "дней")


def days_left(until: int) -> str:
    left = max(0, until - int(time.time()))
    if left >= 86400:
        return f"осталось {day_word(left // 86400)}"
    if left >= 3600:
        return f"осталось {left // 3600} ч"
    return "меньше часа"


def when(stamp: int) -> str:
    """Moscow time, and said so — the server's own clock is nobody's business."""
    return time.strftime("%d.%m.%Y %H:%M", time.gmtime(stamp + MSK_OFFSET)) + " МСК"


# --- paid reach for a profile --------------------------------------------

BOOST_SCREEN = (
    "🚀 <b>Продвижение анкеты</b>\n\n"
    "Пока оплачено, твоя анкета идёт в начале выдачи — её увидит "
    "намного больше людей.\n\n"
    "{coin} Баланс: <b>{coins}</b>\n"
    "{state}\n\n"
    "Выбери срок:"
)
BOOST_RUNNING = "🟢 Идёт — до {until} ({left})."
BOOST_IDLE = "⚪ Сейчас анкета в общей очереди."


def boost_screen(coins: int, until: int) -> str:
    state = (
        _fmt("BOOST_RUNNING", BOOST_RUNNING, until=when(until), left=days_left(until))
        if until > time.time()
        else _fmt("BOOST_IDLE", BOOST_IDLE)
    )
    return _fmt("BOOST_SCREEN", BOOST_SCREEN, coin=coin(), coins=coins, state=state)


BOOST_BOUGHT = (
    "🟢 Продвижение на {days} — списано {price} {coin}.\n"
    "Работает до <b>{until}</b>, анкета уже идёт в начале выдачи.\n"
    "Когда закончится, пришлю, сколько людей её увидело."
)


def boost_bought(days: int, price: int, until: int) -> str:
    return _fmt(
        "BOOST_BOUGHT",
        BOOST_BOUGHT,
        days=day_word(days),
        price=price,
        coin=coin(),
        until=when(until),
    )


BOOST_POOR = "Не хватает монеток: нужно {price}, на балансе {coins}."


def boost_poor(price: int, coins: int) -> str:
    return _fmt("BOOST_POOR", BOOST_POOR, price=price, coins=coins)


BOOST_NEEDS_APPROVED = (
    "Продвигать пока нечего: анкета должна быть одобрена и видна в ленте. "
    "Как только её одобрят — возвращайся."
)

BOOST_REPORT = (
    "🚀 <b>Продвижение закончилось</b>\n\n"
    "Анкету показали <b>{shown}</b> {shown_word}, "
    "купили доступ <b>{sold}</b> {sold_word}.\n\n"
    "Сейчас она вернулась в общую очередь — продлить можно в «Моей анкете»."
)


def times_word(count: int) -> str:
    """1 раз, 2 раза, 5 раз."""
    tail = count % 100
    if 11 <= tail <= 14:
        return "раз"
    return "раза" if 2 <= tail % 10 <= 4 else "раз"


def boost_report(shown: int, sold: int) -> str:
    return _fmt(
        "BOOST_REPORT",
        BOOST_REPORT,
        shown=shown,
        shown_word=times_word(shown),
        sold=sold,
        sold_word=times_word(sold),
    )


# --- a link to one's own profile -----------------------------------------

PROFILE_LINK_INTRO = "🔗 <b>Ты пришёл по ссылке автора.</b>"

PROFILE_LINK_SCREEN = (
    "🔗 <b>Ссылка на твою анкету</b>\n\n"
    "<code>{link}</code>\n\n"
    "Ставь её в свой канал, в описание профиля, куда угодно. Кто перейдёт — "
    "сразу увидит твою анкету и сможет купить доступ к кружочкам.\n\n"
    "Переходов по ссылке: <b>{hits}</b>"
)


def profile_link_screen(link: str, hits: int) -> str:
    return _fmt("PROFILE_LINK_SCREEN", PROFILE_LINK_SCREEN, link=link, hits=hits)


PROFILE_LINK_NEEDS_APPROVED = (
    "Ссылку дам, когда анкету одобрят — сейчас показывать по ней нечего."
)
PROFILE_LINK_GONE = "Анкета, на которую вела ссылка, недоступна."
PROFILE_LINK_OWN = "Это ссылка на твою же анкету 🙂"


# --- auction --------------------------------------------------------------

AUCTION = (
    "🔨 <b>Аукцион: {prize}</b>\n\n"
    "Кто вложит больше всех монеток за {hours} — тот и забирает приз.\n"
    "Монетки списываются сразу. Проигравшим они вернутся все до одной, "
    "как только аукцион закончится.\n\n"
    "⏳ Осталось: <b>{left}</b>\n"
    "🏆 Лидер: <b>{top}</b> {coin}\n"
    "💰 Твоя ставка: <b>{mine}</b> {coin} · твой баланс: {coins}\n"
    "👥 Участников: {bidders}\n\n"
    "Ставка складывается: нажал ещё раз — прибавилось."
)


def auction(
    prize: str, hours: int, left: str, top: int, mine: int, coins: int, bidders: int
) -> str:
    return _fmt(
        "AUCTION",
        AUCTION,
        prize=html.escape(prize),
        hours=hours_word(hours),
        left=left,
        top=top,
        mine=mine,
        coins=coins,
        bidders=bidders,
        coin=coin(),
    )


def hours_word(count: int) -> str:
    """2 часа, 5 часов, 21 час."""
    tail = count % 100
    if 11 <= tail <= 14:
        return f"{count} часов"
    return f"{count} " + {1: "час", 2: "часа", 3: "часа", 4: "часа"}.get(
        tail % 10, "часов"
    )


def time_left(seconds: int) -> str:
    """«1 ч 07 мин», «12 мин», «меньше минуты» — as it counts down."""
    if seconds >= 3600:
        return f"{seconds // 3600} ч {seconds % 3600 // 60:02d} мин"
    if seconds >= 60:
        return f"{seconds // 60} мин"
    return "меньше минуты"


AUCTION_OFF = "Аукцион уже закончился. Загляни в следующий раз 🙂"
AUCTION_BID_SMALL = "Ставка должна быть больше нуля."

AUCTION_BID_OK = "🔨 Принято. Твоя ставка: {mine} монеток"


def auction_bid_ok(mine: int) -> str:
    return _fmt("AUCTION_BID_OK", AUCTION_BID_OK, mine=mine)


AUCTION_BID_ASK = (
    "🔨 Сколько монеток поставить?\n\n"
    "Пришли число. Оно прибавится к твоей ставке.\n"
    "Баланс: <b>{coins}</b> {coin}"
)


def auction_bid_ask(coins: int) -> str:
    return _fmt("AUCTION_BID_ASK", AUCTION_BID_ASK, coins=coins, coin=coin())


AUCTION_WON = (
    "🏆 <b>Ты выиграл аукцион!</b>\n\n"
    "Твоя ставка — <b>{coins}</b> {coin}, она и была самой большой.\n\n"
    "Напиши в поддержку{contact} за доступом — приз выдают там."
)


def auction_won(coins: int, contact: str) -> str:
    return _fmt(
        "AUCTION_WON",
        AUCTION_WON,
        coins=coins,
        coin=coin(),
        contact=f" {contact}" if contact else "",
    )


AUCTION_REFUND = (
    "🔨 Аукцион закончился, приз ушёл к другому.\n"
    "Твои <b>{coins}</b> {coin} вернулись на баланс — до одной монетки."
)
AUCTION_CANCELLED = (
    "🔨 Аукцион отменён. Твои <b>{coins}</b> {coin} вернулись на баланс."
)


def auction_refund(coins: int, cancelled: bool = False) -> str:
    key = "AUCTION_CANCELLED" if cancelled else "AUCTION_REFUND"
    return _fmt(key, AUCTION_CANCELLED if cancelled else AUCTION_REFUND, coins=coins)


AUCTION_POOR = "Не хватает монеток: нужно {amount}, на балансе {coins}."


def auction_poor(amount: int, coins: int) -> str:
    return _fmt("AUCTION_POOR", AUCTION_POOR, amount=amount, coins=coins)


AUCTION_ANNOUNCE = (
    "🔨 <b>АУКЦИОН: {prize}</b>\n\n"
    "У тебя {hours}, чтобы вложить больше всех монеток — приз заберёт один.\n"
    "Проигравшим монетки вернутся полностью.\n\n"
    "Красная кнопка «🔨 АУКЦИОН» — внизу, под клавиатурой."
)


def auction_announce(prize: str, hours: int) -> str:
    return _fmt(
        "AUCTION_ANNOUNCE",
        AUCTION_ANNOUNCE,
        prize=html.escape(prize),
        hours=hours_word(hours),
    )
