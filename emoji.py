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
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import PREMIUM_EMOJI

logger = logging.getLogger(__name__)

COIN = "5471952986970267163"
FEMALE = "5834583952014184479"
MALE = "5834515786588229330"
ANY = "5280816565657300091"
FILM = "5341715473882955310"

# Used until resolve() replaces them, and forever when custom emoji are off.
FALLBACK = {
    COIN: "🪙",
    FEMALE: "♀️",
    MALE: "♂️",
    ANY: "🎲",
    FILM: "🎞️",
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


def label(emoji_id: str) -> str:
    """Prefix for a button label when the icon slot is already taken."""
    return "" if emoji_id in _resolved else FALLBACK[emoji_id] + " "
