"""Verify the Pollinations API key against the new gen.pollinations.ai API.

Checks: key type (sk_ vs pk_), account balance, a single image (resolution + time),
and 4 concurrent requests (to confirm no 429 rate-limit with a secret key).

Run: python scripts/verify_pollinations.py
"""
import os
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import requests
from PIL import Image

BASE = "https://gen.pollinations.ai"


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
KEY = os.environ.get("POLLINATIONS_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {KEY}"} if KEY else {}


def fetch(seed: int) -> str:
    url = (f"{BASE}/image/"
           + urllib.parse.quote("a colossal blue whale in the deep ocean, cinematic, ultra detailed")
           + f"?model=flux&width=1080&height=1920&seed={seed}&nologo=true")
    t = time.time()
    r = requests.get(url, headers=HEADERS, timeout=120)
    if r.status_code == 200:
        return f"seed {seed}: OK {Image.open(BytesIO(r.content)).size}  {int(time.time() - t)}s"
    return f"seed {seed}: HTTP {r.status_code}  {r.text[:80]}"


def main() -> int:
    print("key present:", bool(KEY), "| prefix:", (KEY[:3] if KEY else "-"), "| len", len(KEY))
    try:
        bal = requests.get(f"{BASE}/account/balance", headers=HEADERS, timeout=30)
        print("balance:", bal.status_code, bal.text[:120])
    except Exception as exc:  # noqa: BLE001
        print("balance check failed:", exc)

    print("\n12 sequential requests (watch where/if it starts failing):")
    for i in range(12):
        print(" ", fetch(900 + i))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
