"""Who a user is, for admin-facing screens.

An id alone tells a moderator nothing: they cannot tell a spammer from a paying
author, and cannot search for the person anywhere. Every update carries the
name and username, so the bot keeps the last ones it saw and the panel shows
them next to the id — which stays, because it is the only thing that never
changes and the only thing commands take.
"""

import html

import db

UNKNOWN = "без имени"


def label(row, with_id: bool = True) -> str:
    """«Вася (@vasya) · 123456789» — as much of it as is actually known."""
    if row is None:
        return "—"
    user_id = row["id"] if "id" in row.keys() else row["user_id"]
    name = (row["name"] or "").strip() if "name" in row.keys() else ""
    username = (row["username"] or "").strip() if "username" in row.keys() else ""

    parts = [f"<b>{html.escape(name)}</b>"] if name else []
    if username:
        parts.append(f"@{html.escape(username)}")
    if not parts:
        parts.append(UNKNOWN)
    if with_id:
        parts.append(f"<code>{user_id}</code>")
    return " · ".join(parts)


def short(row) -> str:
    """The same for a button, where there is no room and no HTML."""
    if row is None:
        return "—"
    user_id = row["id"] if "id" in row.keys() else row["user_id"]
    name = (row["name"] or "").strip() if "name" in row.keys() else ""
    username = (row["username"] or "").strip() if "username" in row.keys() else ""
    return (name or (f"@{username}" if username else str(user_id)))[:24]


async def of(user_id: int, with_id: bool = True) -> str:
    """Same label, when only the id is at hand."""
    if not user_id:
        return "—"
    row = await db.user_row(user_id)
    if row is None:
        return f"<code>{user_id}</code>"
    return label(row, with_id)
