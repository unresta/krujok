"""Message texts.

Everything that shows an emoji is built at call time — placeholders are only
known after emoji.resolve() has run against Telegram.
"""

import emoji
import settings
from keyboards import PREF_TITLE


def coin() -> str:
    return emoji.text(emoji.COIN)


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
    floor = settings.get("min_duration_short")
    return (
        "ℹ️ <b>Правила сервиса</b>\n\n"
        "• Запрещены материалы: ЛГБТ, обнажённые видео пользователей до 18 лет, "
        "реклама, спам, оскорбления и незаконный контент\n"
        f"• Полная награда — за кружок от {full} секунд; "
        f"от {floor} до {full - 1} секунд принимаем за меньшую цену, "
        f"короче {floor} секунд — нет\n"
        "• Уважай других пользователей и не злоупотребляй жалобами\n\n"
        "За нарушение правил доступ к боту может быть ограничен без предупреждения."
    )


def faq() -> str:
    return (
        "❓ <b>FAQ</b>\n\n"
        f"<b>Откуда берутся монетки?</b>\n"
        f"Загрузи свой кружок (+{settings.reward('f')} за женский, "
        f"+{settings.reward('m')} за мужской после проверки), позови друга "
        f"(+{settings.get('ref_reward')}) или купи за ⭐ в «Магазине».\n\n"
        f"<b>Сколько стоит просмотр?</b>\n"
        f"{settings.get('watch_cost')} монетки за кружок. "
        "Один и тот же кружок дважды не попадётся, свои — не показываются.\n\n"
        "<b>Как заработать на своих кружочках?</b>\n"
        f"Каждый платный просмотр твоего кружка приносит "
        f"{settings.get('view_payout')} монетку, каждый лайк — "
        f"{settings.get('like_bonus')}. Смотри «Профиль».\n\n"
        "<b>Почему кружок не приняли?</b>\n"
        "Либо он короче минимума, либо такой уже есть в базе, либо модератор "
        "счёл его нарушающим правила.\n\n"
        "<b>Долго ли ждать проверки?</b>\n"
        "Обычно недолго. Пока кружок на проверке, можно загружать следующие — "
        f"до {settings.get('max_pending')} штук.\n\n"
        "<b>Можно ли скачать или переслать кружок?</b>\n"
        "Нет: кружочки уходят с защитой от пересылки и сохранения.\n\n"
        "<b>Кто увидит, что кружок мой?</b>\n"
        "Никто. Автор нигде не показывается, обмен анонимный.\n\n"
        "<b>Что делать с нарушением?</b>\n"
        "Кнопка «Пожаловаться» под кружком. Жалобы уходят модераторам."
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
    return (
        f"{coin()} Баланс: <b>{coins}</b> — "
        f'на просмотр нужно {settings.get("watch_cost")}.\n\n'
        f"Загрузи кружок (+{settings.reward('f')} за женский, "
        f"+{settings.reward('m')} за мужской) "
        "или купи монетки за ⭐."
    )


EMPTY = (
    "Свежих кружочков этого типа пока нет — ты посмотрел все.\n"
    "Загляни позже или смени тип."
)


UPLOAD_PICK_GENDER = "Какой кружок будешь загружать?"


def upload_ask(gender: str) -> str:
    kind = "женский" if gender == "f" else "мужской"
    full = settings.get("min_duration")
    floor = settings.get("min_duration_short")
    return (
        f"🎥 Пришли {kind} кружок одним сообщением.\n\n"
        f"• от {full} сек — <b>+{settings.reward(gender)}</b> {coin()}\n"
        f"• {floor}–{full - 1} сек — <b>+{settings.reward(gender, floor)}</b> {coin()}\n"
        f"• короче {floor} сек не принимаем\n\n"
        "Монетки придут после проверки модератором."
    )


NOT_A_CIRCLE = "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение."


def too_short(duration: int) -> str:
    return (
        f"Кружок {duration} сек — совсем коротко. "
        f'Принимаем от {settings.get("min_duration_short")} сек.'
    )


DUPLICATE = "Такой кружок уже есть в базе."
TOO_MANY_PENDING = "У тебя уже несколько кружков на проверке. Дождись решения."
UPLOAD_ASK_GENDER = "Какой это кружок?"


def upload_sent(circle_id: int, reward: int, short: bool) -> str:
    note = " как короткий" if short else ""
    return (
        f"✅ Кружок <b>#{circle_id}</b> отправлен на проверку{note}.\n"
        f"После одобрения: <b>+{reward}</b> {coin()}"
    )


def approved(reward: int, coins: int, short: bool) -> str:
    note = " (короткий, поэтому меньше)" if short else ""
    return (
        f"🟢 Твой кружок одобрен: <b>+{reward}</b> {coin()}{note}\n"
        f"Баланс: <b>{coins}</b>"
    )


REJECTED = "🔴 Кружок отклонён модератором."
REPORT_SENT = "Жалоба отправлена модераторам."
REPORT_DOUBLE = "Ты уже жаловался на этот кружок."
CIRCLE_REMOVED = "🔴 Твой кружок удалён по жалобам."


def earned_toast(amount: int) -> str:
    return f"Твой кружок посмотрели: +{amount}"


def buy(coins: int) -> str:
    return (
        f"{coin()} Баланс: <b>{coins}</b>\n\n"
        f'1 ⭐ = <b>{settings.get("stars_rate")}</b> {coin()}, '
        f'минимум {settings.get("min_stars")} ⭐.'
    )


def buy_custom() -> str:
    return f'Сколько ⭐ спишем? Пришли число (от {settings.get("min_stars")}).'


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
) -> str:
    return (
        "👤 <b>Профиль</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"{coin()} Баланс: <b>{coins}</b>\n\n"
        f"📤 Мои кружочки: {s['approved']} в базе · {s['pending']} на проверке · "
        f"{s['rejected']} отклонено\n"
        f"👀 Их посмотрели: {views}\n"
        f"👍 Лайков: {likes}\n"
        f"{coin()} Заработано на кружочках: <b>{earned}</b>\n\n"
        f"👀 Сам посмотрел: {s['watched']}\n"
        f"👥 Приглашено: {ref_done}"
    )


BANNED = "Доступ закрыт."
MAINTENANCE = "🔧 Бот на техработах. Загляни чуть позже."
SUBSCRIBE = (
    "📢 Бот работает только для подписчиков канала.\n\n"
    "Подпишись и нажми «Я подписался»."
)
SUBSCRIBE_MISSING = "Подписки не вижу. Подпишись на канал и нажми ещё раз."
