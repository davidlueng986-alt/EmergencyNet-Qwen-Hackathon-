"""Multilingual notes review via qwen3.7-plus (no separate MT model).

Plus supports 100+ languages; notes go straight to clinical escalate-only JSON.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from .constants import (
    ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN,
    SCREENING_QUESTIONS,
)


SUPPORTED_LANGUAGES = (
    ("auto", "Auto-detect"),
    ("en",   "English"),
    ("zh",   "Mandarin Chinese (中文)"),
    ("zh-tw","Traditional Chinese (繁體)"),
    ("ja",   "Japanese (日本語)"),
    ("ko",   "Korean (한국어)"),
    ("vi",   "Vietnamese (Tiếng Việt)"),
    ("id",   "Indonesian (Bahasa Indonesia)"),
    ("tl",   "Filipino (Tagalog)"),
    ("th",   "Thai (ภาษาไทย)"),
    ("ms",   "Malay (Bahasa Melayu)"),
    ("ar",   "Arabic (العربية)"),
    ("es",   "Spanish (Español)"),
    ("fr",   "French (Français)"),
)


_ESCALATE_SYSTEM = (
    "You are a disaster-triage screening reviewer. Notes may be in any language. "
    "Given free-text notes and current Yes/No/Unknown screening answers, suggest "
    "ONLY No -> Yes escalations when notes clearly support them. Never override "
    "Yes or Unknown. Optionally set translation_en to an English rendering of notes "
    "(identical if already English).\n"
    "The 8 hidden-risk questions are:\n"
    "  q5 — Entrapment >30 min\n"
    "  q6 — Distended/rigid abdomen\n"
    "  q7 — Pregnancy abdominal pain or bleeding\n"
    "  q8 — New-onset altered mental status post-trauma\n"
    "  q9 — Airway-burn signs\n"
    "  q10 — Significant injury but reports NO PAIN\n"
    "  q11 — Elderly with head impact and confusion\n"
    "  q12 — Close-range blast exposure\n"
    "Output STRICT JSON only:\n"
    '{"detected_lang":"xx","translation_en":"...","suggestions":'
    '[{"q":"q9","from":"No","to":"Yes","rationale":"..."}]}\n'
    "Empty suggestions if no escalation."
)


def translate_and_review(
    notes: str,
    current_answers: Dict[str, str],
    ai_callable: Optional[Callable[..., str]] = None,
    source_lang_hint: str = "auto",
    **_kwargs,
) -> Dict[str, Any]:
    """Single-model multilingual review (qwen3.7-plus). MT path removed."""
    if not notes or not notes.strip():
        return {
            "ok": True,
            "detected_lang": "n/a",
            "translation_en": "",
            "suggestions": [],
            "raw": "",
            "error": None,
        }

    if ai_callable is None:
        return {
            "ok": True,
            "detected_lang": source_lang_hint or "unknown",
            "translation_en": notes.strip(),
            "suggestions": [],
            "raw": "",
            "error": None,
        }

    answers_text = "\n".join(
        f"  {q}: {current_answers.get(q, ANSWER_UNKNOWN)}"
        for q in SCREENING_QUESTIONS
    )
    user = (
        f"Language hint: {source_lang_hint}\n"
        f"Notes:\n<<<\n{notes.strip()}\n>>>\n\n"
        f"Current answers:\n{answers_text}\n\nReturn JSON only."
    )
    try:
        try:
            raw = ai_callable(user, system=_ESCALATE_SYSTEM)
        except TypeError:
            raw = ai_callable(_ESCALATE_SYSTEM + "\n\n" + user)
    except Exception as exc:
        return _err(str(exc), "")

    if not raw or not str(raw).strip():
        return {
            "ok": True,
            "detected_lang": source_lang_hint or "unknown",
            "translation_en": notes.strip(),
            "suggestions": [],
            "raw": "",
            "error": None,
        }

    parsed = _parse_strict_json(str(raw))
    if parsed is None:
        return {
            "ok": False,
            "detected_lang": "unknown",
            "translation_en": notes.strip(),
            "suggestions": [],
            "raw": str(raw),
            "error": "could not parse JSON",
        }

    suggestions = _filter_safe_suggestions(
        parsed.get("suggestions", []),
        current_answers,
    )
    return {
        "ok": True,
        "detected_lang": str(parsed.get("detected_lang", source_lang_hint or "unknown"))[:16],
        "translation_en": str(parsed.get("translation_en", notes)).strip() or notes.strip(),
        "suggestions": suggestions,
        "raw": str(raw),
        "error": None,
    }


def _err(msg: str, raw: str) -> Dict[str, Any]:
    return {
        "ok": False,
        "detected_lang": "unknown",
        "translation_en": "",
        "suggestions": [],
        "raw": raw,
        "error": msg,
    }


def _parse_strict_json(raw: str) -> Optional[Dict[str, Any]]:
    text = re.sub(r"```(?:json)?\s*", "", raw)
    text = re.sub(r"```\s*", "", text)
    try:
        start = text.index("{")
        depth = 0
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:j + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    return None


def _filter_safe_suggestions(
    suggestions: Any,
    current_answers: Dict[str, str],
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if not isinstance(suggestions, list):
        return out
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        q = str(s.get("q") or s.get("qkey") or "").lower()
        if q not in SCREENING_QUESTIONS:
            continue
        if current_answers.get(q) != ANSWER_NO:
            continue
        to_val = str(s.get("to") or ANSWER_YES)
        if to_val != ANSWER_YES:
            continue
        out.append({
            "q": q,
            "qkey": q,
            "from": ANSWER_NO,
            "to": ANSWER_YES,
            "rationale": str(s.get("rationale") or s.get("reason") or "")[:200],
        })
    return out
