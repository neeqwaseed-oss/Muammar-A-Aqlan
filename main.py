#!/usr/bin/env python3
"""
Libyan ASR Dataset Builder Bot
================================
Entry point.  Run this file to start the bot:

    python main.py

Prerequisites:
  1. Install dependencies:  pip install -r requirements.txt
  2. Install ffmpeg and add it to PATH:  https://ffmpeg.org
  3. Set your bot token in config/config.yaml → telegram.token

Conflict-prevention
-------------------
A PID lock file is written to ``temp/bot.pid`` on startup and removed
on clean exit.  If the file already exists and the recorded PID is still
alive, startup is aborted with a clear message — preventing the
409 Conflict error that occurs when two instances poll simultaneously.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

# ── make the project root importable ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))


def _acquire_pid_lock(pid_file: Path) -> bool:
    """
    Try to acquire a PID lock file.
    Returns True if this process may proceed, False if another instance
    is already running.
    """
    pid_file.parent.mkdir(parents=True, exist_ok=True)

    if pid_file.exists():
        try:
            existing_pid = int(pid_file.read_text().strip())
            # Check if the process is still alive
            os.kill(existing_pid, 0)  # signal 0 = check existence only
            # If we get here, the process is alive → another instance running
            print(
                f"\n⚠️  خطأ: البوت يعمل بالفعل (PID {existing_pid}).\n"
                f"   أوقف النسخة الأخرى أولاً ثم أعد التشغيل.\n"
                f"   أو احذف ملف القفل يدوياً: {pid_file}\n",
                file=sys.stderr,
            )
            return False
        except (ProcessLookupError, ValueError):
            # Process is dead or PID file is corrupt — safe to overwrite
            pid_file.unlink(missing_ok=True)

    pid_file.write_text(str(os.getpid()))
    return True


def _release_pid_lock(pid_file: Path) -> None:
    try:
        pid_file.unlink(missing_ok=True)
    except Exception:
        pass


def main() -> None:
    from config.settings import get_settings
    from utils.logger import setup_logger, get_logger

    cfg = get_settings()

    # ── Initialise logging first ───────────────────────────────────────────
    setup_logger(
        logs_dir=cfg.paths.logs_dir,
        level=cfg.logging.level,
        max_file_size_mb=cfg.logging.max_file_size_mb,
        backup_count=cfg.logging.backup_count,
    )
    logger = get_logger("main")

    # ── PID lock — prevent duplicate instances (→ 409 Conflict) ──────────
    pid_file = cfg.paths.temp_dir / "bot.pid"
    if not _acquire_pid_lock(pid_file):
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("🚀 Libyan ASR Dataset Builder Bot starting…")
    logger.info("Dataset root : %s", cfg.paths.dataset_root)
    logger.info("Model        : %s | Device: %s",
                cfg.transcription.model_size, cfg.transcription.device)
    logger.info("PID lock     : %s", pid_file)

    # ── Ensure required directories exist ─────────────────────────────────
    for attr in ("original_dir", "rejected_dir", "temp_dir", "logs_dir"):
        getattr(cfg.paths, attr).mkdir(parents=True, exist_ok=True)

    # ── Run the bot ────────────────────────────────────────────────────────
    from bot.bot import run_bot
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("⏹ Interrupted by user.  Goodbye.")
    except Exception:
        logger.exception("💥 Fatal error — bot stopped.")
        sys.exit(1)
    finally:
        _release_pid_lock(pid_file)
        logger.info("🔓 PID lock released.")


if __name__ == "__main__":
    main()
