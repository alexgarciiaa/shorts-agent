"""Second-pass fact verification.

For a "did you know" channel, posting a hallucinated fact hurts credibility and can
trip YouTube's misinformation policies. After the script is written, we ask the LLM
(low temperature) to fact-check each narration line and rewrite any inaccurate ones.
Best-effort: if no LLM key / it fails, we return "unknown" and change nothing.
"""
from __future__ import annotations

import logging

from .script import (_GEMINI_URL, _GROQ_MODEL, _GROQ_URL, _LANGUAGES, _loads,
                     _post_json)

log = logging.getLogger(__name__)

_FC_PROMPT = """You are a rigorous fact-checker for a "did you know" facts channel.
Review each numbered NARRATION line for factual accuracy and misleading exaggeration.
If a line is inaccurate, write a corrected version IN {language} that stays short and
punchy (max ~16 words), keeps the same intent, but is TRUE. Hooks/teasers with no
factual claim are accurate by default.
Return ONLY minified JSON:
{{"overall_risk":"low|medium|high","scenes":[{{"id":1,"accurate":true,"issue":"","corrected":""}}]}}

Narration lines:
{lines}"""


def verify_facts(project, gemini_key: str = "", groq_key: str = "",
                 language: str = "en") -> str:
    """Fact-check and (in place) fix scene narration. Returns overall risk level."""
    lines = "\n".join(f"{s.id}: {s.narration}" for s in project.scenes)
    prompt = _FC_PROMPT.format(language=_LANGUAGES.get(language, "ENGLISH"), lines=lines)

    data = None
    if gemini_key:
        try:
            data = _gemini(prompt, gemini_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("Fact-check via Gemini failed (%s); trying fallback", exc)
    if data is None and groq_key:
        try:
            data = _groq(prompt, groq_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("Fact-check via Groq failed (%s); skipping", exc)
    if data is None:
        return "unknown"

    by_id = {s.id: s for s in project.scenes}
    fixed = 0
    for item in data.get("scenes", []):
        if item.get("accurate", True):
            continue
        scene = by_id.get(item.get("id"))
        issue = item.get("issue", "")
        corrected = (item.get("corrected") or "").strip()
        if scene and corrected:
            log.warning("FACT-CHECK fixed scene %s (%s)", scene.id, issue or "inaccurate")
            log.info("   was: %s", scene.narration)
            log.info("   now: %s", corrected)
            scene.narration = corrected
            fixed += 1
        elif scene:
            log.warning("FACT-CHECK flagged scene %s (no fix offered): %s", scene.id, issue)
    risk = data.get("overall_risk", "unknown")
    log.info("Fact-check: risk=%s, %d scene(s) corrected", risk, fixed)
    return risk


def _gemini(prompt: str, key: str) -> dict:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2,
                             "maxOutputTokens": 2048, "thinkingConfig": {"thinkingBudget": 0}},
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    result = _post_json(_GEMINI_URL, body, headers)
    return _loads(result["candidates"][0]["content"]["parts"][0]["text"])


def _groq(prompt: str, key: str) -> dict:
    payload = {
        "model": _GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}, "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    result = _post_json(_GROQ_URL, payload, headers)
    return _loads(result["choices"][0]["message"]["content"])
