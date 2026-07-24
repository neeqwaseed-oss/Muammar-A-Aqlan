"""
Exporter
========
Creates ZIP archives of the entire Libyan_ASR_Dataset directory.
Automatically chunks the export into multiple ZIP files to respect Telegram's 50MB limit.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

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

    def create_zips(self, max_mb: float = 45.0) -> List[Path]:
        """
        Build ZIP files containing the entire dataset and return a list of paths.
        Limits each ZIP to approximately `max_mb` to avoid Telegram upload limits.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        max_bytes = max_mb * 1024 * 1024
        zip_paths: List[Path] = []

        audio_dir = self._p.original_dir
        wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []

        part_num = 1
        current_zip = None
        current_size = 0

        def start_new_zip():
            nonlocal part_num, current_zip, current_size
            zp = self._temp_dir / f"Libyan_ASR_Dataset_{timestamp}_Part{part_num}.zip"
            zip_paths.append(zp)
            logger.info("Creating export ZIP part %d: %s", part_num, zp)
            current_zip = zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED, allowZip64=True)
            current_size = 0
            part_num += 1
            return current_zip

        zf = start_new_zip()
        root = self._p.dataset_root

        # ── flat metadata / index files (Put in Part 1) ───────────────
        for name in _ALWAYS_INCLUDE:
            file_path = root / name
            if file_path.exists():
                arc_name = f"Libyan_ASR_Dataset/{name}"
                zf.write(file_path, arc_name)
                current_size += file_path.stat().st_size
                logger.debug("Added: %s", arc_name)

        # ── audio files (original accepted) ──────────────────────────
        for wav in wav_files:
            file_size = wav.stat().st_size
            
            # إذا كان إضافة هذا الملف سيتجاوز الحد المسموح (والملف الحالي ليس فارغاً)، افتح ملفاً جديداً
            if current_size + file_size > max_bytes and current_size > 0:
                zf.close()
                zf = start_new_zip()

            arc_name = f"Libyan_ASR_Dataset/audio/{wav.name}"
            zf.write(wav, arc_name)
            current_size += file_size

        zf.close()
        
        for zp in zip_paths:
            size_mb = zp.stat().st_size / (1024 * 1024)
            logger.info("ZIP part created: %s (%.2f MB)", zp.name, size_mb)
            
        return zip_paths

    def get_export_info(self) -> dict:
        """Return size and file-count info before sending."""
        audio_dir = self._p.original_dir
        wav_files = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        total_bytes = sum(f.stat().st_size for f in wav_files)
        return {
            "wav_count": len(wav_files),
            "total_audio_bytes": total_bytes,
        }
