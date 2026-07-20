"""
Deterministic triage engine — START / JumpSTART + hidden-risk override.

This module is the single source of truth for triage decisions at the field
edge. The current Base path trusts and aggregates the transmitted deterministic
result; it does not run a second AI or shadow re-triage pass.

No AI. No randomness. No network calls. Pure Python.
"""

from typing import Dict, List, Optional, Any
from .constants import (
    TAG_RED, TAG_YELLOW, TAG_GREEN, TAG_BLACK,
    TAG_RANK, TAG_BASE_SCORE,
    SAFETY_CRITICAL_QS, SCREENING_QUESTIONS,
    ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN, VALID_ANSWERS,
    RISK_LEVEL_SCORE, RISK_RED_NOW, RISK_RED_WITHIN_HOUR,
    SPECIAL_PREGNANT, SPECIAL_CHILD, SPECIAL_ELDERLY,
)
from .risk_engine import evaluate_hidden_risks, risks_force_red


def _normalize(val: Any) -> str:
    """Coerce various truthy/falsy forms into Yes/No/Unknown."""
    if val is True:
        return ANSWER_YES
    if val is False:
        return ANSWER_NO
    if val is None:
        return ANSWER_UNKNOWN
    if isinstance(val, str):
        v = val.strip().lower()
        if v in ("yes", "y", "true", "1"):
            return ANSWER_YES
        if v in ("no", "n", "false", "0"):
            return ANSWER_NO
    return ANSWER_UNKNOWN


def normalize_screening(answers: Dict[str, Any]) -> Dict[str, str]:
    """Return a copy of answers with every value canonicalised.
    Missing questions default to Unknown."""
    return {q: _normalize(answers.get(q)) for q in SCREENING_QUESTIONS}


def compute_confidence(answers: Dict[str, str]) -> float:
    """Confidence = 1 - (unknown_count / 12), capped at 0.4 if any
    safety-critical Q is Unknown."""
    unknown_total = sum(1 for v in answers.values() if v == ANSWER_UNKNOWN)
    base = 1.0 - (unknown_total / 12.0)
    safety_unknowns = sum(1 for q in SAFETY_CRITICAL_QS
                          if answers.get(q) == ANSWER_UNKNOWN)
    if safety_unknowns > 0:
        base = min(base, 0.4)
    return round(base, 2)


def triage_and_risk(
    screening_answers: Dict[str, Any],
    patient_record: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Main decision function.

    Args:
        screening_answers: dict with keys q1..q12 and values Yes/No/Unknown
                           (case-insensitive, bool-friendly)
        patient_record:    dict containing patient metadata
                           (ambulatory, age_estimate, special_markers, etc.)

    Returns:
        {
          "triage_tag":      "RED" | "YELLOW" | "GREEN" | "BLACK",
          "hidden_risks":    [ {risk, detail, timeline, action, source, risk_level}, ...],
          "priority_score":  int,
          "confidence":      float 0..1,
          "needs_human_review": bool,
          "rationale":       [str, ...],
          "screening_answers": {q1..q12: Yes/No/Unknown},   # canonicalised copy
        }
    """
    patient_record = patient_record or {}
    q = normalize_screening(screening_answers)

    # --- Confidence & review flags ---
    confidence = compute_confidence(q)
    needs_review = any(q[qk] == ANSWER_UNKNOWN for qk in SAFETY_CRITICAL_QS)
    if confidence < 0.6:
        needs_review = True

    rationale: List[str] = []
    hidden_risks = evaluate_hidden_risks(q)

    # --- BLACK: not breathing after airway reposition (Q1) ---
    # Pediatric override handled at screening layer (5 rescue breaths); here we
    # simply trust Q1 semantics.
    if q["q1"] == ANSWER_YES:
        tag = TAG_BLACK
        rationale.append("Q1 = Yes (no breathing after airway repositioning) -> BLACK per START")
        return _finalise(tag, q, hidden_risks, patient_record,
                         confidence, needs_review, rationale)

    # --- Collect RED flags ---
    is_red = False
    if q["q2"] == ANSWER_YES:
        is_red = True
        rationale.append("Q2 = Yes (respiratory rate >30 or <10) -> RED per START")
    if q["q3"] == ANSWER_YES:
        is_red = True
        rationale.append("Q3 = Yes (no radial pulse / perfusion failure) -> RED per START")
    if q["q4"] == ANSWER_YES:
        is_red = True
        rationale.append("Q4 = Yes (cannot follow commands) -> RED per START")

    # --- Hidden risks can escalate to RED ---
    if risks_force_red(hidden_risks):
        is_red = True
        for r in hidden_risks:
            if r["risk_level"] in (RISK_RED_NOW, RISK_RED_WITHIN_HOUR):
                rationale.append(
                    f"Hidden risk {r['risk']} ({r['risk_level']}) -> override to RED"
                )

    if is_red:
        return _finalise(TAG_RED, q, hidden_risks, patient_record,
                         confidence, needs_review, rationale)

    # --- YELLOW vs GREEN: ambulatory status ---
    ambulatory = patient_record.get("ambulatory")
    if ambulatory is False or (isinstance(ambulatory, str)
                               and ambulatory.lower() in ("false", "no")):
        rationale.append("Non-ambulatory but stable vitals -> YELLOW per START")
        return _finalise(TAG_YELLOW, q, hidden_risks, patient_record,
                         confidence, needs_review, rationale)

    rationale.append("Ambulatory + stable vitals + no red flags -> GREEN per START")
    return _finalise(TAG_GREEN, q, hidden_risks, patient_record,
                     confidence, needs_review, rationale)


def _finalise(
    tag: str,
    answers: Dict[str, str],
    hidden_risks: List[Dict[str, str]],
    patient_record: Dict[str, Any],
    confidence: float,
    needs_review: bool,
    rationale: List[str],
) -> Dict[str, Any]:
    """Compute priority score and assemble the result dict."""
    score = _priority_score(tag, answers, hidden_risks, patient_record)
    return {
        "triage_tag": tag,
        "hidden_risks": hidden_risks,
        "priority_score": score,
        "confidence": confidence,
        "needs_human_review": needs_review,
        "rationale": rationale,
        "screening_answers": answers,
        # Echo the patient_record so downstream UI / ranking / SITREP can
        # show the patient_id without having to re-zip a parallel list.
        "patient_record": patient_record,
        "patient_id": patient_record.get("patient_id"),
    }


def _priority_score(
    tag: str,
    answers: Dict[str, str],
    hidden_risks: List[Dict[str, str]],
    patient_record: Dict[str, Any],
) -> int:
    """Priority-ranking formula.

    base (tag)
      + per-risk bonus based on risk_level
      + +30 if BOTH Q2 and Q3 = Yes (double vital failure)
      + +10 if Q9 = Yes (airway is time-critical even among REDs)
      + +10 pregnant / +5 child / +5 elderly
      - 5 per safety-critical Unknown
    """
    score = TAG_BASE_SCORE.get(tag, 0)

    for r in hidden_risks:
        score += RISK_LEVEL_SCORE.get(r["risk_level"], 0)

    if answers.get("q2") == ANSWER_YES and answers.get("q3") == ANSWER_YES:
        score += 30
    if answers.get("q9") == ANSWER_YES:
        score += 10

    specials = patient_record.get("special_markers") or []
    if isinstance(specials, str):
        specials = [specials]
    if SPECIAL_PREGNANT in specials:
        score += 10
    if SPECIAL_CHILD in specials:
        score += 5
    if SPECIAL_ELDERLY in specials:
        score += 5

    for qk in SAFETY_CRITICAL_QS:
        if answers.get(qk) == ANSWER_UNKNOWN:
            score -= 5

    return max(score, 0)


def rank_patients(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort a list of triage_and_risk() outputs by evacuation priority.

    Returns the same list (in-place friendly) with an added 'evacuation_rank'
    field (1-based).
    """
    ordered = sorted(
        results,
        key=lambda r: (
            TAG_RANK.get(r.get("triage_tag"), 99),
            -r.get("priority_score", 0),
            -(r.get("confidence", 0.0)),
        ),
    )
    for i, r in enumerate(ordered, start=1):
        r["evacuation_rank"] = i
    return ordered


def summarise_tags(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {TAG_RED: 0, TAG_YELLOW: 0, TAG_GREEN: 0, TAG_BLACK: 0}
    for r in results:
        t = r.get("triage_tag")
        if t in counts:
            counts[t] += 1
    return counts
