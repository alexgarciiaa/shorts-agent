"""Script/idea generation.

`build_script()` returns a VideoProject. If a Gemini key is present it asks the
LLM for a fresh "did you know" script; otherwise it uses a built-in sample so
the MVP runs end-to-end with zero keys.
"""
from __future__ import annotations

import json
import logging
import time

import requests

from ..models import Scene, VideoProject

log = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"

_LANGUAGES = {"en": "ENGLISH", "es": "SPANISH", "pt": "PORTUGUESE", "fr": "FRENCH"}

_PROMPT = """You are a top-tier viral YouTube Shorts writer for a "did you know / mind-blowing facts" channel.
Write a {n}-scene short. The spoken NARRATION, title and description must be in {language}.
Topic / seed idea: {seed}.

WRITING RULES (make it genuinely interesting, not generic):
- Scene 1 is a short INTRO HOOK that opens with "Did you know..." and teases the
  topic to stop the scroll, WITHOUT revealing a fact yet
  (e.g. "Did you know your body does something insane every single night?").
- Scenes 2 onward deliver the actual surprising facts — one fact per scene.
- Pick FRESH, surprising facts most people DON'T already know. Avoid the obvious
  textbook ones. Each fact must have a concrete, specific, jaw-dropping detail
  (a number, comparison, or vivid consequence).
- ESCALATE: order the facts so intrigue builds, and save the single most
  mind-blowing fact for the last scene before the call to action.
- Tone: punchy, energetic, conversational. Each narration line max ~16 words.

IMPORTANT: write 'image_prompt' values in ENGLISH (image models work best in English),
even when the narration is in another language.
Image prompts must be SPECIFIC and VISUALLY DIVERSE across scenes: each one a
concrete, different subject and composition (vary scale, angle, and setting), not
generic repeats of the same picture. Keep a single cohesive 'visual_style' that ties
them together.

Return ONLY valid minified JSON with this exact shape:
{{"topic":"","hook":"","visual_style":"cinematic ...","music_mood":"","cta":"",
"scenes":[{{"narration":"","image_prompt":""}}],
"title":"","description":"","tags":["",""]}}"""


def _prompt(n: int, seed: str, language: str = "en") -> str:
    return _PROMPT.format(n=n, seed=seed or "any mind-blowing topic",
                          language=_LANGUAGES.get(language, "ENGLISH"))


def _host(url: str) -> str:
    return url.split("://")[-1].split("/")[0]


def _loads(text: str) -> dict:
    """Tolerant JSON parse: strips markdown fences and extracts the {...} object."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _post_json(url: str, payload: dict, headers: dict, attempts: int = 3,
               timeout: int = 60) -> dict:
    """POST with retry on transient 5xx/network errors. Errors are sanitized to
    the hostname only — never the URL or body — so API keys never reach the logs."""
    err = "unknown"
    for i in range(attempts):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            err = type(exc).__name__
            time.sleep(1.0 * (i + 1))
            continue
        if resp.status_code < 400:
            return resp.json()
        if 400 <= resp.status_code < 500:
            raise RuntimeError(f"HTTP {resp.status_code} from {_host(url)}")
        err = f"HTTP {resp.status_code}"
        time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"{_host(url)} failed after {attempts} tries ({err})")


def build_script(gemini_api_key: str = "", groq_api_key: str = "",
                 n_scenes: int = 6, seed: str = "", language: str = "en") -> VideoProject:
    """Try Gemini, fall back to Groq, then to the built-in sample script."""
    if gemini_api_key:
        try:
            return _from_gemini(gemini_api_key, n_scenes, seed, language)
        except Exception as exc:  # noqa: BLE001
            log.warning("Gemini script failed (%s); trying fallback", exc)
    if groq_api_key:
        try:
            return _from_groq(groq_api_key, n_scenes, seed, language)
        except Exception as exc:  # noqa: BLE001
            log.warning("Groq script failed (%s); using sample script", exc)
    return _sample_script()


def _from_groq(api_key: str, n_scenes: int, seed: str = "",
               language: str = "en") -> VideoProject:
    payload = {
        "model": _GROQ_MODEL,
        "messages": [{"role": "user", "content": _prompt(n_scenes, seed, language)}],
        "response_format": {"type": "json_object"},
        "temperature": 1.0,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = _post_json(_GROQ_URL, payload, headers)
    data = _loads(result["choices"][0]["message"]["content"])
    log.info("Groq script ok: %s", data.get("topic", ""))
    return _to_project(data)


def _from_gemini(api_key: str, n_scenes: int, seed: str = "",
                 language: str = "en") -> VideoProject:
    body = {
        "contents": [{"parts": [{"text": _prompt(n_scenes, seed, language)}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 1.0,
            "maxOutputTokens": 4096,
            # disable "thinking" so it doesn't eat the output budget and truncate JSON
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    # key goes in a header (NOT the URL) so it never lands in logs/exceptions.
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    result = _post_json(_GEMINI_URL, body, headers)
    text = result["candidates"][0]["content"]["parts"][0]["text"]
    data = _loads(text)
    log.info("Gemini script ok: %s", data.get("topic", ""))
    return _to_project(data)


def _to_project(data: dict) -> VideoProject:
    scenes = [
        Scene(id=i + 1, narration=s["narration"], image_prompt=s["image_prompt"])
        for i, s in enumerate(data["scenes"])
    ]
    return VideoProject(
        topic=data.get("topic", ""), hook=data.get("hook", ""),
        visual_style=data.get("visual_style", ""), music_mood=data.get("music_mood", ""),
        cta=data.get("cta", "Follow for more"), scenes=scenes,
        title=data.get("title", ""), description=data.get("description", ""),
        tags=data.get("tags", []),
    )


def _sample_script() -> VideoProject:
    style = "cinematic space photography, dramatic lighting, ultra detailed, vivid colors"
    facts = [
        ("Here are 7 space facts that sound completely fake but are 100% real.",
         "a breathtaking view of deep space full of colorful nebulae and stars, cinematic"),
        ("A day on Venus is longer than its entire year.",
         "the planet Venus glowing orange, thick swirling clouds, dramatic cinematic space art"),
        ("There is a planet made of burning ice, hotter than fire yet frozen solid.",
         "an exotic blue ice planet glowing with heat in deep space, surreal, cinematic"),
        ("One teaspoon of a neutron star would weigh about a billion tons.",
         "a glowing dense neutron star emitting radiation beams, cosmic, dramatic, cinematic"),
        ("In space, two pieces of metal can weld together instantly on contact.",
         "two metal spacecraft parts touching in orbit above Earth, sparks, cinematic realism"),
        ("The footprints left on the Moon will stay there for millions of years.",
         "a close-up of an astronaut boot footprint on the grey lunar surface, cinematic"),
        ("Jupiter's Great Red Spot is a storm bigger than the entire Earth.",
         "Jupiter's giant swirling red storm seen from space, immense scale, cinematic"),
        ("And somewhere out there, it literally rains glass sideways at 5,000 mph.",
         "an alien planet with sideways glass rain storms, violent winds, cinematic sci-fi art"),
    ]
    scenes = [Scene(id=i + 1, narration=n, image_prompt=p) for i, (n, p) in enumerate(facts)]
    return VideoProject(
        topic="7 space facts that sound fake",
        hook="7 space facts that sound completely fake",
        visual_style=style,
        music_mood="curious-epic",
        cta="Follow for daily facts",
        scenes=scenes,
        title="7 Space Facts That Sound FAKE (But Are 100% Real) 🤯 #shorts",
        description="7 unbelievable space facts that are actually true. "
                    "Follow for daily mind-blowing facts!\n#space #facts #didyouknow #shorts",
        tags=["space", "facts", "did you know", "shorts", "universe", "science"],
    )
