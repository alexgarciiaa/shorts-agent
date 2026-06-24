"""One-time helper: obtain a TikTok refresh token for the Content Posting API.

IMPORTANT: TikTok requires a registered developer app (https://developers.tiktok.com)
with the `video.publish` scope and a configured Redirect URI. Unaudited apps can only
post privately (SELF_ONLY) to the developer's own account. This is why publishing
stays OFF until the app is approved.

Flow:
  1. Set TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET in your env (or pass below).
  2. Run this script; open the printed URL, authorize, and copy the `code` from the
     redirect URL.
  3. Paste it here; the script prints the refresh token for your .env / GitHub secrets.
"""
import os
import sys
import urllib.parse

import requests

REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:8080/callback")
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "video.publish,video.upload"


def main() -> int:
    client_key = os.environ.get("TIKTOK_CLIENT_KEY", "")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    if not (client_key and client_secret):
        print("Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET first.")
        return 1

    params = {
        "client_key": client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": "shorts_agent",
    }
    print("\n1) Open this URL and authorize:\n")
    print(AUTH_URL + "?" + urllib.parse.urlencode(params))
    print(f"\n2) After redirect to {REDIRECT_URI}, copy the `code` query param.\n")
    code = input("Paste code here: ").strip()

    resp = requests.post(TOKEN_URL, data={
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    print("\n=== Add these to your .env (and GitHub secrets) ===")
    print(f"TIKTOK_CLIENT_KEY={client_key}")
    print(f"TIKTOK_CLIENT_SECRET={client_secret}")
    print(f"TIKTOK_REFRESH_TOKEN={data.get('refresh_token')}")
    print("===================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
