"""Verify the YouTube credentials actually authenticate (refresh token is valid).

Run: python scripts/verify_youtube.py
Confirms the .env YT_* values can obtain an access token, and (if the scope allows)
prints the connected channel name so you can confirm it's the right one.
"""
import os
import sys


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()


def main() -> int:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    cid = os.environ.get("YT_CLIENT_ID", "")
    cs = os.environ.get("YT_CLIENT_SECRET", "")
    rt = os.environ.get("YT_REFRESH_TOKEN", "")
    if not (cid and cs and rt):
        print("[XX] Missing YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN in .env")
        return 1

    creds = Credentials(
        token=None, refresh_token=rt, token_uri="https://oauth2.googleapis.com/token",
        client_id=cid, client_secret=cs,
        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    try:
        creds.refresh(Request())
    except Exception as exc:  # noqa: BLE001
        print("[XX] Refresh token INVALID:", type(exc).__name__, str(exc)[:200])
        return 1
    print("[OK] Refresh token valid -> access token obtained.")

    try:
        from googleapiclient.discovery import build
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if items:
            print("[OK] Connected YouTube channel:", items[0]["snippet"]["title"])
    except Exception as exc:  # noqa: BLE001
        print("[info] Channel name not readable with upload-only scope (this is fine):",
              type(exc).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
