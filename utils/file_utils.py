"""
General file utilities used across all modules.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def compute_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Return the SHA-256 hex digest of *file_path* without loading it fully into RAM."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path: Path) -> Path:
    """Create *path* (and parents) if it does not exist; return *path*."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def human_readable_size(num_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def safe_move(src: Path, dst: Path) -> Path:
    """Move *src* to *dst*, creating parent directories as needed."""
    ensure_dir(dst.parent)
    shutil.move(str(src), str(dst))
    return dst


def safe_copy(src: Path, dst: Path) -> Path:
    """Copy *src* to *dst*, creating parent directories as needed."""
    ensure_dir(dst.parent)
    shutil.copy2(str(src), str(dst))
    return dst
