"""AI image generation via Pollinations (free, no key). Falls back to a
locally-rendered gradient placeholder so the pipeline never hard-fails."""
from __future__ import annotations

import logging
import urllib.parse

import requests
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)


class PollinationsImageProvider:
    BASE = "https://image.pollinations.ai/prompt/"

    def __init__(self, width: int, height: int, model: str = "flux",
                 style: str = "", font_candidates: tuple = (), enhance: bool = True,
                 token: str = ""):
        self.width = width
        self.height = height
        self.model = model
        self.style = style
        self.font_candidates = font_candidates
        self.enhance = enhance
        self.token = token

    def fetch(self, prompt: str, out_path: str, seed: int = 0) -> str:
        full_prompt = f"{prompt}, {self.style}" if self.style else prompt
        url = (
            self.BASE
            + urllib.parse.quote(full_prompt)
            + f"?width={self.width}&height={self.height}&nologo=true"
            + f"&model={self.model}&seed={seed}"
            + ("&enhance=true" if self.enhance else "")
            + (f"&token={self.token}" if self.token else "")
        )
        try:
            resp = requests.get(url, timeout=180)
            resp.raise_for_status()
            if not resp.content or len(resp.content) < 2000:
                raise ValueError("empty/too-small image response")
            with open(out_path, "wb") as fh:
                fh.write(resp.content)
            # validate it is a real image
            with Image.open(out_path) as im:
                im.verify()
            log.info("IMG  ok    %s", prompt[:48])
            return out_path
        except Exception as exc:  # noqa: BLE001 - resilience by design
            log.warning("IMG  fail (%s) -> placeholder for %r", exc, prompt[:40])
            self._placeholder(prompt, out_path)
            return out_path

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
