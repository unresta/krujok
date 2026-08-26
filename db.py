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

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
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

_db: aiosqlite.Connection | None = None


async def connect() -> None:
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


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


async def add_coins(user_id: int, amount: int) -> None:
    await ensure_user(user_id)
    await conn().execute(
        "UPDATE users SET coins = coins + ? WHERE id = ?", (amount, user_id)
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


async def review_circle(circle_id: int, status: str, admin_id: int) -> bool:
    """Flip a pending circle. False if somebody reviewed it first."""
    cur = await conn().execute(
        "UPDATE circles SET status = ?, reviewed_by = ?"
        " WHERE id = ? AND status = 'pending'",
        (status, admin_id, circle_id),
    )
    await conn().commit()
    return cur.rowcount > 0


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


# --- settings ------------------------------------------------------------


async def load_settings() -> dict[str, int]:
    async with conn().execute("SELECT key, value FROM settings") as cur:
        return {row["key"]: row["value"] for row in await cur.fetchall()}


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
