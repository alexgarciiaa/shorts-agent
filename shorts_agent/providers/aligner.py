"""Word-level caption timing via faster-whisper.

Edge TTS only exposes sentence boundaries now, so we transcribe the generated
narration with word timestamps to drive perfectly-synced karaoke captions. The
model is loaded lazily and reused; if faster-whisper isn't installed, align()
returns [] and the caller falls back to estimated timing.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

log = logging.getLogger(__name__)

WordTiming = Tuple[str, float, float]


class WhisperAligner:
    def __init__(self, model_size: str = "base", device: str = "cpu",
                 compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._unavailable = False

    def _ensure_model(self):
        if self._model is None and not self._unavailable:
            try:
                from faster_whisper import WhisperModel
                log.info("Loading whisper model '%s' (first run downloads it)...",
                         self.model_size)
                self._model = WhisperModel(self.model_size, device=self.device,
                                           compute_type=self.compute_type)
            except Exception as exc:  # noqa: BLE001
                log.warning("Whisper unavailable (%s); captions will use estimation", exc)
                self._unavailable = True
        return self._model

    def align(self, audio_path: str, language: str = "en") -> List[WordTiming]:
        model = self._ensure_model()
        if model is None:
            return []
        try:
            segments, _ = model.transcribe(audio_path, language=language,
                                           word_timestamps=True)
            words: List[WordTiming] = []
            for seg in segments:
                for w in (seg.words or []):
                    token = w.word.strip()
                    if token:
                        words.append((token, float(w.start), float(w.end)))
            return words
        except Exception as exc:  # noqa: BLE001
            log.warning("Whisper alignment failed (%s); using estimation", exc)
            return []
