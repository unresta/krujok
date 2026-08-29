"""Paid subscriptions: what each one buys, and for how much.

Three tiers, priced per day in coins. What they actually change lives in three
places — the feed stops charging (watch.py), circles stop being protected from
forwarding (watch.py again), and the upload queue gets longer (upload.py) — so
the answer to «what does this tier do» is kept here rather than spelled out at
each of those.

Prices and the two numbers that can drift (A+'s daily allowance, Premium's
upload limit) are settings, not constants: an admin moves them from the panel.
"""

from dataclasses import dataclass

import settings

A1 = "a+"
A2 = "a++"
PRO = "premium"

ORDER = (A1, A2, PRO)


@dataclass(frozen=True)
class Tier:
    code: str
    title: str
    price_key: str  # coins per day, read from settings at call time
    unlimited: bool  # no daily ceiling on free circles
    savable: bool  # circles arrive without protect_content
    perks: tuple[str, ...]

    @property
    def price(self) -> int:
        return settings.get(self.price_key)


TIERS: dict[str, Tier] = {
    A1: Tier(
        code=A1,
        title="A+",
        price_key="tier_a1_price",
        unlimited=False,
        savable=False,
        perks=(
            "Бесплатный просмотр всех кружков",
            "До {views} кружков в день бесплатно",
        ),
    ),
    A2: Tier(
        code=A2,
        title="A++",
        price_key="tier_a2_price",
        unlimited=True,
        savable=True,
        perks=(
            "Бесплатный просмотр всех кружков",
            "Безлимит кружков",
            "Пересылка кружков",
            "Скачивание кружков",
        ),
    ),
    PRO: Tier(
        code=PRO,
        title="PREMIUM",
        price_key="tier_pro_price",
        unlimited=True,
        savable=True,
        perks=(
            "Бесплатный просмотр всех кружков",
            "Безлимит кружков",
            "Пересылка кружков",
            "Скачивание кружков",
            "Лимит загрузки кружков увеличивается до {pending}",
        ),
    ),
}

DAYS = (1, 7, 30)  # what a tier can be bought for at once


def get(code: str) -> Tier | None:
    return TIERS.get(code or "")


def title(code: str) -> str:
    tier = get(code)
    return tier.title if tier else ""


def perks(code: str) -> tuple[str, ...]:
    """The selling points, with the numbers an admin can move filled in."""
    tier = get(code)
    if tier is None:
        return ()
    return tuple(
        line.format(
            views=settings.get("tier_a1_views"),
            pending=settings.get("tier_pro_pending"),
        )
        for line in tier.perks
    )


def price_of(code: str, days: int) -> int:
    tier = get(code)
    return tier.price * days if tier else 0


def daily_views(code: str) -> int:
    """How many free circles a day this tier is good for; 0 means no ceiling."""
    tier = get(code)
    if tier is None:
        return 0
    return 0 if tier.unlimited else settings.get("tier_a1_views")


def free_views(code: str) -> bool:
    """Every paid tier watches for free — the ceiling is what differs."""
    return get(code) is not None


def savable(code: str) -> bool:
    tier = get(code)
    return bool(tier and tier.savable)


def max_pending(code: str) -> int:
    """Premium holds more unmoderated uploads; everyone else the usual number."""
    if code == PRO:
        return settings.get("tier_pro_pending")
    return settings.get("max_pending")
