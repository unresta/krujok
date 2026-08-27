"""SQLite layer of the support bot: its own file, its own tables.

A ticket is a thread. The card in the support chat is its anchor: a moderator
replies to that card, and `ticket_by_admin_msg` turns the reply back into a
ticket id — that is why `admin_msg_id` is indexed and never reused.

Nothing here touches the main bot's database. See mainbase.py for that.
"""

from __future__ import annotations

import time

import aiosqlite

from config import DB_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS tickets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    username     TEXT,
    topic        TEXT    NOT NULL,   -- pay|coins|anketa|circle|payout|other
    status       TEXT    NOT NULL DEFAULT 'open',  -- open|taken|answered|closed
    taken_by     INTEGER,
    admin_msg_id INTEGER,            -- card in the support chat; the reply anchor
    rating       INTEGER,             -- 1 or -1, set by the user after closing
    first_reply  INTEGER,             -- when an admin answered first, for the SLA
    closed_by    INTEGER,             -- who closed it; equals user_id when self-closed
    pinged_at    INTEGER NOT NULL DEFAULT 0,  -- last SLA nudge, so it repeats slowly
    ts           INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    last_ts      INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    closed_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tickets_open ON tickets(status, last_ts);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id, id);
CREATE INDEX IF NOT EXISTS idx_tickets_card ON tickets(admin_msg_id);

CREATE TABLE IF NOT EXISTS ticket_messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL,
    from_admin INTEGER NOT NULL DEFAULT 0,
    author_id  INTEGER NOT NULL,
    text       TEXT    NOT NULL DEFAULT '',
    file_id    TEXT,
    file_type  TEXT,                 -- photo|video|document|voice|video_note
    ts         INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX IF NOT EXISTS idx_tmsg ON ticket_messages(ticket_id, id);

CREATE TABLE IF NOT EXISTS canned (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body  TEXT NOT NULL,
    used  INTEGER NOT NULL DEFAULT 0
);

-- Support's own ban list: a user drowning the queue is muted here without
-- touching their access to the main bot.
CREATE TABLE IF NOT EXISTS blocked (
    user_id INTEGER PRIMARY KEY,
    ts      INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings_text (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columns added after the first release; ALTER is the only way into an existing
# support.db, since CREATE TABLE IF NOT EXISTS leaves old tables alone.
MIGRATIONS: dict[str, dict[str, str]] = {
    "tickets": {
        "pinged_at": "INTEGER NOT NULL DEFAULT 0",
        "closed_by": "INTEGER",
    },
}

OPEN_STATUSES = ("open", "taken", "answered")

_db: aiosqlite.Connection | None = None


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


# --- tickets -------------------------------------------------------------


async def create_ticket(user_id: int, username: str | None, topic: str) -> int:
    cur = await conn().execute(
        "INSERT INTO tickets(user_id, username, topic) VALUES (?, ?, ?)",
        (user_id, username, topic),
    )
    await conn().commit()
    return cur.lastrowid


async def get_ticket(ticket_id: int) -> aiosqlite.Row | None:
    async with conn().execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    ) as cur:
        return await cur.fetchone()


async def ticket_by_admin_msg(msg_id: int) -> aiosqlite.Row | None:
    """A moderator's reply carries the card's message id — this maps it back."""
    async with conn().execute(
        "SELECT * FROM tickets WHERE admin_msg_id = ?", (msg_id,)
    ) as cur:
        return await cur.fetchone()


async def open_ticket_of(user_id: int) -> aiosqlite.Row | None:
    """The thread a user's next message should join, if there is one."""
    async with conn().execute(
        f"SELECT * FROM tickets WHERE user_id = ? AND status IN {OPEN_STATUSES}"
        " ORDER BY id DESC LIMIT 1",
        (user_id,),
    ) as cur:
        return await cur.fetchone()


async def set_admin_msg(ticket_id: int, msg_id: int) -> None:
    await conn().execute(
        "UPDATE tickets SET admin_msg_id = ? WHERE id = ?", (msg_id, ticket_id)
    )
    await conn().commit()


async def add_message(
    ticket_id: int,
    author_id: int,
    text: str,
    from_admin: bool = False,
    file_id: str | None = None,
    file_type: str | None = None,
) -> int:
    """Appends to the thread and bumps the ticket, so the queue sorts by activity."""
    cur = await conn().execute(
        "INSERT INTO ticket_messages(ticket_id, from_admin, author_id, text,"
        " file_id, file_type) VALUES (?, ?, ?, ?, ?, ?)",
        (ticket_id, int(from_admin), author_id, text, file_id, file_type),
    )
    await conn().execute(
        "UPDATE tickets SET last_ts = strftime('%s','now') WHERE id = ?", (ticket_id,)
    )
    if from_admin:  # the first answer is what the SLA measures
        await conn().execute(
            "UPDATE tickets SET first_reply = strftime('%s','now'),"
            " status = 'answered', pinged_at = 0"
            " WHERE id = ? AND first_reply IS NULL",
            (ticket_id,),
        )
        await conn().execute(
            "UPDATE tickets SET status = 'answered' WHERE id = ? AND status != 'closed'",
            (ticket_id,),
        )
    await conn().commit()
    return cur.lastrowid


async def thread(ticket_id: int, limit: int = 50) -> list[aiosqlite.Row]:
    """Oldest first, but only the tail when a thread has grown long."""
    async with conn().execute(
        "SELECT * FROM ticket_messages WHERE ticket_id = ?"
        " ORDER BY id DESC LIMIT ?",
        (ticket_id, limit),
    ) as cur:
        rows = list(await cur.fetchall())
    return rows[::-1]


async def take_ticket(ticket_id: int, admin_id: int) -> aiosqlite.Row | None:
    """Claim it. None when somebody already holds it or it is closed."""
    cur = await conn().execute(
        "UPDATE tickets SET status = 'taken', taken_by = ?"
        " WHERE id = ? AND status IN ('open', 'answered') AND taken_by IS NULL",
        (admin_id, ticket_id),
    )
    await conn().commit()
    if cur.rowcount == 0:
        return None
    return await get_ticket(ticket_id)


async def close_ticket(ticket_id: int, closed_by: int | None = None) -> aiosqlite.Row | None:
    """None when it was closed already, so two closers cannot both notify.

    `closed_by` is the id of whoever closed it — an admin, or the user
    themselves. The card shows which, so a moderator is not left wondering why a
    ticket resolved itself.
    """
    cur = await conn().execute(
        "UPDATE tickets SET status = 'closed', closed_at = strftime('%s','now'),"
        " closed_by = ? WHERE id = ? AND status != 'closed'",
        (closed_by, ticket_id),
    )
    await conn().commit()
    if cur.rowcount == 0:
        return None
    return await get_ticket(ticket_id)


async def rate_ticket(ticket_id: int, value: int) -> bool:
    """One rating per ticket, and only once it is closed."""
    cur = await conn().execute(
        "UPDATE tickets SET rating = ? WHERE id = ? AND status = 'closed'"
        " AND rating IS NULL",
        (value, ticket_id),
    )
    await conn().commit()
    return cur.rowcount > 0


async def open_tickets(limit: int = 10) -> list[aiosqlite.Row]:
    """Queue order: longest untouched first — nobody should be forgotten."""
    async with conn().execute(
        f"SELECT * FROM tickets WHERE status IN {OPEN_STATUSES}"
        " ORDER BY last_ts LIMIT ?",
        (limit,),
    ) as cur:
        return list(await cur.fetchall())


async def user_tickets(user_id: int, limit: int = 10) -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM tickets WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ) as cur:
        return list(await cur.fetchall())


async def tickets_today(user_id: int) -> int:
    """Antispam: how many this user opened in the last 24 hours."""
    async with conn().execute(
        "SELECT COUNT(*) AS n FROM tickets WHERE user_id = ?"
        " AND ts > strftime('%s','now') - 86400",
        (user_id,),
    ) as cur:
        return (await cur.fetchone())["n"]


# --- statistics and SLA --------------------------------------------------


async def stats() -> dict:
    async with conn().execute(
        """
        SELECT
          (SELECT COUNT(*) FROM tickets)                                  AS total,
          (SELECT COUNT(*) FROM tickets WHERE status = 'open')             AS waiting,
          (SELECT COUNT(*) FROM tickets WHERE status = 'taken')            AS taken,
          (SELECT COUNT(*) FROM tickets WHERE status = 'answered')         AS answered,
          (SELECT COUNT(*) FROM tickets WHERE status = 'closed')           AS closed,
          (SELECT COUNT(*) FROM tickets
             WHERE ts > strftime('%s','now') - 86400)                     AS today,
          (SELECT COUNT(*) FROM tickets WHERE rating = 1)                  AS good,
          (SELECT COUNT(*) FROM tickets WHERE rating = -1)                 AS bad,
          (SELECT COUNT(*) FROM ticket_messages)                           AS messages,
          (SELECT CAST(AVG(first_reply - ts) AS INTEGER) FROM tickets
             WHERE first_reply IS NOT NULL)                                AS avg_reply
        """
    ) as cur:
        return dict(await cur.fetchone())


async def by_topic() -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT topic, COUNT(*) AS n FROM tickets GROUP BY topic ORDER BY n DESC"
    ) as cur:
        return list(await cur.fetchall())


async def overdue(hours: int, repeat_hours: int, limit: int = 10) -> list[aiosqlite.Row]:
    """Tickets nobody answered in time and that were not nudged recently."""
    now = int(time.time())
    async with conn().execute(
        "SELECT * FROM tickets WHERE first_reply IS NULL AND status != 'closed'"
        " AND ts < ? AND pinged_at < ? ORDER BY ts LIMIT ?",
        (now - hours * 3600, now - repeat_hours * 3600, limit),
    ) as cur:
        return list(await cur.fetchall())


async def mark_pinged(ticket_id: int) -> None:
    await conn().execute(
        "UPDATE tickets SET pinged_at = strftime('%s','now') WHERE id = ?",
        (ticket_id,),
    )
    await conn().commit()


# --- canned replies ------------------------------------------------------


async def canned_list() -> list[aiosqlite.Row]:
    async with conn().execute(
        "SELECT * FROM canned ORDER BY used DESC, id"
    ) as cur:
        return list(await cur.fetchall())


async def canned_get(canned_id: int) -> aiosqlite.Row | None:
    async with conn().execute("SELECT * FROM canned WHERE id = ?", (canned_id,)) as cur:
        return await cur.fetchone()


async def canned_add(title: str, body: str) -> int:
    cur = await conn().execute(
        "INSERT INTO canned(title, body) VALUES (?, ?)", (title, body)
    )
    await conn().commit()
    return cur.lastrowid


async def canned_delete(canned_id: int) -> bool:
    cur = await conn().execute("DELETE FROM canned WHERE id = ?", (canned_id,))
    await conn().commit()
    return cur.rowcount > 0


async def canned_used(canned_id: int) -> None:
    """Most-used templates float to the top of the list."""
    await conn().execute(
        "UPDATE canned SET used = used + 1 WHERE id = ?", (canned_id,)
    )
    await conn().commit()


# --- support's own ban list ---------------------------------------------


async def is_blocked(user_id: int) -> bool:
    async with conn().execute(
        "SELECT 1 FROM blocked WHERE user_id = ?", (user_id,)
    ) as cur:
        return await cur.fetchone() is not None


async def block(user_id: int) -> None:
    await conn().execute(
        "INSERT OR IGNORE INTO blocked(user_id) VALUES (?)", (user_id,)
    )
    await conn().commit()


async def unblock(user_id: int) -> None:
    await conn().execute("DELETE FROM blocked WHERE user_id = ?", (user_id,))
    await conn().commit()


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
