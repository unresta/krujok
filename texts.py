"""Message texts.

Everything that shows an emoji is built at call time — placeholders are only
known after emoji.resolve() has run against Telegram.
"""

import emoji
import settings
from config import ABOUT_MAX
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
        f"<b>Откуда берутся монетки?</b>\n"
        f"Загрузи свой кружок (+{settings.reward('f')} за женский, "
        f"+{settings.reward('m')} за мужской после проверки), позови друга "
        f"(+{settings.get('ref_reward')}) или купи за ⭐ в «Магазине».\n\n"
        f"<b>Сколько стоит просмотр?</b>\n"
        f"{settings.get('watch_cost')} монетки за кружок. "
        "Один и тот же кружок дважды не попадётся, свои — не показываются.\n\n"
        "<b>Как заработать?</b>\n"
        f"Платный просмотр твоего кружка приносит {settings.get('view_payout')} "
        f"монетку, лайк — {settings.get('like_bonus')}. А главное — анкета: "
        f"другие покупают доступ ко всем твоим кружочкам или твою личку, и тебе "
        f"достаётся {settings.get('author_share')}% от цены.\n\n"
        "<b>Что такое анкета?</b>\n"
        "Витрина: фото, описание и твои цены. Заполняется в «Моя анкета», "
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
        "«Анкета автора», через неё зритель покупает доступ ко всем твоим "
        "кружочкам. Без анкеты этот путь обрывается.\n\n"
        "<b>Кто увидит, кто я?</b>\n"
        "В анкете — только фото и описание, которые ты сам выбрал. Имя и "
        "@username не показываются никогда; @username уходит покупателю только "
        "если ты сам включил продажу лички и он за неё заплатил.\n\n"
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

UPLOAD_NEEDS_PROFILE = (
    "🎬 Сначала анкета.\n\n"
    "Кружочки показываются вместе с анкетой автора: зритель может её открыть и "
    "купить доступ ко всем твоим кружочкам. Без анкеты продавать нечего."
)


def upload_profile_pending(status: str) -> str:
    if status == "pending":
        return "🕒 Анкета на проверке. Как одобрят — можно будет загружать кружочки."
    return "🔴 Анкета отклонена. Заполни её заново в «Моя анкета», потом загружай."


def upload_ask(gender: str) -> str:
    kind = "женский" if gender == "f" else "мужской"
    return (
        f"🎥 Пришли {kind} кружок одним сообщением.\n\n"
        f'• минимум {settings.get("min_duration")} секунд\n'
        f"• <b>+{settings.reward(gender)}</b> {coin()} после проверки модератором"
    )


NOT_A_CIRCLE = "Это не кружок. Зажми 🎥 в поле ввода и запиши видеосообщение."


def too_short(duration: int) -> str:
    return (
        f"Кружок {duration} сек — коротко. "
        f'Минимальная длина: {settings.get("min_duration")} секунд.'
    )


DUPLICATE = "Такой кружок уже есть в базе."
TOO_MANY_PENDING = "У тебя уже несколько кружков на проверке. Дождись решения."
UPLOAD_ASK_GENDER = "Какой это кружок?"


def upload_sent(circle_id: int, reward: int) -> str:
    return (
        f"✅ Кружок <b>#{circle_id}</b> отправлен на проверку.\n"
        f"После одобрения: <b>+{reward}</b> {coin()}"
    )


def approved(reward: int, coins: int) -> str:
    return (
        f"🟢 Твой кружок одобрен: <b>+{reward}</b> {coin()}\n"
        f"Баланс: <b>{coins}</b>"
    )


REJECTED = "🔴 Кружок отклонён модератором."
REPORT_SENT = "Жалоба отправлена модераторам."
REPORT_DOUBLE = "Ты уже жаловался на этот кружок."
REPORT_DOUBLE_PROFILE = "Ты уже жаловался на эту анкету."


def circles_word(count: int) -> str:
    """1 кружок, 2 кружка, 5 кружков."""
    tail = count % 100
    if 11 <= tail <= 14:
        return "кружочков"
    return {1: "кружочек", 2: "кружочка", 3: "кружочка", 4: "кружочка"}.get(
        tail % 10, "кружочков"
    )
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
    sales: dict | None = None,
    withdrawable: int = 0,
) -> str:
    sales = sales or {"content": 0, "contact": 0, "income": 0}
    return (
        "👤 <b>Профиль</b>\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"{coin()} Баланс: <b>{coins}</b>\n\n"
        f"📤 Мои кружочки: {s['approved']} в базе · {s['pending']} на проверке · "
        f"{s['rejected']} отклонено\n"
        f"👀 Их посмотрели: {views}\n"
        f"👍 Лайков: {likes}\n"
        f"{coin()} Заработано на кружочках: <b>{earned}</b>\n"
        f"🛒 Продано: {sales['content']} доступов · {sales['contact']} контактов "
        f"(+{sales['income']} {coin()})\n"
        f"💸 К выводу: <b>{withdrawable}</b> {coin()} "
        f"(~{settings.stars_for(withdrawable)} ⭐)\n\n"
        f"👀 Сам посмотрел: {s['watched']}\n"
        f"👥 Приглашено: {ref_done}"
    )


# --- author profiles -----------------------------------------------------

PROFILE_PHOTO = (
    "🖼 <b>Анкета автора</b>\n\n"
    "Пришли фото для анкеты — его увидят все, кто листает анкеты.\n"
    "Лицо показывать необязательно."
)


def profile_about() -> str:
    return (
        "✍️ Теперь описание — пара строк о себе.\n"
        f"До {ABOUT_MAX} символов. «-» — оставить пустым."
    )


PROFILE_GENDER = "Чьи кружочки ты выкладываешь?"


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


PROFILE_SENT = (
    "✅ Анкета отправлена на проверку. Как только модератор её одобрит, "
    "её начнут показывать другим."
)
PROFILE_NOT_PHOTO = "Нужно именно фото."
PROFILE_APPROVED = "🟢 Твоя анкета одобрена — её уже показывают."
PROFILE_REJECTED = "🔴 Анкета отклонена модератором. Можно переделать и отправить снова."
PROFILE_EMPTY = "Анкет пока нет. Загляни позже."
PROFILE_NONE_YET = "У тебя ещё нет анкеты."


def profile_status(profile) -> str:
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
        f"<b>Моя анкета</b> · {label}\n\n"
        f"{profile['about'] or 'Без описания'}\n\n"
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
        f"<b>{PREF_TITLE(profile['gender'])}</b>\n\n"
        f"{emoji.text(emoji.ABOUT)} {profile['about'] or 'Без описания'}\n\n"
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


BANNED = "Доступ закрыт."
MAINTENANCE = "🔧 Бот на техработах. Загляни чуть позже."
SUBSCRIBE = (
    "📢 Бот работает только для подписчиков канала.\n\n"
    "Подпишись и нажми «Я подписался»."
)
SUBSCRIBE_MISSING = "Подписки не вижу. Подпишись на канал и нажми ещё раз."
