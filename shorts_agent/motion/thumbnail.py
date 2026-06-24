"""Custom thumbnail: a striking scene image + a big bold title, with top/bottom
darkening so the text pops. Vertical 1080x1920 (YouTube accepts it for Shorts)."""
from __future__ import annotations

import logging
import os
from typing import List

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)


def make_thumbnail(image_path: str, title: str, out_path: str, width: int,
                   height: int, font_candidates: tuple) -> str:
    base = Image.open(image_path).convert("RGB").resize((width, height))

    # darken top & bottom thirds with vertical gradients for legibility
    overlay = Image.new("L", (1, height), 0)
    px = overlay.load()
    for y in range(height):
        r = y / height
        if r < 0.33:
            px[0, y] = int(150 * (1 - r / 0.33))
        elif r > 0.6:
            px[0, y] = int(170 * ((r - 0.6) / 0.4))
        else:
            px[0, y] = 0
    shade = overlay.resize((width, height))
    black = Image.new("RGB", (width, height), (0, 0, 0))
    base = Image.composite(black, base, shade)

    draw = ImageDraw.Draw(base)
    font = _font(font_candidates, int(width * 0.115))
    title = (title or "DID YOU KNOW?").upper().replace("#SHORTS", "").strip()
    lines = _wrap(draw, title, font, width * 0.88)[:4]
    stroke = max(8, int(width * 0.012))
    y = height * 0.74
    for line in lines:
        draw.text((width / 2, y), line, font=font, fill=(255, 230, 61, 255),  # brand #FFE63D
                  stroke_width=stroke, stroke_fill=(0, 0, 0, 255), anchor="mm")
        y += font.size * 1.12

    base.save(out_path, quality=90)
    log.info("THUMB -> %s", out_path)
    return out_path


def _font(candidates: tuple, size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: float) -> List[str]:
    words, line, lines = text.split(), "", []
    for w in words:
        trial = (line + " " + w).strip()
        if draw.textlength(trial, font=font) > max_w and line:
            lines.append(line)
            line = w
        else:
            line = trial
    if line:
        lines.append(line)
    return lines
