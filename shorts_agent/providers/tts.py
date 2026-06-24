"""Text-to-speech via edge-tts (Microsoft neural voices, free, no API key).

Word-level caption timing comes from the WhisperAligner (Edge TTS only exposes
sentence boundaries), so this just renders the mp3 and reports its duration.
"""
from __future__ import annotations

import asyncio
import logging

import edge_tts
from mutagen.mp3 import MP3

log = logging.getLogger(__name__)


class EdgeTTSProvider:
    def __init__(self, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    def synth(self, text: str, out_path: str) -> float:
        """Synthesize `text` to an mp3 at `out_path`; return its duration in seconds."""
        asyncio.run(self._synth(text, out_path))
        duration = self.duration(out_path)
        log.info("TTS  %5.2fs  %s", duration, text[:48])
        return duration

    async def _synth(self, text: str, out_path: str) -> None:
        communicate = edge_tts.Communicate(text, self.voice, rate=self.rate,
                                           pitch=self.pitch)
        await communicate.save(out_path)

    @staticmethod
    def duration(path: str) -> float:
        return float(MP3(path).info.length)
