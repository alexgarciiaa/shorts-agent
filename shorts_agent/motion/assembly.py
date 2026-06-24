"""FFmpeg assembly.

Per-scene clips: crop-based Ken Burns (zoom-in / punch-in / zoom-out for variety)
+ cinematic grade + vignette + bouncing word captions.
Final concat: progress bar, whoosh SFX on cuts, and music sidechain-ducked under
the voice.

Paths are passed as argv (never via a list file) so spaces/accents in the project
path -- e.g. "Politécnica" -- are handled as proper Unicode.
"""
from __future__ import annotations

import logging
import os
import subprocess
from typing import List, Optional, Tuple

import imageio_ffmpeg

from ..config import Config
from ..models import Scene

log = logging.getLogger(__name__)

# A caption item: (png_path, width_px, height_px, start_s, end_s)
CaptionItem = Tuple[str, int, int, float, float]

# Ken Burns presets cycled per scene: (zoom_start, zoom_end, pan_x, pan_y)
_MOTION = [
    (1.00, 1.12, 0.5, 0.5),   # slow zoom-in, centered
    (1.16, 1.00, 0.5, 0.4),   # punch-in, settles (impact on the cut)
    (1.12, 1.00, 0.3, 0.5),   # zoom-out drifting left
    (1.00, 1.14, 0.7, 0.6),   # slow zoom-in drifting right
]


class FFmpeg:
    def __init__(self):
        self.exe = imageio_ffmpeg.get_ffmpeg_exe()

    def run(self, args: List[str]) -> None:
        cmd = [self.exe, "-y", "-hide_banner", "-loglevel", "error", *args]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-1800:]
            raise RuntimeError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")


def _esc(expr: str) -> str:
    r"""Escape commas inside filter EXPRESSIONS (e.g. min(a,b) -> min(a\,b)).
    Never use on a filter chain where commas separate filters."""
    return expr.replace(",", r"\,")


def ensure_whoosh(ff: FFmpeg, path: str) -> str:
    """Synthesize a short whoosh SFX once (filtered noise burst with fast envelope)."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ff.run([
        "-f", "lavfi", "-i", "anoisesrc=d=0.45:c=pink:a=0.9",
        "-af", ("highpass=f=250,lowpass=f=3500,"
                "afade=t=in:st=0:d=0.04,afade=t=out:st=0.12:d=0.33,volume=1.0"),
        path,
    ])
    log.info("SFX  generated whoosh -> %s", path)
    return path


def ensure_default_music(ff: FFmpeg, path: str) -> str:
    """Generate a tasteful royalty-free cinematic ambient pad once (a minor-chord
    drone with tremolo + reverb). Replace with your own track for max engagement."""
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ff.run([
        "-f", "lavfi", "-i", "sine=frequency=110:duration=45",   # root
        "-f", "lavfi", "-i", "sine=frequency=164.81:duration=45",  # fifth
        "-f", "lavfi", "-i", "sine=frequency=220:duration=45",   # octave
        "-f", "lavfi", "-i", "sine=frequency=329.63:duration=45",  # shimmer
        "-filter_complex",
        # shimmer note gets vibrato for life; the bed gets a slow tremolo pulse + reverb
        ("[3]vibrato=f=5:d=0.4,volume=0.4[sh];"
         "[0][1][2][sh]amix=inputs=4,tremolo=f=0.5:d=0.35,"
         "aecho=0.8:0.7:60|120:0.4|0.3,lowpass=f=1100,"
         "afade=t=in:st=0:d=3,volume=2.6[a]"),
        "-map", "[a]", path,
    ])
    log.info("MUS  generated default ambient bed -> %s", path)
    return path


def _kenburns_segment(cfg: Config, dur: float, motion_idx: int, src_idx: int,
                      out_label: str) -> str:
    """One still -> a moving WxH segment. zoompan animates zoom via output-frame
    index `on` (supports zoom in/out); rendering at `image_upscale`x then scaling
    down to WxH removes the classic zoompan judder."""
    z0, z1, px, py = _MOTION[motion_idx % len(_MOTION)]
    frames = max(2, round(dur * cfg.fps))
    Z = f"{z0}+({z1 - z0:.3f})*on/{frames}"   # no commas -> no escaping needed
    bw, bh = int(cfg.width * cfg.image_upscale), int(cfg.height * cfg.image_upscale)
    flags = ":flags=lanczos" if cfg.image_sharpen else ""   # better upscaling = less blocky
    chain = (
        f"[{src_idx}:v]scale={bw}:{bh}:force_original_aspect_ratio=increase{flags},"
        f"crop={bw}:{bh},"
        f"zoompan=z='{Z}':d={frames}:x='(iw-iw/zoom)*{px}':y='(ih-ih/zoom)*{py}':"
        f"s={cfg.width}x{cfg.height}:fps={cfg.fps}"
    )
    if cfg.image_sharpen:
        chain += ",unsharp=5:5:1.0:5:5:0.0"   # crisp up edges to fight the low-res source
    if cfg.enable_grade:
        chain += ",eq=contrast=1.08:saturation=1.2:brightness=0.01"
    if cfg.enable_vignette:
        chain += ",vignette=PI/5"
    chain += f",setsar=1[{out_label}]"
    return chain


def build_scene_clip(ff: FFmpeg, scene: Scene, captions: List[CaptionItem],
                     cfg: Config) -> str:
    dur = (scene.audio_duration or scene.duration_hint_s) + cfg.scene_tail_seconds
    images = scene.image_paths or []
    n_img = max(1, len(images))

    # stills first (zoompan generates frames; do NOT -loop them), then audio, captions
    inputs: List[str] = []
    for img in images:
        inputs += ["-i", img]
    audio_idx = n_img
    inputs += ["-i", scene.audio_path]
    for png, *_ in captions:
        inputs += ["-loop", "1", "-i", png]

    # one moving segment per still, concatenated to fill the scene
    seg_dur = dur / n_img
    seg_labels = []
    graph_parts = []
    for i in range(n_img):
        label = f"seg{i}"
        graph_parts.append(
            _kenburns_segment(cfg, seg_dur, scene.id + i, i, label))
        seg_labels.append(f"[{label}]")
    graph = ";".join(graph_parts)
    if n_img == 1:
        graph += f";[seg0]null[bg]"
    else:
        graph += f";{''.join(seg_labels)}concat=n={n_img}:v=1[bg]"

    prev = "bg"
    cap_base = n_img + 1   # after stills + audio
    for idx, (_, _w, _h, start, end) in enumerate(captions):
        in_idx = cap_base + idx
        out = f"v{idx}"
        between = _esc(f"between(t,{start:.3f},{end:.3f})")
        # centered horizontally; quick upward bounce that settles (the "pop")
        yexpr = f"(H*{cfg.caption_y_ratio})-(h/2)+40*exp(-(t-{start:.3f})*20)"
        graph += (f";[{prev}][{in_idx}:v]"
                  f"overlay=x='(W-w)/2':y='{yexpr}':enable='{between}'[{out}]")
        prev = out

    ff.run([
        *inputs,
        "-filter_complex", graph,
        "-map", f"[{prev}]", "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-r", str(cfg.fps),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-t", f"{dur:.3f}",
        scene.clip_path,
    ])
    log.info("CLIP %5.2fs  scene %d  (%d imgs, %d captions)",
             dur, scene.id, n_img, len(captions))
    return scene.clip_path


def build_outro_clip(ff: FFmpeg, cfg: Config, image_path: str, cta_png: str,
                     out_path: str) -> str:
    """A short closing card: dimmed last image + centered CTA text (silent;
    the music bed carries over it in concat)."""
    dur = cfg.outro_seconds
    inputs = [
        "-i", image_path,
        "-f", "lavfi", "-t", f"{dur:.3f}",
        "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
        "-loop", "1", "-i", cta_png,
    ]
    graph = _kenburns_segment(cfg, dur, 0, 0, "kb")
    graph += ";[kb]eq=brightness=-0.18:saturation=0.9[bg]"
    graph += ";[bg][2:v]overlay=x='(W-w)/2':y='(H-h)/2'[v]"
    ff.run([
        *inputs, "-filter_complex", graph,
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-r", str(cfg.fps),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-t", f"{dur:.3f}", out_path,
    ])
    log.info("CLIP %5.2fs  outro CTA", dur)
    return out_path


def concat_clips(ff: FFmpeg, clip_paths: List[str], clip_durations: List[float],
                 out_path: str, cfg: Config, music_path: Optional[str] = None,
                 whoosh_path: Optional[str] = None) -> str:
    inputs: List[str] = []
    for clip in clip_paths:
        inputs += ["-i", clip]
    n = len(clip_paths)
    total = sum(clip_durations)

    concat_in = "".join(f"[{i}:v][{i}:a]" for i in range(n))
    graph = f"{concat_in}concat=n={n}:v=1:a=1[vc][a]"

    # --- video: progress bar ---
    if cfg.enable_progress_bar:
        barw = _esc(f"iw*min(t/{total:.3f},1)")
        graph += (f";[vc]drawbox=x=0:y=0:w='{barw}':h={cfg.progress_bar_height}:"
                  f"color=white@0.85:t=fill[v]")
        v_map = "[v]"
    else:
        v_map = "[vc]"

    # --- audio: voice + ducked music + whooshes ---
    mix: List[str] = []
    next_idx = n
    boundaries = [sum(clip_durations[:k]) for k in range(1, n)] if whoosh_path else []

    if music_path:
        graph += ";[a]asplit=2[am][ak]"
        inputs += ["-i", music_path]
        graph += f";[{next_idx}:a]aloop=loop=-1:size=2e9,volume={cfg.music_volume}[mraw]"
        next_idx += 1
        # real ducking: voice keys a compressor on the music
        graph += (";[mraw][ak]sidechaincompress="
                  "threshold=0.03:ratio=8:attack=5:release=300[mduck]")
        mix = ["[am]", "[mduck]"]
    else:
        mix = ["[a]"]

    for j, b in enumerate(boundaries):
        inputs += ["-i", whoosh_path]
        ms = int(b * 1000)
        graph += f";[{next_idx}:a]adelay={ms}|{ms},volume=0.5[wh{j}]"
        mix.append(f"[wh{j}]")
        next_idx += 1

    if len(mix) == 1:
        pre = mix[0]
    else:
        graph += (";" + "".join(mix)
                  + f"amix=inputs={len(mix)}:normalize=0:duration=first[premix]")
        pre = "[premix]"
    # EBU R128 loudness normalization to YouTube's ~-14 LUFS target (also peak-limits).
    graph += f";{pre}loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
    a_map = "[aout]"

    ff.run([
        *inputs,
        "-filter_complex", graph,
        "-map", v_map, "-map", a_map,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-r", str(cfg.fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        out_path,
    ])
    log.info("MUX  -> %s  (music=%s, whooshes=%d, bar=%s)",
             out_path, bool(music_path), len(boundaries), cfg.enable_progress_bar)
    return out_path
