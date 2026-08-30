"""SQLite layer. Every coin move goes through here so balances stay atomic."""

from __future__ import annotations

import random
import secrets
import time

import aiosqlite

from config import DB_PATH, MSK_OFFSET

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    coins       INTEGER NOT NULL DEFAULT 0,
    pref        TEXT    NOT NULL DEFAULT 'f',   -- f | m | any
    banned      INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- Every subscription ever sold, for the panel's takings and for answering
-- «за что списали»: the users row only carries the one in force.
CREATE TABLE IF NOT EXISTS tier_sales (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tier    TEXT    NOT NULL,
    days    INTEGER NOT NULL,
    price   INTEGER NOT NULL,             -- coins actually taken
    ts      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_tier_sales_user ON tier_sales(user_id, ts);

CREATE TABLE IF NOT EXISTS circles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        TEXT    NOT NULL,
    file_unique_id TEXT    NOT NULL UNIQUE,
    uploader_id    INTEGER NOT NULL,
    gender         TEXT    NOT NULL,            -- f | m
    duration       INTEGER NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    rewarded       INTEGER NOT NULL DEFAULT 0,          -- upload reward already paid
    views          INTEGER NOT NULL DEFAULT 0,
    admin_msg_id   INTEGER,
    reviewed_by    INTEGER,
    created_at     INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_circles_pick ON circles(status, gender);

CREATE TABLE IF NOT EXISTS views (
    user_id   INTEGER NOT NULL,
    circle_id INTEGER NOT NULL,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (user_id, circle_id)
);

CREATE TABLE IF NOT EXISTS reactions (
    user_id   INTEGER NOT NULL,
    circle_id INTEGER NOT NULL,
    value     INTEGER NOT NULL,          -- 1 like, -1 dislike
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (user_id, circle_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    circle_id INTEGER NOT NULL,
    reason    TEXT    NOT NULL DEFAULT '',   -- key from texts.REPORT_REASONS
    handled   INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE (user_id, circle_id)
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id         INTEGER PRIMARY KEY,
    photo_id        TEXT  NOT NULL,
    photo_unique_id TEXT,
    about         TEXT    NOT NULL DEFAULT '',
    gender        TEXT    NOT NULL,
    price_content INTEGER NOT NULL,
    price_contact INTEGER NOT NULL DEFAULT 0,   -- 0 = contact is not for sale
    contact_ok    INTEGER NOT NULL DEFAULT 0,
    username      TEXT,
    status        TEXT    NOT NULL DEFAULT 'pending',
    views         INTEGER NOT NULL DEFAULT 0,
    sold          INTEGER NOT NULL DEFAULT 0,
    admin_msg_id  INTEGER,
    created_at    INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- The last version a moderator approved, kept so that rejecting an edit rolls
-- the author back instead of wiping a profile that was fine yesterday.
CREATE TABLE IF NOT EXISTS profile_backup (
    user_id         INTEGER PRIMARY KEY,
    photo_id        TEXT    NOT NULL,
    photo_unique_id TEXT,
    about           TEXT    NOT NULL DEFAULT '',
    gender          TEXT    NOT NULL,
    price_content   INTEGER NOT NULL,
    price_contact   INTEGER NOT NULL DEFAULT 0,
    contact_ok      INTEGER NOT NULL DEFAULT 0,
    username        TEXT
);

CREATE TABLE IF NOT EXISTS purchases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id      INTEGER NOT NULL,
    author_id     INTEGER NOT NULL,
    kind          TEXT    NOT NULL,             -- content | contact
    price         INTEGER NOT NULL,
    author_share  INTEGER NOT NULL,
    max_circle_id INTEGER NOT NULL DEFAULT 0,   -- content bought is frozen here
    ts            INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE (buyer_id, author_id, kind)
);

CREATE TABLE IF NOT EXISTS profile_views (
    buyer_id  INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (buyer_id, author_id)
);

CREATE TABLE IF NOT EXISTS payouts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    coins        INTEGER NOT NULL,
    stars        INTEGER NOT NULL,
    details      TEXT    NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'open',   -- open | paid | rejected
    admin_msg_id INTEGER,
    ts           INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    closed_at    INTEGER
);

CREATE TABLE IF NOT EXISTS profile_reports (
    user_id   INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    reason    TEXT    NOT NULL DEFAULT '',   -- key from texts.PROFILE_REPORT_REASONS
    handled   INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (user_id, author_id)
);

-- A cheque an admin posts in a channel: the coins are handed out to whoever
-- opens it, one activation per person, until the activations run out. The
-- «refs» kind additionally wants the claimer to have invited people — nothing
-- about the post itself says so, that is the whole point of it.
CREATE TABLE IF NOT EXISTS cheques (
    code       TEXT    PRIMARY KEY,
    coins      INTEGER NOT NULL,
    total      INTEGER NOT NULL,           -- activations it was created for
    used       INTEGER NOT NULL DEFAULT 0,
    kind       TEXT    NOT NULL DEFAULT 'plain',   -- plain | refs
    min_refs   INTEGER NOT NULL DEFAULT 0,
    author_id  INTEGER NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    posted     INTEGER NOT NULL DEFAULT 0, -- the inline result was actually sent
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS cheque_claims (
    code    TEXT    NOT NULL,
    user_id INTEGER NOT NULL,
    ts      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (code, user_id)
);

-- Sponsor channels the gate demands. Several at once: this is what is sold to
-- advertisers, so each one keeps its own count of who came through it.
CREATE TABLE IF NOT EXISTS gate_channels (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    -- A channel is checked by Telegram itself; a sponsor bot is checked through
    -- BotMembers, and then «chat» holds the code that service issued.
    kind     TEXT    NOT NULL DEFAULT 'channel',   -- channel | bot
    chat     TEXT    NOT NULL UNIQUE,       -- @name, -100… or a BotMembers code
    title    TEXT    NOT NULL DEFAULT '',
    link     TEXT    NOT NULL DEFAULT '',   -- filled in from Telegram
    active   INTEGER NOT NULL DEFAULT 1,
    added_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS channel_joins (
    channel_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    ts         INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (channel_id, user_id)
);

-- Who the gate actually sent to a sponsor: a row appears when the person was
-- found outside and asked to join. Without it «пришло через него» counts the
-- sponsor's own crowd too — everyone who was already inside before ever
-- meeting our gate — and reports roughly double what the sponsor sees.
CREATE TABLE IF NOT EXISTS channel_asked (
    channel_id INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    ts         INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (channel_id, user_id)
);

-- A post the admin forwards once and the bot shows on its own: a welcome is
-- seen once per user, a promo comes round again on a timer.
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT    NOT NULL,             -- welcome | promo
    from_chat  INTEGER NOT NULL,             -- where the original still lives
    msg_id     INTEGER NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    shown      INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS post_seen (
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    ts      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY (user_id, post_id)
);

CREATE TABLE IF NOT EXISTS campaigns (
    code       TEXT PRIMARY KEY,          -- what goes after ?start=
    title      TEXT NOT NULL DEFAULT '',
    hits       INTEGER NOT NULL DEFAULT 0, -- every /start, repeats included
    spend      INTEGER NOT NULL DEFAULT 0,
    token      TEXT,                      -- shared with whoever bought the ad
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS campaign_hits (
    code    TEXT    NOT NULL,
    user_id INTEGER NOT NULL,
    ts      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_hits_code ON campaign_hits(code, ts);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_text (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_emoji (
    key   TEXT PRIMARY KEY,
    emoji_id TEXT NOT NULL,
    fallback TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS custom_texts (
    key   TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS payments (
    charge_id TEXT PRIMARY KEY,
    user_id   INTEGER NOT NULL,
    stars     INTEGER NOT NULL,
    coins     INTEGER NOT NULL,
    provider  TEXT    NOT NULL DEFAULT 'stars',  -- stars | cryptobot | xrocket
    asset     TEXT    NOT NULL DEFAULT '',       -- USDT, TON… for crypto
    amount    TEXT    NOT NULL DEFAULT '',       -- what was actually charged
    refunded  INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- A crypto invoice lives here until the provider says it was paid. Nothing of
-- ours is reachable from the internet, so there is no webhook to wait for: the
-- bot asks about its own open invoices and closes them itself.
CREATE TABLE IF NOT EXISTS invoices (
    provider   TEXT    NOT NULL,               -- cryptobot | xrocket
    invoice_id TEXT    NOT NULL,
    user_id    INTEGER NOT NULL,
    coins      INTEGER NOT NULL,
    amount     TEXT    NOT NULL,
    asset      TEXT    NOT NULL,
    link       TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL DEFAULT 'active',  -- active|paid|expired|cancelled
    msg_id     INTEGER,                        -- card to update once it is paid
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    closed_at  INTEGER,
    PRIMARY KEY (provider, invoice_id)
);
CREATE INDEX IF NOT EXISTS idx_invoices_open ON invoices(status, created_at);
"""

REFERRAL_WINDOW = 600  # seconds after signup during which a link still counts

_db: aiosqlite.Connection | None = None


# Columns added after the first release; ALTER is the only way in for an
# existing bot.db, since CREATE TABLE IF NOT EXISTS leaves old tables alone.
MIGRATIONS = {
    "users": {
        "ref_by": "INTEGER",
        "ref_credited": "INTEGER NOT NULL DEFAULT 0",
        "earned": "INTEGER NOT NULL DEFAULT 0",
        "accepted": "INTEGER NOT NULL DEFAULT 0",
        "source": "TEXT",  # campaign code the user arrived with
        "subscribed": "INTEGER NOT NULL DEFAULT 0",  # passed the channel gate
        "last_seen": "INTEGER NOT NULL DEFAULT 0",
        "last_push": "INTEGER NOT NULL DEFAULT 0",
        "free_views": "INTEGER NOT NULL DEFAULT 0",  # circles owed, not coins
        "last_promo": "INTEGER NOT NULL DEFAULT 0",  # when a promo post last came
        # A cheque opened before the gate waits here until the gate is passed.
        "pending_cheque": "TEXT NOT NULL DEFAULT ''",
        # Who this is, for the panel: an id alone tells a moderator nothing.
        # Filled in from every update, so it stays current on its own.
        "name": "TEXT NOT NULL DEFAULT ''",
        "username": "TEXT NOT NULL DEFAULT ''",
        # Paid subscription: which tier, until when, and how much of today's
        # free allowance is spent. An empty tier is everyone who never bought.
        "tier": "TEXT NOT NULL DEFAULT ''",
        "tier_until": "INTEGER NOT NULL DEFAULT 0",
        "tier_day": "INTEGER NOT NULL DEFAULT 0",  # which day the count is for
        "tier_views": "INTEGER NOT NULL DEFAULT 0",
    },
    "profiles": {
        "photo_unique_id": "TEXT",  # tells a re-sent photo from a new one
    },
    "gate_channels": {
        "kind": "TEXT NOT NULL DEFAULT 'channel'",  # everything before was a channel
        # A title typed by hand is not overwritten by the one Telegram reports.
        "titled": "INTEGER NOT NULL DEFAULT 0",
        # Same for a link: a private channel or a tracked invite is the admin's
        # to set, and Telegram's own link must not win over it.
        "linked": "INTEGER NOT NULL DEFAULT 0",
    },
    "campaigns": {
        "spend": "INTEGER NOT NULL DEFAULT 0",  # ad spend in minor units
        "token": "TEXT",  # lets the buyer of the ad watch their own link
    },
    "circles": {
        "likes": "INTEGER NOT NULL DEFAULT 0",
        "dislikes": "INTEGER NOT NULL DEFAULT 0",
        "earned": "INTEGER NOT NULL DEFAULT 0",
        # Set the first time a circle is approved, so a moderator who changes
        # their mind twice cannot pay the upload reward twice.
        "rewarded": "INTEGER NOT NULL DEFAULT 0",
    },
    "reports": {
        "reason": "TEXT NOT NULL DEFAULT ''",  # complaints filed before stay blank
    },
    "profile_reports": {
        "reason": "TEXT NOT NULL DEFAULT ''",
    },
    "payments": {
        "provider": "TEXT NOT NULL DEFAULT 'stars'",  # everything before was stars
        "asset": "TEXT NOT NULL DEFAULT ''",
        "amount": "TEXT NOT NULL DEFAULT ''",
    },
}


async def connect() -> None:
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    # SQLite's own lower() only folds ASCII, so «Аня» would never match «аня».
    await _db.create_function(
        "lower_u", 1, lambda value: value.lower() if value else value, deterministic=True
    )
    await _db.executescript(SCHEMA)
    await _migrate()
    await _db.commit()


async def _migrate() -> None:
    for table, columns in MIGRATIONS.items():
        async with _db.execute(f"PRAGMA table_info({table})") as cur:
            existing = {row["name"] for row in await cur.fetchall()}
        for name, spec in columns.items():
            if name not in existing:
                await _db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


async def close() -> None:
    if _db is not None:
        await _db.close()


def conn() -> aiosqlite.Connection:
    assert _db is not None, "db.connect() was never called"
    return _db


# --- users ---------------------------------------------------------------


async def get_user(user_id: int) -> aiosqlite.Row:
    await conn().execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (user_id,))
    await conn().commit()
    async with conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        row = await cur.fetchone()
    assert row is not None
    return row


async def set_pref(user_id: int, pref: str) -> None:
    await conn().execute("UPDATE users SET pref = ? WHERE id = ?", (pref, user_id))
    await conn().commit()


async def ensure_user(user_id: int) -> None:
    """A row must exist before any UPDATE touches a balance."""
    await conn().execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (user_id,))


async def add_coins(user_id: int, amount: int, earned: bool = False) -> None:
    """`earned` marks coins the user made, and only those can be withdrawn."""
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET coins = coins + ?, earned = earned + ? WHERE id = ?",
        (amount, amount if earned else 0, user_id),
    )
    await conn().commit()


async def deduct_clamped(user_id: int, amount: int) -> None:
    """Take coins back (refunds) without pushing the balance below zero."""
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET coins = MAX(0, coins - ?) WHERE id = ?", (amount, user_id)
    )
    await conn().commit()


async def accept_rules(user_id: int) -> bool:
    """True only the first time — the welcome bonus rides on this."""
    await ensure_user(user_id)
    cur = await conn().execute(
        "UPDATE users SET accepted = 1 WHERE id = ? AND accepted = 0", (user_id,)
    )
    await conn().commit()
    return cur.rowcount > 0


async def set_banned(user_id: int, banned: bool) -> None:
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET banned = ? WHERE id = ?", (int(banned), user_id)
    )
    await conn().commit()


async def try_spend(user_id: int, amount: int) -> bool:
    """Deduct only if the balance covers it. Returns False when it does not."""
    await ensure_user(user_id)
    cur = await conn().execute(
        "UPDATE users SET coins = coins - ? WHERE id = ? AND coins >= ?",
        (amount, user_id, amount),
    )
    await conn().commit()
    return cur.rowcount > 0


async def user_row(user_id: int) -> aiosqlite.Row | None:
    """Read-only lookup — unlike get_user() it does not create the row."""
    async with conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
        return await cur.fetchone()


async def find_users(query: str, limit: int = 12) -> list[aiosqlite.Row]:
    """Look someone up the way an admin actually remembers them.

    A username first, because that is what gets written down and forwarded; a
    name second; a bare id last, since it is the least memorable of the three.
    """
    query = query.strip().lstrip("@")
    if not query:
        return []

    if query.isdigit():  # an id is exact, so it wins outright when it matches
        row = await user_row(int(query))
        if row is not None:
            return [row]

    async with conn().execute(
        """
        SELECT *, MIN(rank) AS rank FROM (
            SELECT *, 0 AS rank FROM users
              WHERE username != '' AND lower_u(username) = lower_u(:q)
            UNION ALL
            SELECT *, 1 AS rank FROM users
              WHERE username != '' AND lower_u(username) LIKE lower_u(:q) || '%'
            UNION ALL
            SELECT *, 2 AS rank FROM users
              WHERE name != '' AND lower_u(name) LIKE '%' || lower_u(:q) || '%'
        )
        GROUP BY id ORDER BY rank, last_seen DESC LIMIT :limit
        """,
        {"q": query, "limit": limit},
    ) as cur:
        return list(await cur.fetchall())


async def touch_identity(user_id: int, name: str, username: str) -> None:
    """Keep the panel's idea of who this is in step with Telegram."""
    await conn().execute(
        "UPDATE users SET name = ?, username = ? WHERE id = ?",
        (name[:64], username or "", user_id),
    )
    await conn().commit()


async def backfill_identity() -> int:
    """Authors already told us their username once — use it until they return."""
    cur = await conn().execute(
        "UPDATE users SET username = COALESCE((SELECT p.username FROM profiles p"
        " WHERE p.user_id = users.id), '') WHERE username = ''"
        " AND EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = users.id"
        "             AND p.username IS NOT NULL AND p.username != '')"
    )
    await conn().commit()
    return cur.rowcount


async def touch_seen(user_id: int, stale: int = 300) -> None:
    """Activity stamp for the reminder job; skipped unless it is already old."""
    await conn().execute(
        "UPDATE users SET last_seen = strftime('%s','now') WHERE id = ?"
        " AND last_seen < strftime('%s','now') - ?",
        (user_id, stale),
    )
    await conn().commit()


# last_seen only started being stamped when the column was added, so a row from
# before that — or from someone who never came back after accepting — carries a
# zero. Reading that as «never idle» hid exactly the people a reminder is for,
# which is why registration time stands in for it.
_LAST_SEEN = "COALESCE(NULLIF(last_seen, 0), created_at)"


async def idle_users(idle: int, cooldown: int, limit: int) -> list[int]:
    """Who went quiet long enough, and was not nudged recently."""
    async with conn().execute(
        f"""
        SELECT id FROM users
        WHERE banned = 0 AND accepted = 1
          AND {_LAST_SEEN} < strftime('%s','now') - :idle
          AND last_push < strftime('%s','now') - :cooldown
        ORDER BY RANDOM() LIMIT :limit
        """,
        {"idle": idle, "cooldown": cooldown, "limit": limit},
    ) as cur:
        return [row[0] for row in await cur.fetchall()]


async def push_pool(idle: int, cooldown: int) -> dict:
    """Who is in line for a reminder and who is not — with the reason why."""
    async with conn().execute(
        f"""
        SELECT
          COUNT(*)                                                  AS total,
          COALESCE(SUM(banned = 1), 0)                              AS banned,
          COALESCE(SUM(banned = 0 AND accepted = 0), 0)             AS not_accepted,
          COALESCE(SUM(banned = 0 AND accepted = 1
                       AND {_LAST_SEEN} >= strftime('%s','now') - :idle), 0)
                                                                    AS still_active,
          COALESCE(SUM(banned = 0 AND accepted = 1
                       AND {_LAST_SEEN} < strftime('%s','now') - :idle
                       AND last_push >= strftime('%s','now') - :cooldown), 0)
                                                                    AS cooling,
          COALESCE(SUM(banned = 0 AND accepted = 1
                       AND {_LAST_SEEN} < strftime('%s','now') - :idle
                       AND last_push < strftime('%s','now') - :cooldown), 0)
                                                                    AS ready,
          COALESCE(SUM(last_push > 0), 0)                           AS ever_pushed
        FROM users
        """,
        {"idle": idle, "cooldown": cooldown},
    ) as cur:
        return dict(await cur.fetchone())


async def grant_free_views(user_id: int, count: int) -> None:
    """Circles owed to a user, without touching the reminder's own stamp."""
    await conn().execute(
        "UPDATE users SET free_views = free_views + ? WHERE id = ?",
        (count, user_id),
    )
    await conn().commit()


async def mark_pushed(user_id: int, free_views: int) -> None:
    """Stamp the reminder and hand out its gift.

    The gift replaces whatever the previous reminder left — it does not add to
    it. Someone who ignores the bot for a week comes back with one free circle,
    not with a week's worth of them; only the newest reminder is live.
    """
    await conn().execute(
        "UPDATE users SET last_push = strftime('%s','now'),"
        " free_views = ? WHERE id = ?",
        (free_views, user_id),
    )
    await conn().commit()


# --- paid subscriptions --------------------------------------------------


def msk_day() -> int:
    """Which Moscow day it is — what a daily allowance is counted against."""
    return int(time.time() + MSK_OFFSET) // 86400


def active_tier(user) -> str:
    """The tier in force right now, '' once it has run out.

    Expiry is read, never swept: a background job that clears rows would only
    be another thing to go wrong, and the timestamp already knows the answer.
    """
    if user is None:
        return ""
    keys = user.keys()
    if "tier" not in keys or not user["tier"]:
        return ""
    return user["tier"] if user["tier_until"] > time.time() else ""


async def buy_tier(user_id: int, tier: str, days: int, price: int) -> int | None:
    """Take the coins and start (or extend) the subscription. None when poor.

    Extending the same tier adds days to what is left; switching to another one
    starts from now, because two subscriptions cannot both be in force.
    """
    if not await try_spend(user_id, price):
        return None

    user = await get_user(user_id)
    now = int(time.time())
    same = active_tier(user) == tier
    start = max(now, user["tier_until"]) if same else now
    until = start + days * 86400

    await conn().execute(
        "UPDATE users SET tier = ?, tier_until = ? WHERE id = ?",
        (tier, until, user_id),
    )
    await conn().execute(
        "INSERT INTO tier_sales(user_id, tier, days, price) VALUES (?, ?, ?, ?)",
        (user_id, tier, days, price),
    )
    await conn().commit()
    return until


async def use_tier_view(user_id: int, limit: int) -> bool:
    """Spend one of today's free circles. True while the allowance holds.

    `limit` of 0 means the tier has no ceiling, and nothing is counted at all.
    The day turns at midnight Moscow time — see MSK_OFFSET in config.
    """
    if not limit:
        return True

    today = msk_day()
    cur = await conn().execute(
        """
        UPDATE users
           SET tier_views = CASE WHEN tier_day = :today THEN tier_views + 1 ELSE 1 END,
               tier_day = :today
         WHERE id = :uid
           AND (tier_day != :today OR tier_views < :limit)
        """,
        {"today": today, "uid": user_id, "limit": limit},
    )
    await conn().commit()
    return cur.rowcount > 0


async def refund_tier_view(user_id: int) -> None:
    """Hand back a circle from today's allowance that never got delivered."""
    await conn().execute(
        "UPDATE users SET tier_views = tier_views - 1"
        " WHERE id = ? AND tier_day = ? AND tier_views > 0",
        (user_id, msk_day()),
    )
    await conn().commit()


def tier_views_left(user, limit: int) -> int:
    """What is left of today's allowance; `limit` back when the day has turned."""
    if not limit:
        return 0
    if "tier_day" not in user.keys():
        return limit
    if user["tier_day"] != msk_day():
        return limit
    return max(0, limit - user["tier_views"])


async def tier_stats() -> dict:
    """Who is subscribed right now, and what the tiers have taken in."""
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM users WHERE tier != ''
             AND tier_until > strftime('%s','now'))                 AS active,
          (SELECT COUNT(*) FROM tier_sales)                         AS sales,
          (SELECT COALESCE(SUM(price), 0) FROM tier_sales)          AS coins,
          (SELECT COALESCE(SUM(price), 0) FROM tier_sales
             WHERE ts > strftime('%s','now') - 86400)               AS coins_today
        """
    ) as cur:
        return dict(await cur.fetchone())


async def tiers_in_force() -> list[aiosqlite.Row]:
    """Active subscriptions grouped by tier, for the panel."""
    async with conn().execute(
        """
        SELECT tier, COUNT(*) AS people FROM users
        WHERE tier != '' AND tier_until > strftime('%s','now')
        GROUP BY tier
        """
    ) as cur:
        return list(await cur.fetchall())


async def use_free_view(user_id: int) -> bool:
    """Spend one owed circle. False when there is none."""
    cur = await conn().execute(
        "UPDATE users SET free_views = free_views - 1"
        " WHERE id = ? AND free_views > 0",
        (user_id,),
    )
    await conn().commit()
    return cur.rowcount > 0


# --- referrals -----------------------------------------------------------


async def set_referrer(user_id: int, referrer_id: int) -> bool:
    """Attach an inviter — only to a user who has none and never earned yet.

    Whoever came first keeps the invite: the WHERE clause makes a second /start
    with somebody else's link a no-op.
    """
    if user_id == referrer_id:
        return False
    await ensure_user(user_id)
    await ensure_user(referrer_id)
    cur = await conn().execute(
        "UPDATE users SET ref_by = ? WHERE id = ? AND ref_by IS NULL"
        " AND ref_credited = 0"
        # Only a freshly created account counts, otherwise an old user could be
        # walked through somebody's link to farm the reward.
        " AND created_at > strftime('%s','now') - ?",
        (referrer_id, user_id, REFERRAL_WINDOW),
    )
    await conn().commit()
    return cur.rowcount > 0


async def take_referral(user_id: int) -> int | None:
    """Claim the reward for this user once, returning whom to pay."""
    cur = await conn().execute(
        "UPDATE users SET ref_credited = 1 WHERE id = ? AND ref_by IS NOT NULL"
        " AND ref_credited = 0",
        (user_id,),
    )
    await conn().commit()
    if cur.rowcount == 0:
        return None
    async with conn().execute(
        "SELECT ref_by FROM users WHERE id = ?", (user_id,)
    ) as inner:
        row = await inner.fetchone()
    return row["ref_by"] if row else None


async def referral_counts(user_id: int) -> tuple[int, int]:
    """(invited and confirmed, invited but not through the gate yet)"""
    async with conn().execute(
        "SELECT SUM(ref_credited = 1) AS done, SUM(ref_credited = 0) AS waiting"
        " FROM users WHERE ref_by = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["done"] or 0, row["waiting"] or 0


# Everything below counts by the invited person's own created_at: the moment a
# referral is credited is not stored, and their arrival is what an admin means
# by «за сутки» anyway.
_INVITED = "ref_by IS NOT NULL AND ref_by != 0"
# Same, for the queries that join the referrer's own row in as «r».
_INVITED_U = "u.ref_by IS NOT NULL AND u.ref_by != 0"


async def referral_overview() -> dict:
    """Every number the referral screen shows, in one pass over the table."""
    async with conn().execute(
        f"""
        SELECT
          COUNT(*)                                             AS invited,
          COALESCE(SUM(ref_credited), 0)                       AS confirmed,
          COALESCE(SUM(ref_credited = 0), 0)                   AS waiting,
          COALESCE(SUM(accepted), 0)                           AS accepted,
          COALESCE(SUM(banned), 0)                             AS banned,
          COALESCE(SUM(last_seen > strftime('%s','now') - 604800), 0) AS alive,
          COALESCE(SUM(coins), 0)                              AS coins,
          COUNT(DISTINCT ref_by)                               AS referrers
        FROM users WHERE {_INVITED}
        """
    ) as cur:
        row = dict(await cur.fetchone())

    # How many of those invited ever paid for anything.
    async with conn().execute(
        f"SELECT COUNT(DISTINCT p.user_id) FROM payments p"
        f" JOIN users u ON u.id = p.user_id WHERE {_INVITED} AND p.refunded = 0"
    ) as cur:
        row["payers"] = (await cur.fetchone())[0]

    for name, window in (("day", 86400), ("week", 604800), ("month", 2592000)):
        async with conn().execute(
            f"""
            SELECT COUNT(*) AS invited, COALESCE(SUM(ref_credited), 0) AS confirmed
            FROM users
            WHERE {_INVITED} AND created_at > strftime('%s','now') - ?
            """,
            (window,),
        ) as cur:
            part = await cur.fetchone()
        row[f"{name}_invited"], row[f"{name}_confirmed"] = part[0], part[1]

    # How the referrers themselves are distributed — a handful of big ones or
    # a long tail changes what an admin does next.
    async with conn().execute(
        f"""
        SELECT
          COALESCE(SUM(done >= 1), 0)  AS with_one,
          COALESCE(SUM(done >= 3), 0)  AS with_three,
          COALESCE(SUM(done >= 10), 0) AS with_ten,
          COALESCE(MAX(done), 0)       AS best
        FROM (SELECT ref_by, SUM(ref_credited) AS done FROM users
              WHERE {_INVITED} GROUP BY ref_by)
        """
    ) as cur:
        row.update(dict(await cur.fetchone()))
    return row


async def top_referrers(
    limit: int = 10, offset: int = 0, window: int = 0, order: str = "confirmed"
) -> list[aiosqlite.Row]:
    """Who brought the most — with who they are, not just their id."""
    clause = "AND u.created_at > strftime('%s','now') - :window" if window else ""
    sort = {
        "confirmed": "confirmed DESC, invited DESC",
        "invited": "invited DESC, confirmed DESC",
        "alive": "alive DESC, confirmed DESC",
    }.get(order, "confirmed DESC, invited DESC")
    async with conn().execute(
        f"""
        SELECT u.ref_by AS user_id, r.name AS name, r.username AS username,
               COUNT(*)                         AS invited,
               COALESCE(SUM(u.ref_credited), 0) AS confirmed,
               COALESCE(SUM(u.banned), 0)       AS banned,
               COALESCE(SUM(u.last_seen > strftime('%s','now') - 604800), 0) AS alive,
               MAX(u.created_at)                AS last_at
        FROM users u LEFT JOIN users r ON r.id = u.ref_by
        WHERE {_INVITED_U} {clause}
        GROUP BY u.ref_by
        ORDER BY {sort} LIMIT :limit OFFSET :offset
        """,
        {"limit": limit, "offset": offset, "window": window},
    ) as cur:
        return list(await cur.fetchall())


async def count_referrers(window: int = 0) -> int:
    clause = "AND created_at > strftime('%s','now') - :window" if window else ""
    async with conn().execute(
        f"SELECT COUNT(DISTINCT ref_by) FROM users WHERE {_INVITED} {clause}",
        {"window": window},
    ) as cur:
        return (await cur.fetchone())[0]


async def suspect_referrers(limit: int = 10) -> list[aiosqlite.Row]:
    """Volume without result: many invited, few of them alive or confirmed.

    This is what farming looks like from the outside — the numbers an admin
    would otherwise have to spot by scrolling the top.
    """
    async with conn().execute(
        f"""
        SELECT u.ref_by AS user_id, r.name AS name, r.username AS username,
               COUNT(*)                         AS invited,
               COALESCE(SUM(u.ref_credited), 0) AS confirmed,
               COALESCE(SUM(u.banned), 0)       AS banned,
               COALESCE(SUM(u.accepted), 0)     AS accepted,
               COALESCE(SUM(u.last_seen > strftime('%s','now') - 604800), 0) AS alive
        FROM users u LEFT JOIN users r ON r.id = u.ref_by
        WHERE {_INVITED_U}
        GROUP BY u.ref_by
        HAVING invited >= 5 AND (alive * 100 / invited) < 25
        ORDER BY invited DESC LIMIT ?
        """,
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def referrer_detail(user_id: int) -> dict:
    """One referrer, in the same terms as the overview."""
    async with conn().execute(
        f"""
        SELECT
          COUNT(*)                           AS invited,
          COALESCE(SUM(ref_credited), 0)     AS confirmed,
          COALESCE(SUM(accepted), 0)         AS accepted,
          COALESCE(SUM(banned), 0)           AS banned,
          COALESCE(SUM(last_seen > strftime('%s','now') - 604800), 0) AS alive,
          COALESCE(SUM(created_at > strftime('%s','now') - 86400), 0) AS day,
          COALESCE(SUM(created_at > strftime('%s','now') - 604800), 0) AS week,
          COALESCE(MIN(created_at), 0)       AS first_at,
          COALESCE(MAX(created_at), 0)       AS last_at
        FROM users WHERE ref_by = ?
        """,
        (user_id,),
    ) as cur:
        return dict(await cur.fetchone())


async def referred_users(user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT id, name, username, created_at, ref_credited, accepted, banned,"
        " last_seen, coins FROM users WHERE ref_by = ?"
        " ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ) as cur:
        return list(await cur.fetchall())


async def referral_totals() -> tuple[int, int]:
    async with conn().execute(
        "SELECT COUNT(*) AS invited,"
        " COALESCE(SUM(ref_credited), 0) AS confirmed"
        " FROM users WHERE ref_by IS NOT NULL"
    ) as cur:
        row = await cur.fetchone()
    return row["invited"], row["confirmed"]


# --- ad campaigns --------------------------------------------------------


async def create_campaign(code: str, title: str = "") -> bool:
    try:
        await conn().execute(
            "INSERT INTO campaigns(code, title, token) VALUES (?, ?, ?)",
            (code, title, secrets.token_hex(4)),
        )
    except aiosqlite.IntegrityError:
        return False
    await conn().commit()
    return True


async def campaign_token(code: str) -> str | None:
    """Mints one for links that predate tokens, so every link has a watcher."""
    async with conn().execute(
        "SELECT token FROM campaigns WHERE code = ?", (code,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    if row["token"]:
        return row["token"]

    token = secrets.token_hex(4)
    await conn().execute(
        "UPDATE campaigns SET token = ? WHERE code = ?", (token, code)
    )
    await conn().commit()
    return token


async def new_campaign_token(code: str) -> str | None:
    """Rotate it — the old command stops working immediately."""
    token = secrets.token_hex(4)
    cur = await conn().execute(
        "UPDATE campaigns SET token = ? WHERE code = ?", (token, code)
    )
    await conn().commit()
    return token if cur.rowcount else None


async def campaign_by_token(token: str) -> str | None:
    async with conn().execute(
        "SELECT code FROM campaigns WHERE token = ?", (token,)
    ) as cur:
        row = await cur.fetchone()
    return row["code"] if row else None


async def get_campaign(code: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM campaigns WHERE code = ?", (code,)
    ) as cur:
        return await cur.fetchone()


async def touch_campaign(code: str, user_id: int) -> bool:
    """Count the click and stamp the user, but only the first link they used.

    A code nobody created is ignored rather than turned into a campaign: with
    three kinds of link sharing ?start=, auto-creation meant every stray or
    mistyped payload showed up in the panel as an ad link of its own.
    """
    if await get_campaign(code) is None:
        return False
    await conn().execute(
        "UPDATE campaigns SET hits = hits + 1 WHERE code = ?", (code,)
    )
    await conn().execute(
        "INSERT INTO campaign_hits(code, user_id) VALUES (?, ?)", (code, user_id)
    )
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET source = ? WHERE id = ? AND source IS NULL",
        (code, user_id),
    )
    await conn().commit()
    return True


async def set_campaign_spend(code: str, spend: int) -> None:
    """Spend is kept in minor units — kopecks, cents — never in floats."""
    await conn().execute(
        "UPDATE campaigns SET spend = ? WHERE code = ?", (spend, code)
    )
    await conn().commit()


async def mark_subscribed(user_id: int) -> bool:
    """True the first time only — the subscription bonus rides on this."""
    await ensure_user(user_id)  # the row may not exist yet on a first touch
    cur = await conn().execute(
        "UPDATE users SET subscribed = 1 WHERE id = ? AND subscribed = 0", (user_id,)
    )
    await conn().commit()
    return cur.rowcount > 0


async def delete_campaign(code: str) -> bool:
    """The link stops being tracked; users keep their stamp for history."""
    cur = await conn().execute("DELETE FROM campaigns WHERE code = ?", (code,))
    await conn().commit()
    return cur.rowcount > 0


async def campaigns() -> list[aiosqlite.Row]:
    async with conn().execute(
        """
        SELECT c.*, (SELECT COUNT(*) FROM users u WHERE u.source = c.code) AS users
        FROM campaigns c ORDER BY c.hits DESC, c.created_at
        """
    ) as cur:
        return list(await cur.fetchall())


async def campaign_stats(code: str, window: int = 0) -> dict | None:
    """Funnel for one link. `window` in seconds limits it to a recent slice.

    A slice counts people who arrived inside the window, so it answers "is this
    link still working", not "what did the old crowd do lately".
    """
    async with conn().execute(
        "SELECT * FROM campaigns WHERE code = ?", (code,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None

    since = 0 if not window else int(time.time()) - window
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM campaign_hits WHERE code = :c AND ts >= :s)  AS hits,
          (SELECT COUNT(*) FROM users
             WHERE source = :c AND created_at >= :s)                         AS users,
          (SELECT COUNT(*) FROM users
             WHERE source = :c AND created_at >= :s AND subscribed = 1)      AS subscribed,
          (SELECT COUNT(*) FROM users
             WHERE source = :c AND created_at >= :s AND accepted = 1)        AS accepted,
          (SELECT COUNT(*) FROM users
             WHERE source = :c AND created_at >= :s AND banned = 1)          AS banned,
          (SELECT COUNT(*) FROM profiles p JOIN users u ON u.id = p.user_id
             WHERE u.source = :c AND u.created_at >= :s
               AND p.status = 'approved')                                    AS profiles,
          (SELECT COUNT(*) FROM circles ci JOIN users u ON u.id = ci.uploader_id
             WHERE u.source = :c AND u.created_at >= :s
               AND ci.status = 'approved')                                   AS circles,
          (SELECT COUNT(*) FROM views v JOIN users u ON u.id = v.user_id
             WHERE u.source = :c AND u.created_at >= :s)                     AS views,
          (SELECT COUNT(DISTINCT pay.user_id) FROM payments pay
             JOIN users u ON u.id = pay.user_id
             WHERE u.source = :c AND pay.refunded = 0 AND pay.ts >= :s)      AS payers,
          (SELECT COALESCE(SUM(pay.stars),0) FROM payments pay
             JOIN users u ON u.id = pay.user_id
             WHERE u.source = :c AND pay.refunded = 0 AND pay.ts >= :s)      AS stars,
          (SELECT COALESCE(SUM(pur.price),0) FROM purchases pur
             JOIN users u ON u.id = pur.buyer_id
             WHERE u.source = :c AND pur.ts >= :s)                           AS spent_coins
        """,
        {"c": code, "s": since},
    ) as cur:
        stats = dict(await cur.fetchone())

    stats.update(code=row["code"], title=row["title"], spend=row["spend"])
    return stats


# --- circles -------------------------------------------------------------


async def add_circle(
    file_id: str,
    file_unique_id: str,
    uploader_id: int,
    gender: str,
    duration: int,
    status: str = "pending",
) -> int | None:
    """None means this exact video note is already in the base.

    uploader_id 0 is the house: circles an admin bulk-loaded, owned by nobody,
    so they are never hidden from anyone and earn no reward.
    """
    if uploader_id:
        await ensure_user(uploader_id)
    try:
        cur = await conn().execute(
            "INSERT INTO circles(file_id, file_unique_id, uploader_id, gender,"
            " duration, status) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, file_unique_id, uploader_id, gender, duration, status),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn().commit()
    return cur.lastrowid


async def set_admin_msg(circle_id: int, msg_id: int) -> None:
    await conn().execute(
        "UPDATE circles SET admin_msg_id = ? WHERE id = ?", (msg_id, circle_id)
    )
    await conn().commit()


async def get_circle(circle_id: int) -> aiosqlite.Row | None:
    async with conn().execute("SELECT * FROM circles WHERE id = ?", (circle_id,)) as cur:
        return await cur.fetchone()


async def circle_by_unique(file_unique_id: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM circles WHERE file_unique_id = ?", (file_unique_id,)
    ) as cur:
        return await cur.fetchone()


async def decide_circle(
    circle_id: int, status: str, admin_id: int
) -> tuple[bool, bool]:
    """Set a verdict, first one or a changed mind alike.

    Returns (the status moved, the upload reward is due now) — the reward is
    remembered on the circle, so approving it a second time cannot pay twice.
    """
    async with conn().execute(
        "SELECT status, rewarded FROM circles WHERE id = ?", (circle_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None or row["status"] == status:
        return False, False

    pay = status == "approved" and not row["rewarded"]
    await conn().execute(
        "UPDATE circles SET status = ?, reviewed_by = ?,"
        " rewarded = CASE WHEN ? THEN 1 ELSE rewarded END WHERE id = ?",
        (status, admin_id, int(pay), circle_id),
    )
    await conn().commit()
    return True, pay


async def set_status(circle_id: int, status: str) -> None:
    """Force a status — used by report handling, where the circle is not pending."""
    await conn().execute(
        "UPDATE circles SET status = ? WHERE id = ?", (status, circle_id)
    )
    await conn().commit()


async def pending_count(user_id: int) -> int:
    async with conn().execute(
        "SELECT COUNT(*) FROM circles WHERE uploader_id = ? AND status = 'pending'",
        (user_id,),
    ) as cur:
        return (await cur.fetchone())[0]


PICK_CANDIDATES = 40  # drawn at random, then weighted — SQLite has no log()


async def pick_circle(
    user_id: int, pref: str, like_boost: int = 0
) -> aiosqlite.Row | None:
    """One unseen circle, favouring the ones people liked.

    A liked circle is shown to more viewers, which is the whole reward for
    making a good one: reach, not coins.
    """
    gender_clause = "" if pref == "any" else "AND gender = :pref"
    async with conn().execute(
        f"""
        SELECT * FROM circles
        WHERE status = 'approved'
          AND uploader_id != :uid
          {gender_clause}
          AND id NOT IN (SELECT circle_id FROM views WHERE user_id = :uid)
        ORDER BY RANDOM() LIMIT :limit
        """,
        {"uid": user_id, "pref": pref, "limit": PICK_CANDIDATES},
    ) as cur:
        rows = list(await cur.fetchall())

    if not rows:
        return None
    if not like_boost:
        return rows[0]

    weights = [1 + max(0, r["likes"] - r["dislikes"]) * like_boost for r in rows]
    return random.choices(rows, weights=weights, k=1)[0]


async def mark_viewed(user_id: int, circle_id: int) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO views(user_id, circle_id) VALUES (?, ?)",
        (user_id, circle_id),
    )
    await conn().execute(
        "UPDATE circles SET views = views + 1 WHERE id = ?", (circle_id,)
    )
    await conn().commit()


async def has_viewed(user_id: int, circle_id: int) -> bool:
    async with conn().execute(
        "SELECT 1 FROM views WHERE user_id = ? AND circle_id = ?",
        (user_id, circle_id),
    ) as cur:
        return await cur.fetchone() is not None


async def user_stats(user_id: int) -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM views WHERE user_id = :uid)                          AS watched,
          (SELECT COUNT(*) FROM circles WHERE uploader_id = :uid AND status='approved') AS approved,
          (SELECT COUNT(*) FROM circles WHERE uploader_id = :uid AND status='pending')  AS pending,
          (SELECT COUNT(*) FROM circles WHERE uploader_id = :uid AND status='rejected') AS rejected
        """,
        {"uid": user_id},
    ) as cur:
        return dict(await cur.fetchone())


async def global_stats() -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM users)                                  AS users,
          (SELECT COUNT(*) FROM circles WHERE status='approved')        AS approved,
          (SELECT COUNT(*) FROM circles WHERE status='pending')         AS pending,
          (SELECT COUNT(*) FROM views)                                  AS views,
          (SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0) AS stars
        """
    ) as cur:
        return dict(await cur.fetchone())


async def next_pending() -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM circles WHERE status = 'pending' ORDER BY id LIMIT 1"
    ) as cur:
        return await cur.fetchone()


async def delete_circle(circle_id: int) -> bool:
    """Everything hanging off the circle goes too, or the counters lie."""
    cur = await conn().execute("DELETE FROM circles WHERE id = ?", (circle_id,))
    await conn().execute("DELETE FROM views WHERE circle_id = ?", (circle_id,))
    await conn().execute("DELETE FROM reactions WHERE circle_id = ?", (circle_id,))
    await conn().execute("DELETE FROM reports WHERE circle_id = ?", (circle_id,))
    await conn().commit()
    return cur.rowcount > 0


async def wipe_circles() -> int:
    """Drop every circle and every view. Balances and payments stay untouched.

    The AUTOINCREMENT counter is reset too, so numbering starts from #1 again.
    """
    total = await total_circles()
    await conn().execute("DELETE FROM circles")
    await conn().execute("DELETE FROM views")
    await conn().execute("DELETE FROM reactions")
    await conn().execute("DELETE FROM reports")
    await conn().execute("DELETE FROM sqlite_sequence WHERE name = 'circles'")
    await conn().commit()
    return total


async def wipe_house_circles() -> int:
    """Remove the seed circles the admin bulk-loaded, leaving users' own alone."""
    async with conn().execute(
        "SELECT COUNT(*) FROM circles WHERE uploader_id = 0"
    ) as cur:
        total = (await cur.fetchone())[0]
    await conn().execute(
        "DELETE FROM views WHERE circle_id IN"
        " (SELECT id FROM circles WHERE uploader_id = 0)"
    )
    await conn().execute(
        "DELETE FROM reactions WHERE circle_id IN"
        " (SELECT id FROM circles WHERE uploader_id = 0)"
    )
    await conn().execute(
        "DELETE FROM reports WHERE circle_id IN"
        " (SELECT id FROM circles WHERE uploader_id = 0)"
    )
    await conn().execute("DELETE FROM circles WHERE uploader_id = 0")
    await conn().commit()
    return total


async def house_circles() -> int:
    async with conn().execute(
        "SELECT COUNT(*) FROM circles WHERE uploader_id = 0"
    ) as cur:
        return (await cur.fetchone())[0]


async def total_circles() -> int:
    """Every circle ever uploaded — that is the number shown to uploaders."""
    async with conn().execute("SELECT COUNT(*) FROM circles") as cur:
        return (await cur.fetchone())[0]


async def top_uploaders(limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        """
        SELECT uploader_id, COUNT(*) AS total,
               SUM(status = 'approved') AS approved
        FROM circles WHERE uploader_id != 0
        GROUP BY uploader_id ORDER BY approved DESC, total DESC LIMIT ?
        """,
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def all_user_ids() -> list[int]:
    async with conn().execute(
        "SELECT id FROM users WHERE banned = 0 ORDER BY id"
    ) as cur:
        return [row[0] for row in await cur.fetchall()]


# --- sweeping out users who blocked the bot ------------------------------

# Per-user rows that exist only to stop repeats: without the person they mean
# nothing, and keeping them would hold circles out of somebody else's feed.
_DEAD_JUNK = (
    ("views", "user_id"),
    ("reactions", "user_id"),
    ("profile_views", "buyer_id"),
    ("post_seen", "user_id"),
)

# What is kept on purpose: money and history. A payment or a payout says what
# happened, and rewriting that to tidy a user list is not tidying.
DEAD_KEPT_TABLES = ("payments", "payouts", "purchases", "tier_sales", "campaign_hits")

# Someone the sweep must not take with it unasked — their content or their
# money is still in play, and the row is what ties it to a person.
_PROTECTED = """
    EXISTS (SELECT 1 FROM circles c WHERE c.uploader_id = u.id)
 OR EXISTS (SELECT 1 FROM profiles p WHERE p.user_id = u.id)
 OR EXISTS (SELECT 1 FROM payouts o WHERE o.user_id = u.id AND o.status = 'open')
"""


async def stage_dead(ids: list[int]) -> int:
    """Park the uploaded ids in a temp table. Returns how many were distinct."""
    await conn().execute(
        "CREATE TEMP TABLE IF NOT EXISTS dead_ids (id INTEGER PRIMARY KEY)"
    )
    await conn().execute("DELETE FROM dead_ids")
    await conn().executemany(
        "INSERT OR IGNORE INTO dead_ids(id) VALUES (?)", [(i,) for i in ids]
    )
    await conn().commit()
    async with conn().execute("SELECT COUNT(*) FROM dead_ids") as cur:
        return (await cur.fetchone())[0]


async def dead_preview() -> dict:
    """What the staged list would actually do, before anything is deleted."""
    async with conn().execute(
        f"""
        SELECT
          (SELECT COUNT(*) FROM dead_ids)                              AS listed,
          (SELECT COUNT(*) FROM users u JOIN dead_ids d ON d.id = u.id) AS found,
          (SELECT COUNT(*) FROM users u JOIN dead_ids d ON d.id = u.id
             WHERE {_PROTECTED})                                       AS keepers,
          (SELECT COALESCE(SUM(u.coins), 0) FROM users u
             JOIN dead_ids d ON d.id = u.id)                           AS coins,
          (SELECT COUNT(*) FROM users u JOIN dead_ids d ON d.id = u.id
             WHERE u.tier != '' AND u.tier_until > strftime('%s','now')) AS subs
        """
    ) as cur:
        return dict(await cur.fetchone())


async def sweep_dead(keep_authors: bool = True) -> dict:
    """Delete the staged users. Returns what went and what was left alone.

    Authors and anyone with an open payout are held back by default: their
    circles, profile or money outlive the account, and an id that no longer has
    a row behind it is how «автор без анкеты» happens all over the panel.
    """
    guard = f"AND NOT ({_PROTECTED})" if keep_authors else ""
    # Resolved once, so the junk sweep and the delete cannot disagree about who.
    async with conn().execute(
        f"SELECT u.id FROM users u WHERE u.id IN (SELECT id FROM dead_ids) {guard}"
    ) as cur:
        doomed = [row[0] for row in await cur.fetchall()]
    if not doomed:
        return {"deleted": 0, "kept": (await dead_preview())["found"]}

    await conn().execute("CREATE TEMP TABLE IF NOT EXISTS doomed_ids (id INTEGER PRIMARY KEY)")
    await conn().execute("DELETE FROM doomed_ids")
    await conn().executemany(
        "INSERT OR IGNORE INTO doomed_ids(id) VALUES (?)", [(i,) for i in doomed]
    )

    for table, column in _DEAD_JUNK:
        await conn().execute(
            f"DELETE FROM {table} WHERE {column} IN (SELECT id FROM doomed_ids)"
        )
    if not keep_authors:
        # Taking an author out means taking their shop window with them, or the
        # feed would keep selling access to somebody who cannot answer.
        await conn().execute(
            "DELETE FROM profiles WHERE user_id IN (SELECT id FROM doomed_ids)"
        )
        await conn().execute(
            "DELETE FROM profile_backup WHERE user_id IN (SELECT id FROM doomed_ids)"
        )
        await conn().execute(
            "UPDATE circles SET status = 'rejected'"
            " WHERE uploader_id IN (SELECT id FROM doomed_ids)"
        )
    # Their referrals point at a row that is about to stop existing.
    await conn().execute(
        "UPDATE users SET ref_by = NULL WHERE ref_by IN (SELECT id FROM doomed_ids)"
    )
    await conn().execute("DELETE FROM users WHERE id IN (SELECT id FROM doomed_ids)")
    await conn().execute("DELETE FROM doomed_ids")
    await conn().commit()

    return {"deleted": len(doomed), "kept": (await dead_preview())["found"]}


async def dashboard() -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM users)                                        AS users,
          (SELECT COUNT(*) FROM users WHERE banned = 1)                       AS banned,
          (SELECT COUNT(*) FROM users
             WHERE created_at > strftime('%s','now') - 86400)                 AS users_today,
          (SELECT COALESCE(SUM(coins),0) FROM users)                          AS coins,
          (SELECT COUNT(*) FROM circles)                                      AS circles,
          (SELECT COUNT(*) FROM circles WHERE status='approved')              AS approved,
          (SELECT COUNT(*) FROM circles WHERE status='pending')               AS pending,
          (SELECT COUNT(*) FROM circles WHERE status='rejected')              AS rejected,
          (SELECT COUNT(*) FROM circles WHERE status='approved' AND gender='f') AS female,
          (SELECT COUNT(*) FROM circles WHERE status='approved' AND gender='m') AS male,
          (SELECT COUNT(*) FROM views)                                        AS views,
          (SELECT COUNT(*) FROM views
             WHERE ts > strftime('%s','now') - 86400)                         AS views_today,
          (SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0)      AS stars,
          (SELECT COUNT(*) FROM payments WHERE refunded=0)                    AS payments
        """
    ) as cur:
        return dict(await cur.fetchone())


# --- reactions and reports ----------------------------------------------


async def set_reaction(user_id: int, circle_id: int, value: int) -> tuple[int, int, int, bool]:
    """Vote, or take the vote back by pressing the same button again.

    Returns (my vote now, likes, dislikes, a like was just added) — the last
    flag is what pays the author, so an unvote-revote cannot pay twice.
    """
    async with conn().execute(
        "SELECT value FROM reactions WHERE user_id = ? AND circle_id = ?",
        (user_id, circle_id),
    ) as cur:
        row = await cur.fetchone()
    old = row["value"] if row else 0
    new = 0 if old == value else value

    if new:
        await conn().execute(
            "INSERT INTO reactions(user_id, circle_id, value) VALUES (?, ?, ?)"
            " ON CONFLICT(user_id, circle_id) DO UPDATE SET value = excluded.value,"
            " ts = strftime('%s','now')",
            (user_id, circle_id, new),
        )
    else:
        await conn().execute(
            "DELETE FROM reactions WHERE user_id = ? AND circle_id = ?",
            (user_id, circle_id),
        )

    await conn().execute(
        "UPDATE circles SET likes = likes + ?, dislikes = dislikes + ? WHERE id = ?",
        ((new == 1) - (old == 1), (new == -1) - (old == -1), circle_id),
    )
    await conn().commit()

    async with conn().execute(
        "SELECT likes, dislikes FROM circles WHERE id = ?", (circle_id,)
    ) as cur:
        counts = await cur.fetchone()
    fresh_like = new == 1 and old != 1
    return new, counts["likes"], counts["dislikes"], fresh_like


async def get_reaction(user_id: int, circle_id: int) -> int:
    async with conn().execute(
        "SELECT value FROM reactions WHERE user_id = ? AND circle_id = ?",
        (user_id, circle_id),
    ) as cur:
        row = await cur.fetchone()
    return row["value"] if row else 0


async def add_report(user_id: int, circle_id: int, reason: str = "") -> int | None:
    """None when this user already complained about this circle."""
    try:
        await conn().execute(
            "INSERT INTO reports(user_id, circle_id, reason) VALUES (?, ?, ?)",
            (user_id, circle_id, reason),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn().commit()
    async with conn().execute(
        "SELECT COUNT(*) FROM reports WHERE circle_id = ? AND handled = 0",
        (circle_id,),
    ) as cur:
        return (await cur.fetchone())[0]


async def has_reported(user_id: int, circle_id: int) -> bool:
    """Checked before the reason menu, so nobody picks one for nothing."""
    async with conn().execute(
        "SELECT 1 FROM reports WHERE user_id = ? AND circle_id = ?",
        (user_id, circle_id),
    ) as cur:
        return await cur.fetchone() is not None


async def report_reasons(circle_id: int) -> list[aiosqlite.Row]:
    """What the open complaints about this circle were about, most common first."""
    async with conn().execute(
        """
        SELECT reason, COUNT(*) AS count FROM reports
        WHERE circle_id = ? AND handled = 0
        GROUP BY reason ORDER BY count DESC
        """,
        (circle_id,),
    ) as cur:
        return list(await cur.fetchall())


async def clear_reports(circle_id: int) -> None:
    await conn().execute(
        "UPDATE reports SET handled = 1 WHERE circle_id = ?", (circle_id,)
    )
    await conn().commit()


async def reported_circles(limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        """
        SELECT c.*, COUNT(r.id) AS complaints
        FROM reports r JOIN circles c ON c.id = r.circle_id
        WHERE r.handled = 0
        GROUP BY c.id ORDER BY complaints DESC, c.id LIMIT ?
        """,
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def open_reports() -> int:
    async with conn().execute(
        "SELECT COUNT(DISTINCT circle_id) FROM reports WHERE handled = 0"
    ) as cur:
        return (await cur.fetchone())[0]


async def pay_author(circle_id: int, uploader_id: int, amount: int) -> None:
    """Author earnings are tracked per circle so the profile can show them."""
    if not uploader_id or not amount:
        return
    await add_coins(uploader_id, amount, earned=True)
    await conn().execute(
        "UPDATE circles SET earned = earned + ? WHERE id = ?", (amount, circle_id)
    )
    await conn().commit()


async def author_earnings(user_id: int) -> tuple[int, int, int, int]:
    """(coins earned by circles, total likes, total dislikes, total views)"""
    async with conn().execute(
        "SELECT COALESCE(SUM(earned),0) AS earned, COALESCE(SUM(likes),0) AS likes,"
        " COALESCE(SUM(dislikes),0) AS dislikes,"
        " COALESCE(SUM(views),0) AS views FROM circles WHERE uploader_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["earned"], row["likes"], row["dislikes"], row["views"]


# --- profiles, purchases, payouts ----------------------------------------


async def save_profile(
    user_id: int,
    photo_id: str,
    about: str,
    gender: str,
    price_content: int,
    price_contact: int,
    contact_ok: bool,
    username: str | None,
    photo_unique_id: str | None = None,
) -> None:
    """An edited profile goes back to moderation — the photo changed too."""
    await ensure_user(user_id)
    await conn().execute(
        """
        INSERT INTO profiles(user_id, photo_id, photo_unique_id, about, gender,
                             price_content, price_contact, contact_ok, username,
                             status)
        VALUES (:uid, :photo, :unique, :about, :gender, :content, :contact, :ok,
                :name, 'pending')
        ON CONFLICT(user_id) DO UPDATE SET
            photo_id = excluded.photo_id,
            photo_unique_id = excluded.photo_unique_id,
            about = excluded.about,
            gender = excluded.gender, price_content = excluded.price_content,
            price_contact = excluded.price_contact,
            contact_ok = excluded.contact_ok, username = excluded.username,
            status = 'pending'
        """,
        {
            "uid": user_id,
            "photo": photo_id,
            "unique": photo_unique_id,
            "about": about,
            "gender": gender,
            "content": price_content,
            "contact": price_contact,
            "ok": int(contact_ok),
            "name": username,
        },
    )
    await conn().commit()


async def get_profile(user_id: int) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM profiles WHERE user_id = ?", (user_id,)
    ) as cur:
        return await cur.fetchone()


async def set_profile_admin_msg(user_id: int, msg_id: int) -> None:
    await conn().execute(
        "UPDATE profiles SET admin_msg_id = ? WHERE user_id = ?", (msg_id, user_id)
    )
    await conn().commit()


async def review_profile(user_id: int, status: str) -> bool:
    cur = await conn().execute(
        "UPDATE profiles SET status = ? WHERE user_id = ? AND status = 'pending'",
        (status, user_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def set_profile_status(user_id: int, status: str) -> None:
    await conn().execute(
        "UPDATE profiles SET status = ? WHERE user_id = ?", (status, user_id)
    )
    await conn().commit()


async def has_public_profile(user_id: int) -> bool:
    async with conn().execute(
        "SELECT 1 FROM profiles WHERE user_id = ? AND status = 'approved'", (user_id,)
    ) as cur:
        return await cur.fetchone() is not None


async def set_profile_prices(
    user_id: int, price_content: int, price_contact: int, contact_ok: bool
) -> bool:
    """Change what the author charges, and nothing else.

    A price is a number the author owns — there is nothing in it for a
    moderator to look at, so `status` is deliberately left where it was and the
    profile stays in the feed. The backup moves with it, or turning down some
    later photo edit would quietly roll the price back too.
    """
    cur = await conn().execute(
        "UPDATE profiles SET price_content = ?, price_contact = ?, contact_ok = ?"
        " WHERE user_id = ?",
        (price_content, price_contact, int(contact_ok), user_id),
    )
    await conn().execute(
        "UPDATE profile_backup SET price_content = ?, price_contact = ?,"
        " contact_ok = ? WHERE user_id = ?",
        (price_content, price_contact, int(contact_ok), user_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def backup_profile(user_id: int) -> None:
    """Snapshot an approved profile, so an edit can be undone."""
    await conn().execute(
        """
        INSERT INTO profile_backup(user_id, photo_id, photo_unique_id, about,
                                   gender, price_content, price_contact,
                                   contact_ok, username)
        SELECT user_id, photo_id, photo_unique_id, about, gender, price_content,
               price_contact, contact_ok, username
        FROM profiles WHERE user_id = ?
        ON CONFLICT(user_id) DO UPDATE SET
            photo_id = excluded.photo_id,
            photo_unique_id = excluded.photo_unique_id,
            about = excluded.about, gender = excluded.gender,
            price_content = excluded.price_content,
            price_contact = excluded.price_contact,
            contact_ok = excluded.contact_ok, username = excluded.username
        """,
        (user_id,),
    )
    await conn().commit()


async def restore_profile(user_id: int) -> bool:
    """Put the last approved version back and mark it approved again."""
    async with conn().execute(
        "SELECT * FROM profile_backup WHERE user_id = ?", (user_id,)
    ) as cur:
        old = await cur.fetchone()
    if old is None:
        return False

    await conn().execute(
        """
        UPDATE profiles SET photo_id = :photo, photo_unique_id = :unique,
            about = :about, gender = :gender, price_content = :content,
            price_contact = :contact, contact_ok = :ok, username = :name,
            status = 'approved'
        WHERE user_id = :uid
        """,
        {
            "uid": user_id,
            "photo": old["photo_id"],
            "unique": old["photo_unique_id"],
            "about": old["about"],
            "gender": old["gender"],
            "content": old["price_content"],
            "contact": old["price_contact"],
            "ok": old["contact_ok"],
            "name": old["username"],
        },
    )
    await conn().commit()
    return True


async def drop_profile_backup(user_id: int) -> None:
    await conn().execute(
        "DELETE FROM profile_backup WHERE user_id = ?", (user_id,)
    )
    await conn().commit()


async def next_pending_profile() -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM profiles WHERE status = 'pending' ORDER BY created_at LIMIT 1"
    ) as cur:
        return await cur.fetchone()


async def pending_profiles() -> int:
    async with conn().execute(
        "SELECT COUNT(*) FROM profiles WHERE status = 'pending'"
    ) as cur:
        return (await cur.fetchone())[0]


async def pick_profile(viewer_id: int) -> aiosqlite.Row | None:
    """A profile the viewer has not seen yet, never their own.

    An author without a single approved circle has nothing to sell, so their
    card never reaches the feed.
    """
    async with conn().execute(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM circles c
                 WHERE c.uploader_id = p.user_id AND c.status = 'approved') AS circles
        FROM profiles p
        WHERE p.status = 'approved' AND p.user_id != :uid
          AND p.user_id NOT IN (SELECT author_id FROM profile_views
                                 WHERE buyer_id = :uid)
          AND EXISTS (SELECT 1 FROM circles c
                       WHERE c.uploader_id = p.user_id AND c.status = 'approved')
        ORDER BY RANDOM() LIMIT 1
        """,
        {"uid": viewer_id},
    ) as cur:
        return await cur.fetchone()


async def approved_circles(author_id: int) -> int:
    async with conn().execute(
        "SELECT COUNT(*) FROM circles WHERE uploader_id = ? AND status = 'approved'",
        (author_id,),
    ) as cur:
        return (await cur.fetchone())[0]


async def mark_profile_seen(viewer_id: int, author_id: int) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO profile_views(buyer_id, author_id) VALUES (?, ?)",
        (viewer_id, author_id),
    )
    await conn().execute(
        "UPDATE profiles SET views = views + 1 WHERE user_id = ?", (author_id,)
    )
    await conn().commit()


async def reset_profile_views(viewer_id: int) -> None:
    """Second lap once every profile has been seen."""
    await conn().execute(
        "DELETE FROM profile_views WHERE buyer_id = ?", (viewer_id,)
    )
    await conn().commit()


async def report_profile(user_id: int, author_id: int, reason: str = "") -> int | None:
    """None when this user already complained about this profile."""
    try:
        await conn().execute(
            "INSERT INTO profile_reports(user_id, author_id, reason) VALUES (?, ?, ?)",
            (user_id, author_id, reason),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn().commit()
    async with conn().execute(
        "SELECT COUNT(*) FROM profile_reports WHERE author_id = ? AND handled = 0",
        (author_id,),
    ) as cur:
        return (await cur.fetchone())[0]


async def has_reported_profile(user_id: int, author_id: int) -> bool:
    async with conn().execute(
        "SELECT 1 FROM profile_reports WHERE user_id = ? AND author_id = ?",
        (user_id, author_id),
    ) as cur:
        return await cur.fetchone() is not None


async def profile_report_reasons(author_id: int) -> list[aiosqlite.Row]:
    async with conn().execute(
        """
        SELECT reason, COUNT(*) AS count FROM profile_reports
        WHERE author_id = ? AND handled = 0
        GROUP BY reason ORDER BY count DESC
        """,
        (author_id,),
    ) as cur:
        return list(await cur.fetchall())


async def clear_profile_reports(author_id: int) -> None:
    await conn().execute(
        "UPDATE profile_reports SET handled = 1 WHERE author_id = ?", (author_id,)
    )
    await conn().commit()


async def get_purchase(buyer_id: int, author_id: int, kind: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM purchases WHERE buyer_id = ? AND author_id = ? AND kind = ?",
        (buyer_id, author_id, kind),
    ) as cur:
        return await cur.fetchone()


async def get_user_purchases(buyer_id: int, kind: str) -> list[aiosqlite.Row]:
    """All purchases of a given kind by this buyer."""
    async with conn().execute(
        "SELECT * FROM purchases WHERE buyer_id = ? AND kind = ?",
        (buyer_id, kind),
    ) as cur:
        return await cur.fetchall()


async def buy_access(
    buyer_id: int, author_id: int, kind: str, price: int, share: int
) -> tuple[str, aiosqlite.Row | None]:
    """Charge the buyer, pay the author their share, record the purchase.

    Returns ('already' | 'poor' | 'ok', purchase row). The money only moves on
    'ok', and the frozen circle boundary is taken at that moment.
    """
    existing = await get_purchase(buyer_id, author_id, kind)
    if existing is not None:
        return "already", existing
    if not await try_spend(buyer_id, price):
        return "poor", None

    max_circle_id = await total_circles_max_id() if kind == "content" else 0
    try:
        await conn().execute(
            "INSERT INTO purchases(buyer_id, author_id, kind, price, author_share,"
            " max_circle_id) VALUES (?, ?, ?, ?, ?, ?)",
            (buyer_id, author_id, kind, price, share, max_circle_id),
        )
        await conn().commit()
    except aiosqlite.IntegrityError:  # two taps at once
        await add_coins(buyer_id, price)
        return "already", await get_purchase(buyer_id, author_id, kind)

    await add_coins(author_id, share, earned=True)
    await conn().execute(
        "UPDATE profiles SET sold = sold + 1 WHERE user_id = ?", (author_id,)
    )
    await conn().commit()
    return "ok", await get_purchase(buyer_id, author_id, kind)


async def total_circles_max_id() -> int:
    async with conn().execute("SELECT COALESCE(MAX(id), 0) FROM circles") as cur:
        return (await cur.fetchone())[0]


async def has_content_access(buyer_id: int, author_id: int, circle_id: int) -> bool:
    """Content bought once covers what existed then, not what came later."""
    async with conn().execute(
        "SELECT max_circle_id FROM purchases"
        " WHERE buyer_id = ? AND author_id = ? AND kind = 'content'",
        (buyer_id, author_id),
    ) as cur:
        row = await cur.fetchone()
    return row is not None and circle_id <= row["max_circle_id"]


async def author_circles(author_id: int, max_circle_id: int) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM circles WHERE uploader_id = ? AND status = 'approved'"
        " AND id <= ? ORDER BY id",
        (author_id, max_circle_id),
    ) as cur:
        return list(await cur.fetchall())


async def sales_stats(user_id: int) -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM purchases WHERE author_id = :uid AND kind='content') AS content,
          (SELECT COUNT(*) FROM purchases WHERE author_id = :uid AND kind='contact') AS contact,
          (SELECT COALESCE(SUM(author_share),0) FROM purchases WHERE author_id = :uid) AS income
        """,
        {"uid": user_id},
    ) as cur:
        return dict(await cur.fetchone())


# --- payouts -------------------------------------------------------------


async def withdrawable(user_id: int) -> int:
    """Earned coins minus what is already requested or paid out."""
    async with conn().execute(
        """
        SELECT (SELECT earned FROM users WHERE id = :uid)
             - (SELECT COALESCE(SUM(coins),0) FROM payouts
                 WHERE user_id = :uid AND status IN ('open','paid'))
        """,
        {"uid": user_id},
    ) as cur:
        return max(0, (await cur.fetchone())[0] or 0)


async def create_payout(user_id: int, coins: int, stars: int, details: str) -> int | None:
    """Freezes the coins right away; a rejected request gives them back."""
    if coins > await withdrawable(user_id):
        return None
    if not await try_spend(user_id, coins):
        return None
    cur = await conn().execute(
        "INSERT INTO payouts(user_id, coins, stars, details) VALUES (?, ?, ?, ?)",
        (user_id, coins, stars, details),
    )
    await conn().commit()
    return cur.lastrowid


async def set_payout_admin_msg(payout_id: int, msg_id: int) -> None:
    await conn().execute(
        "UPDATE payouts SET admin_msg_id = ? WHERE id = ?", (msg_id, payout_id)
    )
    await conn().commit()


async def get_payout(payout_id: int) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM payouts WHERE id = ?", (payout_id,)
    ) as cur:
        return await cur.fetchone()


async def close_payout(payout_id: int, status: str) -> aiosqlite.Row | None:
    """Settle an open request once. Rejection returns the frozen coins."""
    cur = await conn().execute(
        "UPDATE payouts SET status = ?, closed_at = strftime('%s','now')"
        " WHERE id = ? AND status = 'open'",
        (status, payout_id),
    )
    await conn().commit()
    if cur.rowcount == 0:
        return None
    payout = await get_payout(payout_id)
    if status == "rejected" and payout is not None:
        # `earned` was never reduced, so give the coins back without touching it.
        await add_coins(payout["user_id"], payout["coins"])
    return payout


async def open_payouts(limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM payouts WHERE status = 'open' ORDER BY id LIMIT ?", (limit,)
    ) as cur:
        return list(await cur.fetchall())


async def payout_totals() -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM payouts WHERE status='open')                  AS open,
          (SELECT COALESCE(SUM(coins),0) FROM payouts WHERE status='open')    AS open_coins,
          (SELECT COALESCE(SUM(stars),0) FROM payouts WHERE status='paid')    AS paid_stars
        """
    ) as cur:
        return dict(await cur.fetchone())


# --- settings ------------------------------------------------------------


async def load_settings() -> dict[str, int]:
    async with conn().execute("SELECT key, value FROM settings") as cur:
        return {row["key"]: row["value"] for row in await cur.fetchall()}


async def load_text_settings() -> dict[str, str]:
    async with conn().execute("SELECT key, value FROM settings_text") as cur:
        return {row["key"]: row["value"] for row in await cur.fetchall()}


async def save_text_setting(key: str, value: str) -> None:
    await conn().execute(
        "INSERT INTO settings_text(key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn().commit()


async def save_setting(key: str, value: int) -> None:
    await conn().execute(
        "INSERT INTO settings(key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn().commit()


# --- custom emoji and texts ----------------------------------------------


async def load_custom_emoji() -> dict[str, dict]:
    """Returns {key: {'emoji_id': str, 'fallback': str, 'description': str}}"""
    async with conn().execute("SELECT * FROM custom_emoji") as cur:
        return {
            row["key"]: {
                "emoji_id": row["emoji_id"],
                "fallback": row["fallback"],
                "description": row["description"],
            }
            for row in await cur.fetchall()
        }


async def save_custom_emoji(key: str, emoji_id: str, fallback: str, description: str = "") -> None:
    await conn().execute(
        "INSERT INTO custom_emoji(key, emoji_id, fallback, description) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET emoji_id = excluded.emoji_id, "
        "fallback = excluded.fallback, description = excluded.description",
        (key, emoji_id, fallback, description),
    )
    await conn().commit()


async def load_custom_texts() -> dict[str, dict]:
    """Returns {key: {'text': str, 'description': str}}"""
    async with conn().execute("SELECT * FROM custom_texts") as cur:
        return {
            row["key"]: {"text": row["text"], "description": row["description"]}
            for row in await cur.fetchall()
        }


async def save_custom_text(key: str, text: str, description: str = "") -> None:
    await conn().execute(
        "INSERT INTO custom_texts(key, text, description) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET text = excluded.text, description = excluded.description",
        (key, text, description),
    )
    await conn().commit()


async def delete_custom_emoji(key: str) -> None:
    await conn().execute("DELETE FROM custom_emoji WHERE key = ?", (key,))
    await conn().commit()


async def delete_custom_text(key: str) -> None:
    await conn().execute("DELETE FROM custom_texts WHERE key = ?", (key,))
    await conn().commit()


async def wipe_custom_texts() -> int:
    cur = await conn().execute("DELETE FROM custom_texts")
    await conn().commit()
    return cur.rowcount


# --- payments ------------------------------------------------------------


async def add_payment(
    charge_id: str,
    user_id: int,
    stars: int,
    coins: int,
    provider: str = "stars",
    asset: str = "",
    amount: str = "",
) -> bool:
    """False when a charge we already credited comes round again.

    Both the button the payer taps and the background poller end up here, so
    this is the one place that decides whether coins are owed.
    """
    try:
        await conn().execute(
            "INSERT INTO payments(charge_id, user_id, stars, coins, provider,"
            " asset, amount) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (charge_id, user_id, stars, coins, provider, asset, amount),
        )
    except aiosqlite.IntegrityError:
        return False
    await conn().commit()
    return True


# --- cheques -------------------------------------------------------------

CHEQUE_REUSE = 600  # seconds an unposted cheque is offered again while typing


async def make_cheque(
    author_id: int, coins: int, total: int, kind: str, min_refs: int
) -> str:
    """The code for this cheque, minting one only when there is none to reuse.

    Every keystroke in the inline field asks for a cheque, so an identical
    request that was never posted and never claimed is handed back instead of
    littering the table with codes nobody will ever see.
    """
    async with conn().execute(
        """
        SELECT code FROM cheques
        WHERE author_id = ? AND coins = ? AND total = ? AND kind = ?
          AND used = 0 AND posted = 0 AND active = 1
          AND created_at > strftime('%s','now') - ?
        ORDER BY created_at DESC LIMIT 1
        """,
        (author_id, coins, total, kind, CHEQUE_REUSE),
    ) as cur:
        row = await cur.fetchone()
    if row:
        return row["code"]

    code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
    await conn().execute(
        "INSERT INTO cheques(code, coins, total, kind, min_refs, author_id)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (code, coins, total, kind, min_refs, author_id),
    )
    await conn().commit()
    return code


async def mark_cheque_posted(code: str) -> None:
    await conn().execute("UPDATE cheques SET posted = 1 WHERE code = ?", (code,))
    await conn().commit()


async def get_cheque(code: str) -> aiosqlite.Row | None:
    async with conn().execute("SELECT * FROM cheques WHERE code = ?", (code,)) as cur:
        return await cur.fetchone()


async def has_claimed(code: str, user_id: int) -> bool:
    async with conn().execute(
        "SELECT 1 FROM cheque_claims WHERE code = ? AND user_id = ?", (code, user_id)
    ) as cur:
        return await cur.fetchone() is not None


async def claim_cheque(code: str, user_id: int) -> bool:
    """Take one activation, or False if there is none left for this person.

    The claim row goes in first — its primary key is what stops one person from
    taking a cheque twice — and the counter is moved with a conditional update,
    so two people racing for the last activation cannot both get it.
    """
    try:
        await conn().execute(
            "INSERT INTO cheque_claims(code, user_id) VALUES (?, ?)", (code, user_id)
        )
    except aiosqlite.IntegrityError:
        return False

    cur = await conn().execute(
        "UPDATE cheques SET used = used + 1 WHERE code = ? AND active = 1"
        " AND used < total",
        (code,),
    )
    if cur.rowcount == 0:  # ran out between the check and here
        await conn().execute(
            "DELETE FROM cheque_claims WHERE code = ? AND user_id = ?", (code, user_id)
        )
        await conn().commit()
        return False
    await conn().commit()
    return True


async def stop_cheque(code: str) -> None:
    await conn().execute("UPDATE cheques SET active = 0 WHERE code = ?", (code,))
    await conn().commit()


async def cheques(limit: int = 20) -> list[aiosqlite.Row]:
    """What was actually posted, newest first — drafts are not interesting."""
    async with conn().execute(
        "SELECT * FROM cheques WHERE posted = 1 OR used > 0"
        " ORDER BY active DESC, created_at DESC LIMIT ?",
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def cheque_totals() -> dict:
    async with conn().execute(
        """
        SELECT
          COALESCE(SUM(active = 1 AND used < total), 0) AS live,
          COALESCE(SUM(used), 0)                        AS claims,
          COALESCE(SUM(used * coins), 0)                AS coins
        FROM cheques WHERE posted = 1 OR used > 0
        """
    ) as cur:
        return dict(await cur.fetchone())


async def drop_stale_cheques() -> int:
    """Codes that were typed in the inline field but never posted."""
    cur = await conn().execute(
        "DELETE FROM cheques WHERE posted = 0 AND used = 0"
        " AND created_at < strftime('%s','now') - 3600"
    )
    await conn().commit()
    return cur.rowcount


async def remember_cheque(user_id: int, code: str) -> None:
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET pending_cheque = ? WHERE id = ?", (code, user_id)
    )
    await conn().commit()


async def take_pending_cheque(user_id: int) -> str:
    """The cheque this person opened before the gate, cleared as it is read."""
    async with conn().execute(
        "SELECT pending_cheque FROM users WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    code = row["pending_cheque"] if row else ""
    if code:
        await conn().execute(
            "UPDATE users SET pending_cheque = '' WHERE id = ?", (user_id,)
        )
        await conn().commit()
    return code


# --- sponsor channels ----------------------------------------------------


async def add_channel(
    chat: str,
    title: str = "",
    link: str = "",
    kind: str = "channel",
    linked: bool = False,
) -> int | None:
    """None when that channel or bot is already on the list."""
    try:
        cur = await conn().execute(
            "INSERT INTO gate_channels(chat, title, link, kind, linked)"
            " VALUES (?, ?, ?, ?, ?)",
            (chat, title, link, kind, int(linked)),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn().commit()
    return cur.lastrowid


# «joined» is everyone ever seen inside; «brought» only those the gate had to
# send there first. The difference is the sponsor's own audience, which we have
# no business billing anyone for.
_CHANNEL_COUNTS = """
       (SELECT COUNT(*) FROM channel_joins j WHERE j.channel_id = c.id)
           AS joined,
       (SELECT COUNT(*) FROM channel_joins j WHERE j.channel_id = c.id
          AND j.ts > strftime('%s','now') - 86400) AS joined_today,
       (SELECT COUNT(*) FROM channel_joins j WHERE j.channel_id = c.id
          AND EXISTS (SELECT 1 FROM channel_asked a
                       WHERE a.channel_id = j.channel_id
                         AND a.user_id = j.user_id)) AS brought,
       (SELECT COUNT(*) FROM channel_joins j WHERE j.channel_id = c.id
          AND j.ts > strftime('%s','now') - 86400
          AND EXISTS (SELECT 1 FROM channel_asked a
                       WHERE a.channel_id = j.channel_id
                         AND a.user_id = j.user_id)) AS brought_today
"""


async def channels(active_only: bool = False) -> list[aiosqlite.Row]:
    """Every sponsor channel with what it brought in — today and in total."""
    where = "WHERE c.active = 1" if active_only else ""
    async with conn().execute(
        f"""
        SELECT c.*, {_CHANNEL_COUNTS}
        FROM gate_channels c {where} ORDER BY c.active DESC, c.id
        """
    ) as cur:
        return list(await cur.fetchall())


async def get_channel(channel_id: int) -> aiosqlite.Row | None:
    """Carries the same join counts as channels(), so cards render the same."""
    async with conn().execute(
        f"""
        SELECT c.*, {_CHANNEL_COUNTS}
        FROM gate_channels c WHERE c.id = ?
        """,
        (channel_id,),
    ) as cur:
        return await cur.fetchone()


async def set_channel_active(channel_id: int, active: bool) -> None:
    await conn().execute(
        "UPDATE gate_channels SET active = ? WHERE id = ?", (int(active), channel_id)
    )
    await conn().commit()


async def set_channel_meta(channel_id: int, title: str, link: str) -> None:
    """Refresh from Telegram — but never over a name or link the admin chose."""
    await conn().execute(
        "UPDATE gate_channels SET title = CASE WHEN titled = 1 THEN title ELSE ? END,"
        " link = CASE WHEN linked = 1 THEN link ELSE ? END WHERE id = ?",
        (title, link, channel_id),
    )
    await conn().commit()


async def set_channel_title(channel_id: int, title: str) -> None:
    """What the button says, chosen by hand and kept that way."""
    await conn().execute(
        "UPDATE gate_channels SET title = ?, titled = 1 WHERE id = ?",
        (title, channel_id),
    )
    await conn().commit()


async def set_channel_link(channel_id: int, link: str) -> None:
    """Where the button leads. An empty link hands the choice back to Telegram."""
    await conn().execute(
        "UPDATE gate_channels SET link = ?, linked = ? WHERE id = ?",
        (link, int(bool(link)), channel_id),
    )
    await conn().commit()


async def drop_channel(channel_id: int) -> None:
    await conn().execute("DELETE FROM gate_channels WHERE id = ?", (channel_id,))
    await conn().execute("DELETE FROM channel_joins WHERE channel_id = ?", (channel_id,))
    await conn().execute("DELETE FROM channel_asked WHERE channel_id = ?", (channel_id,))
    await conn().commit()


async def mark_join(channel_id: int, user_id: int) -> bool:
    """True the first time this person is seen inside this channel."""
    try:
        await conn().execute(
            "INSERT INTO channel_joins(channel_id, user_id) VALUES (?, ?)",
            (channel_id, user_id),
        )
    except aiosqlite.IntegrityError:
        return False
    await conn().commit()
    return True


async def mark_asked(channel_id: int, user_id: int) -> None:
    """Remember that the gate sent this person to that sponsor.

    Only for someone who is not inside yet: without that guard, a person who
    leaves the channel later would be re-counted as an arrival we delivered.
    """
    await conn().execute(
        """
        INSERT OR IGNORE INTO channel_asked(channel_id, user_id)
        SELECT ?, ? WHERE NOT EXISTS (
            SELECT 1 FROM channel_joins WHERE channel_id = ? AND user_id = ?
        )
        """,
        (channel_id, user_id, channel_id, user_id),
    )
    await conn().commit()


# --- welcome and promo posts ---------------------------------------------


async def add_post(kind: str, from_chat: int, msg_id: int, title: str) -> int:
    cur = await conn().execute(
        "INSERT INTO posts(kind, from_chat, msg_id, title) VALUES (?, ?, ?, ?)",
        (kind, from_chat, msg_id, title),
    )
    await conn().commit()
    return cur.lastrowid


async def posts(kind: str | None = None) -> list[aiosqlite.Row]:
    where = "WHERE kind = ?" if kind else ""
    args = (kind,) if kind else ()
    async with conn().execute(
        f"SELECT * FROM posts {where} ORDER BY active DESC, id", args
    ) as cur:
        return list(await cur.fetchall())


async def get_post(post_id: int) -> aiosqlite.Row | None:
    async with conn().execute("SELECT * FROM posts WHERE id = ?", (post_id,)) as cur:
        return await cur.fetchone()


async def set_post_active(post_id: int, active: bool) -> None:
    await conn().execute(
        "UPDATE posts SET active = ? WHERE id = ?", (int(active), post_id)
    )
    await conn().commit()


async def drop_post(post_id: int) -> None:
    await conn().execute("DELETE FROM posts WHERE id = ?", (post_id,))
    await conn().execute("DELETE FROM post_seen WHERE post_id = ?", (post_id,))
    await conn().commit()


async def unseen_welcome(user_id: int) -> list[aiosqlite.Row]:
    """Active welcome posts this person has not been shown yet."""
    async with conn().execute(
        """
        SELECT * FROM posts
        WHERE kind = 'welcome' AND active = 1
          AND id NOT IN (SELECT post_id FROM post_seen WHERE user_id = ?)
        ORDER BY id
        """,
        (user_id,),
    ) as cur:
        return list(await cur.fetchall())


async def pick_promo(user_id: int) -> aiosqlite.Row | None:
    """A promo the user has seen least recently; ties broken at random."""
    async with conn().execute(
        """
        SELECT p.* FROM posts p
        LEFT JOIN post_seen s ON s.post_id = p.id AND s.user_id = :uid
        WHERE p.kind = 'promo' AND p.active = 1
        ORDER BY COALESCE(s.ts, 0), RANDOM() LIMIT 1
        """,
        {"uid": user_id},
    ) as cur:
        return await cur.fetchone()


async def mark_shown(user_id: int, post_id: int, promo: bool = False) -> None:
    await conn().execute(
        "INSERT INTO post_seen(user_id, post_id) VALUES (?, ?)"
        " ON CONFLICT(user_id, post_id) DO UPDATE SET ts = strftime('%s','now')",
        (user_id, post_id),
    )
    await conn().execute("UPDATE posts SET shown = shown + 1 WHERE id = ?", (post_id,))
    if promo:
        await conn().execute(
            "UPDATE users SET last_promo = strftime('%s','now') WHERE id = ?",
            (user_id,),
        )
    await conn().commit()


async def promo_due(user_id: int, cooldown: int) -> bool:
    async with conn().execute(
        "SELECT last_promo < strftime('%s','now') - ? FROM users WHERE id = ?",
        (cooldown, user_id),
    ) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])


async def post_stats() -> dict:
    async with conn().execute(
        """
        SELECT
          COALESCE(SUM(kind = 'welcome' AND active = 1), 0) AS welcome,
          COALESCE(SUM(kind = 'promo' AND active = 1), 0)   AS promo,
          COALESCE(SUM(shown), 0)                           AS shown
        FROM posts
        """
    ) as cur:
        return dict(await cur.fetchone())


# --- crypto invoices -----------------------------------------------------


async def add_invoice(
    provider: str,
    invoice_id: str,
    user_id: int,
    coins: int,
    amount: str,
    asset: str,
    link: str,
) -> None:
    await conn().execute(
        "INSERT OR REPLACE INTO invoices(provider, invoice_id, user_id, coins,"
        " amount, asset, link) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (provider, invoice_id, user_id, coins, amount, asset, link),
    )
    await conn().commit()


async def get_invoice(provider: str, invoice_id: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM invoices WHERE provider = ? AND invoice_id = ?",
        (provider, invoice_id),
    ) as cur:
        return await cur.fetchone()


async def set_invoice_msg(provider: str, invoice_id: str, msg_id: int) -> None:
    await conn().execute(
        "UPDATE invoices SET msg_id = ? WHERE provider = ? AND invoice_id = ?",
        (msg_id, provider, invoice_id),
    )
    await conn().commit()


async def close_invoice(provider: str, invoice_id: str, status: str) -> bool:
    """False when somebody closed it first — the poller and the button race."""
    cur = await conn().execute(
        "UPDATE invoices SET status = ?, closed_at = strftime('%s','now')"
        " WHERE provider = ? AND invoice_id = ? AND status = 'active'",
        (status, provider, invoice_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def open_invoices(limit: int = 100) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM invoices WHERE status = 'active'"
        " ORDER BY created_at LIMIT ?",
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def invoice_totals() -> dict:
    async with conn().execute(
        """
        SELECT
          COALESCE(SUM(status = 'active'), 0)    AS open,
          COALESCE(SUM(status = 'paid'), 0)      AS paid,
          COALESCE(SUM(status = 'expired'), 0)   AS expired,
          COALESCE(SUM(status = 'cancelled'), 0) AS cancelled
        FROM invoices
        """
    ) as cur:
        return dict(await cur.fetchone())


async def crypto_totals() -> list[aiosqlite.Row]:
    """What came in through each provider, for the payments screen."""
    async with conn().execute(
        """
        SELECT provider, asset, COUNT(*) AS payments,
               COALESCE(SUM(coins), 0) AS coins,
               COALESCE(SUM(CAST(amount AS REAL)), 0) AS amount
        FROM payments WHERE provider != 'stars' AND refunded = 0
        GROUP BY provider, asset ORDER BY payments DESC
        """
    ) as cur:
        return list(await cur.fetchall())


async def get_payment(charge_id: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM payments WHERE charge_id = ?", (charge_id,)
    ) as cur:
        return await cur.fetchone()


async def recent_payments(limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM payments ORDER BY ts DESC LIMIT ?", (limit,)
    ) as cur:
        return list(await cur.fetchall())


async def mark_refunded(charge_id: str) -> None:
    await conn().execute(
        "UPDATE payments SET refunded = 1 WHERE charge_id = ?", (charge_id,)
    )
    await conn().commit()
