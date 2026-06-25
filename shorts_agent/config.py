"""Central configuration. MVP keeps it as a dataclass + env overrides;
Fase 1 will load this from config.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # --- canvas / video ---
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # --- voice (edge-tts) ---
    tts_voice: str = "en-US-AndrewMultilingualNeural"  # warm, natural, human-sounding
    tts_rate: str = "+15%"                   # snappy "shorts" pacing
    tts_pitch: str = "+0Hz"
    scene_tail_seconds: float = 0.05         # silence held after each scene's speech

    # --- images (Pollinations) ---
    image_model: str = "flux"
    image_enhance: bool = False              # OFF: enhance is very slow (~45s/img) and doesn't raise resolution
    image_upscale: float = 2.0              # render motion at Nx then downscale (anti-judder)
    image_sharpen: bool = True               # LANCZOS scaling + unsharp to fight pixelation
    # Pollinations anonymous tier caps output at ~576x1024; a free token unlocks
    # native high resolution. Set env POLLINATIONS_TOKEN to use it.
    pollinations_token: str = field(default_factory=lambda: os.environ.get("POLLINATIONS_TOKEN", ""))
    visual_style_default: str = (
        "cinematic, dramatic cinematic lighting, ultra-detailed, razor sharp focus, "
        "8k, highly detailed, professional color grading, masterpiece"
    )
    # rotated per shot to force variety while keeping a cohesive look
    art_directions: tuple = (
        "wide establishing shot, epic scale",
        "extreme close-up, macro detail, shallow depth of field",
        "low angle dramatic hero shot",
        "aerial top-down view",
        "dynamic dutch angle, motion",
        "symmetrical centered composition",
    )
    # ~1 image per N seconds of narration, capped. Higher N = fewer images (faster,
    # gentler on the free image API). Lower it once you have a POLLINATIONS_TOKEN.
    seconds_per_image: float = 5.0
    max_shots_per_scene: int = 2
    image_workers: int = 1                  # concurrent image fetches; 1 avoids 429 on the free tier

    # --- niche / ideation ---
    language: str = "en"                       # "en", "es", ... drives script + voice
    n_scenes: int = 8                          # more scenes = longer video (~5-6s each)
    niche_file: str = "knowledge/niche.yaml"   # seed subtopics for variety
    enable_fact_check: bool = True             # LLM second pass to verify/fix facts
    enable_trends: bool = True                 # ground ideas in trending Reddit facts
    trends_subreddits: tuple = (
        "todayilearned", "space", "Damnthatsinteresting", "science",
        "history", "psychology",
    )

    # --- captions ---
    caption_words_per_chunk: int = 1   # 1 = TikTok/brainrot word-by-word
    caption_font_candidates: tuple = (
        "assets/fonts/Anton-Regular.ttf",   # brand font (bundled)
        "C:/Windows/Fonts/impact.ttf",      # fallbacks
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    )
    caption_size_ratio: float = 0.098       # font size as fraction of width
    caption_y_ratio: float = 0.60           # vertical position (0=top, 1=bottom)
    caption_sync: str = "estimate"          # "estimate" (fast, no model) | "whisper" (exact, heavy)
    whisper_model: str = "base"             # tiny|base|small — bigger = more accurate, slower
    caption_fill_color: tuple = (244, 241, 232, 255)    # brand off-white #F4F1E8
    caption_emphasis_color: tuple = (255, 230, 61, 255)  # brand yellow #FFE63D
    caption_emphasis_min_len: int = 5    # highlight content words >= this many letters (+ numbers)
    caption_shadow: bool = True

    # --- cinematic look ---
    enable_grade: bool = True               # contrast/saturation pop
    enable_vignette: bool = True
    enable_progress_bar: bool = True        # thin growing bar at the top
    progress_bar_height: int = 7

    # --- outro CTA + thumbnail ---
    enable_outro: bool = True               # closing "follow for more" card
    outro_seconds: float = 1.8
    # Channel-level CTA — topic-agnostic so it never mismatches the video's subject.
    outro_cta: str = "FOLLOW FOR DAILY FACTS"
    enable_thumbnail: bool = True           # custom thumbnail image

    # Channel hashtags appended to every video description (consistent branding).
    hashtags: tuple = ("#didyouknow", "#facts", "#shorts", "#funfacts",
                       "#todayilearned", "#mindblown")

    # --- sound ---
    enable_whoosh: bool = True
    enable_music: bool = True
    music_volume: float = 0.55              # base level before sidechain ducking

    # --- performance ---
    use_cache: bool = True                  # reuse images/voice by content hash

    # --- paths ---
    out_dir: str = "out"
    work_dir: str = "out/work"
    cache_dir: str = "out/work/cache"
    music_dir: str = "assets/music"
    sfx_dir: str = "assets/sfx"
    state_db: str = "state/history.db"

    # --- publishing (Fase 1) — OFF by default; activate only when polished ---
    # auto = post with configured privacy; semi = force private + notify for review.
    mode: str = "semi"
    # Platforms to upload to on --upload. Empty = generate only, never post.
    # Set via env SHORTS_PLATFORMS="youtube,tiktok" (unset = none = not in production).
    platforms: tuple = field(default_factory=lambda: tuple(
        p.strip() for p in os.environ.get("SHORTS_PLATFORMS", "").split(",") if p.strip()))
    youtube_privacy: str = "private"        # private | unlisted | public
    youtube_category_id: str = "27"         # 27=Education, 28=Science & Tech
    tiktok_privacy: str = "SELF_ONLY"       # SELF_ONLY (private) | PUBLIC_TO_EVERYONE

    # --- API keys / secrets (from env; .env auto-loaded by main) ---
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    groq_api_key: str = field(default_factory=lambda: os.environ.get("GROQ_API_KEY", ""))
    yt_client_id: str = field(default_factory=lambda: os.environ.get("YT_CLIENT_ID", ""))
    yt_client_secret: str = field(default_factory=lambda: os.environ.get("YT_CLIENT_SECRET", ""))
    yt_refresh_token: str = field(default_factory=lambda: os.environ.get("YT_REFRESH_TOKEN", ""))
    tiktok_client_key: str = field(default_factory=lambda: os.environ.get("TIKTOK_CLIENT_KEY", ""))
    tiktok_client_secret: str = field(default_factory=lambda: os.environ.get("TIKTOK_CLIENT_SECRET", ""))
    tiktok_refresh_token: str = field(default_factory=lambda: os.environ.get("TIKTOK_REFRESH_TOKEN", ""))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))


# Secrets come from env only; never override these from config.yaml.
_SECRET_FIELDS = {
    "gemini_api_key", "groq_api_key", "yt_client_id", "yt_client_secret",
    "yt_refresh_token", "tiktok_client_key", "tiktok_client_secret",
    "tiktok_refresh_token", "telegram_bot_token", "telegram_chat_id",
}


def load_config(path: str = "config.yaml") -> Config:
    """Build Config from defaults, then overlay non-secret values from config.yaml."""
    cfg = Config()
    if not os.path.exists(path):
        return cfg
    import yaml
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    for key, value in data.items():
        if key in _SECRET_FIELDS or not hasattr(cfg, key):
            continue
        # keep tuple-typed fields as tuples
        if isinstance(getattr(cfg, key), tuple) and isinstance(value, list):
            value = tuple(value)
        setattr(cfg, key, value)
    return cfg
