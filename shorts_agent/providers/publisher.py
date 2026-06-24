"""Multi-platform publishing.

- YouTubePublisher: Data API v3 videos.insert via a stored OAuth refresh token.
- TikTokPublisher: Content Posting API (init + FILE_UPLOAD). NOTE: TikTok requires
  an approved app; unaudited apps can only post privately (SELF_ONLY) to the
  developer's own account.

Everything is OFF by default (cfg.platforms is empty). `build_publishers()` only
constructs publishers for the platforms you explicitly enable.

Get tokens once:
  YouTube -> python scripts/get_youtube_token.py
  TikTok  -> python scripts/get_tiktok_token.py
"""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from ..config import Config
from ..models import VideoProject

log = logging.getLogger(__name__)

YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YT_TOKEN_URI = "https://oauth2.googleapis.com/token"


class YouTubePublisher:
    name = "youtube"

    def __init__(self, client_id: str, client_secret: str, refresh_token: str,
                 category_id: str = "27", privacy: str = "private"):
        if not (client_id and client_secret and refresh_token):
            raise ValueError(
                "Missing YouTube OAuth credentials. Set YT_CLIENT_ID, "
                "YT_CLIENT_SECRET and YT_REFRESH_TOKEN (see scripts/get_youtube_token.py)."
            )
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.category_id = category_id
        self.privacy = privacy

    def _service(self):
        creds = Credentials(
            token=None, refresh_token=self.refresh_token, token_uri=YT_TOKEN_URI,
            client_id=self.client_id, client_secret=self.client_secret,
            scopes=YT_SCOPES,
        )
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def upload(self, project: VideoProject) -> str:
        body = {
            "snippet": {
                "title": (project.title or project.topic)[:100],
                "description": project.description,
                "tags": project.tags,
                "categoryId": self.category_id,
            },
            "status": {"privacyStatus": self.privacy, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(project.output_path, chunksize=-1, resumable=True,
                                mimetype="video/mp4")
        yt = self._service()
        request = yt.videos().insert(
            part="snippet,status", body=body, media_body=media)
        log.info("YouTube upload (%s): %s", self.privacy, body["snippet"]["title"])
        response = None
        while response is None:
            _, response = request.next_chunk()
        video_id = response["id"]
        self._set_thumbnail(yt, video_id, project)
        url = f"https://youtu.be/{video_id}"
        log.info("YouTube uploaded: %s", url)
        return url

    def _set_thumbnail(self, yt, video_id: str, project: VideoProject) -> None:
        thumb = project.thumbnail_path
        if not (thumb and os.path.exists(thumb)):
            return
        try:
            yt.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumb, mimetype="image/jpeg")).execute()
            log.info("Custom thumbnail set.")
        except Exception as exc:  # noqa: BLE001 - needs a verified channel
            log.warning("Could not set thumbnail (channel may need verification): %s", exc)


class TikTokPublisher:
    name = "tiktok"
    TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"

    def __init__(self, client_key: str, client_secret: str, refresh_token: str,
                 privacy: str = "SELF_ONLY"):
        if not (client_key and client_secret and refresh_token):
            raise ValueError(
                "Missing TikTok credentials. Set TIKTOK_CLIENT_KEY, "
                "TIKTOK_CLIENT_SECRET and TIKTOK_REFRESH_TOKEN "
                "(see scripts/get_tiktok_token.py). TikTok also requires an approved app."
            )
        self.client_key = client_key
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.privacy = privacy

    def _access_token(self) -> str:
        resp = requests.post(self.TOKEN_URL, data={
            "client_key": self.client_key,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }, timeout=30)
        resp.raise_for_status()
        return resp.json()["access_token"]

    def upload(self, project: VideoProject) -> str:
        import os
        token = self._access_token()
        size = os.path.getsize(project.output_path)
        init = requests.post(self.INIT_URL, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }, json={
            "post_info": {
                "title": (project.title or project.topic)[:150],
                "privacy_level": self.privacy,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": size,
                "total_chunk_count": 1,
            },
        }, timeout=60)
        init.raise_for_status()
        data = init.json()["data"]
        upload_url, publish_id = data["upload_url"], data["publish_id"]

        with open(project.output_path, "rb") as fh:
            requests.put(upload_url, data=fh.read(), headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{size - 1}/{size}",
            }, timeout=300).raise_for_status()

        log.info("TikTok upload submitted (%s): publish_id=%s", self.privacy, publish_id)
        return f"tiktok:{publish_id}"


def build_publishers(cfg: Config) -> List[Tuple[str, object]]:
    """Construct publishers only for the platforms enabled in cfg.platforms.
    In `semi` mode, privacy is forced to private regardless of config — you review
    and publish manually."""
    semi = cfg.mode == "semi"
    yt_privacy = "private" if semi else cfg.youtube_privacy
    tk_privacy = "SELF_ONLY" if semi else cfg.tiktok_privacy
    out: List[Tuple[str, object]] = []
    for platform in cfg.platforms:
        if platform == "youtube":
            out.append(("youtube", YouTubePublisher(
                cfg.yt_client_id, cfg.yt_client_secret, cfg.yt_refresh_token,
                cfg.youtube_category_id, yt_privacy)))
        elif platform == "tiktok":
            out.append(("tiktok", TikTokPublisher(
                cfg.tiktok_client_key, cfg.tiktok_client_secret,
                cfg.tiktok_refresh_token, tk_privacy)))
        else:
            raise ValueError(f"Unknown platform: {platform!r}")
    return out
