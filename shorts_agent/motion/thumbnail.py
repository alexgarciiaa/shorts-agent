"""Custom thumbnail: bold black title centered on a solid brand-yellow background.
High contrast = high click-through. Vertical 1080x1920 (YouTube accepts it for Shorts)."""
from __future__ import annotations

import logging
import os
import re
from typing import List

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

BG = (255, 230, 61)    # brand yellow #FFE63D
FG = (0, 0, 0)         # black text


def make_thumbnail(title: str, out_path: str, width: int, height: int,
                   font_candidates: tuple, bg=BG, fg=FG) -> str:
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    text = re.sub(r"#\w+", "", title or "DID YOU KNOW?")          # drop hashtags
    text = text.encode("ascii", "ignore").decode().upper().strip()  # drop emojis
    if not text:
        text = "DID YOU KNOW?"

    font = _fit_font(draw, text, font_candidates, width, height)
    lines = _wrap(draw, text, font, width * 0.86)
    line_h = font.size * 1.08
    y = (height - line_h * len(lines)) / 2
    for line in lines:
        draw.text((width / 2, y + line_h / 2), line, font=font, fill=fg, anchor="mm")
        y += line_h

    img.save(out_path, quality=92)
    log.info("THUMB -> %s", out_path)
    return out_path


def _fit_font(draw, text, font_candidates, width, height):
    """Shrink the font until the wrapped title fits comfortably on screen."""
    for ratio in (0.15, 0.135, 0.12, 0.105, 0.09):
        font = _font(font_candidates, int(width * ratio))
        lines = _wrap(draw, text, font, width * 0.86)
        if len(lines) * font.size * 1.08 <= height * 0.8 and len(lines) <= 6:
            return font
    return _font(font_candidates, int(width * 0.09))


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
