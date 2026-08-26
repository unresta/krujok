"""Premium (custom) emoji ids and their plain fallbacks.

Custom emoji work only for bots whose owner has Premium or that bought extra
usernames on Fragment — everyone else gets an API error. PREMIUM_EMOJI=0 in .env
switches the whole bot back to plain unicode without touching any other code.

In message text a custom emoji is an HTML <tg-emoji> tag; on a button it is the
`icon_custom_emoji_id` field, which renders one icon before the label — so a
button can carry exactly one custom emoji, and it always sits first.
"""

from config import PREMIUM_EMOJI

COIN = "5471952986970267163"
FEMALE = "5834583952014184479"
MALE = "5834515786588229330"
ANY = "5280816565657300091"
FILM = "5341715473882955310"

FALLBACK = {
    COIN: "🪙",
    FEMALE: "♀",
    MALE: "♂",
    ANY: "🎲",
    FILM: "🎞",
}


def text(emoji_id: str) -> str:
    """Custom emoji for message text (HTML parse mode)."""
    plain = FALLBACK[emoji_id]
    if not PREMIUM_EMOJI:
        return plain
    return f'<tg-emoji emoji-id="{emoji_id}">{plain}</tg-emoji>'


def icon(emoji_id: str) -> str | None:
    """Value for InlineKeyboardButton.icon_custom_emoji_id."""
    return emoji_id if PREMIUM_EMOJI else None


def label(emoji_id: str) -> str:
    """Prefix for a button label when the icon slot is already taken."""
    return "" if PREMIUM_EMOJI else FALLBACK[emoji_id] + " "
