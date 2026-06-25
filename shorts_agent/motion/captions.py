"""Karaoke-style captions rendered as tight transparent PNGs with Pillow.

Each chunk renders to a snug RGBA image (soft drop shadow + thick outline; numbers
and "power words" highlighted). The assembly layer overlays it centered with a
quick bounce so words "pop" TikTok-style. Rendering with Pillow keeps us
independent of the ffmpeg build's font support and dodges Windows font-path escaping.
"""
from __future__ import annotations

import logging
import os
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger(__name__)

# Words that get the emphasis color even without digits.
_POWER_WORDS = {
    "NEVER", "ALWAYS", "MOST", "EVERY", "ONLY", "FIRST", "LARGEST", "SMALLEST",
    "FASTEST", "BIGGEST", "DEADLY", "BILLION", "MILLION", "TRILLION", "BIGGER",
    "IMPOSSIBLE", "FOREVER", "INSTANTLY", "NOTHING", "EVERYTHING", "NASA",
}


def chunk_caption(text: str, total_duration: float, words_per_chunk: int = 1
                  ) -> List[Tuple[str, float, float]]:
    """Split `text` into word-chunks spread across `total_duration` proportionally
    to each chunk's word count. Returns (chunk_text, start, end)."""
    words = text.split()
    if not words:
        return []
    chunks = [" ".join(words[i:i + words_per_chunk])
              for i in range(0, len(words), words_per_chunk)]
    total_words = len(words)
    out, cursor = [], 0.0
    for chunk in chunks:
        dur = total_duration * (len(chunk.split()) / total_words)
        out.append((chunk, cursor, cursor + dur))
        cursor += dur
    if out:  # absorb rounding into the last chunk
        t, s, _ = out[-1]
        out[-1] = (t, s, total_duration)
    return out


def chunks_from_timings(word_timings, words_per_chunk: int = 1, total_duration: float = 0.0):
    """Build (text, start, end) caption chunks from exact per-word timings
    (edge-tts WordBoundary). Groups words and uses real spoken times — perfect sync."""
    if not word_timings:
        return []
    out = []
    for i in range(0, len(word_timings), words_per_chunk):
        group = word_timings[i:i + words_per_chunk]
        text = " ".join(w[0] for w in group)
        out.append((text, group[0][1], group[-1][2]))
    # extend the last chunk to the end so nothing flickers off early
    if total_duration and out:
        t, s, e = out[-1]
        out[-1] = (t, s, max(e, total_duration - 0.05))
    return out


def _load_any_font(candidates: tuple, size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_text_block(text: str, out_path: str, width: int, font_candidates: tuple,
                      size_ratio: float = 0.12, fill=(255, 255, 255, 255),
                      max_width_ratio: float = 0.82):
    """Render centered, word-wrapped, multi-line text (shadow + outline) to a tight
    RGBA png. Used for the outro CTA card. Returns (path, w, h)."""
    text = text.upper()
    font = _load_any_font(font_candidates, int(width * size_ratio))
    stroke = max(6, int(width * size_ratio * 0.1))
    spacing = int(width * 0.02)
    measure = ImageDraw.Draw(Image.new("RGBA", (4, 4)))

    words, line, lines = text.split(), "", []
    for w in words:
        trial = (line + " " + w).strip()
        if measure.textlength(trial, font=font) > width * max_width_ratio and line:
            lines.append(line)
            line = w
        else:
            line = trial
    if line:
        lines.append(line)
    block = "\n".join(lines)

    l, t, r, b = measure.multiline_textbbox((0, 0), block, font=font,
                                            stroke_width=stroke, align="center",
                                            spacing=spacing)
    blur = 14
    pad = int(width * 0.045) + blur
    w, h = int((r - l) + pad * 2), int((b - t) + pad * 2)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).multiline_text((w / 2, h / 2 + 10), block, font=font,
                                          fill=(0, 0, 0, 210), anchor="mm",
                                          align="center", spacing=spacing)
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(blur)))

    ImageDraw.Draw(img).multiline_text((w / 2, h / 2), block, font=font, fill=fill,
                                       stroke_width=stroke, stroke_fill=(0, 0, 0, 255),
                                       anchor="mm", align="center", spacing=spacing)
    img.save(out_path)
    return out_path, w, h


# Common long-but-unremarkable words that should stay white even though they're long.
_STOPWORDS = {
    "ABOUT", "THERE", "THEIR", "THESE", "THOSE", "WHICH", "WOULD", "COULD", "SHOULD",
    "WHERE", "WHILE", "BEING", "AFTER", "BEFORE", "BECAUSE", "THROUGH", "ITSELF",
    "REALLY", "ALMOST", "USUALLY", "ACTUALLY", "SOMETHING", "ANOTHER", "BETWEEN",
}


def _is_emphasis(text: str, min_len: int = 5) -> bool:
    """Highlight numbers, designated power words, and any content word that is at
    least `min_len` letters (excluding common long function words)."""
    if any(c.isdigit() for c in text):
        return True
    cleaned = text.strip(".,!?;:'\"-").upper()
    if cleaned in _POWER_WORDS:
        return True
    return len(cleaned) >= min_len and cleaned not in _STOPWORDS


class CaptionRenderer:
    def __init__(self, width: int, height: int, font_candidates: tuple,
                 y_ratio: float = 0.60, fill=(255, 255, 255, 255),
                 emphasis=(255, 221, 0, 255), shadow: bool = True,
                 size_ratio: float = 0.098, emphasis_min_len: int = 5):
        self.width = width
        self.height = height
        self.y_ratio = y_ratio
        self.fill = fill
        self.emphasis = emphasis
        self.emphasis_min_len = emphasis_min_len
        self.shadow = shadow
        self.stroke = max(6, int(width * size_ratio * 0.1))
        self.font = self._load_font(font_candidates, size=int(width * size_ratio))

    def _load_font(self, candidates: tuple, size: int) -> ImageFont.FreeTypeFont:
        for path in candidates:
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
        log.warning("No TrueType font found; falling back to PIL default (small).")
        return ImageFont.load_default()

    def render(self, text: str, out_path: str) -> Tuple[str, int, int]:
        """Render a snug caption PNG. Returns (path, width_px, height_px)."""
        text = text.upper()
        fill = self.emphasis if _is_emphasis(text, self.emphasis_min_len) else self.fill

        measure = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
        l, t, r, b = measure.textbbox((0, 0), text, font=self.font,
                                      stroke_width=self.stroke)
        blur = 14
        pad = int(self.width * 0.04) + blur
        w, h = (r - l) + pad * 2, (b - t) + pad * 2
        cx, cy = w / 2, h / 2

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))

        if self.shadow:
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            sdraw = ImageDraw.Draw(shadow)
            sdraw.text((cx, cy + 10), text, font=self.font, fill=(0, 0, 0, 200),
                       anchor="mm")
            shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
            img = Image.alpha_composite(img, shadow)

        draw = ImageDraw.Draw(img)
        draw.text((cx, cy), text, font=self.font, fill=fill,
                  stroke_width=self.stroke, stroke_fill=(0, 0, 0, 255), anchor="mm")
        img.save(out_path)
        return out_path, w, h
