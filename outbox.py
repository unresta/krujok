"""Sending into the shared chats without tripping Telegram's flood limits.

A group chat takes about twenty messages a minute. An upload costs two of them
— the circle and its card — so twenty people uploading at once is already over
the line, and Telegram answers «Flood control exceeded, retry in 25 seconds».
What used to happen then was that the card was logged as lost and the moderator
never saw the circle at all.

Everything headed for a moderation chat goes through here instead. One worker
per chat sends in order, leaves a gap between messages, and when Telegram asks
to wait it waits exactly that long and tries the same message again. The person
who uploaded waits for none of it: their own confirmation goes to a private
chat, which is a different limit entirely.

A job queued with `post` must do its sending through `call` — that is where the
pacing and the retry live.
"""

import asyncio
import logging
import time

from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

logger = logging.getLogger(__name__)

INTERVAL = 3.0  # seconds between two messages into one chat — 20 per minute
RETRIES = 3  # how many times one message waits out a flood limit
QUEUE_MAX = 1000  # a backlog past this is a broken chat, not a busy one

_queues: dict[str, asyncio.Queue] = {}
_workers: dict[str, asyncio.Task] = {}
_next_free: dict[str, float] = {}  # chat -> when it may take another message


async def _slot(chat) -> None:
    """Hold until this chat may take another message, booking that slot."""
    key = str(chat)
    now = time.monotonic()
    ready = max(_next_free.get(key, 0.0), now)
    _next_free[key] = ready + INTERVAL
    if ready > now:
        await asyncio.sleep(ready - now)


def _hold_off(chat, seconds: float) -> None:
    """Telegram asked to wait — nothing goes into that chat until it is over."""
    key = str(chat)
    _next_free[key] = max(_next_free.get(key, 0.0), time.monotonic() + seconds)


async def call(chat, action, what: str = ""):
    """One API call into a shared chat: paced, retried when told to wait.

    The retry sits around a single message rather than around a whole job, so a
    card that runs into the limit is not paid for by sending its video note a
    second time. Returns what the call returned, or None if it never got through.
    """
    for attempt in range(1, RETRIES + 1):
        await _slot(chat)
        try:
            return await action()
        except TelegramRetryAfter as error:
            # A second on top: the countdown starts on Telegram's clock, not ours.
            _hold_off(chat, error.retry_after + 1)
            logger.warning(
                "outbox: %s into %s told to wait %ss (попытка %s из %s)",
                what or "сообщение", chat, error.retry_after, attempt, RETRIES,
            )
        except TelegramAPIError as error:
            logger.error(
                "outbox: %s into %s failed: %s", what or "сообщение", chat, error
            )
            return None
    logger.error(
        "outbox: %s into %s gave up after %s tries", what or "сообщение", chat, RETRIES
    )
    return None


def post(chat, job, what: str = "") -> None:
    """Queue a job for that chat and return at once.

    The worker is started on the first job for a chat and lives until shutdown.
    """
    key = str(chat)
    queue = _queues.get(key)
    if queue is None:
        queue = _queues[key] = asyncio.Queue(maxsize=QUEUE_MAX)
        _workers[key] = asyncio.create_task(_worker(key, queue), name=f"outbox:{key}")
    try:
        queue.put_nowait((job, what))
    except asyncio.QueueFull:
        # Dropping is the honest outcome: a queue this long means the chat has
        # been unreachable for an hour, and holding more of it helps nobody.
        logger.error(
            "outbox: %s dropped, %s is backed up past %s",
            what or "сообщение", chat, QUEUE_MAX,
        )


async def _worker(key: str, queue: asyncio.Queue) -> None:
    """One crash must not take the chat's whole queue down with it."""
    while True:
        job, what = await queue.get()
        try:
            await job()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 — the worker outlives anything
            logger.exception("outbox: %s into %s crashed: %s", what, key, error)
        finally:
            queue.task_done()


def pending(chat) -> int:
    """How much is still waiting for that chat — the panel reads this."""
    queue = _queues.get(str(chat))
    return queue.qsize() if queue is not None else 0


async def close() -> None:
    for task in _workers.values():
        task.cancel()
    _workers.clear()
    _queues.clear()
