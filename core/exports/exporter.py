"""
Exporter
========
Creates a ZIP archive of the entire Libyan_ASR_Dataset directory
and returns the Path to the archive so the bot can send it via Telegram.

The archive is built incrementally to avoid loading large files into RAM.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config.settings import PathsConfig
from utils.logger import get_logger

logger = get_logger(__name__)

# Files/directories to always include when they exist
_ALWAYS_INCLUDE = [
    "metadata.csv",
    "dataset.json",
    "database.sqlite",
    "train.csv",
    "validation.csv",
    "test.csv",
    "statistics.json",
    "README.txt",
]


class Exporter:

    def __init__(self, paths: PathsConfig, temp_dir: Path) -> None:
        self._p = paths
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def create_zip(self) -> Path:
        """
        Build a ZIP file containing the entire dataset and return its path.
        The caller is responsible for deleting the file after sending it.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_path = self._temp_dir / f"Libyan_ASR_Dataset_{timestamp}.zip"

        logger.info("Creating export ZIP: %s", zip_path)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            root = self._p.dataset_root

            # ── flat metadata / index files ──────────────────────────────
            for name in _ALWAYS_INCLUDE:
                file_path = root / name
                if file_path.exists():
                    arc_name = f"Libyan_ASR_Dataset/{name}"
                    zf.write(file_path, arc_name)
                    logger.debug("Added: %s", arc_name)

            # ── audio files (original accepted) ──────────────────────────
            audio_dir = self._p.original_dir
            if audio_dir.exists():
                for wav in sorted(audio_dir.glob("*.wav")):
                    arc_name = f"Libyan_ASR_Dataset/audio/{wav.name}"
                    zf.write(wav, arc_name)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info("ZIP created: %s (%.2f MB)", zip_path.name, size_mb)
        return zip_path

    def get_export_info(self) -> dict:
        """Return size and file-count info before sending."""
        root = self._p.dataset_root
        audio_dir = self._p.original_dir
        wav_files = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        total_bytes = sum(f.stat().st_size for f in wav_files)
        return {
            "wav_count": len(wav_files),
            "total_audio_bytes": total_bytes,
        }
