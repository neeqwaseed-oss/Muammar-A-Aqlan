"""
Audio Processor
===============
Converts any supported audio format to the standard WAV format required for ASR:
  - Sample rate : 16 000 Hz
  - Channels    : Mono
  - Bit depth   : PCM 16-bit
  - Silence trimmed from head and tail
  - Loudness normalised

Depends on: pydub, ffmpeg (must be on PATH), numpy
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence
    from pydub.effects import normalize
except ImportError as e:  # pragma: no cover
    raise ImportError("pydub is required: pip install pydub") from e

from config.settings import AudioConfig
from utils.logger import get_logger
from utils.file_utils import compute_sha256

logger = get_logger(__name__)


@dataclass
class AudioProcessingResult:
    success: bool
    output_path: Optional[Path]
    duration_seconds: float
    sample_rate: int
    channels: int
    file_size_bytes: int
    original_format: str
    file_hash: str
    rejection_reason: Optional[str] = None


class AudioProcessor:
    """
    Accepts a raw audio file and produces a clean, standardised WAV file
    ready for transcription.  Returns an *AudioProcessingResult* that the
    pipeline uses for downstream steps.
    """

    def __init__(self, cfg: AudioConfig, temp_dir: Path) -> None:
        self._cfg = cfg
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._verify_ffmpeg()

    # ── public interface ───────────────────────────────────────────────────

    def process(self, src: Path, dst: Path) -> AudioProcessingResult:
        """
        Full pipeline:
          1. Detect format
          2. Load via pydub (uses ffmpeg internally for non-WAV)
          3. Validate duration
          4. Convert to mono / 16 kHz / 16-bit
          5. Trim silence
          6. Normalise loudness
          7. Detect speech presence
          8. Write to *dst*
          9. Return result
        """
        original_format = src.suffix.lstrip(".").lower()
        logger.info("Processing audio file: %s (format=%s)", src.name, original_format)

        # ── 1. load ──────────────────────────────────────────────────────
        try:
            seg = AudioSegment.from_file(str(src))
        except Exception as exc:
            return self._reject(
                src, original_format,
                f"Failed to load audio file: {exc}"
            )

        # ── 2. duration check (before conversion) ────────────────────────
        raw_duration = len(seg) / 1000.0
        if raw_duration < self._cfg.min_duration_seconds:
            return self._reject(
                src, original_format,
                f"Too short: {raw_duration:.2f}s < {self._cfg.min_duration_seconds}s"
            )

        # ── 3. convert: mono → target sample rate → 16-bit ───────────────
        seg = seg.set_channels(self._cfg.target_channels)
        seg = seg.set_frame_rate(self._cfg.target_sample_rate)
        seg = seg.set_sample_width(self._cfg.target_bit_depth // 8)

        # ── 4. silence trim ───────────────────────────────────────────────
        seg = self._trim_silence(seg)
        trimmed_duration = len(seg) / 1000.0

        if trimmed_duration < self._cfg.min_duration_seconds:
            return self._reject(
                src, original_format,
                f"After silence trim, too short: {trimmed_duration:.2f}s"
            )

        # ── 5. normalise loudness ─────────────────────────────────────────
        seg = normalize(seg)

        # ── 6. speech activity check ──────────────────────────────────────
        if not self._has_speech(seg):
            return self._reject(
                src, original_format,
                "No speech detected (VAD check failed)"
            )

        # ── 7. export ─────────────────────────────────────────────────────
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            seg.export(
                str(dst),
                format="wav",
                parameters=["-acodec", "pcm_s16le"],
            )
        except Exception as exc:
            return self._reject(
                src, original_format,
                f"Failed to export WAV: {exc}"
            )

        file_hash = compute_sha256(dst)
        file_size = dst.stat().st_size
        final_duration = len(seg) / 1000.0

        logger.info(
            "Audio processed successfully: %s → %s (%.2fs, %d bytes)",
            src.name, dst.name, final_duration, file_size,
        )

        return AudioProcessingResult(
            success=True,
            output_path=dst,
            duration_seconds=final_duration,
            sample_rate=seg.frame_rate,
            channels=seg.channels,
            file_size_bytes=file_size,
            original_format=original_format,
            file_hash=file_hash,
        )

    # ── private helpers ────────────────────────────────────────────────────

    def _trim_silence(self, seg: "AudioSegment") -> "AudioSegment":
        """Remove leading and trailing silence."""
        threshold = self._cfg.silence_threshold_db

        start_trim = detect_leading_silence(seg, silence_threshold=threshold)
        end_trim = detect_leading_silence(seg.reverse(), silence_threshold=threshold)

        duration_ms = len(seg)
        trimmed_start = start_trim
        trimmed_end = duration_ms - end_trim

        if trimmed_start >= trimmed_end:
            return seg  # Fully silent — caller will reject it
        return seg[trimmed_start:trimmed_end]

    def _has_speech(self, seg: "AudioSegment") -> bool:
        """
        Simple energy-based VAD:
        At least 10 % of 20 ms frames must be above the silence threshold.
        """
        frame_ms = 20
        threshold = self._cfg.silence_threshold_db
        total_frames = len(seg) // frame_ms
        if total_frames == 0:
            return False

        speech_frames = 0
        for i in range(total_frames):
            chunk = seg[i * frame_ms : (i + 1) * frame_ms]
            if chunk.dBFS > threshold:
                speech_frames += 1

        ratio = speech_frames / total_frames
        logger.debug("Speech ratio: %.2f", ratio)
        return ratio >= 0.10

    def _reject(
        self,
        src: Path,
        original_format: str,
        reason: str,
    ) -> AudioProcessingResult:
        logger.warning("Audio rejected (%s): %s", reason, src.name)
        # Compute hash of original file for duplicate detection even on rejection
        try:
            file_hash = compute_sha256(src)
            file_size = src.stat().st_size
        except Exception:
            file_hash = ""
            file_size = 0
        return AudioProcessingResult(
            success=False,
            output_path=None,
            duration_seconds=0.0,
            sample_rate=0,
            channels=0,
            file_size_bytes=file_size,
            original_format=original_format,
            file_hash=file_hash,
            rejection_reason=reason,
        )

    @staticmethod
    def _verify_ffmpeg() -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg not found on PATH.  "
                "Install it from https://ffmpeg.org and add it to your PATH."
            )
