"""Economy knobs an admin can turn without a redeploy.

config.py holds the defaults; whatever the admin changes lands in the settings
table and is loaded back on start. Read through get()/reward() at call time —
never import a value into a module constant, or edits stop taking effect.
"""

import logging

import config
import db

logger = logging.getLogger(__name__)

DEFAULTS: dict[str, int] = {
    "watch_cost": config.WATCH_COST,
    "reward_f": config.REWARD["f"],
    "reward_m": config.REWARD["m"],
    "star_cost": config.STAR_COST,
    "min_stars": config.MIN_STARS,
    "min_duration": config.MIN_DURATION,
    "max_pending": config.MAX_PENDING,
    "ref_reward": config.REF_REWARD,
    "welcome_bonus": config.WELCOME_BONUS,
    "welcome_circle": config.WELCOME_CIRCLE,
    "sub_bonus": config.SUB_BONUS,
    "view_payout": config.VIEW_PAYOUT,
    "like_bonus": config.LIKE_BONUS,
    "like_boost": config.LIKE_BOOST,
    "reports_to_hide": config.REPORTS_TO_HIDE,
    "push_enabled": config.PUSH_ENABLED,
    "push_idle_hours": config.PUSH_IDLE_HOURS,
    "push_cooldown_hours": config.PUSH_COOLDOWN_HOURS,
    "push_batch": config.PUSH_BATCH,
    "push_free_views": config.PUSH_FREE_VIEWS,
    "author_share": config.AUTHOR_SHARE,
    "price_min": config.PRICE_MIN,
    "price_max": config.PRICE_MAX,
    "payout_min": config.PAYOUT_MIN,
    "payout_rate": config.PAYOUT_RATE,
    "star_price": config.STAR_PRICE,
    "stars_per_usd": config.STARS_PER_USD,
    "usdt_rate": config.USDT_RATE,
    "promo_enabled": config.PROMO_ENABLED,
    "promo_every_circles": config.PROMO_EVERY_CIRCLES,
    "cheque_min_refs": config.CHEQUE_MIN_REFS,
    "tier_a1_price": config.TIER_A1_PRICE,
    "tier_a2_price": config.TIER_A2_PRICE,
    "tier_pro_price": config.TIER_PRO_PRICE,
    "tier_a1_views": config.TIER_A1_VIEWS,
    "tier_pro_pending": config.TIER_PRO_PENDING,
    "boost_price": config.BOOST_PRICE,
    "boost_weight": config.BOOST_WEIGHT,
    "maintenance": 0,
}

# Free-form values live apart: the settings table holds integers.
TEXT_DEFAULTS: dict[str, str] = {
    "channel": config.CHANNEL,  # @name or -100… ; empty disables the gate
    "reports_chat": config.REPORTS_CHAT,  # empty falls back to ADMIN_CHAT_ID
    "profiles_chat": config.PROFILES_CHAT,
    "circles_chat": config.CIRCLES_CHAT,
    "currency": config.CURRENCY,
    "crypto_asset": config.CRYPTO_ASSET,
}

TITLES: dict[str, str] = {
    "watch_cost": "Просмотр, монеток",
    "reward_f": "Награда за женский",
    "reward_m": "Награда за мужской",
    "star_cost": "⭐ за 1 монетку",
    "min_stars": "Минимум ⭐ за раз",
    "min_duration": "Минимум, сек",
    "max_pending": "Кружков на проверке",
    "ref_reward": "За реферала",
    "welcome_bonus": "Новичку при старте",
    "welcome_circle": "Кружок при старте, 0/1",
    "sub_bonus": "За подписку на канал",
    "view_payout": "Автору за просмотр",
    "like_bonus": "Автору за лайк",
    "like_boost": "Вес лайка в выдаче",
    "reports_to_hide": "Жалоб до скрытия",
    "push_idle_hours": "Напоминание после, ч",
    "push_cooldown_hours": "Не чаще чем раз в, ч",
    "push_batch": "Напоминаний за проход",
    "push_free_views": "Кружков в подарок",
    "author_share": "Автору с продажи, %",
    "price_min": "Мин. цена анкеты",
    "price_max": "Макс. цена анкеты",
    "payout_min": "Минимум вывода",
    "payout_rate": "Монеток за 1 ⭐ (вывод)",
    "star_price": "Цена 1 ⭐ в копейках",
    "stars_per_usd": "Звёзд за 1 $ (курс TG)",
    "usdt_rate": "Монеток за 1 USDT",
    "promo_every_circles": "Показ раз в N кружков",
    "cheque_min_refs": "Рефералов для чека",
    "tier_a1_price": "A+ монеток в день",
    "tier_a2_price": "A++ монеток в день",
    "tier_pro_price": "Premium монеток в день",
    "tier_a1_views": "A+ кружков в день",
    "tier_pro_pending": "Premium кружков на проверке",
    "boost_price": "Продвижение: монеток в день",
    "boost_weight": "Продвижение: вес в выдаче",
}

# Twenty-four knobs in one column is a wall; the panel shows them by subject.
GROUPS: dict[str, tuple[str, ...]] = {
    "🎬 Просмотр и лента": (
        "watch_cost",
        "view_payout",
        "like_bonus",
        "like_boost",
        "min_duration",
        "max_pending",
        "reward_f",
        "reward_m",
    ),
    "💰 Продажи": ("author_share", "price_min", "price_max"),
    "⭐ Покупка монеток": (
        "star_cost",
        "min_stars",
        "star_price",
        "stars_per_usd",
        "usdt_rate",
    ),
    "💸 Вывод": ("payout_min", "payout_rate"),
    "🎁 Бонусы": ("welcome_bonus", "welcome_circle", "sub_bonus", "ref_reward"),
    "🔔 Напоминания": (
        "push_idle_hours",
        "push_cooldown_hours",
        "push_batch",
        "push_free_views",
    ),
    "💎 Подписки": (
        "tier_a1_price",
        "tier_a2_price",
        "tier_pro_price",
        "tier_a1_views",
        "tier_pro_pending",
    ),
    "⚠️ Модерация": ("reports_to_hide",),
    "📰 Посты": ("promo_every_circles",),
    "🚀 Продвижение анкеты": ("boost_price", "boost_weight"),
    "🎟 Чеки": ("cheque_min_refs",),
}

LIMITS: dict[str, tuple[int, int]] = {
    "watch_cost": (1, 1000),
    "reward_f": (0, 1000),
    "reward_m": (0, 1000),
    "star_cost": (1, 1000),
    "min_stars": (1, 10_000),
    "min_duration": (1, 60),
    "max_pending": (1, 100),
    "ref_reward": (0, 1000),
    "welcome_bonus": (0, 1000),
    "welcome_circle": (0, 1),
    "sub_bonus": (0, 1000),
    "view_payout": (0, 1000),
    "like_bonus": (0, 1000),
    "like_boost": (0, 100),
    "reports_to_hide": (1, 1000),
    "push_enabled": (0, 1),
    "push_idle_hours": (1, 720),
    "push_cooldown_hours": (1, 720),
    "push_batch": (1, 1000),
    "push_free_views": (0, 10),
    "author_share": (0, 100),
    "price_min": (1, 10_000),
    "price_max": (1, 100_000),
    "payout_min": (1, 1_000_000),
    "payout_rate": (1, 1000),
    "star_price": (1, 1_000_000),
    "stars_per_usd": (1, 100_000),
    "usdt_rate": (1, 1_000_000),
    "promo_enabled": (0, 1),
    "promo_every_circles": (1, 1000),
    "cheque_min_refs": (1, 1000),
    "tier_a1_price": (1, 100_000),
    "tier_a2_price": (1, 100_000),
    "tier_pro_price": (1, 100_000),
    "tier_a1_views": (1, 10_000),
    "tier_pro_pending": (1, 1000),
    "boost_price": (1, 100_000),
    "boost_weight": (1, 100),
}

_values: dict[str, int] = dict(DEFAULTS)
_texts: dict[str, str] = dict(TEXT_DEFAULTS)


LEGACY_USDT_RATE = 200  # what shipped: a coin for a sixth of its price in stars
_REPAIRED = "usdt_rate_repaired"  # marker row; no title, so the panel never shows it


async def load() -> None:
    _values.update(DEFAULTS)
    _values.update(await db.load_settings())
    _texts.update(TEXT_DEFAULTS)
    _texts.update(await db.load_text_settings())
    await _repair_crypto_rate()


async def _repair_crypto_rate() -> None:
    """Once: unstick a bot still selling coins for a sixth of the star price.

    A setting saved in the database wins over the default, so correcting the
    default alone would leave every running bot mispriced. Only the number that
    shipped is touched, and only on the first start after this — an admin who
    picks 200 on purpose afterwards keeps it.
    """
    if _values.get(_REPAIRED):
        return
    if _values["usdt_rate"] == LEGACY_USDT_RATE != crypto_parity():
        await set("usdt_rate", crypto_parity())
        logger.warning(
            "курс крипты %s был в %.1f раза ниже звёздного, исправлен на %s",
            LEGACY_USDT_RATE,
            LEGACY_USDT_RATE / crypto_parity(),
            _values["usdt_rate"],
        )
    await set(_REPAIRED, 1)


def get(key: str) -> int:
    return _values[key]


def reward(gender: str) -> int:
    return _values["reward_f" if gender == "f" else "reward_m"]


def author_share(price: int) -> int:
    """What the author keeps from a sale; the rest is the service's cut."""
    return price * _values["author_share"] // 100


def boost_price(days: int, discount: int) -> int:
    """What that many days of paid reach cost, rounded down to a tidy ten."""
    full = days * _values["boost_price"] * (100 - discount) // 100
    return max(1, full // 10 * 10) if full >= 10 else max(1, full)


def coins_for(stars: int) -> int:
    """What that many stars buy. A coin costs whole stars, so this rounds down."""
    return stars // _values["star_cost"]


def stars_of(coins: int) -> int:
    """The other way: what those coins cost, and what the invoice is issued for.

    Money is only ever taken for whole coins — charging for the remainder of a
    star would be charging for nothing.
    """
    return coins * _values["star_cost"]


def stars_for(coins: int) -> int:
    """Cashing out, which runs on its own rate — see «Вывод» in the panel."""
    return coins // _values["payout_rate"]


def usd_of_stars(stars: int) -> float:
    """What that many stars cost the buyer, in dollars."""
    return stars / _values["stars_per_usd"]


def crypto_parity() -> int:
    """The `usdt_rate` that would charge the same as paying in stars.

    Two checkouts for one product only work while they cost the same; whichever
    is cheaper is the only one anybody uses. This is the number to compare the
    real rate against — see the crypto screen in the panel.
    """
    # Rounded down: fewer coins for a dollar is the dearer, safer side to land on.
    return max(1, _values["stars_per_usd"] // _values["star_cost"])


def crypto_gap() -> float:
    """How far the crypto price sits from the star price. 1.0 means the same.

    Below 1 crypto is cheaper — the dangerous side, and the one that shipped:
    200 coins for a dollar against 33 was six times off.
    """
    parity = crypto_parity()
    return _values["usdt_rate"] and parity / _values["usdt_rate"] or 0.0


def reports_chat() -> int | str:
    """Where complaints land: their own chat if set, the moderation one if not."""
    return _texts["reports_chat"].strip() or config.ADMIN_CHAT_ID


def money(minor: int) -> str:
    """Minor units to something a human reads: 1073720 -> «10737.20 ₽»."""
    return f"{minor // 100}.{minor % 100:02d} {_texts['currency']}"


def revenue_of(stars: int) -> int:
    """What those stars are worth, in minor units."""
    return stars * _values["star_price"]


def circles_chat() -> int | str:
    """Where uploaded circles go for review."""
    return _texts["circles_chat"].strip() or config.ADMIN_CHAT_ID


def profiles_chat() -> int | str:
    """Where profiles go for review: their own chat, or the moderation one."""
    return _texts["profiles_chat"].strip() or config.ADMIN_CHAT_ID


def maintenance() -> bool:
    return bool(_values["maintenance"])


async def set(key: str, value: int) -> None:
    _values[key] = value
    await db.save_setting(key, value)


def default(key: str) -> int:
    return DEFAULTS[key]


def groups() -> dict[str, tuple[str, ...]]:
    """Every titled setting belongs somewhere, even one added after the fact."""
    known = {key for keys in GROUPS.values() for key in keys}
    rest = tuple(key for key in TITLES if key not in known)
    return {**GROUPS, "📋 Прочее": rest} if rest else dict(GROUPS)


def get_text(key: str) -> str:
    return _texts[key]


async def set_text(key: str, value: str) -> None:
    _texts[key] = value
    await db.save_text_setting(key, value)
