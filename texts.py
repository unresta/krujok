"""Message texts.

Everything that shows an emoji is built at call time — placeholders are only
known after emoji.resolve() has run against Telegram.
"""

import emoji
from config import MIN_DURATION, MIN_STARS, REWARD, STARS_RATE, WATCH_COST
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
        f"{coin()} Баланс: <b>{coins}</b> — на просмотр нужно {WATCH_COST}.\n\n"
        f"Загрузи кружок (+{REWARD['f']} за женский, +{REWARD['m']} за мужской) "
        "или купи монетки за ⭐."
    )


EMPTY = (
    "Свежих кружочков этого типа пока нет — ты посмотрел все.\n"
    "Загляни позже или смени тип."
)


def upload_ask() -> str:
    return (
        "🎥 Пришли кружок одним сообщением.\n\n"
        f"• минимум {MIN_DURATION} сек\n"
        f"• +{REWARD['f']} {coin()} за женский, +{REWARD['m']} {coin()} за мужской\n"
        "• монетки придут после проверки модератором"
    )


NOT_A_CIRCLE = "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение."


def too_short(duration: int) -> str:
    return f"Кружок {duration} сек — коротко. Нужно от {MIN_DURATION} сек."


DUPLICATE = "Такой кружок уже есть в базе."
TOO_MANY_PENDING = "У тебя уже несколько кружков на проверке. Дождись решения."
UPLOAD_ASK_GENDER = "Какой это кружок?"
UPLOAD_SENT = "✅ Отправлено на проверку. Монетки придут после одобрения."


def approved(reward: int, coins: int) -> str:
    return (
        f"🟢 Твой кружок одобрен: <b>+{reward}</b> {coin()}\n"
        f"Баланс: <b>{coins}</b>"
    )


REJECTED = "🔴 Кружок отклонён модератором."


def buy(coins: int) -> str:
    return (
        f"{coin()} Баланс: <b>{coins}</b>\n\n"
        f"1 ⭐ = <b>{STARS_RATE}</b> {coin()}, минимум {MIN_STARS} ⭐."
    )


BUY_CUSTOM = f"Сколько ⭐ спишем? Пришли число (от {MIN_STARS})."
BUY_BAD_INPUT = f"Нужно целое число от {MIN_STARS}."


def paid(stars: int, coins_added: int, coins: int) -> str:
    return (
        f"🟢 Оплачено {stars} ⭐ → <b>+{coins_added}</b> {coin()}\n"
        f"Баланс: <b>{coins}</b>"
    )


def profile(coins: int, s: dict) -> str:
    return (
        "<b>Профиль</b>\n\n"
        f"{coin()} Баланс: <b>{coins}</b>\n"
        f"👀 Просмотрено: {s['watched']}\n"
        f"📤 Загружено: {s['approved']} одобрено · "
        f"{s['pending']} на проверке · {s['rejected']} отклонено"
    )


BANNED = "Доступ закрыт."
