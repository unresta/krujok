"""Settings for the support bot.

A separate service with its own token, its own database and its own chat. It
never writes to the main bot's base — see mainbase.py for the read-only side.
"""

import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("SUPPORT_BOT_TOKEN", "")
# Group where ticket cards land. Moderators answer by replying to a card, so the
# bot has to be a member (an administrator, if the group hides message authors).
SUPPORT_CHAT: str = os.getenv("SUPPORT_CHAT", "")
# Personal ids allowed to open /admin. Replying in the chat needs no id at all:
# whoever is in that group is trusted to answer.
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("SUPPORT_ADMIN_IDS", "").replace(" ", "").split(",") if x
}
DB_PATH: str = os.getenv("SUPPORT_DB_PATH", "support.db")
# The main bot's base, opened read-only to enrich a card with the user's balance
# and history. Empty (or missing file) simply drops those lines from the card.
MAIN_DB_PATH: str = os.getenv("MAIN_DB_PATH", "")

# --- limits ---
TEXT_MAX = 1000  # characters in one ticket message
THREAD_LIMIT = 50  # messages kept on screen when showing a whole thread
LIST_LIMIT = 10  # tickets per screen in "my tickets" and the admin queue

# --- SLA reminders ---
SLA_HOURS = 12  # unanswered for longer than this and the chat gets pinged
SLA_TICK = 1800.0  # seconds between sweeps
SLA_REPEAT_HOURS = 12  # never ping the same ticket more often than this

if not BOT_TOKEN:
    raise RuntimeError("SUPPORT_BOT_TOKEN is missing, fill support/.env")
