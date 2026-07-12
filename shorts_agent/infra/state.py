"""SQLite-backed history: topic dedupe, per-video variant tags (for A/B tests),
and analytics snapshots. Committed back to the repo by CI so state survives runs.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import time


class StateStore:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS videos ("
            " topic_hash TEXT PRIMARY KEY,"
            " topic TEXT, title TEXT, video_url TEXT, privacy TEXT,"
            " created_at TEXT)"
        )
        # variant tags for the A/B feedback loop (added later; tolerate old DBs)
        for col in ("subtopic TEXT", "hook_style TEXT", "intro_card INTEGER"):
            try:
                self.conn.execute(f"ALTER TABLE videos ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass  # column already exists
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS stats ("
            " video_id TEXT, fetched_at TEXT,"
            " views INTEGER, avg_view_duration REAL, avg_view_pct REAL,"
            " PRIMARY KEY (video_id, fetched_at))"
        )
        self.conn.commit()

    @staticmethod
    def _h(topic: str) -> str:
        return hashlib.sha1(topic.lower().strip().encode("utf-8")).hexdigest()[:16]

    def seen(self, topic: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM videos WHERE topic_hash=?", (self._h(topic),))
        return cur.fetchone() is not None

    def recent_topics(self, limit: int = 30) -> list:
        cur = self.conn.execute(
            "SELECT topic FROM videos ORDER BY created_at DESC LIMIT ?", (limit,))
        return [row[0] for row in cur.fetchall() if row[0]]

    def record(self, topic: str, title: str, url: str, privacy: str,
               subtopic: str = "", hook_style: str = "",
               intro_card: bool | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO videos "
            "(topic_hash, topic, title, video_url, privacy, created_at,"
            " subtopic, hook_style, intro_card) VALUES (?,?,?,?,?,?,?,?,?)",
            (self._h(topic), topic, title, url, privacy,
             time.strftime("%Y-%m-%dT%H:%M:%S"),
             subtopic, hook_style,
             None if intro_card is None else int(intro_card)),
        )
        self.conn.commit()

    def videos_with_urls(self) -> list:
        """(video_id, title, subtopic, hook_style, intro_card) for published videos."""
        cur = self.conn.execute(
            "SELECT video_url, title, subtopic, hook_style, intro_card FROM videos"
            " WHERE video_url LIKE '%youtu%'")
        out = []
        for url, title, sub, hook, intro in cur.fetchall():
            vid = url.rstrip("/").split("/")[-1].split("=")[-1]
            if vid:
                out.append((vid, title or "", sub or "", hook or "", intro))
        return out

    def save_stats(self, video_id: str, views: int, avg_dur: float,
                   avg_pct: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO stats VALUES (?,?,?,?,?)",
            (video_id, time.strftime("%Y-%m-%d"), views, avg_dur, avg_pct))
        self.conn.commit()

    def latest_stats(self) -> dict:
        """video_id -> (views, avg_view_duration, avg_view_pct), latest snapshot."""
        cur = self.conn.execute(
            "SELECT video_id, views, avg_view_duration, avg_view_pct FROM stats s"
            " WHERE fetched_at = (SELECT MAX(fetched_at) FROM stats s2"
            "                     WHERE s2.video_id = s.video_id)")
        return {vid: (v, d, p) for vid, v, d, p in cur.fetchall()}

    def subtopic_scores(self) -> dict:
        """subtopic -> mean avg_view_pct across its videos (for weighted ideation)."""
        cur = self.conn.execute(
            "SELECT v.subtopic, AVG(st.avg_view_pct) FROM videos v"
            " JOIN stats st ON v.video_url LIKE '%' || st.video_id"
            " WHERE v.subtopic != '' GROUP BY v.subtopic")
        return {sub: score for sub, score in cur.fetchall() if sub and score}

    def close(self) -> None:
        self.conn.close()
