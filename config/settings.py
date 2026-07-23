"""
Settings loader — reads config/config.yaml and exposes a typed dataclass.
All paths are resolved relative to the project root so the bot works
regardless of the working directory it is launched from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


# Resolve the project root once at import time
_CONFIG_PATH = Path(__file__).parent / "config.yaml"
_PROJECT_ROOT = Path(__file__).parent.parent


# ── typed sub-configs ──────────────────────────────────────────────────────

@dataclass
class TelegramConfig:
    token: str
    allowed_users: List[int] = field(default_factory=list)


@dataclass
class PathsConfig:
    dataset_root: Path
    audio_dir: Path
    original_dir: Path
    rejected_dir: Path
    temp_dir: Path
    logs_dir: Path
    db_file: Path
    metadata_csv: Path
    dataset_json: Path
    train_csv: Path
    validation_csv: Path
    test_csv: Path
    statistics_json: Path
    readme_txt: Path


@dataclass
class AudioConfig:
    target_sample_rate: int
    target_channels: int
    target_bit_depth: int
    min_duration_seconds: float
    max_duration_seconds: float
    silence_threshold_db: float
    normalize_target_db: float
    supported_formats: List[str]


@dataclass
class TranscriptionConfig:
    model_size: str
    device: str
    compute_type: str
    language: Optional[str]
    min_confidence: float
    beam_size: int
    vad_filter: bool


@dataclass
class SplitsConfig:
    train: float
    validation: float
    test: float


@dataclass
class ProcessingConfig:
    queue_workers: int
    max_retries: int
    retry_delay_seconds: int


@dataclass
class LoggingConfig:
    level: str
    max_file_size_mb: int
    backup_count: int


# ── main settings object ───────────────────────────────────────────────────

@dataclass
class Settings:
    telegram: TelegramConfig
    paths: PathsConfig
    audio: AudioConfig
    transcription: TranscriptionConfig
    splits: SplitsConfig
    processing: ProcessingConfig
    logging: LoggingConfig


def _resolve(base: Path, rel: str) -> Path:
    """Resolve a relative path string against *base*."""
    p = Path(rel)
    return p if p.is_absolute() else base / p


def load_settings(config_path: Path = _CONFIG_PATH) -> Settings:
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    dataset_root = _resolve(_PROJECT_ROOT, raw["paths"]["dataset_root"])
    p = raw["paths"]

    return Settings(
        telegram=TelegramConfig(**raw["telegram"]),
        paths=PathsConfig(
            dataset_root=dataset_root,
            audio_dir=dataset_root / p["audio_dir"],
            original_dir=dataset_root / p["original_dir"],
            rejected_dir=dataset_root / p["rejected_dir"],
            temp_dir=_resolve(_PROJECT_ROOT, p["temp_dir"]),
            logs_dir=_resolve(_PROJECT_ROOT, p["logs_dir"]),
            db_file=dataset_root / p["db_file"],
            metadata_csv=dataset_root / p["metadata_csv"],
            dataset_json=dataset_root / p["dataset_json"],
            train_csv=dataset_root / p["train_csv"],
            validation_csv=dataset_root / p["validation_csv"],
            test_csv=dataset_root / p["test_csv"],
            statistics_json=dataset_root / p["statistics_json"],
            readme_txt=dataset_root / p["readme_txt"],
        ),
        audio=AudioConfig(**raw["audio"]),
        transcription=TranscriptionConfig(**raw["transcription"]),
        splits=SplitsConfig(**raw["splits"]),
        processing=ProcessingConfig(**raw["processing"]),
        logging=LoggingConfig(**raw["logging"]),
    )


# ── module-level singleton ─────────────────────────────────────────────────

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
