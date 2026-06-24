# YouTube Shorts Agent

Autonomous agent that generates and (later) uploads "did you know" YouTube Shorts
at ~0 € operating cost. **Visual style: AI-generated images + dynamic motion**
(varied Ken Burns, fast cuts, karaoke captions, music, SFX). See [PLAN.md](PLAN.md)
for the full architecture.

## Status
- ✅ **Fase 0 — local MVP (dry-run):** end-to-end pipeline producing a polished 9:16 Short.
- ✅ **Polish pass:** music + ducking, word-by-word captions, cinematic grade/vignette,
  progress bar, smoother 2× zoom, 1-2 varied images per scene, smaller captions.
- ✅ **Fase 1 scaffolding (OFF by default):** YouTube + TikTok publishers, SQLite dedupe,
  GitHub Actions workflow. Nothing posts until you opt in (see below).
- ✅ **Fase 2 hardening:** `config.yaml` (edit without code), `semi`/`auto` mode (semi forces
  private + notifies), Telegram + GitHub job-summary notifications, niche-seeded ideation
  for topic variety, LLM failover (Gemini→Groq→sample) with retry, API keys never logged.

## Configuration & modes
- Edit `config.yaml` to change voice, style, captions, look, mode, platforms — no code.
- `mode: semi` (default) = uploads as **private** and notifies you to review/publish manually.
  `mode: auto` = posts with the configured privacy.
- Ideation seeds each run from a **trending Reddit fact** (`enable_trends`), falling back to
  a random subtopic from `knowledge/niche.yaml`. Topics already in `state/history.db` are skipped.
  (Reddit may rate-limit anonymous requests; the fallback keeps it working.)
- **Multi-language / second channel:** set `language: es` (and a Spanish voice like
  `tts_voice: es-ES-AlvaroNeural`) in a separate `config.yaml` to run a Spanish channel with
  the same code. Image prompts stay in English for quality; narration/title are translated.
- Notifications: set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` to get the finished video
  pinged to you (no-op if unset).

## Publishing — NOT in production yet
Generation is fully decoupled from posting. Nothing is ever uploaded unless you
explicitly enable it:
- `cfg.platforms` is empty by default; set env `SHORTS_PLATFORMS="youtube,tiktok"` to enable.
- `--dry-run` (default) never uploads; `--upload` only posts to the enabled platforms.
- The GitHub Actions schedule is commented out; manual runs default to dry-run.
- Get tokens once: `python scripts/get_youtube_token.py`, `python scripts/get_tiktok_token.py`.
  (TikTok also needs an approved developer app.)

## What it produces
A vertical 1080×1920 / 30 fps Short with:
- **Script** from Gemini (fresh each run) or a built-in sample.
- **Voice** (edge-tts) + **AI images** (Pollinations/FLUX), one per scene.
- **Word-by-word captions** with soft shadow, thick outline, yellow emphasis on
  numbers/power-words, and a bounce — **frame-accurately synced** to the voice via
  faster-whisper word-level alignment.
- **Broadcast audio**: music side-chain ducked under the voice + whoosh SFX, then
  EBU R128 loudness-normalized to YouTube's ~-14 LUFS.
- **Varied motion** per scene (zoom-in / punch-in / zoom-out), cinematic grade + vignette.
- **Audio**: music bed **side-chain ducked** under the voice + **whoosh** SFX on cuts,
  peak-limited to avoid clipping.
- A thin **progress bar** at the top (retention cue), an **outro CTA card**
  ("follow for more"), and a **custom thumbnail** (set on upload when the channel
  is eligible).

## Stack (all free)
| Stage | Tool |
|-------|------|
| Script / ideas | Gemini 2.5 Flash (optional) → built-in sample fallback |
| Voice | edge-tts (Microsoft neural voices) |
| Images | Pollinations (FLUX) → local placeholder fallback |
| Captions | Pillow-rendered PNG overlays |
| Assembly | FFmpeg (bundled via `imageio-ffmpeg`) |

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
Optional, for a fresh AI script each run: copy `.env.example` to `.env` and add your
free Gemini key from https://aistudio.google.com/apikey

## Run
```powershell
# Fresh AI script (uses .env GEMINI_API_KEY):
.\.venv\Scripts\python.exe -m shorts_agent.main run --dry-run

# Built-in sample script (no keys needed):
.\.venv\Scripts\python.exe -m shorts_agent.main run --dry-run --no-llm

# Ignore the asset cache and regenerate everything:
.\.venv\Scripts\python.exe -m shorts_agent.main run --dry-run --fresh
```
Output: one folder per video at `out/<timestamp>_<slug>/` containing `short.mp4`,
`thumbnail.jpg`, and a structured `metadata.json` (title, description, tags, scenes,
duration, fact-risk…). Nothing is uploaded in `--dry-run`.

The script is **fact-checked** by a second low-temperature LLM pass
(`enable_fact_check`): dubious facts are flagged and rewritten before TTS, with an
overall risk level (low/medium/high) reported.

## Pre-flight check
```powershell
.\.venv\Scripts\python.exe -m shorts_agent.main check
```
Validates FFmpeg, deps, fonts, whisper, LLM key, and (per enabled platform) upload
credentials before going live. `[XX]` items block readiness; `[!!]` are fine for
generation-only.

## Tests
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## Customizing
Everything is in `shorts_agent/config.py`: voice, visual style, caption font/colors,
grade/vignette/progress-bar toggles, music volume.

- **Music:** drop any `.mp3` in `assets/music/` and it is used automatically (ducked
  under the voice). With none present, a default ambient bed is generated. For maximum
  engagement, add a trending track.
- **Caching:** images and voice are cached by content hash under `out/work/cache`, so
  re-runs are fast. Use `--fresh` to bypass.
- **Brand identity:** captions use the bundled **Anton** font, off-white `#F4F1E8` for
  normal words and `#FFE63D` for emphasis (numbers/power-words). Channel `hashtags`
  (in `config.yaml`) are appended to every description.

## Project layout
```
shorts_agent/
  config.py            # all tunables
  models.py            # Scene, VideoProject
  providers/           # tts (edge), images (pollinations), script (gemini/sample)
  motion/              # captions (Pillow), assembly (FFmpeg motion + mix)
  pipeline.py          # the DAG orchestrator (+ asset cache)
  main.py              # CLI
tests/                 # pure-logic unit tests
```
