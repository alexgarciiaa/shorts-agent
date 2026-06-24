"""Trending-idea signal from Reddit's public JSON (no auth, free).

Returns a single popular fact/title to seed the script with, so topics are grounded
in content that already proved engaging. Degrades gracefully: any failure (Reddit
rate-limits, 403, network) returns "" and the pipeline falls back to a niche subtopic.
"""
from __future__ import annotations

import logging
import random

import requests

log = logging.getLogger(__name__)

_UA = "shorts-agent/0.1 (idea research; contact: via github)"
_PREFIXES = ("til that ", "til: ", "til ", "psa: ", "did you know that ",
             "did you know ")


def trending_seed(cfg) -> str:
    if not getattr(cfg, "enable_trends", False) or not cfg.trends_subreddits:
        return ""
    subs = list(cfg.trends_subreddits)
    random.shuffle(subs)
    for sub in subs[:3]:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json",
                params={"t": "week", "limit": 20},
                headers={"User-Agent": _UA}, timeout=15)
            if resp.status_code != 200:
                continue
            children = resp.json().get("data", {}).get("children", [])
            titles = [c["data"]["title"] for c in children
                      if not c["data"].get("over_18")]
            random.shuffle(titles)
            for title in titles:
                seed = _clean(title)
                if 25 <= len(seed) <= 180:
                    log.info("Trending seed from r/%s: %s", sub, seed[:70])
                    return seed
        except Exception as exc:  # noqa: BLE001
            log.warning("Trends fetch r/%s failed: %s", sub, exc)
    return ""


def _clean(title: str) -> str:
    t = title.strip()
    low = t.lower()
    for p in _PREFIXES:
        if low.startswith(p):
            t = t[len(p):]
            break
    return t.strip()
