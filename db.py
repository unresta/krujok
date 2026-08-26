"""SQLite layer. Every coin move goes through here so balances stay atomic."""

from __future__ import annotations

import aiosqlite

from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY,
    coins       INTEGER NOT NULL DEFAULT 0,
    pref        TEXT    NOT NULL DEFAULT 'f',   -- f | m | any
    banned      INTEGER NOT NULL DEFAULT 0,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS circles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        TEXT    NOT NULL,
    file_unique_id TEXT    NOT NULL UNIQUE,
    uploader_id    INTEGER NOT NULL,
    gender         TEXT    NOT NULL,            -- f | m
    duration       INTEGER NOT NULL,
    status         TEXT    NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
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
    handled   INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE (user_id, circle_id)
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id       INTEGER PRIMARY KEY,
    photo_id      TEXT    NOT NULL,
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

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_text (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    charge_id TEXT PRIMARY KEY,
    user_id   INTEGER NOT NULL,
    stars     INTEGER NOT NULL,
    coins     INTEGER NOT NULL,
    refunded  INTEGER NOT NULL DEFAULT 0,
    ts        INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
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
    },
    "circles": {
        "likes": "INTEGER NOT NULL DEFAULT 0",
        "dislikes": "INTEGER NOT NULL DEFAULT 0",
        "earned": "INTEGER NOT NULL DEFAULT 0",
    },
}


async def connect() -> None:
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
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


async def referral_totals() -> tuple[int, int]:
    async with conn().execute(
        "SELECT COUNT(*) AS invited,"
        " COALESCE(SUM(ref_credited), 0) AS confirmed"
        " FROM users WHERE ref_by IS NOT NULL"
    ) as cur:
        row = await cur.fetchone()
    return row["invited"], row["confirmed"]


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


async def review_circle(circle_id: int, status: str, admin_id: int) -> bool:
    """Flip a pending circle. False if somebody reviewed it first."""
    cur = await conn().execute(
        "UPDATE circles SET status = ?, reviewed_by = ?"
        " WHERE id = ? AND status = 'pending'",
        (status, admin_id, circle_id),
    )
    await conn().commit()
    return cur.rowcount > 0


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


async def pick_circle(user_id: int, pref: str) -> aiosqlite.Row | None:
    gender_clause = "" if pref == "any" else "AND gender = :pref"
    async with conn().execute(
        f"""
        SELECT * FROM circles
        WHERE status = 'approved'
          AND uploader_id != :uid
          {gender_clause}
          AND id NOT IN (SELECT circle_id FROM views WHERE user_id = :uid)
        ORDER BY RANDOM() LIMIT 1
        """,
        {"uid": user_id, "pref": pref},
    ) as cur:
        return await cur.fetchone()


async def mark_viewed(user_id: int, circle_id: int) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO views(user_id, circle_id) VALUES (?, ?)",
        (user_id, circle_id),
    )
    await conn().execute(
        "UPDATE circles SET views = views + 1 WHERE id = ?", (circle_id,)
    )
    await conn().commit()


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
    cur = await conn().execute("DELETE FROM circles WHERE id = ?", (circle_id,))
    await conn().execute("DELETE FROM views WHERE circle_id = ?", (circle_id,))
    await conn().commit()
    return cur.rowcount > 0


async def wipe_circles() -> int:
    """Drop every circle and every view. Balances and payments stay untouched.

    The AUTOINCREMENT counter is reset too, so numbering starts from #1 again.
    """
    total = await total_circles()
    await conn().execute("DELETE FROM circles")
    await conn().execute("DELETE FROM views")
    await conn().execute("DELETE FROM sqlite_sequence WHERE name = 'circles'")
    await conn().commit()
    return total


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


async def add_report(user_id: int, circle_id: int) -> int | None:
    """None when this user already complained about this circle."""
    try:
        await conn().execute(
            "INSERT INTO reports(user_id, circle_id) VALUES (?, ?)",
            (user_id, circle_id),
        )
    except aiosqlite.IntegrityError:
        return None
    await conn().commit()
    async with conn().execute(
        "SELECT COUNT(*) FROM reports WHERE circle_id = ? AND handled = 0",
        (circle_id,),
    ) as cur:
        return (await cur.fetchone())[0]


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


async def author_earnings(user_id: int) -> tuple[int, int, int]:
    """(coins earned by circles, total likes, total views)"""
    async with conn().execute(
        "SELECT COALESCE(SUM(earned),0) AS earned, COALESCE(SUM(likes),0) AS likes,"
        " COALESCE(SUM(views),0) AS views FROM circles WHERE uploader_id = ?",
        (user_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["earned"], row["likes"], row["views"]


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
) -> None:
    """An edited profile goes back to moderation — the photo changed too."""
    await ensure_user(user_id)
    await conn().execute(
        """
        INSERT INTO profiles(user_id, photo_id, about, gender, price_content,
                             price_contact, contact_ok, username, status)
        VALUES (:uid, :photo, :about, :gender, :content, :contact, :ok, :name,
                'pending')
        ON CONFLICT(user_id) DO UPDATE SET
            photo_id = excluded.photo_id, about = excluded.about,
            gender = excluded.gender, price_content = excluded.price_content,
            price_contact = excluded.price_contact,
            contact_ok = excluded.contact_ok, username = excluded.username,
            status = 'pending'
        """,
        {
            "uid": user_id,
            "photo": photo_id,
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
    """A profile the viewer has not seen yet, never their own."""
    async with conn().execute(
        """
        SELECT p.*,
               (SELECT COUNT(*) FROM circles c
                 WHERE c.uploader_id = p.user_id AND c.status = 'approved') AS circles
        FROM profiles p
        WHERE p.status = 'approved' AND p.user_id != :uid
          AND p.user_id NOT IN (SELECT author_id FROM profile_views
                                 WHERE buyer_id = :uid)
        ORDER BY RANDOM() LIMIT 1
        """,
        {"uid": viewer_id},
    ) as cur:
        return await cur.fetchone()


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


async def get_purchase(buyer_id: int, author_id: int, kind: str) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM purchases WHERE buyer_id = ? AND author_id = ? AND kind = ?",
        (buyer_id, author_id, kind),
    ) as cur:
        return await cur.fetchone()


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


# --- payments ------------------------------------------------------------


async def add_payment(charge_id: str, user_id: int, stars: int, coins: int) -> bool:
    """False when Telegram replays a charge we already credited."""
    try:
        await conn().execute(
            "INSERT INTO payments(charge_id, user_id, stars, coins) VALUES (?, ?, ?, ?)",
            (charge_id, user_id, stars, coins),
        )
    except aiosqlite.IntegrityError:
        return False
    await conn().commit()
    return True


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
