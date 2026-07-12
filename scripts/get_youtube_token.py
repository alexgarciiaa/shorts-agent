"""One-time helper: run the YouTube OAuth consent flow and print the refresh token.

Prerequisites:
  1. Google Cloud project with the *YouTube Data API v3* enabled.
  2. An OAuth client of type "Desktop app"; download its JSON as client_secret.json.
  3. Add yourself as a test user (or publish the app to "In production" so the
     refresh token does NOT expire after 7 days).

Usage:
  python scripts/get_youtube_token.py [path/to/client_secret.json]

It opens a browser, you approve, and it prints the three values to put in .env
(YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN) or in GitHub secrets.
"""
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/yt-analytics.readonly",  # weekly stats report
]


def main() -> int:
    client_secret = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    # access_type=offline + prompt=consent guarantee a refresh token is returned.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print("\n=== Add these to your .env (and GitHub secrets) ===")
    print(f"YT_CLIENT_ID={creds.client_id}")
    print(f"YT_CLIENT_SECRET={creds.client_secret}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    print("===================================================\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
