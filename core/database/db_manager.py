"""
Database Manager
================
Manages the SQLite database that is the single source of truth for the dataset.

Schema
------
SpeechDataset
  id                INTEGER  PRIMARY KEY AUTOINCREMENT
  filename          TEXT     NOT NULL UNIQUE   (audio_000001.wav)
  original_filename TEXT
  transcript        TEXT
  duration          REAL
  language          TEXT
  sample_rate       INTEGER
  channels          INTEGER
  confidence        REAL
  file_hash         TEXT     NOT NULL UNIQUE
  file_size         INTEGER
  created_at        TEXT     (ISO-8601)
  processing_status TEXT     (accepted | rejected)
  rejection_reason  TEXT
  telegram_user_id  INTEGER
  telegram_file_id  TEXT

Concurrency notes (v2)
----------------------
- WAL mode is enabled so readers never block writers.
- busy_timeout=10 000 ms means concurrent writers retry for up to 10 s
  before raising OperationalError, eliminating "database is locked" crashes
  under multi-worker load.
- next_filename() now derives the sequence number from MAX(id)+1, which is
  safe under concurrent access when the caller holds the external seq_lock
  (provided by QueueManager).  Do NOT call next_filename() without holding
  that lock.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Generator, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS SpeechDataset (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    filename          TEXT     NOT NULL UNIQUE,
    original_filename TEXT,
    transcript        TEXT,
    duration          REAL,
    language          TEXT,
    sample_rate       INTEGER,
    channels          INTEGER,
    confidence        REAL,
    file_hash         TEXT     NOT NULL UNIQUE,
    file_size         INTEGER,
    created_at        TEXT     NOT NULL,
    processing_status TEXT     NOT NULL DEFAULT 'pending',
    rejection_reason  TEXT,
    telegram_user_id  INTEGER,
    telegram_file_id  TEXT
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_file_hash ON SpeechDataset(file_hash);
CREATE INDEX IF NOT EXISTS idx_status    ON SpeechDataset(processing_status);
CREATE INDEX IF NOT EXISTS idx_user_id   ON SpeechDataset(telegram_user_id);
"""


class DatabaseManager:
    """
    Thread-safe SQLite wrapper.

    Each public method opens a **fresh connection** so it is safe to call
    from any thread or asyncio task without sharing connection objects.
    WAL mode + busy_timeout provide concurrent-write resilience.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── connection helper ──────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(
            str(self._db_path),
            timeout=30,            # seconds to wait for a write lock
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        # WAL: readers and the single writer don't block each other
        conn.execute("PRAGMA journal_mode=WAL")
        # busy_timeout: if the DB file is locked, retry for up to 10 s
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        # Faster writes without losing durability under WAL
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── initialisation ─────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_CREATE_TABLE + _CREATE_INDEXES)
        logger.info("Database initialised at %s", self._db_path)

    # ── duplicate detection ────────────────────────────────────────────────

    def hash_exists(self, file_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM SpeechDataset WHERE file_hash = ?", (file_hash,)
            ).fetchone()
        return row is not None

    # ── next available filename ────────────────────────────────────────────

    def next_filename(self) -> str:
        """
        Return the next sequential audio_XXXXXX.wav filename.

        Uses MAX(id)+1 (not COUNT) so the sequence is monotonically
        increasing even after deletions and is safe when the caller holds
        the external QueueManager.seq_lock.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS max_id FROM SpeechDataset"
            ).fetchone()
        next_id = (row["max_id"] if row else 0) + 1
        return f"audio_{next_id:06d}.wav"

    # ── insert ─────────────────────────────────────────────────────────────

    def insert_record(
        self,
        *,
        filename: str,
        original_filename: str,
        transcript: str,
        duration: float,
        language: str,
        sample_rate: int,
        channels: int,
        confidence: float,
        file_hash: str,
        file_size: int,
        processing_status: str,
        rejection_reason: Optional[str] = None,
        telegram_user_id: Optional[int] = None,
        telegram_file_id: Optional[str] = None,
    ) -> int:
        created_at = datetime.now(tz=timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO SpeechDataset
                  (filename, original_filename, transcript, duration, language,
                   sample_rate, channels, confidence, file_hash, file_size,
                   created_at, processing_status, rejection_reason,
                   telegram_user_id, telegram_file_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    filename, original_filename, transcript, duration, language,
                    sample_rate, channels, confidence, file_hash, file_size,
                    created_at, processing_status, rejection_reason,
                    telegram_user_id, telegram_file_id,
                ),
            )
        record_id = cur.lastrowid
        logger.debug("Inserted record id=%d filename=%s", record_id, filename)
        return record_id

    # ── queries ────────────────────────────────────────────────────────────

    def get_accepted(self) -> List[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM SpeechDataset
                WHERE processing_status = 'accepted'
                ORDER BY id ASC
                """
            ).fetchall()
        return rows

    def get_statistics(self) -> Dict:
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM SpeechDataset"
            ).fetchone()["c"]
            accepted = conn.execute(
                "SELECT COUNT(*) AS c FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()["c"]
            rejected = conn.execute(
                "SELECT COUNT(*) AS c FROM SpeechDataset WHERE processing_status='rejected'"
            ).fetchone()["c"]
            duration_row = conn.execute(
                "SELECT SUM(duration) AS s, AVG(duration) AS a "
                "FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()
            size_row = conn.execute(
                "SELECT SUM(file_size) AS s "
                "FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()

        total_seconds = duration_row["s"] or 0.0
        avg_seconds   = duration_row["a"] or 0.0
        total_bytes   = size_row["s"] or 0

        return {
            "total_files":              total,
            "accepted_files":           accepted,
            "rejected_files":           rejected,
            "total_duration_seconds":   round(total_seconds, 2),
            "total_duration_hours":     round(total_seconds / 3600, 4),
            "average_duration_seconds": round(avg_seconds, 2),
            "total_size_bytes":         total_bytes,
        }
