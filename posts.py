"""Posts the bot shows on its own: welcomes and promos.

An admin forwards a message once; the bot keeps where it lives and copies it
from there, so anything Telegram can send — photo, video, album-less media —
works without the bot having to understand it.

Buttons are the exception. copyMessage builds a fresh message and carries no
keyboard over, so an advertiser's «Купить» button vanished on the way to the
user and the post went out pointing at nothing. The keyboard is therefore kept
alongside the post and passed back on every copy — see keep_markup.

    welcome — shown to a person once, right after /start
    promo   — an ad break in the feed: every «Показ раз в N кружков» circles,
              right after the circle that earned it

Both are sold to advertisers, so every showing is counted.
"""

import json
import logging
from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

import db
import settings
import sponsors

logger = logging.getLogger(__name__)

WELCOME, PROMO = "welcome", "promo"
KINDS = {WELCOME: "Приветка", PROMO: "Показ"}
# Written out rather than built by adding «и» — that turns Показ into «Покази».
PLURALS = {WELCOME: "Приветки", PROMO: "Показы"}


def keep_markup(markup: InlineKeyboardMarkup | None) -> str:
    """The buttons worth reproducing, as JSON for the posts row.

    Only buttons that act on their own survive: a link, a copyable text. A
    callback button would come back to *this* bot with data meant for another
    one, and the user would get «кнопка устарела» instead of an advert. In
    practice Telegram already strips those when a message is forwarded — this
    is what makes a post composed by hand behave the same way.
    """
    if markup is None or not getattr(markup, "inline_keyboard", None):
        return ""
    rows = []
    for row in markup.inline_keyboard:
        kept = [b for b in row if b.url or b.copy_text]
        if kept:
            rows.append([b.model_dump(exclude_none=True) for b in kept])
    return json.dumps({"inline_keyboard": rows}, ensure_ascii=False) if rows else ""


UNRECORDED = "?"  # saved before the keyboard was kept; see BACKFILLS in db.py


def markup_of(post) -> InlineKeyboardMarkup | None:
    """What to hand copyMessage so the copy carries the post's own buttons."""
    raw = post["markup"] if "markup" in post.keys() else ""
    if not raw or raw == UNRECORDED:
        return None
    try:
        return InlineKeyboardMarkup.model_validate_json(raw)
    except ValueError as error:  # a row saved by an older, different shape
        logger.warning("post %s: кнопки не разобрались: %s", post["id"], error)
        return None


def buttons_of(post) -> list[str]:
    """The button labels, for the admin card — proof they were captured."""
    markup = markup_of(post)
    if markup is None:
        return []
    return [b.text for row in markup.inline_keyboard for b in row]


async def send(bot: Bot, user_id: int, post, promo: bool = False) -> bool:
    """Copy one post to a user and remember that they have seen it."""
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=post["from_chat"],
            message_id=post["msg_id"],
            reply_markup=markup_of(post),
        )
    except TelegramAPIError as error:
        # A deleted original, a bot kicked from the source chat, a blocked user:
        # none of it is worth failing whatever the user was actually doing.
        logger.warning("post %s not shown to %s: %s", post["id"], user_id, error)
        return False
    await db.mark_shown(user_id, post["id"], promo=promo)
    return True


async def show_welcome(bot: Bot, user_id: int) -> int:
    """Every welcome this person has not seen yet. Returns how many landed."""
    shown = 0
    for post in await db.unseen_welcome(user_id):
        if await send(bot, user_id, post):
            shown += 1
    return shown


SPONSOR_CHECKS = 3  # sponsors asked about one person before we give up and send


async def pick(user_id: int):
    """The promo to show this person, skipping the ones that already worked.

    An advert is bought to bring people somewhere. Once somebody is there, the
    post is spent on them: it takes a slot from an advertiser who still has
    something to say to them, and reads as a bot that does not notice anything.
    So the sponsor is asked, the answer is remembered, and the post is dropped
    for that person for good.

    Only a handful of sponsors are asked per circle — the rest wait for the next
    one. An advert nobody could vouch for is shown: silence is not a conversion.
    """
    candidates = await db.promo_candidates(user_id)
    for post in candidates[:SPONSOR_CHECKS]:
        if not post["sponsor_method"]:
            return post
        inside = await sponsors.check(
            post["sponsor_method"], post["sponsor_secret"], user_id
        )
        if not inside:
            return post
        await db.mark_converted(post["id"], user_id)
        logger.info(
            "промо #%s больше не показывается %s — он уже в %s",
            post["id"], user_id, post["sponsor_name"] or "боте спонсора",
        )
    # Everything asked about came back «уже там»; whatever is left goes as is.
    return candidates[SPONSOR_CHECKS] if len(candidates) > SPONSOR_CHECKS else None


async def after_circle(bot: Bot, user_id: int) -> bool:
    """One circle went out; every so many of them, a promo follows it.

    Hung off the circle rather than off every update on purpose: that is the
    moment attention is on the bot, and a promo can no longer land in the
    middle of a question the bot itself asked.
    """
    every = settings.get("promo_every_circles")
    if not settings.get("promo_enabled") or not every:
        return False
    if not await db.promo_due(user_id, every):
        return False

    post = await pick(user_id)
    if post is None:
        return False
    with suppress(TelegramAPIError):
        return await send(bot, user_id, post, promo=True)
    return False
