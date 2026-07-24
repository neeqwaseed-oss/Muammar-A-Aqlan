"""
Exporter  (v4 — single-archive, Saved Messages)
================================================
Creates a single ZIP archive of the entire dataset and, if it exceeds
Telegram's 50 MB upload limit, splits it into numbered binary parts that
can be reassembled on any system.

Split-file format
-----------------
Parts are named:
    Libyan_ASR_Dataset_<timestamp>_part01.zip   ← extract this one
    Libyan_ASR_Dataset_<timestamp>_part02.zip.part
    Libyan_ASR_Dataset_<timestamp>_part03.zip.part
    …

To reassemble on Linux/macOS:
    cat Libyan_ASR_Dataset_*_part*.zip* > full.zip && unzip full.zip

To reassemble on Windows (PowerShell):
    Get-Content Libyan_ASR_Dataset_*_part*.zip* -Encoding Byte -Raw |
        Set-Content full.zip -Encoding Byte
"""

from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple

from config.settings import PathsConfig
from utils.logger import get_logger

logger = get_logger(__name__)

TELEGRAM_MAX_BYTES: int = 49 * 1024 * 1024   # 49 MB — safe margin under 50 MB

# Metadata files to always include (small text files, land in archive first)
_ALWAYS_INCLUDE = [
    "metadata.csv",
    "dataset.json",
    "train.csv",
    "validation.csv",
    "test.csv",
    "statistics.json",
    "README.txt",
]


class ExportResult(NamedTuple):
    """Outcome of create_export()."""
    parts: List[Path]          # ordered list of file parts to send
    total_bytes: int           # sum of all parts on disk
    original_zip: Path | None  # the full ZIP before splitting (may equal parts[0])
    split: bool                # True when more than one part was produced


class Exporter:

    def __init__(self, paths: PathsConfig, temp_dir: Path) -> None:
        self._p = paths
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    # ── public: single-archive export ──────────────────────────────────────

    def create_export(self) -> ExportResult:
        """
        Build a single ZIP of the whole dataset, then split it into ≤49 MB
        parts if necessary.  Returns an ExportResult describing the parts.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_path  = self._temp_dir / f"Libyan_ASR_Dataset_{timestamp}.zip"

        self._build_zip(zip_path)

        total = zip_path.stat().st_size
        logger.info("Archive created: %s (%.2f MB)", zip_path.name, total / 1e6)

        if total <= TELEGRAM_MAX_BYTES:
            return ExportResult(
                parts=[zip_path],
                total_bytes=total,
                original_zip=zip_path,
                split=False,
            )

        # Split into binary parts
        parts = self._split_zip(zip_path, timestamp)
        total_split = sum(p.stat().st_size for p in parts)
        return ExportResult(
            parts=parts,
            total_bytes=total_split,
            original_zip=zip_path,
            split=True,
        )

    # ── backward-compat wrappers used by old code ──────────────────────────

    def create_zips(self, max_mb: float = 40.0) -> List[Path]:
        """Legacy: return list of split parts (or single zip)."""
        return self.create_export().parts

    def create_zips_ex(self, max_mb: float = 40.0):  # → ExportResult
        return self.create_export()

    # ── helpers ─────────────────────────────────────────────────────────────

    def _build_zip(self, out_path: Path) -> None:
        """Write the complete dataset into a single ZIP at *out_path*."""
        root      = self._p.dataset_root
        audio_dir = self._p.original_dir
        wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            # ── metadata files ────────────────────────────────────────────
            for name in _ALWAYS_INCLUDE:
                fp = root / name
                if fp.exists():
                    zf.write(fp, f"Libyan_ASR_Dataset/{name}")
                    logger.debug("+ %s", name)

            # ── database.sqlite ───────────────────────────────────────────
            db = root / "database.sqlite"
            if db.exists():
                zf.write(db, "Libyan_ASR_Dataset/database.sqlite")
                logger.debug("+ database.sqlite (%.1f MB raw)", db.stat().st_size / 1e6)

            # ── audio files ───────────────────────────────────────────────
            for wav in wav_files:
                zf.write(wav, f"Libyan_ASR_Dataset/audio/{wav.name}")

        logger.info(
            "ZIP built: %d audio files, %.2f MB on disk",
            len(wav_files),
            out_path.stat().st_size / 1e6,
        )

    def _split_zip(self, zip_path: Path, timestamp: str) -> List[Path]:
        """
        Split *zip_path* into TELEGRAM_MAX_BYTES-sized binary chunks.
        First part is named  …_part01.zip  (directly openable in ZIP tools).
        Subsequent parts:    …_part02.zip.part, …_part03.zip.part, …
        """
        chunk = TELEGRAM_MAX_BYTES
        total = zip_path.stat().st_size
        n_parts = (total + chunk - 1) // chunk
        logger.info("Splitting %.2f MB archive into %d parts…", total / 1e6, n_parts)

        parts: List[Path] = []
        with open(zip_path, "rb") as src:
            for i in range(1, n_parts + 1):
                if i == 1:
                    part_path = self._temp_dir / (
                        f"Libyan_ASR_Dataset_{timestamp}_part{i:02d}.zip"
                    )
                else:
                    part_path = self._temp_dir / (
                        f"Libyan_ASR_Dataset_{timestamp}_part{i:02d}.zip.part"
                    )
                data = src.read(chunk)
                part_path.write_bytes(data)
                parts.append(part_path)
                logger.info(
                    "Part %d/%d: %s (%.2f MB)",
                    i, n_parts, part_path.name,
                    part_path.stat().st_size / 1e6,
                )

        return parts

    # ── info helpers ─────────────────────────────────────────────────────────

    def get_export_info(self) -> dict:
        audio_dir = self._p.original_dir
        wav_files = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        total_bytes = sum(f.stat().st_size for f in wav_files)
        return {"wav_count": len(wav_files), "total_audio_bytes": total_bytes}
