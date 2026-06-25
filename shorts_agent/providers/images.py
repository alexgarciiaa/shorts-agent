"""AI image generation via Pollinations (free, no key). Falls back to a
locally-rendered gradient placeholder so the pipeline never hard-fails."""
from __future__ import annotations

import logging
import time
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)


class PollinationsImageProvider:
    # gen.* needs a Bearer key and costs Pollen but gives native 1080x1920;
    # image.* is free/anonymous but caps at 576x1024 and rate-limits. We try the
    # paid one first (while Pollen lasts) and fall back to the free one -> always $0.
    NEW_BASE = "https://gen.pollinations.ai/image/"
    OLD_BASE = "https://image.pollinations.ai/prompt/"

    def __init__(self, width: int, height: int, model: str = "flux",
                 style: str = "", font_candidates: tuple = (), token: str = ""):
        self.width = width
        self.height = height
        self.model = model
        self.style = style
        self.font_candidates = font_candidates
        self.token = token

    def fetch(self, prompt: str, out_path: str, seed: int = 0) -> bool:
        """Returns True if a real image was written, False if it fell back to a
        local placeholder (the caller can then swap in a real image instead)."""
        full_prompt = f"{prompt}, {self.style}" if self.style else prompt
        quoted = urllib.parse.quote(full_prompt)

        # 1) high-res via the paid API (only if we have a key + Pollen balance)
        if self.token:
            new_url = (f"{self.NEW_BASE}{quoted}?model={self.model}"
                       f"&width={self.width}&height={self.height}&seed={seed}&nologo=true")
            if self._try(new_url, {"Authorization": f"Bearer {self.token}"}, out_path):
                log.info("IMG  hi-res  %s", prompt[:46])
                return True

        # 2) free anonymous fallback (576x1024, rate-limited)
        old_url = (f"{self.OLD_BASE}{quoted}?width={self.width}&height={self.height}"
                   f"&nologo=true&model={self.model}&seed={seed}")
        if self._try(old_url, {}, out_path):
            log.info("IMG  free    %s", prompt[:46])
            return True

        # 3) local placeholder so the pipeline never hard-fails
        log.warning("IMG  fail -> placeholder for %r", prompt[:40])
        self._placeholder(prompt, out_path)
        return False

    def _try(self, url: str, headers: dict, out_path: str) -> bool:
        """Fetch one image; retry transient 429/5xx, give up on other 4xx (e.g. 402)."""
        for i in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=60)
                if resp.status_code == 429 or resp.status_code >= 500:
                    time.sleep(2.0 * (i + 1))
                    continue
                if resp.status_code != 200:
                    return False   # 402 no-balance / other 4xx -> fall back
                if not resp.content or len(resp.content) < 2000:
                    return False
                with open(out_path, "wb") as fh:
                    fh.write(resp.content)
                with Image.open(out_path) as im:
                    im.verify()
                return True
            except requests.RequestException:
                time.sleep(2.0 * (i + 1))
            except Exception:  # noqa: BLE001 - bad image data
                return False
        return False

    def _placeholder(self, prompt: str, out_path: str) -> None:
        img = Image.new("RGB", (self.width, self.height))
        top, bottom = (18, 22, 54), (90, 30, 110)
        px = img.load()
        for y in range(self.height):
            t = y / self.height
            px_row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            for x in range(self.width):
                px[x, y] = px_row
        draw = ImageDraw.Draw(img)
        font = self._font(60)
        words, line, lines = prompt.split(), "", []
        for w in words:
            trial = (line + " " + w).strip()
            if draw.textlength(trial, font=font) > self.width * 0.8:
                lines.append(line)
                line = w
            else:
                line = trial
        lines.append(line)
        draw.multiline_text((self.width / 2, self.height / 2), "\n".join(lines[:8]),
                            font=font, fill=(255, 255, 255), anchor="mm",
                            align="center", spacing=16)
        img.save(out_path)

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        for path in self.font_candidates:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()
