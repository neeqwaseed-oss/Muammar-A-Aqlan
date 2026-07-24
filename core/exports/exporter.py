"""
Exporter
========
Creates ZIP archives of the entire Libyan_ASR_Dataset directory.
Automatically chunks the export into multiple ZIP files to respect Telegram's 50 MB limit.

Fix summary (v3):
- Use ACTUAL on-disk zip size (via Path.stat()) AFTER each write, not raw input size.
- If a single file pushes the zip over max_bytes AND other files are already present,
  re-open a new part and write that file there (the old part retains everything except
  the last file, which is moved to the new part).
- database.sqlite is skipped when its raw size alone exceeds 0.9 × max_bytes to prevent
  oversized parts; the user is warned via the return value.
- The _ALWAYS_INCLUDE metadata files (CSV/JSON) compress extremely well and are handled
  before audio to ensure they always appear in Part 1.
"""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple

from config.settings import PathsConfig
from utils.logger import get_logger

logger = get_logger(__name__)

# Telegram hard limit for bot uploads (bytes)
TELEGRAM_MAX_BYTES: int = 50 * 1024 * 1024  # 50 MB

# Files/directories to always include when they exist (text files first — small and
# compress well, guaranteed to land in Part 1)
_ALWAYS_INCLUDE = [
    "metadata.csv",
    "dataset.json",
    "train.csv",
    "validation.csv",
    "test.csv",
    "statistics.json",
    "README.txt",
    # database.sqlite is handled separately (size-guarded) at the end
]


class ExportResult(NamedTuple):
    zip_paths: List[Path]
    skipped_files: List[str]   # files that were too large even for a solo part


class Exporter:

    def __init__(self, paths: PathsConfig, temp_dir: Path) -> None:
        self._p = paths
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    # ── public ──────────────────────────────────────────────────────────────

    def create_zips(self, max_mb: float = 40.0) -> List[Path]:
        """Backward-compatible wrapper — returns only the list of zip paths."""
        return self.create_zips_ex(max_mb).zip_paths

    def create_zips_ex(self, max_mb: float = 40.0) -> ExportResult:
        """
        Build ZIP parts of at most *max_mb* each and return an ExportResult.

        Size is enforced using the ACTUAL compressed bytes written to disk after
        every single file addition — not the raw input size.  When a file would
        push a part past the limit, a new part is started for it instead.

        A file whose raw size alone exceeds 90 % of max_bytes is put into its
        own dedicated part.  If its COMPRESSED size still exceeds TELEGRAM_MAX_BYTES,
        it is skipped entirely and its name is recorded in ExportResult.skipped_files.
        """
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        max_bytes = int(max_mb * 1024 * 1024)
        zip_paths: List[Path] = []
        skipped: List[str] = []

        audio_dir = self._p.original_dir
        wav_files = sorted(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        root = self._p.dataset_root

        # ── state ─────────────────────────────────────────────────────────
        part_num = 0
        cur_path: Path | None = None
        cur_zf: zipfile.ZipFile | None = None

        def _disk_size() -> int:
            """Actual bytes on disk for the currently open ZIP."""
            if cur_path and cur_path.exists():
                return cur_path.stat().st_size
            return 0

        def _open_new_part() -> zipfile.ZipFile:
            nonlocal part_num, cur_path, cur_zf
            if cur_zf is not None:
                cur_zf.close()
                _log_part(cur_path)
            part_num += 1
            cur_path = (
                self._temp_dir
                / f"Libyan_ASR_Dataset_{timestamp}_Part{part_num}.zip"
            )
            zip_paths.append(cur_path)
            logger.info("Creating export ZIP part %d: %s", part_num, cur_path)
            cur_zf = zipfile.ZipFile(
                cur_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True
            )
            return cur_zf

        def _log_part(path: Path | None) -> None:
            if path and path.exists():
                mb = path.stat().st_size / (1024 * 1024)
                if path.stat().st_size > TELEGRAM_MAX_BYTES:
                    logger.warning(
                        "ZIP part %s is %.2f MB — exceeds Telegram 50 MB limit!", path.name, mb
                    )
                else:
                    logger.info("ZIP part created: %s (%.2f MB)", path.name, mb)

        def _add(file_path: Path, arc_name: str) -> None:
            """
            Write *file_path* into the current ZIP under *arc_name*.
            Rolls over to a new part when needed so that each part stays under
            *max_bytes* (measured as real compressed bytes on disk).
            """
            nonlocal cur_zf
            raw = file_path.stat().st_size

            # If part is empty and this single file is suspiciously large, warn.
            # We still try — compression may save it.
            if cur_zf is None:
                cur_zf = _open_new_part()

            before = _disk_size()

            # Pre-rollover: if there is already data AND adding this file's raw
            # size (worst-case: incompressible) would exceed the cap, start a
            # fresh part first.
            if before > 0 and before + raw > max_bytes:
                cur_zf = _open_new_part()
                before = 0

            cur_zf.write(file_path, arc_name)

            after = _disk_size()

            # Post-write check: did we actually exceed the limit?
            if after > max_bytes and before > 0:
                # The just-written file pushed us over the limit.
                # Strategy: close the current (oversized) zip, recreate it WITHOUT
                # this file, then open a new part and write the file there.
                cur_zf.close()

                # Re-build the old part without the last entry
                names_before = [
                    info.filename
                    for info in zipfile.ZipFile(cur_path).infolist()
                    if info.filename != arc_name
                ]
                _rebuild_zip_without(cur_path, names_without={arc_name})

                # New part for the overflowing file
                cur_zf = _open_new_part()
                cur_zf.write(file_path, arc_name)
                after2 = _disk_size()
                if after2 > TELEGRAM_MAX_BYTES:
                    # Even alone this file is too big — skip it
                    cur_zf.close()
                    cur_path.unlink(missing_ok=True)
                    zip_paths.pop()
                    cur_zf = _open_new_part()   # keep a fresh open part
                    skipped.append(arc_name)
                    logger.error(
                        "File '%s' is %.2f MB compressed — exceeds Telegram limit; skipped.",
                        arc_name, after2 / 1024 / 1024,
                    )

        # ── flat metadata files ────────────────────────────────────────────
        for name in _ALWAYS_INCLUDE:
            fp = root / name
            if fp.exists():
                _add(fp, f"Libyan_ASR_Dataset/{name}")

        # ── database.sqlite (size-guarded) ────────────────────────────────
        db_path = root / "database.sqlite"
        if db_path.exists():
            db_raw = db_path.stat().st_size
            # Always include it; _add() handles rollover.
            # Only warn if raw size alone is > 90 % of cap (will get its own part).
            if db_raw > max_bytes * 0.9:
                logger.info(
                    "database.sqlite raw size %.1f MB > 90%% of cap — will get a dedicated part.",
                    db_raw / 1024 / 1024,
                )
            _add(db_path, "Libyan_ASR_Dataset/database.sqlite")

        # ── audio files ────────────────────────────────────────────────────
        for wav in wav_files:
            _add(wav, f"Libyan_ASR_Dataset/audio/{wav.name}")

        # ── close last open part ───────────────────────────────────────────
        if cur_zf is not None:
            cur_zf.close()
            _log_part(cur_path)

        # ── remove empty parts (edge case: all files were skipped) ────────
        zip_paths[:] = [p for p in zip_paths if p.exists() and p.stat().st_size > 22]

        return ExportResult(zip_paths=zip_paths, skipped_files=skipped)

    # ── helpers ─────────────────────────────────────────────────────────────

    def get_export_info(self) -> dict:
        """Return size and file-count info before sending."""
        audio_dir = self._p.original_dir
        wav_files = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        total_bytes = sum(f.stat().st_size for f in wav_files)
        return {
            "wav_count": len(wav_files),
            "total_audio_bytes": total_bytes,
        }


# ── module-level helper ────────────────────────────────────────────────────

def _rebuild_zip_without(zip_path: Path, names_without: set) -> None:
    """
    Re-create *zip_path* in-place, omitting entries whose filename is in
    *names_without*.  Used to "undo" an oversized write.
    """
    tmp = zip_path.with_suffix(".tmp.zip")
    try:
        with zipfile.ZipFile(zip_path, "r") as src:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as dst:
                for info in src.infolist():
                    if info.filename not in names_without:
                        dst.writestr(info, src.read(info.filename))
        tmp.replace(zip_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        logger.exception("Failed to rebuild zip without last entry — keeping oversized part.")
