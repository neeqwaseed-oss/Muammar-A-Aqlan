"""
Dataset Manager
===============
Writes and maintains all dataset artefact files derived from the database:

  metadata.csv   — per-file metadata
  dataset.json   — HuggingFace-compatible JSONL records
  train.csv      — 80 % split
  validation.csv — 10 % split
  test.csv       — 10 % split
  statistics.json
  README.txt

All writes are atomic: we write to a temp file first then rename.
"""

from __future__ import annotations

import csv
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from config.settings import PathsConfig, SplitsConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class DatasetManager:

    def __init__(self, paths: PathsConfig, splits: SplitsConfig) -> None:
        self._p = paths
        self._s = splits
        self._ensure_dirs()

    # ── public interface ───────────────────────────────────────────────────

    def rebuild(self, rows: list) -> None:
        """
        Re-create all dataset files from *rows* (list of sqlite3.Row objects
        representing accepted records).  Called by /rebuild and after every
        new accepted file.
        """
        logger.info("Rebuilding dataset files from %d records…", len(rows))

        self._write_metadata_csv(rows)
        self._write_dataset_json(rows)

        train, validation, test = self._split(rows)
        self._write_split_csv(train, self._p.train_csv, "train")
        self._write_split_csv(validation, self._p.validation_csv, "validation")
        self._write_split_csv(test, self._p.test_csv, "test")

        self._write_readme(len(rows))
        logger.info("Dataset rebuild complete.")

    def update_statistics(self, stats: dict) -> None:
        """Write statistics.json from a dict returned by DatabaseManager.get_statistics()."""
        stats["last_updated"] = datetime.now(tz=timezone.utc).isoformat()
        self._atomic_write_text(
            self._p.statistics_json,
            json.dumps(stats, ensure_ascii=False, indent=2),
        )
        logger.debug("statistics.json updated.")

    # ── file writers ───────────────────────────────────────────────────────

    def _write_metadata_csv(self, rows: list) -> None:
        fieldnames = [
            "filename", "text", "duration", "sample_rate",
            "channels", "confidence", "language", "file_size",
            "file_hash", "created_at",
        ]
        lines = [
            {
                "filename": f"audio/{r['filename']}",
                "text": r["transcript"],
                "duration": round(r["duration"], 4),
                "sample_rate": r["sample_rate"],
                "channels": r["channels"],
                "confidence": round(r["confidence"], 4),
                "language": r["language"],
                "file_size": r["file_size"],
                "file_hash": r["file_hash"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        self._atomic_write_csv(self._p.metadata_csv, fieldnames, lines)
        logger.debug("metadata.csv written (%d rows).", len(lines))

    def _write_dataset_json(self, rows: list) -> None:
        """HuggingFace Common-Voice style JSONL."""
        records = [
            {
                "audio": f"audio/{r['filename']}",
                "sentence": r["transcript"],
                "duration": round(r["duration"], 4),
                "language": r["language"],
                "confidence": round(r["confidence"], 4),
            }
            for r in rows
        ]
        content = json.dumps(records, ensure_ascii=False, indent=2)
        self._atomic_write_text(self._p.dataset_json, content)
        logger.debug("dataset.json written (%d records).", len(records))

    def _write_split_csv(self, rows: list, out_path: Path, split_name: str) -> None:
        fieldnames = ["filename", "text", "duration"]
        lines = [
            {
                "filename": f"audio/{r['filename']}",
                "text": r["transcript"],
                "duration": round(r["duration"], 4),
            }
            for r in rows
        ]
        self._atomic_write_csv(out_path, fieldnames, lines)
        logger.debug("%s written (%d rows).", out_path.name, len(lines))

    def _write_readme(self, total: int) -> None:
        text = (
            "Libyan ASR Dataset\n"
            "==================\n\n"
            f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Total accepted files: {total}\n\n"
            "Structure\n"
            "---------\n"
            "  audio/          WAV files (16 kHz, mono, PCM 16-bit)\n"
            "  metadata.csv    Per-file metadata (filename, text, duration, …)\n"
            "  dataset.json    HuggingFace-compatible records\n"
            "  train.csv       80 % split\n"
            "  validation.csv  10 % split\n"
            "  test.csv        10 % split\n"
            "  statistics.json Aggregate statistics\n"
            "  database.sqlite Full SQLite database\n\n"
            "Compatible Models\n"
            "-----------------\n"
            "  OpenAI Whisper / Faster-Whisper\n"
            "  Facebook Wav2Vec2\n"
            "  HuBERT\n"
            "  NVIDIA NeMo\n"
            "  HuggingFace Speech Models\n\n"
            "License\n"
            "-------\n"
            "  See individual file metadata for origin information.\n"
        )
        self._atomic_write_text(self._p.readme_txt, text)

    # ── split helper ───────────────────────────────────────────────────────

    def _split(self, rows: list):
        n = len(rows)
        train_end = int(n * self._s.train)
        val_end = train_end + int(n * self._s.validation)
        return rows[:train_end], rows[train_end:val_end], rows[val_end:]

    # ── atomic writers ─────────────────────────────────────────────────────

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        shutil.move(str(tmp), str(path))

    @staticmethod
    def _atomic_write_csv(path: Path, fieldnames: List[str], rows: list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        shutil.move(str(tmp), str(path))

    def _ensure_dirs(self) -> None:
        for d in (self._p.original_dir, self._p.rejected_dir):
            d.mkdir(parents=True, exist_ok=True)
