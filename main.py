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
"""

from __future__ import annotations

import sys
from pathlib import Path

# ── make the project root importable ──────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import get_settings
from utils.logger import setup_logger, get_logger


def main() -> None:
    cfg = get_settings()

    # Initialise logging as the very first action
    setup_logger(
        logs_dir=cfg.paths.logs_dir,
        level=cfg.logging.level,
        max_file_size_mb=cfg.logging.max_file_size_mb,
        backup_count=cfg.logging.backup_count,
    )
    logger = get_logger("main")
    logger.info("=" * 60)
    logger.info("Libyan ASR Dataset Builder Bot starting…")
    logger.info("Dataset root: %s", cfg.paths.dataset_root)
    logger.info("Model: %s | Device: %s", cfg.transcription.model_size, cfg.transcription.device)

    # Ensure required directories exist
    for attr in (
        "original_dir", "rejected_dir", "temp_dir", "logs_dir",
    ):
        path = getattr(cfg.paths, attr)
        path.mkdir(parents=True, exist_ok=True)

    # Import and run the bot (blocks until Ctrl-C)
    from bot.bot import run_bot
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Interrupted by user.  Goodbye.")
    except Exception:
        logger.exception("Fatal error — bot stopped.")
        sys.exit(1)


if __name__ == "__main__":
    main()
