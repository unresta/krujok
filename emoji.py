"""Premium (custom) emoji ids, with their placeholders resolved at startup.

A <tg-emoji> tag carries a plain emoji as fallback text, and Telegram validates
it: if it is not the base emoji of that custom emoji, the whole send fails with
ENTITY_TEXT_INVALID. So the placeholders are not guessed — resolve() asks
getCustomEmojiStickers for each id and takes the `emoji` field it returns.

Anything that cannot be resolved (unknown id, no rights, network) silently falls
back to plain unicode instead of breaking every message. PREMIUM_EMOJI=0 in .env
turns custom emoji off wholesale.

On a button the icon lives in `icon_custom_emoji_id` — one per button, always
rendered before the label, and free of the placeholder problem.

NOW WITH DATABASE OVERRIDE SUPPORT: emoji_manager can override these defaults.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import PREMIUM_EMOJI

logger = logging.getLogger(__name__)

# Default values - can be overridden via emoji_manager
COIN = "5471952986970267163"
FEMALE = "5834515786588229330"
MALE = "5834583952014184479"
ANY = "5280816565657300091"
FILM = "5341715473882955310"

# Main menu and circle reactions.
UPLOAD = "6028115612163641653"
WATCH = "5850346984501680054"
PROFILE = "6035084557378654059"
REF = "6033108709213736873"
SHOP = "6028338546736107668"
RULES = "5334544901428229844"
FEED = "5850309953293653168"
LIKE = "5307804022726467465"
DISLIKE = "5346076867143147808"
AUTHOR_PROFILE = "6032994772321309200"
NEXT_CIRCLE = "5850346984501680054"
REPORT = "5834895792409677476"
MY_CIRCLES = "5798430918771220206"

# Lines of an author's profile card.
ABOUT = "5258503720928288433"
PRICE = "5348418461838098123"
CIRCLE_COUNT = "5294299296928117557"
SOLD = "5879770735999717115"
INFO = "5352741157442961082"

# User profile page.
PROFILE_HEADER = "6032693626394382504"
UPLOADED_COUNT = "5294299296928117557"
RATINGS_ICON = "5350790271627968474"
LIKE_EMOJI = "5350417283783084711"
DISLIKE_EMOJI = "5348132683304156113"
VIEWS_COUNT = "6030506650522096180"
BALANCE_ICON = "5404359483155570991"
COIN_EMOJI = "5474394658698188879"
EARNINGS_ICON = "5904462880941545555"

# Used until resolve() replaces them, and forever when custom emoji are off.
FALLBACK = {
    COIN: "🪙",
    FEMALE: "♀️",
    MALE: "♂️",
    ANY: "🎲",
    FILM: "🎞️",
    UPLOAD: "🎥",
    WATCH: "▶️",
    PROFILE: "👤",
    REF: "👥",
    SHOP: "⭐",
    RULES: "ℹ️",
    FEED: "🎛️",
    LIKE: "👍",
    DISLIKE: "👎",
    ABOUT: "📝",
    PRICE: "💲",
    CIRCLE_COUNT: "⚪",
    SOLD: "👤",
    INFO: "📌",
    AUTHOR_PROFILE: "👤",
    NEXT_CIRCLE: "▶️",
    REPORT: "⚠️",
    MY_CIRCLES: "⚪",
    PROFILE_HEADER: "👤",
    UPLOADED_COUNT: "⚪",
    RATINGS_ICON: "⭐",
    LIKE_EMOJI: "👍",
    DISLIKE_EMOJI: "👎",
    VIEWS_COUNT: "👁️",
    BALANCE_ICON: "💰",
    COIN_EMOJI: "🪙",
    EARNINGS_ICON: "💼",
}

# Ids Telegram confirmed — only these are allowed to render as custom emoji.
_resolved: set[str] = set()


async def resolve(bot: Bot) -> None:
    """Ask Telegram for the real placeholder of every id we ship."""
    if not PREMIUM_EMOJI:
        logger.info("custom emoji disabled by PREMIUM_EMOJI")
        return

    try:
        stickers = await bot.get_custom_emoji_stickers(
            custom_emoji_ids=list(FALLBACK)
        )
    except TelegramAPIError as error:
        logger.warning("custom emoji unavailable (%s), using plain unicode", error)
        return

    for sticker in stickers:
        if sticker.custom_emoji_id in FALLBACK and sticker.emoji:
            FALLBACK[sticker.custom_emoji_id] = sticker.emoji
            _resolved.add(sticker.custom_emoji_id)

    for emoji_id, plain in FALLBACK.items():
        if emoji_id in _resolved:
            logger.info("custom emoji %s -> %s", emoji_id, plain)
        else:
            logger.warning("custom emoji %s not found, using %s", emoji_id, plain)


def text(emoji_id: str) -> str:
    """Custom emoji for message text (HTML parse mode)."""
    plain = FALLBACK[emoji_id]
    if emoji_id not in _resolved:
        return plain
    return f'<tg-emoji emoji-id="{emoji_id}">{plain}</tg-emoji>'


def icon(emoji_id: str) -> str | None:
    """Value for InlineKeyboardButton.icon_custom_emoji_id."""
    return emoji_id if emoji_id in _resolved else None


def plain(emoji_id: str) -> str:
    """Bare emoji, for button labels where the icon slot cannot be used."""
    return FALLBACK[emoji_id]


def label(emoji_id: str) -> str:
    """Prefix for a button label when the icon slot is already taken."""
    return "" if emoji_id in _resolved else FALLBACK[emoji_id] + " "
