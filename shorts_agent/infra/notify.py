"""Lightweight observability: write a GitHub Actions job summary and (optionally)
send a Telegram message/video. All no-ops if the relevant env/secrets are absent."""
from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

# Telegram rejects sendVideo over ~50 MB via the bot API.
_TELEGRAM_VIDEO_LIMIT = 49 * 1024 * 1024


def notify(cfg, text: str, video_path: str | None = None) -> None:
    _job_summary(text)
    _telegram(cfg, text, video_path)


def _job_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n\n")
    except OSError as exc:
        log.warning("Job summary write failed: %s", exc)


def _telegram(cfg, text: str, video_path: str | None) -> None:
    token, chat = cfg.telegram_bot_token, cfg.telegram_chat_id
    if not (token and chat):
        return
    base = f"https://api.telegram.org/bot{token}"
    try:
        if (video_path and os.path.exists(video_path)
                and os.path.getsize(video_path) < _TELEGRAM_VIDEO_LIMIT):
            with open(video_path, "rb") as fh:
                requests.post(f"{base}/sendVideo",
                              data={"chat_id": chat, "caption": text[:1024]},
                              files={"video": fh}, timeout=120)
        else:
            requests.post(f"{base}/sendMessage",
                          data={"chat_id": chat, "text": text}, timeout=30)
        log.info("Telegram notification sent.")
    except Exception as exc:  # noqa: BLE001
        log.warning("Telegram notify failed: %s", exc)
