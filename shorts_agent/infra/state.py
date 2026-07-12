"""SQLite-backed history for topic dedupe and an audit trail of uploads.

The DB is meant to be committed back to the repo by the CI workflow so state
survives across runs at zero cost.
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

    def record(self, topic: str, title: str, url: str, privacy: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?)",
            (self._h(topic), topic, title, url, privacy,
             time.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
