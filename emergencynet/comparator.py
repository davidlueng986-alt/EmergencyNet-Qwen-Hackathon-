"""Field-vs-shadow disagreement comparator.

Given a field-decoded patient (what the OnePlus Pad sent over LoRa) and
the shadow-inference result computed at the base, produce a structured
disagreement record the commander can review.

A disagreement is *visible* (commander sees it) when:
    - tags differ, OR
    - any of the 12 screening answers differ, OR
    - hidden_risk_qs differ
"""
from __future__ import annotations

from typing import Dict, Any, List


def compare_field_vs_shadow(
    decoded: Dict[str, Any],
    shadow: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a diff between the field decision (in ``decoded``) and the
    shadow decision (``shadow["shadow_result"]``)."""
    field_tag = decoded.get("triage_tag")
    shadow_result = shadow.get("shadow_result", {})
    shadow_tag = shadow_result.get("triage_tag")

    field_screen = decoded.get("screening") or {}
    shadow_screen = shadow.get("shadow_screening") or {}

    answer_diffs: List[Dict[str, str]] = []
    for q in [f"q{i}" for i in range(1, 13)]:
        f = field_screen.get(q)
        s = shadow_screen.get(q)
        if f != s:
            answer_diffs.append({"qkey": q, "field": str(f), "shadow": str(s)})

    field_risks = set(decoded.get("hidden_risk_qs") or [])
    shadow_risk_qs = {
        r.get("qkey")
        for r in (shadow_result.get("hidden_risks") or [])
        if r.get("qkey")
    }
    field_only = sorted(field_risks - shadow_risk_qs)
    shadow_only = sorted(shadow_risk_qs - field_risks)

    has_diff = (
        field_tag != shadow_tag
        or bool(answer_diffs)
        or bool(field_only)
        or bool(shadow_only)
    )

    severity = "none"
    if field_tag != shadow_tag:
        # Tag-level disagreement is the most important
        severity = _tag_diff_severity(field_tag, shadow_tag)
    elif answer_diffs or field_only or shadow_only:
        severity = "minor"

    return {
        "has_disagreement": has_diff,
        "severity": severity,
        "field_tag": field_tag,
        "shadow_tag": shadow_tag,
        "answer_diffs": answer_diffs,
        "risks_field_only": field_only,
        "risks_shadow_only": shadow_only,
        "shadow_confidence": shadow_result.get("confidence"),
    }


def _tag_diff_severity(field_tag: str, shadow_tag: str) -> str:
    """Heuristic: shadow saying RED while field says GREEN/BLACK is critical."""
    pri = {"RED": 0, "YELLOW": 1, "GREEN": 2, "BLACK": 3}
    if field_tag is None or shadow_tag is None:
        return "minor"
    if "RED" in (field_tag, shadow_tag):
        # If one of them is RED and the other isn't, that's critical
        if field_tag != shadow_tag:
            return "critical"
    if pri.get(field_tag, 9) != pri.get(shadow_tag, 9):
        return "major"
    return "minor"
