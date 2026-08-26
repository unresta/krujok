import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
# Chat where every upload lands for moderation (bot must be admin there).
ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
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
REWARD = {"f": 5, "m": 3}
MIN_DURATION = 8  # seconds
STARS_RATE = 3  # coins per star
MIN_STARS = 20
MAX_STARS = 100_000
MAX_PENDING = 5  # unmoderated uploads a user may hold at once
WATCH_COOLDOWN = 1.0  # seconds between "watch" taps

STAR_PACKS = (20, 50, 100, 250)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing, fill .env")
if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is missing, fill .env")
