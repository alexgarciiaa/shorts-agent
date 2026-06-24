"""Pre-flight checks: verify the environment and config before going live.

Run: python -m shorts_agent.main check
Errors ([XX]) block readiness; warnings ([!!]) are fine for generation-only.
"""
from __future__ import annotations

import importlib
import os
import subprocess


def _imp(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:  # noqa: BLE001
        return False


def run_checks(cfg) -> bool:
    rows = []  # (status, label, detail)

    def add(status, label, detail=""):
        rows.append((status, label, detail))

    # FFmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        r = subprocess.run([exe, "-version"], capture_output=True, text=True)
        add("ok" if r.returncode == 0 else "err", "FFmpeg",
            os.path.basename(exe) if r.returncode == 0 else "-version failed")
    except Exception as exc:  # noqa: BLE001
        add("err", "FFmpeg", str(exc))

    # core deps
    for mod in ("edge_tts", "PIL", "mutagen", "requests", "yaml"):
        add("ok" if _imp(mod) else "err", f"dep: {mod}")

    # caption font
    font = next((p for p in cfg.caption_font_candidates if os.path.exists(p)), None)
    add("ok" if font else "warn", "Caption font",
        os.path.basename(font) if font else "none found -> ugly default font")

    # caption sync / whisper
    if cfg.caption_sync == "whisper":
        has = _imp("faster_whisper")
        add("ok" if has else "warn", "Whisper (caption sync)",
            "" if has else "not installed -> falls back to estimated timing")
    else:
        add("ok", "Caption sync", "estimate")

    # LLM
    if cfg.gemini_api_key or cfg.groq_api_key:
        add("ok", "LLM key", "gemini" if cfg.gemini_api_key else "groq")
    else:
        add("warn", "LLM key", "none -> uses built-in sample script")

    # fact-check
    if cfg.enable_fact_check and not (cfg.gemini_api_key or cfg.groq_api_key):
        add("warn", "Fact-check", "enabled but no LLM key -> skipped")

    # publishing
    if not cfg.platforms:
        add("warn", "Publishing", "no platforms enabled (generation only)")
    else:
        google_ok = _imp("googleapiclient") and _imp("google.oauth2.credentials")
        for platform in cfg.platforms:
            if platform == "youtube":
                if not google_ok:
                    add("err", "YouTube libs", "google-api-python-client missing")
                missing = [k for k, v in (
                    ("YT_CLIENT_ID", cfg.yt_client_id),
                    ("YT_CLIENT_SECRET", cfg.yt_client_secret),
                    ("YT_REFRESH_TOKEN", cfg.yt_refresh_token)) if not v]
                add("ok" if not missing else "err", "YouTube creds",
                    "ok" if not missing else "missing " + ", ".join(missing))
            elif platform == "tiktok":
                missing = [k for k, v in (
                    ("TIKTOK_CLIENT_KEY", cfg.tiktok_client_key),
                    ("TIKTOK_CLIENT_SECRET", cfg.tiktok_client_secret),
                    ("TIKTOK_REFRESH_TOKEN", cfg.tiktok_refresh_token)) if not v]
                add("ok" if not missing else "err", "TikTok creds",
                    "ok" if not missing else "missing " + ", ".join(missing))
            else:
                add("err", "Platform", f"unknown: {platform}")

    # output dirs
    try:
        os.makedirs(cfg.work_dir, exist_ok=True)
        os.makedirs(cfg.out_dir, exist_ok=True)
        add("ok", "Output dirs", cfg.out_dir)
    except Exception as exc:  # noqa: BLE001
        add("err", "Output dirs", str(exc))

    # .env
    add("ok" if os.path.exists(".env") else "warn", ".env file",
        "" if os.path.exists(".env") else "not found (using process env)")

    # render
    marks = {"ok": "[OK]", "warn": "[!!]", "err": "[XX]"}
    print("\nPre-flight check")
    print("=" * 48)
    for status, label, detail in rows:
        line = f"{marks[status]} {label}"
        if detail:
            line += f"  -- {detail}"
        print(line)
    print("=" * 48)

    errors = sum(1 for s, _, _ in rows if s == "err")
    warnings = sum(1 for s, _, _ in rows if s == "warn")
    if errors:
        print(f"NOT READY: {errors} error(s), {warnings} warning(s). Fix the [XX] items.")
        return False
    mode = ("GENERATION ONLY (nothing is uploaded)" if not cfg.platforms
            else f"PUBLISH to: {', '.join(cfg.platforms)}")
    print(f"READY ({warnings} warning(s)). Mode: {mode}.")
    return True
