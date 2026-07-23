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
"""

from __future__ import annotations

import sqlite3
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


class DatabaseManager:
    """Thread-safe SQLite wrapper.  Uses WAL mode for better concurrency."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── connection helper ──────────────────────────────────────────────────

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
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
            conn.execute(_CREATE_TABLE)
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
        """Return the next sequential audio_XXXXXX.wav filename."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM SpeechDataset WHERE processing_status = 'accepted'"
            ).fetchone()
        count = row["cnt"] if row else 0
        return f"audio_{count + 1:06d}.wav"

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
            total = conn.execute("SELECT COUNT(*) AS c FROM SpeechDataset").fetchone()["c"]
            accepted = conn.execute(
                "SELECT COUNT(*) AS c FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()["c"]
            rejected = conn.execute(
                "SELECT COUNT(*) AS c FROM SpeechDataset WHERE processing_status='rejected'"
            ).fetchone()["c"]
            duration_row = conn.execute(
                "SELECT SUM(duration) AS s, AVG(duration) AS a FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()
            size_row = conn.execute(
                "SELECT SUM(file_size) AS s FROM SpeechDataset WHERE processing_status='accepted'"
            ).fetchone()

        total_seconds = duration_row["s"] or 0.0
        avg_seconds = duration_row["a"] or 0.0
        total_bytes = size_row["s"] or 0

        return {
            "total_files": total,
            "accepted_files": accepted,
            "rejected_files": rejected,
            "total_duration_seconds": round(total_seconds, 2),
            "total_duration_hours": round(total_seconds / 3600, 4),
            "average_duration_seconds": round(avg_seconds, 2),
            "total_size_bytes": total_bytes,
        }
