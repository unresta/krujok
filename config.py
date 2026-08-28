import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
# Chat where every upload lands for moderation (bot must be admin there).
ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
# Complaints go here instead, when set — otherwise they join the moderation chat.
REPORTS_CHAT: str = os.getenv("REPORTS_CHAT", "")
# Author profiles awaiting review; empty falls back to the moderation chat too.
PROFILES_CHAT: str = os.getenv("PROFILES_CHAT", "")
# Circles awaiting review; empty means ADMIN_CHAT_ID.
CIRCLES_CHAT: str = os.getenv("CIRCLES_CHAT", "")
# Personal ids allowed to run /stats and /refund.
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}
DB_PATH: str = os.getenv("DB_PATH", "bot.db")
# Custom emoji need a Premium owner or Fragment usernames; set to 0 to fall back
# to plain unicode everywhere.
PREMIUM_EMOJI: bool = os.getenv("PREMIUM_EMOJI", "1") not in ("0", "false", "False")

# --- economy ---
WATCH_COST = 2
# Uploading pays nothing: a circle is a shop window for the author's profile,
# and the only way to earn coins is selling access to it.
REWARD = {"f": 0, "m": 0}
MIN_DURATION = 8  # seconds; anything shorter is refused
STARS_RATE = 3  # coins per star
MIN_STARS = 20
MAX_STARS = 100_000
MAX_PENDING = 5  # unmoderated uploads a user may hold at once
WATCH_COOLDOWN = 1.0  # seconds between "watch" taps

STAR_PACKS = (20, 50, 100, 250)
WELCOME_BONUS = 6  # coins handed to a newcomer, enough for a few circles
SUB_BONUS = 4  # paid once, when the channel subscription is first confirmed
REF_REWARD = 3  # coins for a referral that made it through the subscription gate
VIEW_PAYOUT = 0  # views and likes buy reach, not coins
LIKE_BONUS = 0
LIKE_BOOST = 1  # how much one net like weighs when picking what to show
# --- re-engagement pushes ---
PUSH_ENABLED = 1
PUSH_IDLE_HOURS = 20  # silence before someone is worth a nudge
PUSH_COOLDOWN_HOURS = 48  # never nudge the same person more often
PUSH_BATCH = 40  # per tick, so a big base is spread over hours
PUSH_FREE_VIEWS = 1  # circles handed out with the reminder
PUSH_TICK = 900.0  # seconds between sweeps

REPORTS_TO_HIDE = 5  # complaints that pull a circle out of rotation on their own

# --- author profiles and payouts ---
AUTHOR_SHARE = 50  # percent of a sale that reaches the author
PRICE_MIN = 1
PRICE_MAX = 10_000
PAYOUT_MIN = 1000  # coins
PAYOUT_RATE = 3  # coins per star when cashing out
ABOUT_MAX = 300  # characters in a profile description

# --- legal ---
# Both documents have to be reachable from every screen where money changes
# hands: card acquirers check for them, Stars alone never needed it.
TERMS_URL = "https://telegra.ph/PUBLICHNAYA-OFERTA-08-12-15"
PRIVACY_URL = "https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-12-99"

# --- ad accounting ---
CURRENCY = "₽"
STAR_PRICE = 130  # what one ⭐ is worth to you, in minor units (1.30 ₽)

# Channel users must join before they can use the bot; empty turns the gate off.
# The bot has to be an administrator there to see who is a member.
CHANNEL: str = os.getenv("CHANNEL", "")
SUB_CACHE = 0.0  # seconds a confirmed subscription is trusted without asking

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing, fill .env")
if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is missing, fill .env")
