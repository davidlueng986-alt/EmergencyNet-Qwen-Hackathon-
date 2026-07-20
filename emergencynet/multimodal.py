"""Multimodal wound-photo review via Qwen Cloud vision (qwen3.7-plus).

Photo + form data → structured escalation suggestions.

Output contract (same shape as multilingual / notes review):
    suggestions: list of {qkey, from, to, rationale|reason}
    visual_findings: short free-text description

Safety:
    - Vision may ONLY suggest No → Yes escalations.
    - Yes / Unknown are never overridden.
    - Photo never traverses LoRa — only text suggestions / findings.
"""
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib import request, error

from .constants import (
    ANSWER_YES, ANSWER_NO,
    SCREENING_QUESTIONS,
)
from .multilingual import _parse_strict_json, _filter_safe_suggestions  # reuse


_SYSTEM_PROMPT = (
    "You are a disaster-triage visual reviewer. Given a single photo of a "
    "patient or wound and a structured form summary, suggest whether any of "
    "the 8 hidden-risk screening questions should escalate from No to Yes "
    "based on visual findings.\n"
    "\n"
    "You may ONLY suggest No -> Yes. You may NEVER override Yes or Unknown. "
    "If the image is uninformative, low-light, blurred, or shows nothing "
    "clinically relevant, return suggestions: [].\n"
    "\n"
    "Visual signs that justify each escalation:\n"
    "  q5  — visible compression by debris, ischemic limb appearance, "
    "         compartment swelling — suggest ONLY if form indicates entrapment\n"
    "  q6  — distended abdomen, visible bruising over flank/torso\n"
    "  q7  — pregnancy-related visual cues only if form marks pregnant\n"
    "  q8  — altered mental status visual cues with trauma context\n"
    "  q9  — facial burn, singed nasal hair, soot in mouth/nostril, "
    "         carbonaceous sputum, swelling of lips/tongue\n"
    "  q10 — significant injury with paradoxically painless presentation\n"
    "  q11 — elderly patient with visible head impact (raccoon eyes, "
    "         Battle's sign, scalp laceration in elderly per form)\n"
    "  q12 — close-range blast pattern (powder burns, peppering, tympanic "
    "         injury suggested by ear bleeding, reported enclosed-space exposure)\n"
    "\n"
    "Output STRICT JSON only (one object). Schema:\n"
    "  {\n"
    '    "image_useful": true|false,\n'
    '    "visual_findings": "<2-3 sentence description of what is seen>",\n'
    '    "suggestions": [\n'
    '      {"qkey": "q9", "from": "No", "to": "Yes", '
    '       "reason": "<short visual+clinical justification>"}\n'
    "    ]\n"
    "  }\n"
    "Use qkey (q5..q12), not a bare letter. Do not emit a second JSON object."
)


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------
class MultimodalReviewer:
    """Qwen Cloud vision review (default qwen3.7-plus)."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_sec: float | None = None,
        max_tokens: int = 384,
        client=None,
        api_key: str | None = None,
    ):
        from .ai_config import chat_completions_url, load_ai_config
        from .field_ai import _is_legacy_local_endpoint
        from .qwen_client import QwenClient

        if endpoint and _is_legacy_local_endpoint(endpoint):
            endpoint = None
        cfg = load_ai_config()
        cfg = cfg.with_overrides(api_key=api_key, base_url=endpoint, model_field=model)
        self.endpoint = chat_completions_url(cfg.base_url)
        self.model = model or cfg.model_vision
        self.timeout_sec = timeout_sec if timeout_sec is not None else cfg.timeout_sec
        self.max_tokens = max_tokens
        self._client = client or QwenClient(cfg)
        self._last_latency_ms: Optional[float] = None
        self._last_error: Optional[str] = None

    def available(self) -> bool:
        return self._client.available()

    def review_photo(
        self,
        image_path: str | Path | bytes,
        form_summary: Dict[str, Any],
        current_answers: Dict[str, str],
    ) -> Dict[str, Any]:
        try:
            b64 = _encode_image_b64(image_path)
        except Exception as exc:
            return _err(f"image-encode-error: {exc}", "")

        form_text = _format_form_summary(form_summary)
        answer_text = "\n".join(
            f"  {q}: {current_answers.get(q, 'Unknown')}"
            for q in SCREENING_QUESTIONS
        )
        user_text = (
            f"Patient form summary:\n{form_text}\n\n"
            f"Current screening answers (do not override Yes or Unknown):\n"
            f"{answer_text}\n\nReturn JSON only."
        )
        resp = self._client.chat_vision(
            user_text,
            b64,
            system=_SYSTEM_PROMPT,
            model=self.model,
        )
        self._last_latency_ms = resp.latency_ms
        self._last_error = resp.error
        if not resp.ok:
            return _err(resp.error or "vision-failed", "")

        content = resp.content or ""
        parsed = _parse_strict_json(content)
        if parsed is None:
            return _err("could not parse model JSON", content)

        suggestions = _filter_safe_suggestions(
            parsed.get("suggestions", []), current_answers,
        )
        return {
            "ok": True,
            "image_useful": bool(parsed.get("image_useful", False)),
            "visual_findings": str(parsed.get("visual_findings", ""))[:600],
            "suggestions": suggestions,
            "raw": content,
            "latency_ms": self._last_latency_ms,
            "error": None,
        }

    @property
    def last_latency_ms(self) -> Optional[float]:
        return self._last_latency_ms

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _encode_image_b64(image: str | Path | bytes) -> str:
    if isinstance(image, (bytes, bytearray)):
        data = bytes(image)
    else:
        p = Path(image)
        if not p.exists():
            raise FileNotFoundError(p)
        data = p.read_bytes()
    if len(data) > 8 * 1024 * 1024:
        # Hard cap — Colab/local endpoints choke on very large images,
        # and clinical photos rarely need >8 MB.
        raise ValueError(f"image too large: {len(data)} bytes")
    return base64.b64encode(data).decode("ascii")


def _format_form_summary(form: Dict[str, Any]) -> str:
    """Compact, readable summary for the model (field Gradio form keys)."""
    keys = (
        "patient_id", "age", "walking",
        "injury_types", "burn_location", "airway_signs",
        "breathing_status", "resp_rate", "pulse_radial", "mental_status",
        "pain_response", "entrapment_min", "special_markers", "preg_symptoms",
        "notes",
    )
    lines: List[str] = []
    for k in keys:
        v = form.get(k)
        if v in (None, "", []):
            continue
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        lines.append(f"  {k}: {v}")
    return "\n".join(lines) if lines else "  (no form data)"


def _err(msg: str, raw: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "image_useful": False,
        "visual_findings": "",
        "suggestions": [],
        "raw": raw,
        "latency_ms": None,
        "error": msg,
    }
