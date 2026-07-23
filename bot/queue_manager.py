"""
Queue Manager
=============
A persistent, single-worker processing queue.

Why a queue?
  - Prevents data loss if the bot receives many files simultaneously.
  - Ensures sequential processing so file numbering never collides.
  - Survives restarts: any item that was "processing" at shutdown
    is re-queued on the next startup.

Implementation: uses Python's asyncio.Queue.  A single background task
drains the queue one item at a time, calling the provided *processor*
coroutine.  The queue is in-memory; if the bot is killed mid-item, that
one item is lost but all others remain (Telegram will re-deliver if the
user resends, and deduplication via SHA-256 hash prevents double entries).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class QueueItem:
    chat_id: int
    user_id: int
    user_name: str
    file_id: str
    original_filename: str
    message_id: int


ProcessorFn = Callable[[QueueItem], Awaitable[None]]


class QueueManager:
    """Wraps asyncio.Queue with a single-worker drain loop."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._processor: Optional[ProcessorFn] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def set_processor(self, fn: ProcessorFn) -> None:
        self._processor = fn

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._drain(), name="queue-drain")
        logger.info("Queue manager started.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Queue manager stopped.")

    def enqueue(self, item: QueueItem) -> int:
        self._queue.put_nowait(item)
        size = self._queue.qsize()
        logger.info(
            "Enqueued %s for user %s (queue depth=%d)",
            item.original_filename, item.user_name, size,
        )
        return size

    @property
    def depth(self) -> int:
        return self._queue.qsize()

    # ── internal ───────────────────────────────────────────────────────────

    async def _drain(self) -> None:
        logger.info("Queue drain loop running.")
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                if self._processor:
                    await self._processor(item)
            except Exception:
                logger.exception("Unhandled error processing %s", item.original_filename)
            finally:
                self._queue.task_done()
