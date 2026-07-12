"""YouTube Analytics feedback loop.

Pulls per-video retention/views via the YouTube Analytics API, stores snapshots
in state/history.db, and prints a report (per video, per subtopic, per hook
style). Requires the OAuth token to include the yt-analytics.readonly scope
(re-run scripts/get_youtube_token.py once after updating it).

Run: python -m shorts_agent.main stats
"""
from __future__ import annotations

import datetime
import logging

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def fetch_video_stats(cfg, video_ids: list) -> dict:
    """video_id -> (views, avg_view_duration_s, avg_view_pct)."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None, refresh_token=cfg.yt_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cfg.yt_client_id, client_secret=cfg.yt_client_secret,
        scopes=SCOPES)
    yta = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    end = datetime.date.today().isoformat()
    out = {}
    # filter accepts up to ~500 ids; chunk to stay safe
    for i in range(0, len(video_ids), 200):
        chunk = video_ids[i:i + 200]
        resp = yta.reports().query(
            ids="channel==MINE", startDate="2026-01-01", endDate=end,
            metrics="views,averageViewDuration,averageViewPercentage",
            dimensions="video", filters="video==" + ",".join(chunk),
        ).execute()
        for row in resp.get("rows", []):
            out[row[0]] = (int(row[1]), float(row[2]), float(row[3]))
    return out


def run_stats(cfg) -> int:
    """Refresh stats for all published videos and print the weekly report."""
    from .state import StateStore

    state = StateStore(cfg.state_db)
    videos = state.videos_with_urls()
    if not videos:
        print("No published videos in history yet.")
        return 0

    ids = [v[0] for v in videos]
    try:
        stats = fetch_video_stats(cfg, ids)
    except Exception as exc:  # noqa: BLE001
        print(f"Analytics fetch FAILED: {exc}")
        print("Hint: the OAuth token may lack the yt-analytics.readonly scope —"
              " re-run scripts/get_youtube_token.py and update YT_REFRESH_TOKEN.")
        return 1

    for vid, (views, dur, pct) in stats.items():
        state.save_stats(vid, views, dur, pct)

    # ---- report ----
    print("\n## Channel report\n")
    print("| Video | Views | Avg % viewed | Hook | Intro card |")
    print("|---|---|---|---|---|")
    scored = []
    for vid, title, sub, hook, intro in videos:
        v, d, p = stats.get(vid, (0, 0.0, 0.0))
        scored.append((p, v, title[:45], hook, intro, sub))
    for p, v, title, hook, intro, _ in sorted(scored, reverse=True):
        card = "-" if intro is None else ("on" if intro else "off")
        print(f"| {title} | {v} | {p:.0f}% | {hook or '-'} | {card} |")

    def _group(idx, label):
        groups = {}
        for row in scored:
            key = row[idx]
            if key not in ("", None):
                groups.setdefault(key, []).append(row[0])
        if groups:
            print(f"\n**Avg retention by {label}:**")
            for key, vals in sorted(groups.items(), key=lambda kv: -sum(kv[1]) / len(kv[1])):
                print(f"- {key}: {sum(vals) / len(vals):.0f}%  ({len(vals)} videos)")

    _group(5, "subtopic")
    _group(3, "hook style")
    _group(4, "intro card")

    state.close()
    print("\nSnapshots saved to", cfg.state_db)
    return 0
