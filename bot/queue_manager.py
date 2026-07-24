"""
Queue Manager  (v2 — multi-worker)
===================================
A concurrent, multi-worker processing queue built on asyncio.

Design goals
------------
* **Concurrency** — up to ``max_workers`` files are processed simultaneously.
  Downloading, audio conversion, and Whisper transcription all run in parallel
  across different users, so one slow file does not block everyone else.

* **No filename collisions** — a dedicated ``asyncio.Lock`` (``_seq_lock``)
  serialises only the tiny critical section: reserving the next filename,
  moving the final WAV, and inserting the DB record.  Everything else
  (download, pydub, Whisper) runs concurrently outside the lock.

* **Debounced rebuild** — instead of calling ``DatasetManager.rebuild()``
  after every single accepted file (expensive I/O), a background task
  accumulates writes and rebuilds at most once per ``rebuild_debounce_s``
  seconds.

* **Fair queue-depth reporting** — ``depth`` counts items not yet started.
  ``active`` counts items currently being processed.

Usage
-----
    mgr = QueueManager(max_workers=3, rebuild_debounce_s=10)
    mgr.set_processor(my_coroutine)
    mgr.set_rebuild(dataset_mgr.rebuild_from_db)   # called after batch
    await mgr.start()
    ...
    await mgr.stop()
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


ProcessorFn = Callable[[QueueItem, "asyncio.Lock"], Awaitable[None]]
RebuildFn   = Callable[[], Awaitable[None]]


class QueueManager:
    """Multi-worker asyncio queue with a shared sequence lock and debounced rebuild."""

    def __init__(
        self,
        max_workers: int = 3,
        rebuild_debounce_s: float = 10.0,
    ) -> None:
        self._max_workers      = max_workers
        self._rebuild_debounce = rebuild_debounce_s

        self._queue:   asyncio.Queue[QueueItem] = asyncio.Queue()
        self._processor: Optional[ProcessorFn]  = None
        self._rebuild_fn: Optional[RebuildFn]   = None

        # Shared lock — held only during filename reservation + DB insert.
        # Workers acquire it for < 50 ms so concurrency is not harmed.
        self.seq_lock: asyncio.Lock = asyncio.Lock()

        # Debounced rebuild state
        self._pending_rebuild: bool            = False
        self._rebuild_task: Optional[asyncio.Task] = None

        # Worker tasks
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False

        # Active counter (items currently being processed)
        self._active = 0

    # ── public API ─────────────────────────────────────────────────────────

    def set_processor(self, fn: ProcessorFn) -> None:
        """Register the coroutine that processes one QueueItem."""
        self._processor = fn

    def set_rebuild(self, fn: RebuildFn) -> None:
        """Register the coroutine that rebuilds dataset files after a batch."""
        self._rebuild_fn = fn

    def notify_rebuild_needed(self) -> None:
        """
        Called by the processor when a file is accepted.
        Schedules a debounced rebuild (runs once per batch, not per file).
        """
        self._pending_rebuild = True

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            t = asyncio.create_task(self._worker(i), name=f"queue-worker-{i}")
            self._worker_tasks.append(t)
        self._rebuild_task = asyncio.create_task(
            self._rebuild_loop(), name="rebuild-loop"
        )
        logger.info(
            "QueueManager started with %d workers (rebuild debounce %.0fs).",
            self._max_workers, self._rebuild_debounce,
        )

    async def stop(self) -> None:
        self._running = False
        for t in self._worker_tasks:
            t.cancel()
        if self._rebuild_task:
            self._rebuild_task.cancel()
        results = await asyncio.gather(
            *self._worker_tasks,
            self._rebuild_task or asyncio.sleep(0),
            return_exceptions=True,
        )
        self._worker_tasks.clear()
        self._rebuild_task = None
        logger.info("QueueManager stopped.")

    def enqueue(self, item: QueueItem) -> int:
        """Add *item* to the queue. Returns current queue depth (not yet started)."""
        self._queue.put_nowait(item)
        depth = self._queue.qsize()
        logger.info(
            "Enqueued '%s' for %s (waiting=%d, active=%d).",
            item.original_filename, item.user_name, depth, self._active,
        )
        return depth

    @property
    def depth(self) -> int:
        """Items waiting to be picked up by a worker."""
        return self._queue.qsize()

    @property
    def active(self) -> int:
        """Items currently being processed."""
        return self._active

    @property
    def total_pending(self) -> int:
        """Items waiting + items in flight."""
        return self._queue.qsize() + self._active

    # ── internal: workers ──────────────────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        logger.debug("Worker %d started.", worker_id)
        while self._running:
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            self._active += 1
            try:
                if self._processor:
                    # Pass the shared seq_lock so the processor can use it
                    # for the critical filename-reservation + DB-insert step.
                    await self._processor(item, self.seq_lock)
            except Exception:
                logger.exception(
                    "Worker %d: unhandled error processing '%s'.",
                    worker_id, item.original_filename,
                )
            finally:
                self._active -= 1
                self._queue.task_done()

        logger.debug("Worker %d stopped.", worker_id)

    # ── internal: debounced rebuild ────────────────────────────────────────

    async def _rebuild_loop(self) -> None:
        """
        Sleeps for ``rebuild_debounce_s`` seconds and, if any accepted files
        arrived in that window, triggers a single rebuild — instead of one
        rebuild per accepted file.
        """
        logger.debug("Rebuild loop started (debounce=%.0fs).", self._rebuild_debounce)
        while self._running:
            try:
                await asyncio.sleep(self._rebuild_debounce)
            except asyncio.CancelledError:
                break

            if self._pending_rebuild and self._rebuild_fn:
                self._pending_rebuild = False
                try:
                    logger.info("Rebuild triggered (debounced).")
                    await self._rebuild_fn()
                except Exception:
                    logger.exception("Rebuild failed.")

        logger.debug("Rebuild loop stopped.")

