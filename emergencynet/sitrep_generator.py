"""SITREP (Situation Report) builder.

Folds the running patient list, anomaly alerts, comparator disagreements
and (optionally) a strategy-AI advice block into a single human-readable
report suitable for the base-station commander dashboard.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional

from .constants import TAG_RED, TAG_YELLOW, TAG_GREEN, TAG_BLACK, ZONE_NAME
from .triage_core import summarise_tags
from .protocol_db import all_protocol_names


def build_sitrep(
    patients: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    disagreements: List[Dict[str, Any]],
    zone_breakdown: Optional[Dict[int, int]] = None,
    advice: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Returns a dict containing both a markdown text and the structured
    fields used by the dashboard.

    The markdown is what the user sees; the structured fields are what
    the dashboard tables / charts consume.
    """
    summary = summarise_tags(
        [{"triage_tag": p.get("triage_tag")} for p in patients]
    )

    high_severity_disagreements = [
        d for d in disagreements
        if d.get("severity") in ("major", "critical")
    ]

    md_parts: List[str] = []
    md_parts.append(f"# SITREP — {len(patients)} patients on net\n")

    md_parts.append("## Triage breakdown")
    md_parts.append(
        f"- RED:    {summary[TAG_RED]}\n"
        f"- YELLOW: {summary[TAG_YELLOW]}\n"
        f"- GREEN:  {summary[TAG_GREEN]}\n"
        f"- BLACK:  {summary[TAG_BLACK]}\n"
    )

    if zone_breakdown:
        md_parts.append("## Zone breakdown")
        for code, count in sorted(zone_breakdown.items(), key=lambda x: -x[1]):
            md_parts.append(f"- {ZONE_NAME.get(code, '?')}: {count}")
        md_parts.append("")

    if alerts:
        md_parts.append("## Active anomalies")
        for a in alerts:
            md_parts.append(
                f"- [{a.get('severity','?').upper()}] {a.get('type','?')}: "
                f"{a.get('message','')}"
            )
        md_parts.append("")

    # Field-vs-shadow disagreements removed from product (no base shadow).

    if advice:
        md_parts.append("## Advisor")
        if advice.get("summary"):
            md_parts.append(f"**Summary:** {advice['summary']}")

        # v5.3 5-field schema (StrategyAI.advise() output)
        # Rendered to match the Advisor tab in base_dashboard.py so
        # SITREP report == Advisor tab display. Was silently dropping
        # key_findings/recommended_actions/things_to_watch/uncertainty_notes
        # (KI-10). See DOC_REALITY_DIFF.md row 39.
        key_findings = advice.get("key_findings") or []
        if key_findings:
            md_parts.append("\n**Key Findings:**")
            for f in key_findings:
                md_parts.append(f"- {f}")

        actions = advice.get("recommended_actions") or []
        if actions:
            md_parts.append("\n**Recommended Actions:**")
            md_parts.append("| Priority | Action | Rationale |")
            md_parts.append("|---|---|---|")
            for a in actions:
                prio = str(a.get("priority", "")).upper()
                action = a.get("action", "")
                rationale = a.get("rationale", "")
                md_parts.append(f"| {prio} | {action} | {rationale} |")

        watches = advice.get("things_to_watch") or []
        if watches:
            md_parts.append("\n**Things to Watch:**")
            for w in watches:
                md_parts.append(f"- {w}")

        if advice.get("uncertainty_notes"):
            md_parts.append(f"\n**Uncertainty:** _{advice['uncertainty_notes']}_")

        # Legacy v4 keys (hazmat/command/citations) — kept as dead-branch
        # fallback for any external caller still passing the old shape.
        # StrategyAI.advise() v5.3+ no longer produces these, so in the
        # normal SITREP path these blocks render nothing.
        if advice.get("hazmat"):
            md_parts.append(f"\n**HazMat:** {advice['hazmat']}")
        if advice.get("command"):
            md_parts.append(f"\n**Command:** {advice['command']}")
        cits = advice.get("citations") or []
        if cits:
            md_parts.append("\n**Citations:** " + ", ".join(
                f"{c.get('source','?')}" for c in cits
            ))
        md_parts.append("")

    md_parts.append("---")
    md_parts.append(
        "Protocols recognised by this system: "
        + ", ".join(all_protocol_names())
    )

    return {
        "markdown": "\n".join(md_parts),
        "summary_counts": summary,
        "alert_count": len(alerts),
        "disagreement_count": len(high_severity_disagreements),
        "patient_count": len(patients),
    }
