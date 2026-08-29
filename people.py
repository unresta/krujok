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
    """«@vasya · Вася · 123456789», username first.

    A username is what an admin writes down, forwards and searches by, so it
    leads. A person without one gets their name as a tg:// link instead — one
    tap still opens the profile, which an id alone never did.
    """
    if row is None:
        return "—"
    user_id = row["id"] if "id" in row.keys() else row["user_id"]
    name = (row["name"] or "").strip() if "name" in row.keys() else ""
    username = (row["username"] or "").strip() if "username" in row.keys() else ""

    parts = []
    if username:
        parts.append(f"<b>@{html.escape(username)}</b>")
        if name:
            parts.append(html.escape(name))
    elif name:
        parts.append(f'<b><a href="tg://user?id={user_id}">{html.escape(name)}</a></b>')
    else:
        parts.append(f'<a href="tg://user?id={user_id}">{UNKNOWN}</a>')
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
    return (f"@{username}" if username else name or str(user_id))[:24]


async def of(user_id: int, with_id: bool = True) -> str:
    """Same label, when only the id is at hand."""
    if not user_id:
        return "—"
    row = await db.user_row(user_id)
    if row is None:
        return f"<code>{user_id}</code>"
    return label(row, with_id)
