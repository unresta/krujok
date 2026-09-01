"""Coin cheques: minted in the inline field, opened from a channel post.

    @AnonKrujokBot 100 5     — 100 монеток, 5 активаций

Two results come back for that: a plain cheque and one only people who have
invited enough friends can take. The posts are byte-identical on purpose — the
condition shows up when someone tries to open it, not before.

Only admins can mint: an inline query from anyone else returns nothing at all,
because the alternative is letting strangers print coins.

The post carries a deep link rather than a callback button: a channel reader is
not in a chat with the bot yet, and `?start=chq_<code>` both opens that chat and
carries the code. If the gate stops them there, the code waits on their row
until they are through — see middlewares/user.py.
"""

import logging

from aiogram import Bot, F, Router
from aiogram.types import (
    ChosenInlineResult,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
)

import db
import keyboards as kb
import settings
import texts
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

router = Router()

PREFIX = "chq_"  # what a cheque deep link starts with
PLAIN, REFS = "plain", "refs"


def parse_link(payload: str) -> str:
    """«chq_ab12» -> «ab12»; anything else is not a cheque."""
    payload = (payload or "").strip()
    if not payload.startswith(PREFIX):
        return ""
    code = payload[len(PREFIX):]
    return code if code.isalnum() else ""


def _parse_query(query: str) -> tuple[int, int] | None:
    parts = query.split()
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    coins, total = int(parts[0]), int(parts[1])
    if not (1 <= coins <= 1_000_000 and 1 <= total <= 100_000):
        return None
    return coins, total


@router.inline_query()
async def make(query: InlineQuery) -> None:
    if query.from_user.id not in ADMIN_IDS:
        await query.answer([], cache_time=1, is_personal=True)
        return

    parsed = _parse_query(query.query)
    if parsed is None:
        await query.answer(
            [],
            cache_time=1,
            is_personal=True,
            button=InlineQueryResultsButton(
                text="Формат: 100 5 — 100 монеток, 5 активаций",
                start_parameter="cheques",
            ),
        )
        return

    coins, total = parsed
    min_refs = settings.get("cheque_min_refs")
    results = []
    for kind, title in (
        (PLAIN, f"🎟 Чек · {coins} монеток × {total}"),
        (REFS, f"🎟 Чек · {coins} × {total} · только от {min_refs} рефералов"),
    ):
        code = await db.make_cheque(
            query.from_user.id, coins, total, kind, min_refs if kind == REFS else 0
        )
        results.append(
            InlineQueryResultArticle(
                id=f"{kind}:{code}",
                title=title,
                description=(
                    "Пост одинаковый у обоих; условие проверяется при активации."
                    if kind == REFS
                    else "Открыть может любой, кто прошёл обязательную подписку."
                ),
                input_message_content=InputTextMessageContent(
                    message_text=texts.cheque_post(coins, total),
                    parse_mode="HTML",
                ),
                reply_markup=kb.cheque(code),
            )
        )
    # Cached results would hand the same code to a second, different cheque.
    await query.answer(results, cache_time=0, is_personal=True)


@router.chosen_inline_result()
async def posted(chosen: ChosenInlineResult) -> None:
    """The cheque was actually sent somewhere, so it stops being a draft."""
    _, _, code = chosen.result_id.partition(":")
    if code:
        await db.mark_cheque_posted(code)
        await db.drop_stale_cheques()


async def redeem(bot: Bot, user_id: int, code: str) -> bool:
    """Hand over the coins, or say why not. True when they were handed over.

    Written straight into the user's chat rather than as a reply: a cheque is
    often taken from a button on a two-day-old gate message, and Telegram hands
    those to us as an `InaccessibleMessage` that cannot be answered.
    """
    cheque = await db.get_cheque(code)
    if cheque is None:
        await bot.send_message(user_id, texts.CHEQUE_GONE)
        return False
    if await db.has_claimed(code, user_id):
        await bot.send_message(user_id, texts.CHEQUE_TAKEN)
        return False
    if not cheque["active"] or cheque["used"] >= cheque["total"]:
        await bot.send_message(user_id, texts.CHEQUE_EMPTY)
        return False

    if cheque["kind"] == REFS:
        done, _ = await db.referral_counts(user_id)
        if done < cheque["min_refs"]:
            await bot.send_message(
                user_id,
                texts.cheque_needs_refs(cheque["min_refs"], done),
                reply_markup=kb.referrals(_link(user_id)),
            )
            return False

    if not await db.claim_cheque(code, user_id):  # someone took the last one
        await bot.send_message(user_id, texts.CHEQUE_EMPTY)
        return False

    await db.add_coins(user_id, cheque["coins"])
    balance = (await db.get_user(user_id))["coins"]
    await bot.send_message(user_id, texts.cheque_claimed(cheque["coins"], balance))
    logger.info("cheque %s claimed by %s (+%s)", code, user_id, cheque["coins"])
    return True


def _link(user_id: int) -> str:
    import access

    return access.referral_link(user_id)
