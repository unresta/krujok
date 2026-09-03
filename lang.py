"""Which language this update is being answered in.

One update, one language, held in a context variable rather than passed down
through every call: `texts.menu(coins, pref)` and `kb.main_menu()` are called
from a hundred places, and threading a parameter through all of them would be a
hundred chances to forget one.

The middleware sets it from the users row before any handler runs. Background
jobs write to people nobody is talking to, so they set it themselves around
each recipient — `with lang.use(row["lang"]): ...` — and the default outside
either of those is Russian, which is what the moderation chats read.

Its own module because both texts.py and keyboards.py need it, and texts.py
already imports keyboards.
"""

from contextlib import contextmanager
from contextvars import ContextVar

LANGS = ("ru", "en")
DEFAULT = "ru"

_current: ContextVar[str] = ContextVar("lang", default=DEFAULT)

# Telegram reports the language a client is set to, not a country. These are the
# ones whose speakers read Russian well enough to be answered in it; everything
# else — and a missing code, which means an old client or a hidden setting —
# gets English.
RU_SPEAKING = frozenset({"ru", "be", "uk", "kk", "ky", "uz", "tg", "hy", "az", "mo"})


def get() -> str:
    return _current.get()


def set(value: str) -> None:  # noqa: A001 — it is a language, not a builtin
    _current.set(value if value in LANGS else DEFAULT)


@contextmanager
def use(value: str):
    token = _current.set(value if value in LANGS else DEFAULT)
    try:
        yield
    finally:
        _current.reset(token)


def detect(language_code: str | None) -> str:
    """What to speak to somebody the bot has not asked yet."""
    code = (language_code or "").lower().replace("_", "-").split("-")[0]
    return "ru" if code in RU_SPEAKING else "en"


def title(value: str) -> str:
    return {"ru": "🇷🇺 Русский", "en": "🇬🇧 English"}.get(value, value)
