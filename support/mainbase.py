"""Read-only window into the main bot's database.

A support card is worth much more when it already carries the balance, what the
user bought and what they uploaded: most tickets ("stars gone, no coins", "my
profile is stuck") are answered by looking at that, not by asking the user.

Three rules hold this together:

  * The connection is opened with `mode=ro`, so a bug here cannot corrupt the
    main bot's base. SQLite refuses the write at the driver level.
  * Every lookup degrades. No MAIN_DB_PATH, a missing file, an old schema
    without some table — the card simply loses those lines, and the ticket still
    works. Support must never go down because the main bot moved its database.
  * Nothing is cached beyond the connection: the main bot writes constantly, and
    a stale balance on a payment ticket is worse than none.
"""

import logging

import aiosqlite

from config import MAIN_DB_PATH

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None
_broken = False  # set once the base proves unusable, to stop retrying per card


async def connect() -> None:
    """Best effort: a failure here is normal operation, not an error."""
    global _db, _broken
    if not MAIN_DB_PATH:
        logger.info("main base not configured, cards will carry no user history")
        _broken = True
        return
    try:
        _db = await aiosqlite.connect(f"file:{MAIN_DB_PATH}?mode=ro", uri=True)
        _db.row_factory = aiosqlite.Row
        await _db.execute("SELECT 1 FROM users LIMIT 1")
    except Exception as error:  # missing file, no permission, no users table
        logger.warning("main base %s unusable (%s), cards go without it", MAIN_DB_PATH, error)
        if _db is not None:
            await _db.close()
        _db = None
        _broken = True
        return
    logger.info("main base %s opened read-only", MAIN_DB_PATH)


async def close() -> None:
    if _db is not None:
        await _db.close()


def available() -> bool:
    return _db is not None and not _broken


async def _one(sql: str, args: tuple = ()) -> aiosqlite.Row | None:
    """Any failure is swallowed: a card without extras beats no card at all."""
    if not available():
        return None
    try:
        async with _db.execute(sql, args) as cur:
            return await cur.fetchone()
    except Exception as error:  # table gone, schema changed, file truncated
        logger.warning("main base query failed (%s), skipping", error)
        return None


async def profile(user_id: int) -> dict | None:
    """Everything the main bot knows about this person, or None."""
    user = await _one(
        "SELECT coins, banned, earned, accepted, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    if user is None:
        return None

    data = dict(user)

    circles = await _one(
        "SELECT COUNT(*) AS total,"
        " SUM(status = 'approved') AS approved,"
        " SUM(status = 'pending')  AS pending,"
        " SUM(status = 'rejected') AS rejected"
        " FROM circles WHERE uploader_id = ?",
        (user_id,),
    )
    data["circles"] = dict(circles) if circles else None

    payments = await _one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(stars), 0) AS stars,"
        " COALESCE(SUM(refunded), 0) AS refunded"
        " FROM payments WHERE user_id = ?",
        (user_id,),
    )
    data["payments"] = dict(payments) if payments else None

    last = await _one(
        "SELECT charge_id, stars, coins, refunded, ts FROM payments"
        " WHERE user_id = ? ORDER BY ts DESC LIMIT 1",
        (user_id,),
    )
    data["last_payment"] = dict(last) if last else None

    prof = await _one(
        "SELECT status, price_content, price_contact, views, sold FROM profiles"
        " WHERE user_id = ?",
        (user_id,),
    )
    data["profile"] = dict(prof) if prof else None

    payouts = await _one(
        "SELECT COUNT(*) AS n, SUM(status = 'open') AS open,"
        " COALESCE(SUM(CASE WHEN status = 'paid' THEN stars END), 0) AS paid_stars"
        " FROM payouts WHERE user_id = ?",
        (user_id,),
    )
    data["payouts"] = dict(payouts) if payouts else None

    bought = await _one(
        "SELECT COUNT(*) AS n FROM purchases WHERE buyer_id = ?", (user_id,)
    )
    data["bought"] = bought["n"] if bought else None

    return data


async def find_payment(charge_id: str) -> dict | None:
    """Look a charge up by the id the user pasted from their Telegram receipt."""
    row = await _one(
        "SELECT charge_id, user_id, stars, coins, refunded, ts FROM payments"
        " WHERE charge_id = ?",
        (charge_id,),
    )
    return dict(row) if row else None
