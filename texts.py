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
        f"{emoji.text(emoji.FILM)} Показываю: <b>{PREF_TITLE(pref)}</b>"
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


def profile(coins: int, s: dict, ref_done: int, ref_wait: int, link: str) -> str:
    reward = settings.get("ref_reward")
    waiting = f" · ждут подписки: {ref_wait}" if ref_wait else ""
    return (
        "<b>Профиль</b>\n\n"
        f"{coin()} Баланс: <b>{coins}</b>\n"
        f"👀 Просмотрено: {s['watched']}\n"
        f"📤 Загружено: {s['approved']} одобрено · "
        f"{s['pending']} на проверке · {s['rejected']} отклонено\n\n"
        f"👥 Приглашено: <b>{ref_done}</b>{waiting}\n"
        f"За друга, который подпишется на канал, — <b>+{reward}</b> {coin()}\n"
        f"<code>{link}</code>"
    )


BANNED = "Доступ закрыт."
MAINTENANCE = "🔧 Бот на техработах. Загляни чуть позже."
SUBSCRIBE = (
    "📢 Бот работает только для подписчиков канала.\n\n"
    "Подпишись и нажми «Я подписался»."
)
SUBSCRIBE_MISSING = "Подписки не вижу. Подпишись на канал и нажми ещё раз."
