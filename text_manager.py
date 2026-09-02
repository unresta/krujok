"""Texts an admin can rewrite from the panel.

The defaults live in texts.py and nowhere else — this module only knows which
of them may be edited, and swaps an override straight into that module. That is
what makes a change show up in the next message instead of after a restart, and
what keeps the panel from drifting apart from the code.

A text shown in a toast or an alert is stored as plain text: Telegram renders no
HTML there, so bold and premium emoji would arrive as visible tags.
"""

import logging
import re
from typing import NamedTuple

import db
import texts

logger = logging.getLogger(__name__)


class Item(NamedTuple):
    description: str
    category: str
    plain: bool = False  # lives in a toast/alert, where formatting is not shown
    # {vstavka} -> what the bot puts there. An edit may move them around or drop
    # them, but may not invent new ones — save() checks that.
    vars: dict[str, str] = {}


CATEGORY_ICON = {
    "Меню и лента": "🏠",
    "Правила и FAQ": "ℹ️",
    "Система": "⚙️",
    "Профиль": "🧾",
    "Анкета автора": "👤",
    "Загрузка": "🎥",
    "Просмотр": "👀",
    "Жалобы": "⚠️",
    "Покупки": "💰",
    "Выплаты": "💸",
    "Рефералы": "👥",
    "Подписка": "📢",  # обязательная подписка на канал, не платная
    "Платные подписки": "💎",
    "Короткие ответы": "💬",
}

# Values that show up again and again, described once.
_COIN = {"coin": "значок монетки"}
_PRICE_RANGE = {"price_min": "мин. цена", "price_max": "макс. цена"}

EDITABLE: dict[str, Item] = {
    # --- Меню и лента ---
    "MENU": Item(
        "Главное меню",
        "Меню и лента",
        vars={
            "coin": "значок монетки",
            "coins": "баланс",
            "film": "значок ленты",
            "pref": "какие кружки показываем",
        },
    ),
    "FEED": Item("Экран «Лента»", "Меню и лента", vars={"pref": "выбранный тип"}),
    "EMPTY": Item("Кружочки этого типа кончились", "Меню и лента"),
    "ARCHIVE_NOTE": Item("Кружок из архива бота", "Меню и лента", plain=True),
    "NOT_ENOUGH": Item(
        "Не хватает монеток на просмотр",
        "Меню и лента",
        vars={
            "coin": "значок монетки",
            "coins": "баланс",
            "watch_cost": "цена просмотра",
            "earn": "подсказка, как заработать (ниже)",
        },
    ),
    "NOT_ENOUGH_UPLOAD": Item(
        "…подсказка, когда за загрузку платят",
        "Меню и лента",
        vars={"reward": "размер награды"},
    ),
    "NOT_ENOUGH_SELL": Item(
        "…подсказка, когда зарабатывают продажей",
        "Меню и лента",
        vars={"author_share": "доля автора, %"},
    ),
    "FREE_VIEW_LEFT": Item(
        "Просмотр в подарок", "Меню и лента", vars={"left": "сколько осталось"}
    ),
    "FREE_VIEW_LAST": Item(
        "Последний подарочный просмотр",
        "Меню и лента",
        vars={"watch_cost": "цена просмотра", "coin": "значок монетки"},
    ),
    "PUSH_NEW": Item(
        "Напоминание: появились новые",
        "Меню и лента",
        vars={"free": "сколько бесплатных", "circles": "«кружочка/кружочков»"},
    ),
    "PUSH_MISSED": Item(
        "Напоминание: давно не заходил",
        "Меню и лента",
        vars={"free": "сколько бесплатных", "circles": "«кружочка/кружочков»"},
    ),
    "PUSH_UNACCEPTED": Item(
        "Напоминание: так и не начал",
        "Меню и лента",
        vars={"free": "сколько бесплатных", "circles": "«кружочка/кружочков»"},
    ),
    "TRIAL_PUSH": Item(
        "Напоминание новичку про бесплатные",
        "Меню и лента",
        vars={"left": "сколько осталось", "circles": "«кружочка/кружочков»"},
    ),
    "AUCTION_RULE_BACK": Item(
        "…правило: проигравшим вернём", "Меню и лента"
    ),
    "AUCTION_RULE_KEEP": Item(
        "…правило: монетки не возвращаются", "Меню и лента"
    ),
    "AUCTION_LOST": Item(
        "Проигравшему: монетки остались в банке",
        "Меню и лента",
        vars={"coins": "сколько"},
    ),
    "AUCTION": Item(
        "Экран аукциона",
        "Меню и лента",
        vars={
            "prize": "что разыгрываем",
            "rule": "строка про возврат монеток (ниже)",
            "hours": "сколько идёт",
            "left": "сколько осталось",
            "top": "ставка лидера",
            "mine": "своя ставка",
            "coins": "баланс",
            "bidders": "участников",
        },
    ),
    "AUCTION_ANNOUNCE": Item(
        "Объявление аукциона всем",
        "Меню и лента",
        vars={
            "prize": "что разыгрываем",
            "hours": "сколько идёт",
            "rule": "строка про возврат монеток (ниже)",
        },
    ),
    "AUCTION_OUTBID": Item(
        "Ставку перебили",
        "Меню и лента",
        vars={
            "top": "ставка лидера",
            "mine": "своя ставка",
            "left": "сколько осталось",
        },
    ),
    "AUCTION_OFF": Item("Аукцион закончился", "Меню и лента", plain=True),
    "AUCTION_BID_SMALL": Item("Ставка меньше монетки", "Меню и лента", plain=True),
    "AUCTION_BID_OK": Item(
        "Ставка принята", "Меню и лента", plain=True, vars={"mine": "своя ставка"}
    ),
    "AUCTION_POOR": Item(
        "На ставку не хватает",
        "Меню и лента",
        plain=True,
        vars={"amount": "сколько нужно", "coins": "баланс"},
    ),
    "AUCTION_BID_ASK": Item(
        "Спрашиваем свою ставку", "Меню и лента", vars={"coins": "баланс"}
    ),
    "AUCTION_WON": Item(
        "Победителю аукциона",
        "Меню и лента",
        vars={"coins": "его ставка", "contact": "куда идти за призом"},
    ),
    "AUCTION_REFUND": Item(
        "Проигравшему: монетки вернулись", "Меню и лента", vars={"coins": "сколько"}
    ),
    "AUCTION_CANCELLED": Item(
        "Аукцион отменён, монетки вернулись", "Меню и лента", vars={"coins": "сколько"}
    ),
    "PUSH_WAITING": Item(
        "Напоминание: записали новый кружок",
        "Меню и лента",
        vars={"free": "сколько бесплатных", "circles": "«кружочка/кружочков»"},
    ),
    # --- Правила и FAQ ---
    "RULES": Item(
        "Правила сервиса", "Правила и FAQ", vars={"min_duration": "минимум секунд"}
    ),
    "FAQ": Item(
        "FAQ",
        "Правила и FAQ",
        vars={
            "author_share": "доля автора, %",
            "ref_reward": "награда за реферала",
            "watch_cost": "цена просмотра",
            "payout_min": "минимум вывода",
            "payout_rate": "монеток за 1 ⭐",
            "max_pending": "кружков на проверке",
        },
    ),
    "ACCEPTED": Item("Согласие принято", "Правила и FAQ", plain=True),
    # --- Система ---
    "BANNED": Item("Сообщение забаненному", "Система", plain=True),
    "MAINTENANCE": Item("Режим техработ", "Система", plain=True),
    "STALE_BUTTON": Item("Кнопка устарела", "Система", plain=True),
    "NOT_SO_FAST": Item("Слишком частые нажатия", "Система", plain=True),
    "SEND_FAILED": Item("Кружок не отправился", "Система"),
    # --- Профиль пользователя ---
    "PROFILE": Item(
        "Экран «Профиль»",
        "Профиль",
        vars={
            "icon_profile": "значок профиля",
            "icon_uploaded": "значок загрузок",
            "icon_ratings": "значок оценок",
            "icon_like": "значок лайка",
            "icon_dislike": "значок дизлайка",
            "icon_views": "значок просмотров",
            "icon_balance": "значок баланса",
            "icon_coin": "значок монеты",
            "icon_earnings": "значок заработка",
            "coin": "значок монетки",
            "approved": "одобрено кружков",
            "watched": "просмотрено кружков",
            "likes": "лайков",
            "dislikes": "дизлайков",
            "coins": "баланс",
            "earned": "заработано всего",
            "ref_done": "приглашено друзей",
            "withdraw": "строка «из них можно вывести»",
            "withdrawable": "доступно к выводу",
            "stars": "это же в ⭐",
            "sold_content": "продано доступов",
            "sold_contact": "продано контактов",
            "views": "просмотров его кружков",
            "user_id": "id пользователя",
        },
    ),
    "PROFILE_WITHDRAW": Item(
        "…строка «из них можно вывести»",
        "Профиль",
        vars={
            "withdrawable": "доступно к выводу",
            "stars": "это же в ⭐",
            "coin": "значок монетки",
        },
    ),
    "MY_CIRCLES": Item(
        "Мои загруженные кружки",
        "Профиль",
        vars={
            "approved": "одобрено",
            "pending": "на проверке",
            "rejected": "отклонено",
            "total": "всего",
        },
    ),
    "MY_CIRCLES_EMPTY": Item("Мои кружки: пусто", "Профиль"),
    "MY_CIRCLES_STATUS_EMPTY": Item(
        "Мои кружки: в этом списке пусто", "Профиль", plain=True
    ),
    "MY_CIRCLES_DONE": Item("Мои кружки: список кончился", "Профиль"),
    "MY_CIRCLES_MORE": Item(
        "Мои кружки: осталось ещё",
        "Профиль",
        vars={"left": "сколько осталось", "circles": "«кружочка/кружочков»"},
    ),
    "MY_CIRCLE_INFO": Item(
        "Мои кружки: карточка кружка",
        "Профиль",
        plain=True,
        vars={
            "circle_id": "номер кружка",
            "date": "когда загружен",
            "duration": "длина, сек",
            "views": "просмотров",
            "likes": "лайков",
            "dislikes": "дизлайков",
            "earned": "заработано на нём",
        },
    ),
    "MY_CIRCLE_INFO_REASON": Item(
        "…строка с причиной отказа",
        "Профиль",
        plain=True,
        vars={"reason": "текст причины"},
    ),
    "MY_CIRCLE_GONE": Item("Мои кружки: кружка больше нет", "Профиль", plain=True),
    "MY_CIRCLE_ASK": Item("Мои кружки: подтверждение удаления", "Профиль", plain=True),
    "MY_CIRCLE_DELETED": Item("Мои кружки: кружок удалён", "Профиль", plain=True),
    "BOUGHT_HEADER": Item("Купленные кружочки: заголовок", "Профиль"),
    # No {author_id} on purpose: an id identifies a person, and the buyer paid
    # for circles. Leaving it out of the registry keeps it out of an edit too.
    "BOUGHT_ROW": Item(
        "Купленные кружочки: строка автора",
        "Профиль",
        vars={
            "index": "номер по списку",
            "who": "«Девушка»/«Парень»",
            "count": "сколько кружков",
            "circles": "«кружочка/кружочков»",
        },
    ),
    "AUTHOR_NO_PROFILE": Item("Автор без анкеты", "Профиль"),
    "BOUGHT_EMPTY": Item("Купленные кружочки: пусто", "Профиль"),
    # --- Анкета автора ---
    "PROFILE_INTRO": Item("Приглашение завести анкету", "Анкета автора"),
    "PROFILE_PHOTO": Item("Просьба прислать фото", "Анкета автора"),
    "PROFILE_ABOUT": Item(
        "Просьба написать описание", "Анкета автора", vars={"limit": "лимит символов"}
    ),
    "PROFILE_ABOUT_TEXT_ONLY": Item("Описание — только текстом", "Анкета автора"),
    "PROFILE_GENDER": Item("Вопрос о поле", "Анкета автора"),
    "PROFILE_PRICE_CONTENT": Item(
        "Вопрос о цене кружочков",
        "Анкета автора",
        vars={**_PRICE_RANGE, "author_share": "доля автора, %"},
    ),
    "PROFILE_CONTACT_ASK": Item("Продавать ли личку", "Анкета автора"),
    "PROFILE_PRICE_CONTACT": Item(
        "Вопрос о цене лички", "Анкета автора", vars=_PRICE_RANGE
    ),
    "PROFILE_BAD_PRICE": Item("Цена не подходит", "Анкета автора", vars=_PRICE_RANGE),
    "PROFILE_NO_USERNAME": Item("Нужен @username", "Анкета автора", plain=True),
    "PROFILE_STILL_NO_USERNAME": Item(
        "@username так и нет", "Анкета автора", plain=True
    ),
    "PROFILE_SENT": Item("Анкета ушла на проверку", "Анкета автора"),
    "PROFILE_NOT_PHOTO": Item("Прислали не фото", "Анкета автора"),
    "PROFILE_APPROVED": Item("Анкета одобрена", "Анкета автора"),
    "PROFILE_FIELD_SAVED": Item(
        "Поле анкеты обновлено",
        "Анкета автора",
        vars={"field": "что поменяли"},
    ),
    "PROFILE_LINK_INTRO": Item("Пришли по ссылке автора", "Анкета автора"),
    "PROFILE_LINK_SCREEN": Item(
        "Ссылка на свою анкету",
        "Анкета автора",
        vars={"link": "сама ссылка", "hits": "сколько переходов"},
    ),
    "PROFILE_LINK_NEEDS_APPROVED": Item(
        "Ссылку рано: анкета не одобрена", "Анкета автора", plain=True
    ),
    "PROFILE_LINK_GONE": Item("Анкета по ссылке недоступна", "Анкета автора"),
    "PROFILE_LINK_OWN": Item("Это твоя же ссылка", "Анкета автора"),
    "PROFILE_STATUS_BOOST": Item(
        "Своя анкета: идёт продвижение",
        "Анкета автора",
        vars={"left": "до какого числа"},
    ),
    "BOOST_SCREEN": Item(
        "Продвижение: экран покупки",
        "Анкета автора",
        vars=_COIN | {"coins": "баланс", "state": "идёт или нет"},
    ),
    "BOOST_RUNNING": Item(
        "Продвижение: идёт",
        "Анкета автора",
        vars={"until": "до какого числа", "left": "сколько осталось"},
    ),
    "BOOST_IDLE": Item("Продвижение: не идёт", "Анкета автора", vars=_COIN),
    "BOOST_BOUGHT": Item(
        "Продвижение куплено",
        "Анкета автора",
        vars=_COIN | {"days": "на сколько дней", "price": "сколько списано",
                      "until": "до какого числа"},
    ),
    "BOOST_REPORT": Item(
        "Продвижение кончилось: отчёт",
        "Анкета автора",
        vars={"shown": "сколько раз показали", "shown_word": "«раз/раза»",
              "sold": "сколько раз купили", "sold_word": "«раз/раза»"},
    ),
    "BOOST_POOR": Item(
        "Не хватает на продвижение",
        "Анкета автора",
        plain=True,
        vars={"price": "сколько нужно", "coins": "баланс"},
    ),
    "BOOST_NEEDS_APPROVED": Item(
        "Продвигать нечего: анкета не одобрена", "Анкета автора", plain=True
    ),
    "PROFILE_PRICE_SAVED": Item(
        "Цена обновлена, без проверки",
        "Анкета автора",
        vars=_COIN | {"field": "какая цена", "price": "новая цена"},
    ),
    "PROFILE_CONTACT_OFF": Item("Личка снята с продажи", "Анкета автора"),
    "PROFILE_REVERTED": Item(
        "Правки отклонены, вернули прошлую",
        "Анкета автора",
        vars={"reason": "причина, если её указали"},
    ),
    "PROFILE_REJECTED": Item(
        "Анкета отклонена",
        "Анкета автора",
        vars={"reason": "причина, если её указали"},
    ),
    "PROFILE_REASON_TAIL": Item(
        "…строка с причиной отказа",
        "Анкета автора",
        vars={"reason": "текст причины"},
    ),
    "PROFILE_FROZEN": Item(
        "Анкета снята с показа по жалобам",
        "Анкета автора",
        vars={"reason": "список жалоб, если они есть"},
    ),
    "PROFILE_FROZEN_REASONS": Item(
        "…список, на что жаловались",
        "Анкета автора",
        vars={"list": "перечень причин"},
    ),
    "PROFILE_STATUS": Item(
        "Своя анкета: карточка",
        "Анкета автора",
        vars={
            "status": "статус словами",
            "about": "описание",
            "price_content": "цена кружочков",
            "coin": "значок монетки",
            "contact": "цена лички или «не продаётся»",
            "views": "показов",
            "sold": "покупок",
            "boost": "строка про продвижение (ниже)",
        },
    ),
    "STATUS_PENDING": Item("Статус: на проверке", "Анкета автора", plain=True),
    "STATUS_APPROVED": Item("Статус: показывается", "Анкета автора", plain=True),
    "STATUS_REJECTED": Item("Статус: отклонена", "Анкета автора", plain=True),
    "CONTACT_NOT_SOLD": Item("Личка не продаётся (в карточке)", "Анкета автора"),
    "PROFILE_EMPTY_WAIT": Item("Анкеты кончились", "Анкета автора"),
    "PROFILE_EMPTY_PITCH": Item(
        "Анкет нет — стань первым",
        "Анкета автора",
        vars={"author_share": "доля автора, %", "payout_min": "минимум вывода"},
    ),
    "PROFILE_CARD": Item(
        "Чужая анкета: карточка",
        "Анкета автора",
        vars={
            "who": "«Девушка»/«Парень»",
            "icon_about": "значок описания",
            "about": "описание",
            "icon_count": "значок количества",
            "circles": "сколько кружочков",
            "icon_price": "значок цены",
            "price_content": "цена доступа",
            "coin": "значок монетки",
            "contact": "цена лички или «не продаётся»",
            "icon_sold": "значок покупок",
            "sold": "сколько раз купили",
            "icon_info": "значок сноски",
        },
    ),
    # --- Загрузка ---
    "UPLOAD_NEEDS_PROFILE": Item("Сначала анкета", "Загрузка"),
    "UPLOAD_WAIT_REVIEW": Item("Анкета ещё на проверке", "Загрузка"),
    "UPLOAD_PROFILE_REJECTED": Item("Анкета отклонена — загрузка закрыта", "Загрузка"),
    "UPLOAD_ASK": Item(
        "Просьба прислать кружок",
        "Загрузка",
        vars={
            "kind": "женский/мужской",
            "min_duration": "минимум секунд",
            "payoff": "что за это будет (ниже)",
        },
    ),
    "UPLOAD_ASK_PAID": Item(
        "…когда за кружок платят",
        "Загрузка",
        vars={"reward": "награда", "coin": "значок монетки"},
    ),
    "UPLOAD_ASK_FREE": Item("…когда не платят", "Загрузка"),
    "NOT_A_CIRCLE": Item("Прислали не кружок", "Загрузка"),
    "TOO_SHORT": Item(
        "Кружок слишком короткий",
        "Загрузка",
        vars={"duration": "его длина", "min_duration": "минимум"},
    ),
    "DUPLICATE": Item("Кружок уже есть в базе", "Загрузка"),
    "TOO_MANY_PENDING": Item("Слишком много на проверке", "Загрузка"),
    "UPLOAD_SENT": Item(
        "Кружок ушёл на проверку",
        "Загрузка",
        vars={"circle_id": "номер кружка", "tail": "что будет после одобрения"},
    ),
    "UPLOAD_SENT_PAID": Item(
        "…с наградой", "Загрузка", vars={"reward": "награда", "coin": "значок монетки"}
    ),
    "UPLOAD_SENT_FREE": Item("…без награды", "Загрузка"),
    "APPROVED_PAID": Item(
        "Кружок одобрен, с наградой",
        "Загрузка",
        vars={"reward": "награда", "coin": "значок монетки", "coins": "баланс"},
    ),
    "APPROVED_FREE": Item("Кружок одобрен, без награды", "Загрузка"),
    "REJECTED": Item(
        "Кружок отклонён", "Загрузка", vars={"reason": "причина, если её указали"}
    ),
    "CIRCLE_REASON_TAIL": Item(
        "…строка с причиной отказа", "Загрузка", vars={"reason": "текст причины"}
    ),
    "CIRCLE_DELETED": Item(
        "Кружок удалён при проверке",
        "Загрузка",
        vars={"reason": "причина, если её указали"},
    ),
    "EARNED_TOAST": Item(
        "Кружок посмотрели", "Просмотр", vars={"amount": "сколько начислили"}
    ),
    "LIKE_BONUS_NOTE": Item(
        "Кружок лайкнули", "Просмотр", vars={"amount": "сколько начислили"}
    ),
    # --- Жалобы ---
    "REPORT_ASK": Item("Вопрос «за что жалуешься»", "Жалобы", plain=True),
    "REPORT_SENT": Item("Жалоба отправлена", "Жалобы", plain=True),
    "REPORT_DOUBLE": Item("Повторная жалоба на кружок", "Жалобы", plain=True),
    "REPORT_DOUBLE_PROFILE": Item("Повторная жалоба на анкету", "Жалобы", plain=True),
    "CIRCLE_HIDDEN": Item("Кружок сняли с показа", "Жалобы"),
    "CIRCLE_RESTORED": Item("Кружок вернули в показ", "Жалобы"),
    "CIRCLE_REMOVED": Item("Кружок удалён по жалобам", "Жалобы"),
    # --- Покупки ---
    "BUY": Item(
        "Магазин монеток",
        "Покупки",
        vars={
            "coin": "значок монетки",
            "coins": "баланс",
            "star_cost": "⭐ за 1 монетку",
            "min_stars": "минимум ⭐",
        },
    ),
    "BUY_CUSTOM": Item("Своя сумма: вопрос", "Покупки", vars={"min_stars": "минимум ⭐"}),
    "BUY_BAD_INPUT": Item(
        "Своя сумма: не то число", "Покупки", vars={"min_stars": "минимум ⭐"}
    ),
    "BUY_CHOOSE_METHOD": Item(
        "Выбор способа оплаты",
        "Покупки",
        vars={
            "stars": "сколько ⭐",
            "coins": "сколько монеток",
            "coin": "значок монетки",
            "bonus": "строка про бонус за оплату картой (пусто, если выключен)",
        },
    ),
    "BUY_PICK_METHOD": Item("Подсказка: жми кнопку оплаты", "Покупки"),
    "CRYPTO_INVOICE": Item(
        "Счёт на оплату криптой",
        "Покупки",
        vars={
            "amount": "сумма к оплате",
            "asset": "валюта (USDT, TON…)",
            "coins": "сколько монеток",
            "coin": "значок монетки",
            "provider": "CryptoBot или xRocket",
            "minutes": "сколько минут живёт счёт",
            "bonus": "строка про бонус за оплату картой (пусто, если его нет)",
        },
    ),
    "CRYPTO_PAID": Item(
        "Оплата криптой прошла",
        "Покупки",
        vars={
            "amount": "сумма",
            "asset": "валюта",
            "coins": "сколько начислили",
            "coin": "значок монетки",
            "balance": "баланс",
        },
    ),
    "CRYPTO_PENDING": Item("Оплата ещё не пришла", "Покупки", plain=True),
    "CRYPTO_EXPIRED": Item("Счёт просрочен", "Покупки", plain=True),
    "CRYPTO_CANCELLED": Item("Счёт отменён", "Покупки", plain=True),
    "CRYPTO_GONE": Item("Счёт не найден", "Покупки", plain=True),
    "CRYPTO_FAILED": Item("Не удалось выставить счёт", "Покупки"),
    "BUY_NO_AMOUNT": Item("Сумма потерялась", "Покупки", plain=True),
    "BUY_CARD_SOON": Item("Оплата картой пока не работает", "Покупки", plain=True),
    "PAID": Item(
        "Оплата прошла",
        "Покупки",
        vars={
            "stars": "сколько ⭐",
            "added": "сколько начислили",
            "coin": "значок монетки",
            "coins": "баланс",
        },
    ),
    "BOUGHT_CONTENT": Item(
        "Куплен доступ к кружочкам",
        "Покупки",
        vars={
            "count": "сколько кружочков",
            "circles": "«кружочка/кружочков»",
            "share": "доля автора",
        },
    ),
    "BOUGHT_CONTACT": Item(
        "Куплена личка", "Покупки", vars={"username": "@username автора"}
    ),
    "SALE_NOTE": Item(
        "Автору: у тебя купили",
        "Покупки",
        vars={"what": "что купили", "share": "сколько начислили", "coin": "значок монетки"},
    ),
    "SALE_KIND_CONTENT": Item("…«доступ к кружочкам»", "Покупки"),
    "SALE_KIND_CONTACT": Item("…«личка»", "Покупки"),
    "MORE_CIRCLES": Item(
        "Осталось ещё кружочков",
        "Покупки",
        vars={"left": "сколько осталось", "circles": "«кружочка/кружочков»"},
    ),
    "SENDING_CIRCLES": Item(
        "Отправляю кружочки", "Покупки", plain=True, vars={"count": "сколько"}
    ),
    "CIRCLES_LOST": Item(
        "Часть кружочков не дошла",
        "Покупки",
        vars={"sent": "сколько дошло", "total": "сколько отправляли"},
    ),
    "CONTACT_NOT_FOR_SALE": Item("Личка не продаётся", "Покупки", plain=True),
    "NOTHING_TO_SELL": Item("У автора нет кружочков", "Покупки", plain=True),
    "ALREADY_BOUGHT": Item("Уже куплено", "Покупки", plain=True),
    "BUY_FIRST": Item("Сначала купи доступ", "Покупки", plain=True),
    "AUTHOR_EMPTY": Item("У автора нечего смотреть", "Покупки", plain=True),
    "NOT_ENOUGH_COINS_TOAST": Item("Не хватает монеток", "Покупки", plain=True),
    "BOUGHT_TOAST": Item("Куплено", "Покупки", plain=True),
    "CHEQUE_POST": Item(
        "Чек: сам пост",
        "Покупки",
        vars={"coins": "монеток за активацию", "total": "сколько активаций"},
    ),
    "CHEQUE_CLAIMED": Item(
        "Чек: активирован",
        "Покупки",
        vars={"coins": "сколько начислили", "coin": "значок монетки", "balance": "баланс"},
    ),
    "CHEQUE_NEEDS_REFS": Item(
        "Чек: нужны рефералы",
        "Покупки",
        vars={"need": "сколько нужно", "have": "сколько есть"},
    ),
    "CHEQUE_GONE": Item("Чек: не найден", "Покупки"),
    "CHEQUE_TAKEN": Item("Чек: уже активирован тобой", "Покупки"),
    "CHEQUE_EMPTY": Item("Чек: активации кончились", "Покупки"),
    # --- Выплаты ---
    "PAYOUT_SCREEN": Item(
        "Экран вывода",
        "Выплаты",
        vars={
            "available": "доступно к выводу",
            "coin": "значок монетки",
            "stars": "это же в ⭐",
            "rate": "монеток за 1 ⭐",
            "low": "минимум",
            "spent": "строка про потраченный заработок",
            "pending": "строка про заявки в работе",
        },
    ),
    "PAYOUT_SCREEN_SPENT": Item(
        "…строка «заработок потрачен в боте»",
        "Выплаты",
        vars={"spent": "сколько потрачено"},
    ),
    "PAYOUT_SCREEN_PENDING": Item(
        "…строка «заявок в работе»", "Выплаты", vars={"pending": "сколько заявок"}
    ),
    "PAYOUT_ASK_AMOUNT": Item(
        "Сколько вывести",
        "Выплаты",
        vars={"available": "доступно", "low": "минимум"},
    ),
    "PAYOUT_NOT_A_NUMBER": Item("Сумма не число", "Выплаты"),
    "PAYOUT_OVER_AVAILABLE": Item(
        "Сумма больше доступного", "Выплаты", vars={"available": "доступно"}
    ),
    "PAYOUT_UNDER_MIN": Item("Сумма меньше минимума", "Выплаты", vars={"low": "минимум"}),
    "PAYOUT_ASK_DETAILS": Item("Запрос реквизитов", "Выплаты"),
    "PAYOUT_CREATED": Item(
        "Заявка создана",
        "Выплаты",
        vars={
            "payout_id": "номер заявки",
            "coins": "сколько монеток",
            "coin": "значок монетки",
            "stars": "сколько ⭐",
        },
    ),
    "PAYOUT_PAID": Item(
        "Заявка выплачена",
        "Выплаты",
        vars={"payout_id": "номер заявки", "stars": "сколько ⭐"},
    ),
    "PAYOUT_REJECTED": Item(
        "Заявка отклонена",
        "Выплаты",
        vars={"payout_id": "номер заявки", "coins": "сколько вернули"},
    ),
    "PAYOUT_SPENT": Item(
        "Монетки уже потрачены",
        "Выплаты",
        vars={"balance": "баланс", "wanted": "сколько просили"},
    ),
    "PAYOUT_TOO_SMALL": Item(
        "Меньше минимума вывода",
        "Выплаты",
        vars={"low": "минимум", "available": "доступно"},
    ),
    # --- Рефералы ---
    "REFERRALS": Item(
        "Экран «Рефералы»",
        "Рефералы",
        vars={
            "done": "приглашено",
            "waiting": "строка «ждут подписки»",
            "ref_reward": "награда за друга",
            "coin": "значок монетки",
            "link": "ссылка-приглашение",
        },
    ),
    "REFERRALS_WAITING": Item(
        "…строка «ждут подписки»", "Рефералы", vars={"waiting": "сколько ждут"}
    ),
    "REFERRAL_PAID": Item(
        "По ссылке пришёл друг",
        "Рефералы",
        vars={"reward": "награда", "done": "всего приглашено"},
    ),
    "TRAFFER_UNKNOWN": Item("Неизвестная команда траффера", "Рефералы"),
    "TRAFFER_REPORT": Item(
        "Отчёт по рекламной ссылке",
        "Рефералы",
        vars={
            "title": "название ссылки",
            "users": "новых людей",
            "subscribed": "прошли подписку",
            "subscribed_pct": "их доля",
            "accepted": "дошли до бота",
            "accepted_pct": "их доля",
            "payers": "платили",
            "payers_pct": "их доля",
            "week_users": "людей за 7 дней",
            "week_subscribed": "подписок за 7 дней",
            "day_users": "людей за сутки",
            "day_subscribed": "подписок за сутки",
            "link": "сама ссылка",
        },
    ),
    # --- Подписка ---
    "SUBSCRIBE": Item(
        "Требование подписки",
        "Подписка",
        vars={
            "what": "«канал» или «все каналы»",
            "gift": "строка про бонус (ниже)",
        },
    ),
    "SUBSCRIBE_ONE": Item("…когда канал один", "Подписка"),
    "SUBSCRIBE_MANY": Item("…когда каналов несколько", "Подписка"),
    "SUBSCRIBE_SPONSORS": Item("…когда в списке есть боты", "Подписка"),
    "SUBSCRIBE_GIFT": Item(
        "…строка про бонус за подписку", "Подписка", vars={"bonus": "размер бонуса"}
    ),
    "SUBSCRIBE_MISSING": Item("Подписки не видно", "Подписка", plain=True),
    "SUBSCRIBE_OK": Item("Подписка засчитана", "Подписка", plain=True),
    "SUB_BONUS": Item(
        "Бонус за подписку начислен",
        "Подписка",
        vars={"amount": "сколько", "coin": "значок монетки"},
    ),
    # --- Короткие ответы на нажатия ---
    "VOTE_LIKE": Item("Поставил лайк", "Короткие ответы", plain=True),
    "VOTE_DISLIKE": Item("Поставил дизлайк", "Короткие ответы", plain=True),
    "VOTE_CANCEL": Item("Отменил оценку", "Короткие ответы", plain=True),
    "CIRCLE_OWN_VOTE": Item("Свой кружок не оценить", "Короткие ответы", plain=True),
    "CIRCLE_NOT_SHOWN": Item("Кружок тебе не показывали", "Короткие ответы", plain=True),
    "CIRCLE_GONE": Item("Кружка больше нет", "Короткие ответы", plain=True),
    "PROFILE_GONE": Item("Анкета пропала", "Короткие ответы", plain=True),
    "PROFILE_OWN": Item("Это твоя анкета", "Короткие ответы", plain=True),
    "PROFILE_NONE_YET": Item("У автора нет анкеты", "Короткие ответы", plain=True),
    "PROFILE_NOTHING_TO_HIDE": Item("Скрывать нечего", "Короткие ответы", plain=True),
    "PROFILE_HIDDEN_TOAST": Item("Анкета скрыта", "Короткие ответы", plain=True),
    "PROFILE_SAVED_TOAST": Item("Сохранено", "Короткие ответы", plain=True),
    "CONTACT_OFF_TOAST": Item("Личка снята с продажи", "Короткие ответы", plain=True),
    "USERNAME_SEEN": Item("@username увидели", "Короткие ответы", plain=True),
    "NEED_PROFILE_FIRST": Item("Сначала заполни анкету", "Короткие ответы", plain=True),
    # --- Платные подписки ---
    "TIERS_HEADER": Item("Витрина: заголовок", "Платные подписки"),
    "TIERS_ACTIVE": Item(
        "Витрина: какая подписка сейчас",
        "Платные подписки",
        vars={"tier": "название тарифа", "until": "до какого числа",
              "left": "сколько осталось"},
    ),
    "TIERS_BALANCE": Item(
        "Витрина: баланс", "Платные подписки", vars=_COIN | {"coins": "баланс"}
    ),
    "TIER_CARD": Item(
        "Карточка тарифа",
        "Платные подписки",
        vars=_COIN | {"tier": "название тарифа", "price": "цена за день",
                      "perks": "список того, что даёт", "coins": "баланс"},
    ),
    "TIER_SWITCH": Item(
        "Предупреждение о смене тарифа",
        "Платные подписки",
        vars={"current": "текущий тариф", "left": "сколько осталось"},
    ),
    "TIER_BOUGHT": Item(
        "Подписка куплена",
        "Платные подписки",
        vars=_COIN | {"tier": "название тарифа", "days": "на сколько дней",
                      "price": "сколько списано", "until": "до какого числа"},
    ),
    "TIER_POOR": Item(
        "Не хватает на подписку",
        "Платные подписки",
        plain=True,
        vars={"price": "сколько нужно", "coins": "баланс"},
    ),
    "TIER_LIMIT_HIT": Item(
        "Дневной лимит A+ кончился",
        "Платные подписки",
        vars=_COIN | {"views": "лимит в день", "circles": "«кружочков»",
                      "watch_cost": "цена просмотра"},
    ),
    "TIER_VIEWS_LEFT": Item(
        "Сколько бесплатных осталось сегодня",
        "Платные подписки",
        vars={"left": "осталось"},
    ),
}


_defaults: dict[str, str] = {}
_custom: dict[str, str] = {}


def _snapshot() -> None:
    """The values texts.py was shipped with, taken before anything overrides."""
    if _defaults:
        return
    for key in EDITABLE:
        value = getattr(texts, key, None)
        if isinstance(value, str):
            _defaults[key] = value
        else:  # a key that no longer exists in the code must not hide the rest
            logger.warning("editable text %s is missing from texts.py", key)


def apply() -> None:
    """Push the current values into texts.py, overrides and defaults alike."""
    _snapshot()
    for key, default in _defaults.items():
        setattr(texts, key, _custom.get(key, default))


async def load_from_db() -> None:
    _snapshot()
    _custom.clear()
    for key, row in (await db.load_custom_texts()).items():
        if key in _defaults:
            _custom[key] = row["text"]
    apply()
    logger.info("custom texts loaded: %s", len(_custom))


def default(key: str) -> str:
    _snapshot()
    return _defaults.get(key, "")


def get(key: str) -> str:
    return _custom.get(key) or default(key)


def is_custom(key: str) -> bool:
    return key in _custom


def known(key: str) -> bool:
    _snapshot()
    return key in _defaults


def keys_in(category: str) -> list[str]:
    return [
        key
        for key in EDITABLE
        if EDITABLE[key].category == category and known(key)
    ]


def categories() -> list[tuple[str, int, int]]:
    """(name, texts in it, how many of them are overridden)"""
    out = []
    for name in CATEGORY_ICON:
        keys = keys_in(name)
        if keys:
            out.append((name, len(keys), sum(is_custom(k) for k in keys)))
    return out


def custom_count() -> int:
    return len(_custom)


# A preview is only useful if it looks like the real message, so the inserts are
# filled with what actually goes there: live settings, real emoji, plausible
# numbers — and for a text built out of others, that other text.
_ICONS = {
    "coin": "COIN",
    "icon_coin": "COIN_EMOJI",
    "film": "FILM",
    "icon_profile": "PROFILE_HEADER",
    "icon_uploaded": "UPLOADED_COUNT",
    "icon_ratings": "RATINGS_ICON",
    "icon_like": "LIKE_EMOJI",
    "icon_dislike": "DISLIKE_EMOJI",
    "icon_views": "VIEWS_COUNT",
    "icon_balance": "BALANCE_ICON",
    "icon_earnings": "EARNINGS_ICON",
    "icon_about": "ABOUT",
    "icon_count": "CIRCLE_COUNT",
    "icon_price": "PRICE",
    "icon_sold": "SOLD",
    "icon_info": "INFO",
}

_FROM_SETTINGS = {
    "watch_cost": "watch_cost",
    "author_share": "author_share",
    "ref_reward": "ref_reward",
    "payout_rate": "payout_rate",
    "payout_min": "payout_min",
    "max_pending": "max_pending",
    "min_duration": "min_duration",
    "price_min": "price_min",
    "price_max": "price_max",
    "star_cost": "star_cost",
    "min_stars": "min_stars",
    "rate": "payout_rate",
    "low": "payout_min",
}

_NUMBERS = {
    "coins": "128",
    "approved": "12",
    "pending": "2",
    "rejected": "1",
    "total": "15",
    "watched": "34",
    "likes": "42",
    "dislikes": "3",
    "ref_done": "5",
    "done": "5",
    "waiting": "2",
    "withdrawable": "1500",
    "available": "1500",
    "spent": "260",
    "balance": "40",
    "wanted": "1000",
    "stars": "500",
    "sold_content": "7",
    "sold_contact": "2",
    "sold": "9",
    "views": "310",
    "shown": "340",
    "hits": "128",
    "earned": "900",
    "user_id": "123456789",
    "author_id": "123456789",
    "circle_id": "417",
    "payout_id": "12",
    "count": "8",
    "left": "4",
    "free": "1",
    "amount": "3",
    "added": "300",
    "share": "25",
    "bonus": "10",
    "reward": "5",
    "duration": "3",
    "limit": "300",
    "price": "560",
    "price_content": "50",
    "circles": "9",
    "users": "100",
    "subscribed": "60",
    "accepted": "55",
    "payers": "5",
    "week_users": "20",
    "week_subscribed": "12",
    "day_users": "5",
    "day_subscribed": "3",
    "subscribed_pct": "60.0%",
    "accepted_pct": "55.0%",
    "payers_pct": "5.0%",
}

_WORDS = {
    "pref": "♀️ женские",
    "who": "♀️ Девушка",
    "kind": "женский",
    "about": "пара строк о себе",
    "username": "durov",
    "link": "https://t.me/bot?start=p123456789",
    "title": "Реклама в канале",
    "field": "Фото",
    "reason": "реклама в анкете",
    "tier": "A++",
    "current": "A+",
    "state": "⚪ Сейчас анкета в общей очереди.",
    "until": "03.09.2026 12:40",
    "days": "7 дней",
    "perks": "• Бесплатный просмотр всех кружков\n• Безлимит кружков",
}

# {gift}, {tail}, {earn}… hold another editable text, and the same name means
# different things in different messages.
_COMPOSED = {
    ("SUBSCRIBE", "gift"): "SUBSCRIBE_GIFT",
    ("NOT_ENOUGH", "earn"): "NOT_ENOUGH_SELL",
    ("UPLOAD_SENT", "tail"): "UPLOAD_SENT_PAID",
    ("UPLOAD_ASK", "payoff"): "UPLOAD_ASK_PAID",
    ("REFERRALS", "waiting"): "REFERRALS_WAITING",
    ("PAYOUT_SCREEN", "pending"): "PAYOUT_SCREEN_PENDING",
    ("PAYOUT_SCREEN", "spent"): "PAYOUT_SCREEN_SPENT",
    ("PROFILE", "withdraw"): "PROFILE_WITHDRAW",
    ("PROFILE_REVERTED", "reason"): "PROFILE_REASON_TAIL",
    ("PROFILE_REJECTED", "reason"): "PROFILE_REASON_TAIL",
    ("PROFILE_FROZEN", "reason"): "PROFILE_FROZEN_REASONS",
    ("REJECTED", "reason"): "CIRCLE_REASON_TAIL",
    ("CIRCLE_DELETED", "reason"): "CIRCLE_REASON_TAIL",
    ("PROFILE_STATUS", "status"): "STATUS_APPROVED",
    ("PROFILE_STATUS", "boost"): "PROFILE_STATUS_BOOST",
    ("PROFILE_STATUS", "contact"): "CONTACT_NOT_SOLD",
    ("PROFILE_CARD", "contact"): "CONTACT_NOT_SOLD",
    ("SALE_NOTE", "what"): "SALE_KIND_CONTENT",
    ("AUCTION", "rule"): "AUCTION_RULE_BACK",
    ("AUCTION_ANNOUNCE", "rule"): "AUCTION_RULE_BACK",
}

# The tables above are keyed by name alone, and a name is not always the same
# thing twice: {left} is «сколько осталось» nearly everywhere, but a date in the
# продвижение tail, where a bare «4» would read as four of something.
_BY_KEY = {
    ("PROFILE_STATUS_BOOST", "left"): "03.09.2026 12:40",
}


def _sample_value(key: str, name: str, depth: int = 0) -> str:
    import emoji  # late: emoji resolves against Telegram at startup

    if (key, name) in _COMPOSED and depth < 2:
        inner = _COMPOSED[(key, name)]
        return sample(inner, get(inner), depth + 1)
    if (key, name) in _BY_KEY:
        return _BY_KEY[(key, name)]
    if name in _ICONS:
        return emoji.text(getattr(emoji, _ICONS[name]))
    if name in _FROM_SETTINGS:
        import settings

        return str(settings.get(_FROM_SETTINGS[name]))
    if name in _NUMBERS:
        return _NUMBERS[name]
    if name in _WORDS:
        return _WORDS[name]
    return f"«{vars_of(key).get(name, name)}»"


# {coin} is filled in for every formatted text (see texts._fmt), so it is
# offered in all of them instead of being declared a hundred times over. Two
# kinds of text are left out: one with no inserts at all is sent exactly as
# written and would show the braces, and a toast renders no HTML, so a premium
# emoji would arrive there as a visible tag.
COMMON_VARS = {"coin": "значок монетки"}


def vars_of(key: str) -> dict[str, str]:
    """Everything this text may hold, its own inserts and the common ones."""
    item = EDITABLE[key]
    if not item.vars or item.plain:
        return dict(item.vars)
    return {**item.vars, **COMMON_VARS}


def sample(key: str, value: str, depth: int = 0) -> str:
    """The template as the user would see it, with real values in the inserts."""
    return value.format(
        **{name: _sample_value(key, name, depth) for name in vars_of(key)}
    )


def vars_hint(key: str) -> str:
    names = vars_of(key)
    if not names:
        return "Вставок в этом тексте нет."
    pairs = [f"<code>{{{name}}}</code> — {what}" for name, what in names.items()]
    # A screen like the profile has two dozen of them; a bullet each turns the
    # card into a wall, so long lists go inline.
    if len(pairs) > 6:
        return "Можно вставить: " + " · ".join(pairs)
    return "Можно вставить:\n" + "\n".join(f"• {pair}" for pair in pairs)


# Tags the bot's own texts are written with, as they come back escaped.
_TAGS = "b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-emoji|tg-spoiler|blockquote|span"
_ESCAPED_TAG = re.compile(
    rf"&lt;(/?)({_TAGS})((?:(?!&gt;).)*)&gt;", re.IGNORECASE | re.DOTALL
)


def _unescape_tags(html_text: str) -> str:
    """Put back the tags the admin typed, leaving everything else escaped."""

    def restore(match: re.Match) -> str:
        import html as html_module

        attrs = html_module.unescape(match.group(3))
        return f"<{match.group(1)}{match.group(2)}{attrs}>"

    return _ESCAPED_TAG.sub(restore, html_text)


def incoming(key: str, text: str, html_text: str) -> tuple[str, str | None]:
    """What to store for this message, and what to fall back to if it fails.

    Telegram hands the same message over twice: as typed, and with whatever the
    sender formatted — bold, links, premium emoji — already turned into tags.
    Only the second one carries those, so it is the one to keep; but it escapes
    tags that were typed by hand, and a text copied out of the card is full of
    them. Hence: take the formatted version, then un-escape the tags in it.
    """
    if EDITABLE[key].plain:
        return (text or "").strip(), None
    escaped = html_text.strip()
    return _unescape_tags(escaped), escaped


def check(key: str, value: str) -> str | None:
    """What is wrong with this template, or None when it is fine."""
    try:
        sample(key, value)
    except KeyError as error:
        name = error.args[0]
        allowed = ", ".join(f"{{{v}}}" for v in vars_of(key)) or "никаких"
        return (
            f"Нет такой вставки: <code>{{{name}}}</code>.\n"
            f"В этом тексте доступны: {allowed}"
        )
    except (IndexError, ValueError):
        return (
            "Фигурные скобки не на месте. Вставка пишется как "
            "<code>{coins}</code>; обычная скобка — <code>{{</code>."
        )
    return None


async def save(key: str, value: str) -> None:
    if not known(key):
        return
    _custom[key] = value
    await db.save_custom_text(key, value, EDITABLE[key].description)
    apply()


async def reset(key: str) -> None:
    _custom.pop(key, None)
    await db.delete_custom_text(key)
    apply()


async def reset_all() -> int:
    dropped = await db.wipe_custom_texts()
    _custom.clear()
    apply()
    return dropped
