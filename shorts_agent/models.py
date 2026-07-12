"""Typed domain objects passed between pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Scene:
    id: int
    narration: str          # spoken by the TTS voice
    image_prompt: str       # what the AI image shows
    duration_hint_s: float = 3.0

    # filled in at runtime
    audio_path: Optional[str] = None
    audio_duration: Optional[float] = None
    image_paths: List[str] = field(default_factory=list)   # 1-2 shots per scene
    clip_path: Optional[str] = None
    # caption chunks: (text, start_s, end_s) relative to the scene clip
    caption_chunks: List[Tuple[str, float, float]] = field(default_factory=list)


@dataclass
class VideoProject:
    topic: str
    hook: str
    visual_style: str
    music_mood: str
    cta: str
    scenes: List[Scene] = field(default_factory=list)

    # metadata for upload
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)

    # quality / safety
    fact_risk: str = ""        # low | medium | high | unknown (from fact-check)

    # A/B variant tags (fed back through analytics to learn what works)
    subtopic: str = ""
    hook_style: str = ""       # didyouknow | claim | question
    intro_card: bool = True

    # final artifact
    output_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    video_url: Optional[str] = None

    @property
    def total_duration(self) -> float:
        return sum((s.audio_duration or s.duration_hint_s) for s in self.scenes)
