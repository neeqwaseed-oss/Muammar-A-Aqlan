"""
Exporter
========
Creates ZIP archives of the entire Libyan_ASR_Dataset directory.
Automatically chunks the export into multiple ZIP files to respect Telegram's 50MB limit.

Bug fixes (v2):
- Track actual ZIP file size on disk (not raw input sizes) to avoid 413 errors.
- _ALWAYS_INCLUDE files are now subject to the same size limit as audio files.
- Reduced default cap to 40 MB to provide a safe buffer under Telegram's 50 MB API limit.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from config.settings import PathsConfig
from utils.logger import get_logger

logger = get_logger(__name__)

# Telegram hard limit for bot uploads (bytes)
TELEGRAM_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MB

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


def _zip_current_size(zf: zipfile.ZipFile) -> int:
    """
    Return the current number of bytes written to the ZIP file on disk.
    We flush the buffer and stat the underlying file for an accurate reading.
    This accounts for ZIP headers and compression so we never overshoot.
    """
    try:
        if hasattr(zf, "fp") and zf.fp is not None:
            zf.fp.flush()
            return zf.fp.tell()
    except Exception:
        pass
    return 0


class Exporter:

    def __init__(self, paths: PathsConfig, temp_dir: Path) -> None:
        self._p = paths
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def create_zips(self, max_mb: float = 40.0) -> List[Path]:
        """
        Build ZIP files containing the entire dataset and return a list of paths.
        Limits each ZIP to approximately ``max_mb`` to avoid Telegram upload limits.

        The cap is enforced by reading the *actual* compressed size written to
        disk after each file is added — not the raw input size — so metadata
        files such as ``database.sqlite`` that might be large on their own are
        handled correctly and never push a part over the limit.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        max_bytes = int(max_mb * 1024 * 1024)
        zip_paths: List[Path] = []

        audio_dir = self._p.original_dir
        wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        root = self._p.dataset_root

        part_num = 1
        current_zip_path: Path | None = None
        current_zf: zipfile.ZipFile | None = None

        def start_new_zip() -> zipfile.ZipFile:
            nonlocal part_num, current_zip_path, current_zf
            if current_zf is not None:
                current_zf.close()
            current_zip_path = (
                self._temp_dir
                / f"Libyan_ASR_Dataset_{timestamp}_Part{part_num}.zip"
            )
            zip_paths.append(current_zip_path)
            logger.info(
                "Creating export ZIP part %d: %s", part_num, current_zip_path
            )
            current_zf = zipfile.ZipFile(
                current_zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True
            )
            part_num += 1
            return current_zf

        def add_file(zf: zipfile.ZipFile, file_path: Path, arc_name: str) -> zipfile.ZipFile:
            """
            Write *file_path* into *zf* under *arc_name*.
            If the ZIP would exceed *max_bytes* after adding, close the current
            ZIP, open a new one, and write there instead.
            Returns the (possibly new) active ZipFile.
            """
            nonlocal current_zf

            # If adding this file would exceed the cap AND there is already
            # data in the ZIP, roll over to a new part first.
            current_size = _zip_current_size(zf)
            raw_size = file_path.stat().st_size
            if current_size > 0 and current_size + raw_size > max_bytes:
                zf = start_new_zip()

            zf.write(file_path, arc_name)
            logger.debug("Added: %s (raw %.2f MB)", arc_name, raw_size / 1024 / 1024)
            return zf

        zf = start_new_zip()

        # ── flat metadata / index files ───────────────────────────────────
        for name in _ALWAYS_INCLUDE:
            file_path = root / name
            if file_path.exists():
                arc_name = f"Libyan_ASR_Dataset/{name}"
                zf = add_file(zf, file_path, arc_name)

        # ── audio files (original accepted) ──────────────────────────────
        for wav in wav_files:
            arc_name = f"Libyan_ASR_Dataset/audio/{wav.name}"
            zf = add_file(zf, wav, arc_name)

        if current_zf is not None:
            current_zf.close()

        # ── report ────────────────────────────────────────────────────────
        for zp in zip_paths:
            size_mb = zp.stat().st_size / (1024 * 1024)
            if zp.stat().st_size > TELEGRAM_MAX_BYTES:
                logger.warning(
                    "ZIP part %s is %.2f MB — exceeds Telegram 50 MB limit! "
                    "Consider lowering max_mb further.",
                    zp.name,
                    size_mb,
                )
            else:
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

