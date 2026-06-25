"""Deterministic DAG pipeline: script -> TTS -> images -> captions -> assembly -> publish."""
from __future__ import annotations

import glob
import hashlib
import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .infra.notify import notify
from .infra.state import StateStore
from .infra.trends import trending_seed
from .models import VideoProject
from .motion.assembly import (FFmpeg, build_outro_clip, build_scene_clip,
                              concat_clips, ensure_default_music, ensure_whoosh)
from .motion.captions import (CaptionRenderer, chunk_caption, chunks_from_timings,
                              render_text_block)
from .motion.thumbnail import make_thumbnail
from .providers.aligner import WhisperAligner
from .providers.factcheck import verify_facts
from .providers.images import PollinationsImageProvider
from .providers.publisher import build_publishers
from .providers.script import build_script
from .providers.tts import EdgeTTSProvider

log = logging.getLogger(__name__)


def _hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def run_pipeline(cfg: Config, dry_run: bool = True, use_llm: bool = True,
                 fresh: bool = False) -> VideoProject:
    for d in (cfg.work_dir, cfg.out_dir, cfg.cache_dir):
        os.makedirs(d, exist_ok=True)
    cache = cfg.use_cache and not fresh
    state = StateStore(cfg.state_db)

    # 1-2. Idea + script (trending seed > niche subtopic; dedupe against history)
    log.info("== Stage 1-2: script ==")
    seed = ""
    if use_llm:
        seed = trending_seed(cfg) or _pick_subtopic(cfg)
        log.info("Idea seed: %s", seed)
    project = _unique_script(cfg, use_llm, state, seed)

    # 1a-bis. Duplicate guard: if the LLM is down it falls back to the sample script,
    # so skip the run instead of re-uploading an already-published topic.
    if use_llm and not dry_run and state.seen(project.topic):
        log.warning("No fresh topic (LLM may be down) and %r already published — "
                    "skipping this run to avoid a duplicate.", project.topic)
        return project

    # 1b. Fact-check pass — verify/fix dubious facts before we commit to TTS/video
    if use_llm and cfg.enable_fact_check and (cfg.gemini_api_key or cfg.groq_api_key):
        project.fact_risk = verify_facts(project, cfg.gemini_api_key,
                                         cfg.groq_api_key, cfg.language)

    # 1c. Branding: standardize the description's hashtags to the channel set
    if cfg.hashtags:
        base = re.sub(r"#\w+", "", project.description or "").rstrip()
        project.description = (base + "\n\n" + " ".join(cfg.hashtags)).strip()
    style = project.visual_style or cfg.visual_style_default
    log.info("Topic: %s  (%d scenes)", project.topic, len(project.scenes))

    ff = FFmpeg()
    tts = EdgeTTSProvider(cfg.tts_voice, cfg.tts_rate, cfg.tts_pitch)
    images = PollinationsImageProvider(cfg.width, cfg.height, cfg.image_model,
                                       style=style,
                                       font_candidates=cfg.caption_font_candidates,
                                       enhance=cfg.image_enhance,
                                       token=cfg.pollinations_token)
    captions = CaptionRenderer(cfg.width, cfg.height, cfg.caption_font_candidates,
                               y_ratio=cfg.caption_y_ratio,
                               fill=cfg.caption_fill_color,
                               emphasis=cfg.caption_emphasis_color,
                               shadow=cfg.caption_shadow,
                               size_ratio=cfg.caption_size_ratio)
    aligner = WhisperAligner(cfg.whisper_model) if cfg.caption_sync == "whisper" else None

    whoosh = ensure_whoosh(ff, os.path.join(cfg.sfx_dir, "whoosh.wav")) \
        if cfg.enable_whoosh else None

    # 3a. Synthesize ALL voices in parallel (network-bound; ~5s each)
    def _do_tts(scene):
        akey = _hash(cfg.tts_voice, cfg.tts_rate, scene.narration)
        scene.audio_path = os.path.join(cfg.cache_dir, f"tts_{akey}.mp3")
        if cache and _exists(scene.audio_path):
            scene.audio_duration = tts.duration(scene.audio_path)
        else:
            scene.audio_duration = tts.synth(scene.narration, scene.audio_path)

    log.info("== Stage 3: voices (parallel) ==")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_do_tts, project.scenes))

    # 3b. Fetch ALL images in parallel (network-bound; ~45s each on CI -> the bottleneck)
    img_tasks = []  # (prompt, path, seed)
    for scene in project.scenes:
        n_shots = max(1, min(cfg.max_shots_per_scene,
                             round(scene.audio_duration / cfg.seconds_per_image)))
        scene.image_paths = []
        for j in range(n_shots):
            art = cfg.art_directions[(scene.id + j) % len(cfg.art_directions)]
            prompt = f"{scene.image_prompt}, {art}"
            seed = 1000 + scene.id * 10 + j
            ikey = _hash(prompt, style, str(seed), f"{cfg.width}x{cfg.height}")
            path = os.path.join(cfg.cache_dir, f"img_{ikey}.png")
            scene.image_paths.append(path)
            if not (cache and _exists(path)):
                img_tasks.append((prompt, path, seed))

    log.info("== Stage 3b: images (parallel, %d to fetch) ==", len(img_tasks))
    if img_tasks:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda t: images.fetch(t[0], t[1], seed=t[2]), img_tasks))

    # 4-5. Captions (whisper align, sequential) + scene clips
    log.info("== Stage 4-5: captions + clips ==")
    clip_paths, clip_durations = [], []
    for scene in project.scenes:
        word_timings = _word_timings(cfg, aligner, scene.audio_path, cache)
        if word_timings:
            scene.caption_chunks = chunks_from_timings(
                word_timings, cfg.caption_words_per_chunk, scene.audio_duration)
        else:
            scene.caption_chunks = chunk_caption(
                scene.narration, scene.audio_duration, cfg.caption_words_per_chunk)
        caption_items = []
        for ci, (text, start, end) in enumerate(scene.caption_chunks):
            png = os.path.join(cfg.work_dir, f"cap_{scene.id}_{ci}.png")
            _, cw, ch = captions.render(text, png)
            caption_items.append((png, cw, ch, start, end))

        scene.clip_path = os.path.join(cfg.work_dir, f"clip_{scene.id}.mp4")
        build_scene_clip(ff, scene, caption_items, cfg)
        clip_paths.append(scene.clip_path)
        clip_durations.append(
            (scene.audio_duration or scene.duration_hint_s) + cfg.scene_tail_seconds)

    # 5a-bis. Outro CTA card (channel-level text, NOT the per-video topic)
    if cfg.enable_outro and project.scenes and project.scenes[-1].image_paths:
        cta_png = os.path.join(cfg.work_dir, "cta.png")
        render_text_block(cfg.outro_cta or "FOLLOW FOR MORE", cta_png, cfg.width,
                          cfg.caption_font_candidates, size_ratio=0.12,
                          fill=cfg.caption_emphasis_color)
        outro_clip = os.path.join(cfg.work_dir, "clip_outro.mp4")
        build_outro_clip(ff, cfg, project.scenes[-1].image_paths[0], cta_png, outro_clip)
        clip_paths.append(outro_clip)
        clip_durations.append(cfg.outro_seconds)

    # 5b. Concat (progress bar + whoosh on cuts + ducked music)
    log.info("== Stage 5: assembly ==")
    music = _resolve_music(ff, cfg)
    if music:
        log.info("Music bed: %s", music)
    # structured output: one folder per video (short.mp4 + thumbnail.jpg + metadata.json)
    out_folder = os.path.join(cfg.out_dir,
                              f"{time.strftime('%Y%m%d-%H%M%S')}_{_slug(project.topic)}")
    os.makedirs(out_folder, exist_ok=True)
    project.output_path = os.path.join(out_folder, "short.mp4")
    concat_clips(ff, clip_paths, clip_durations, project.output_path, cfg,
                 music_path=music, whoosh_path=whoosh)

    # 5c. Custom thumbnail (bold black title on brand-yellow background)
    if cfg.enable_thumbnail and (project.title or project.topic):
        project.thumbnail_path = os.path.join(out_folder, "thumbnail.jpg")
        make_thumbnail(project.title or project.topic, project.thumbnail_path,
                       cfg.width, cfg.height, cfg.caption_font_candidates)

    # 5d. Structured metadata manifest
    _write_metadata(project, out_folder, cfg, sum(clip_durations))

    # 6-7. Publish
    log.info("== Stage 6-7: publish ==")
    _publish(project, cfg, state, dry_run)
    _notify_done(cfg, project, dry_run)
    state.close()
    return project


def _notify_done(cfg: Config, project: VideoProject, dry_run: bool) -> None:
    if dry_run:
        status = "DRY-RUN (not uploaded)"
    elif project.video_url:
        review = " — review & publish manually" if cfg.mode == "semi" else ""
        status = f"uploaded{review}: {project.video_url}"
    else:
        status = "generated (no platforms enabled)"
    text = (f"🎬 Short ready: {project.title or project.topic}\n"
            f"Status: {status}\n"
            f"Duration: {project.total_duration:.0f}s | Scenes: {len(project.scenes)}\n"
            f"File: {project.output_path}")
    notify(cfg, text, video_path=project.output_path)


def _pick_subtopic(cfg: Config) -> str:
    """Pick a random subtopic from the niche file to keep topics varied."""
    try:
        import yaml
        with open(cfg.niche_file, encoding="utf-8") as fh:
            subs = (yaml.safe_load(fh) or {}).get("subtopics") or []
        return random.choice(subs) if subs else ""
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read niche file (%s); no seed", exc)
        return ""


def _unique_script(cfg: Config, use_llm: bool, state: StateStore, seed: str = "",
                   attempts: int = 3) -> VideoProject:
    gemini = cfg.gemini_api_key if use_llm else ""
    groq = cfg.groq_api_key if use_llm else ""
    project = build_script(gemini, groq, n_scenes=cfg.n_scenes, seed=seed,
                           language=cfg.language)
    if not use_llm:
        return project
    for _ in range(attempts - 1):
        if not state.seen(project.topic):
            return project
        log.info("Topic already used (%s); regenerating...", project.topic)
        project = build_script(gemini, groq, n_scenes=cfg.n_scenes, seed=seed,
                               language=cfg.language)
    return project


def _exists(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _word_timings(cfg: Config, aligner, audio_path: str, cache: bool):
    """Word timings for captions: cached sidecar JSON, else run whisper alignment."""
    if aligner is None:
        return []
    sidecar = audio_path + ".words.json"
    if cache and _exists(sidecar):
        try:
            with open(sidecar, encoding="utf-8") as fh:
                return [tuple(w) for w in json.load(fh)]
        except (OSError, ValueError):
            pass
    timings = aligner.align(audio_path, language=cfg.language)
    try:
        with open(sidecar, "w", encoding="utf-8") as fh:
            json.dump(timings, fh)
    except OSError:
        pass
    return timings


def _resolve_music(ff: FFmpeg, cfg: Config):
    """User-provided track wins; otherwise generate a default ambient bed."""
    if not cfg.enable_music:
        return None
    for ext in ("*.mp3", "*.m4a", "*.wav"):
        hits = [h for h in glob.glob(os.path.join(cfg.music_dir, ext))
                if os.path.basename(h) != "ambient_default.wav"]
        if hits:
            return hits[0]
    return ensure_default_music(ff, os.path.join(cfg.music_dir, "ambient_default.wav"))


def _slug(text: str, maxlen: int = 50) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "short").lower()).strip("-")
    return s[:maxlen].rstrip("-") or "short"


def _write_metadata(project: VideoProject, out_folder: str, cfg: Config,
                    duration: float) -> None:
    meta = {
        "topic": project.topic,
        "title": project.title,
        "hook": project.hook,
        "description": project.description,
        "tags": project.tags,
        "cta": project.cta,
        "language": cfg.language,
        "fact_risk": project.fact_risk,
        "duration_seconds": round(duration, 2),
        "n_scenes": len(project.scenes),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "video": os.path.basename(project.output_path),
        "thumbnail": (os.path.basename(project.thumbnail_path)
                      if project.thumbnail_path else None),
        "platforms_target": list(cfg.platforms),
        "scenes": [{"id": s.id, "narration": s.narration,
                    "image_prompt": s.image_prompt} for s in project.scenes],
    }
    path = os.path.join(out_folder, "metadata.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    log.info("META -> %s", path)


def _publish(project: VideoProject, cfg: Config, state: StateStore,
             dry_run: bool) -> None:
    publishers = build_publishers(cfg)
    if dry_run or not publishers:
        why = "DRY-RUN" if dry_run else "no platforms enabled (cfg.platforms empty)"
        log.info("%s: not uploading. Final video ready at:\n  %s", why, project.output_path)
        log.info("Planned metadata: title=%s | tags=%s",
                 project.title, ", ".join(project.tags))
        if project.fact_risk:
            log.info("Fact-check risk: %s", project.fact_risk)
        return

    urls = []
    for name, pub in publishers:
        try:
            url = pub.upload(project)
            urls.append(url)
            state.record(f"{project.topic} [{name}]", project.title or project.topic,
                         url, getattr(pub, "privacy", ""))
            log.info("Published to %s: %s", name, url)
        except Exception as exc:  # noqa: BLE001 - one platform failing shouldn't abort others
            log.error("Publish to %s FAILED: %s", name, exc)
    project.video_url = urls[0] if urls else None
