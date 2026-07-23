"""
Speech Transcriber
==================
Wraps Faster-Whisper to transcribe WAV files to Arabic text.

Returns a *TranscriptionResult* with:
  - transcript text
  - detected language
  - average confidence (mean segment probability)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.settings import TranscriptionConfig
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TranscriptionResult:
    success: bool
    text: str
    language: str
    confidence: float
    rejection_reason: Optional[str] = None


class Transcriber:
    """
    Lazy-loads the Faster-Whisper model on first use so startup is fast
    even when the model is large.
    """

    def __init__(self, cfg: TranscriptionConfig) -> None:
        self._cfg = cfg
        self._model = None  # loaded lazily

    # ── public interface ───────────────────────────────────────────────────

    def transcribe(self, wav_path: Path) -> TranscriptionResult:
        """Transcribe a 16 kHz mono WAV file and return a *TranscriptionResult*."""
        logger.info("Transcribing: %s", wav_path.name)

        model = self._get_model()

        try:
            segments, info = model.transcribe(
                str(wav_path),
                language=self._cfg.language or None,
                beam_size=self._cfg.beam_size,
                vad_filter=self._cfg.vad_filter,
                word_timestamps=False,
            )
        except Exception as exc:
            return self._reject(f"Transcription error: {exc}")

        # Collect segments eagerly (generator)
        seg_list = list(segments)

        if not seg_list:
            return self._reject("No speech segments returned by Whisper")

        # Build full transcript text
        full_text = " ".join(s.text.strip() for s in seg_list).strip()

        if not full_text:
            return self._reject("Transcript is empty after joining segments")

        # Average log-probability → linear probability as confidence proxy
        avg_logprob = sum(s.avg_logprob for s in seg_list) / len(seg_list)
        # avg_logprob is in (-∞, 0]; map to (0, 1] via exp
        import math
        confidence = math.exp(avg_logprob)

        language = info.language or (self._cfg.language or "unknown")

        logger.info(
            "Transcription done | lang=%s | conf=%.3f | text='%s...'",
            language, confidence, full_text[:60],
        )

        if confidence < self._cfg.min_confidence:
            return self._reject(
                f"Confidence too low: {confidence:.3f} < {self._cfg.min_confidence}"
            )

        return TranscriptionResult(
            success=True,
            text=full_text,
            language=language,
            confidence=confidence,
        )

    # ── private helpers ────────────────────────────────────────────────────

    def _get_model(self):
        if self._model is None:
            logger.info(
                "Loading Faster-Whisper model '%s' on %s (%s)…",
                self._cfg.model_size, self._cfg.device, self._cfg.compute_type,
            )
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ImportError(
                    "faster-whisper is required: pip install faster-whisper"
                ) from exc

            self._model = WhisperModel(
                self._cfg.model_size,
                device=self._cfg.device,
                compute_type=self._cfg.compute_type,
            )
            logger.info("Model loaded successfully.")
        return self._model

    @staticmethod
    def _reject(reason: str) -> TranscriptionResult:
        logger.warning("Transcription rejected: %s", reason)
        return TranscriptionResult(
            success=False,
            text="",
            language="unknown",
            confidence=0.0,
            rejection_reason=reason,
        )
