"""
Form -> 12-Q screening converter (pure Python, NO AI).

This is the deterministic mapping from Gradio form values to the 12 screening
answers. The function `form_to_screening` is the single conversion point used
by the field device. The transmitted packet carries the resulting answers and
tag; the active base pipeline decodes and aggregates them without a second
"shadow" triage model.

Optional AI helpers in this file:
    review_notes_with_ai(form, current_answers, ai_callable)
        Reads the free-text 'notes' field and *suggests* answer changes
        (No -> Yes only, never the reverse). Operator must accept manually.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple
from .constants import (
    ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN,
    SCREENING_QUESTIONS,
    BREATHING_NORMAL, BREATHING_RAPID_WEAK, BREATHING_ABSENT,
    PULSE_STRONG, PULSE_WEAK, PULSE_ABSENT,
    MENTAL_ALERT, MENTAL_CONFUSED, MENTAL_UNRESPONSIVE,
    PAIN_YES, PAIN_NO, PAIN_UNKNOWN,
    INJURY_BLEEDING, INJURY_FRACTURE, INJURY_BURN, INJURY_ENTRAPPED,
    INJURY_EXPLOSION, INJURY_ABDOMINAL, INJURY_HEAD_TRAUMA,
    BURN_FACE, BURN_NECK,
    AIRWAY_SOOT, AIRWAY_HOARSE,
    SPECIAL_PREGNANT, SPECIAL_CHILD, SPECIAL_ELDERLY,
    PREG_ABDOMINAL, PREG_BLEEDING, PREG_FETAL,
    CRUSH_MIN_THRESHOLD,
    PEDIATRIC_RR_HIGH, PEDIATRIC_RR_LOW,
    ADULT_RR_HIGH, ADULT_RR_LOW,
)


# =============================================================================
# Form value validators
# =============================================================================
def _as_list(val) -> List[str]:
    """Tolerate scalar / None / list inputs."""
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(x) for x in val]
    return [str(val)]


def _is_pediatric(form: Dict[str, Any]) -> bool:
    specials = _as_list(form.get("special_markers"))
    if SPECIAL_CHILD in specials:
        return True
    age = form.get("age")
    if age is None:
        return False
    try:
        return int(age) < 8
    except (ValueError, TypeError):
        return False


# =============================================================================
# 12-Q derivation rules (one helper per question)
# =============================================================================
def _q1_breathing_absent(form: Dict[str, Any]) -> str:
    """Q1: Not breathing after airway repositioning?

    For pediatric (JumpSTART): if breathing absent, the responder is supposed
    to give 5 rescue breaths first. We can't know the result of that here, so
    we return Unknown for absent-breathing pediatric -> forces human review.
    """
    if form.get("breathing_status") == BREATHING_ABSENT:
        if _is_pediatric(form):
            # JumpSTART: rescue-breath outcome unknown until responder tries
            return ANSWER_UNKNOWN
        return ANSWER_YES
    return ANSWER_NO


def _q2_resp_rate(form: Dict[str, Any]) -> str:
    """Q2: RR > threshold or < threshold?
       Pediatric (JumpSTART): >45 or <15
       Adult (START):         >30 or <10
    """
    if form.get("breathing_status") == BREATHING_RAPID_WEAK:
        return ANSWER_YES
    rr = form.get("resp_rate")
    if rr is None:
        return ANSWER_NO  # we have a categorical breathing field; trust that
    try:
        rr = int(rr)
    except (ValueError, TypeError):
        return ANSWER_UNKNOWN
    if rr <= 0:
        # zero implies absent breathing -> Q1 covers it
        return ANSWER_NO
    if _is_pediatric(form):
        if rr > PEDIATRIC_RR_HIGH or rr < PEDIATRIC_RR_LOW:
            return ANSWER_YES
        return ANSWER_NO
    if rr > ADULT_RR_HIGH or rr < ADULT_RR_LOW:
        return ANSWER_YES
    return ANSWER_NO


def _q3_pulse(form: Dict[str, Any]) -> str:
    """Q3: No radial pulse?  weak -> Unknown (clinically ambiguous)."""
    pulse = form.get("pulse_radial")
    if pulse == PULSE_ABSENT:
        return ANSWER_YES
    if pulse == PULSE_STRONG:
        return ANSWER_NO
    if pulse == PULSE_WEAK:
        return ANSWER_UNKNOWN
    return ANSWER_UNKNOWN


def _q4_cant_follow_commands(form: Dict[str, Any]) -> str:
    """Q4: Cannot follow simple commands?
    'unresponsive' -> Yes; 'confused/drowsy' is captured by Q8 (altered MS).
    """
    return ANSWER_YES if form.get("mental_status") == MENTAL_UNRESPONSIVE else ANSWER_NO


def _q5_crush(form: Dict[str, Any]) -> str:
    """Q5: Trapped > 30 min?"""
    injuries = _as_list(form.get("injury_types"))
    if INJURY_ENTRAPPED not in injuries:
        return ANSWER_NO
    minutes = form.get("entrapment_min")
    if minutes is None:
        # injury says entrapped but no duration -> safer to flag
        return ANSWER_UNKNOWN
    try:
        minutes = int(minutes)
    except (ValueError, TypeError):
        return ANSWER_UNKNOWN
    return ANSWER_YES if minutes >= CRUSH_MIN_THRESHOLD else ANSWER_NO


def _q6_abdominal(form: Dict[str, Any]) -> str:
    """Q6: Abdominal pain after blunt trauma?"""
    injuries = _as_list(form.get("injury_types"))
    return ANSWER_YES if INJURY_ABDOMINAL in injuries else ANSWER_NO


def _q7_pregnancy(form: Dict[str, Any]) -> str:
    """Q7: Pregnant + (abdominal pain OR vaginal bleeding OR decreased fetal movement)?

    Form contract:
        - special_markers includes 'pregnant' to enable
        - preg_symptoms is a checkbox group (visible only when pregnant);
          contains any of: abdominal_pain, vaginal_bleeding, decreased_fetal_movement
        - if injury_types contains 'abdominal_pain' that also satisfies the rule
    """
    specials = _as_list(form.get("special_markers"))
    if SPECIAL_PREGNANT not in specials:
        return ANSWER_NO

    preg_symptoms = _as_list(form.get("preg_symptoms"))
    injuries = _as_list(form.get("injury_types"))

    has_symptom = (
        PREG_ABDOMINAL in preg_symptoms
        or PREG_BLEEDING in preg_symptoms
        or PREG_FETAL in preg_symptoms
        or INJURY_ABDOMINAL in injuries
        or INJURY_BLEEDING in injuries
    )
    return ANSWER_YES if has_symptom else ANSWER_NO


def _q8_altered_mental(form: Dict[str, Any]) -> str:
    """Q8: New altered mental status since injury?
    'confused/drowsy' OR 'unresponsive' -> Yes.
    Form assumes the altered state is post-injury (operator confirms in UI).
    """
    return ANSWER_YES if form.get("mental_status") in (MENTAL_CONFUSED, MENTAL_UNRESPONSIVE) else ANSWER_NO


def _q9_airway_burn(form: Dict[str, Any]) -> str:
    """Q9: Burns to face/neck OR soot OR hoarse voice?"""
    injuries = _as_list(form.get("injury_types"))
    if INJURY_BURN not in injuries:
        return ANSWER_NO
    burn_loc = _as_list(form.get("burn_location"))
    airway = _as_list(form.get("airway_signs"))
    if BURN_FACE in burn_loc or BURN_NECK in burn_loc:
        return ANSWER_YES
    if AIRWAY_SOOT in airway or AIRWAY_HOARSE in airway:
        return ANSWER_YES
    return ANSWER_NO


def _q10_painless_injury(form: Dict[str, Any]) -> str:
    """Q10: Significant injury but reports NO PAIN?"""
    pain = form.get("pain_response")
    if pain == PAIN_YES:
        return ANSWER_NO
    if pain == PAIN_UNKNOWN:
        return ANSWER_UNKNOWN
    if pain == PAIN_NO:
        injuries = _as_list(form.get("injury_types"))
        # Need at least one substantive injury for "significant injury but no pain"
        substantive = {INJURY_BLEEDING, INJURY_FRACTURE, INJURY_BURN,
                       INJURY_ENTRAPPED, INJURY_EXPLOSION, INJURY_HEAD_TRAUMA}
        if any(i in substantive for i in injuries):
            return ANSWER_YES
        return ANSWER_NO
    return ANSWER_UNKNOWN  # pain field not filled


def _q11_elderly_head(form: Dict[str, Any]) -> str:
    """Q11: Elderly (>65) + head impact + confusion/drowsiness?"""
    specials = _as_list(form.get("special_markers"))
    if SPECIAL_ELDERLY not in specials:
        # also allow age-based check
        age = form.get("age")
        if age is None:
            return ANSWER_NO
        try:
            if int(age) <= 65:
                return ANSWER_NO
        except (ValueError, TypeError):
            return ANSWER_NO
    injuries = _as_list(form.get("injury_types"))
    if INJURY_HEAD_TRAUMA not in injuries:
        return ANSWER_NO
    if form.get("mental_status") not in (MENTAL_CONFUSED, MENTAL_UNRESPONSIVE):
        return ANSWER_NO
    return ANSWER_YES


def _q12_blast_quiet(form: Dict[str, Any]) -> str:
    """Q12: Near explosion + currently feels fine?"""
    injuries = _as_list(form.get("injury_types"))
    if INJURY_EXPLOSION not in injuries:
        return ANSWER_NO
    # 'feels fine' = all primary vitals normal
    if form.get("breathing_status") != BREATHING_NORMAL:
        return ANSWER_NO
    if form.get("pulse_radial") != PULSE_STRONG:
        return ANSWER_NO
    if form.get("mental_status") != MENTAL_ALERT:
        return ANSWER_NO
    return ANSWER_YES


# =============================================================================
# Public API
# =============================================================================
_RULES = {
    "q1": _q1_breathing_absent,
    "q2": _q2_resp_rate,
    "q3": _q3_pulse,
    "q4": _q4_cant_follow_commands,
    "q5": _q5_crush,
    "q6": _q6_abdominal,
    "q7": _q7_pregnancy,
    "q8": _q8_altered_mental,
    "q9": _q9_airway_burn,
    "q10": _q10_painless_injury,
    "q11": _q11_elderly_head,
    "q12": _q12_blast_quiet,
}


def form_to_screening(form: Dict[str, Any]) -> Dict[str, str]:
    """Convert a Gradio form-data dict into the 12 screening answers.
    Pure deterministic Python — no AI."""
    return {q: _RULES[q](form) for q in SCREENING_QUESTIONS}


def form_to_patient_record(form: Dict[str, Any]) -> Dict[str, Any]:
    """Build the patient_record dict that triage_and_risk() expects."""
    return {
        "patient_id": form.get("patient_id", "P?"),
        "age_estimate": form.get("age"),
        "ambulatory": bool(form.get("walking", False)),
        "breathing": form.get("breathing_status"),
        "resp_rate_estimate": form.get("resp_rate"),
        "pulse_radial": form.get("pulse_radial"),
        "mental_status": form.get("mental_status"),
        "injury_types": list(_as_list(form.get("injury_types"))),
        "burn_location": list(_as_list(form.get("burn_location"))),
        "airway_signs": list(_as_list(form.get("airway_signs"))),
        "pain_response": form.get("pain_response"),
        "special_markers": list(_as_list(form.get("special_markers"))),
        "preg_symptoms": list(_as_list(form.get("preg_symptoms"))),
        "entrapment_duration_min": form.get("entrapment_min"),
        "notes": form.get("notes"),
        "gps": form.get("gps"),  # (lat, lon) tuple
    }


# =============================================================================
# Optional AI notes review
# =============================================================================
def review_notes_with_ai(
    form: Dict[str, Any],
    current_answers: Dict[str, str],
    ai_callable: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """Ask Qwen Cloud whether the free-text notes contain information
    that should *escalate* any current No -> Yes.

    Hard rule: AI can only escalate (No -> Yes), never de-escalate.

    Args:
        form: complete form dict (must contain 'notes')
        current_answers: 12-Q answers from form_to_screening
        ai_callable: function(prompt: str) -> str. If None, returns no
                     suggestions (offline / AI disabled).
    Returns:
        {
          "suggestions": [
              {"qkey": "q5", "from": "No", "to": "Yes",
               "reason": "notes mention 45min entrapment", ...},
          ],
          "ai_used": bool,
          "raw_response": str,
        }
    """
    notes = (form.get("notes") or "").strip()
    if not notes or ai_callable is None:
        return {"suggestions": [], "ai_used": False, "raw_response": ""}

    # Compose a tight prompt. The model is instructed to output JSON only.
    candidate_qs = [q for q, v in current_answers.items() if v == ANSWER_NO]
    prompt = _build_notes_review_prompt(form, current_answers, notes, candidate_qs)
    try:
        raw = ai_callable(prompt)
    except Exception as exc:
        return {"suggestions": [], "ai_used": False, "raw_response": f"ERR: {exc}"}

    suggestions = _parse_review_json(raw, current_answers)
    return {"suggestions": suggestions, "ai_used": True, "raw_response": raw}


def _build_notes_review_prompt(form, current, notes, candidate_qs):
    return (
        "You are a medical screening reviewer for disaster triage.\n"
        "Given a patient's form-derived screening answers and free-text notes,\n"
        "decide whether the notes contain information that should escalate any\n"
        "currently-No answer to Yes.\n\n"
        "RULES:\n"
        "1. You may ONLY escalate No -> Yes. Never the reverse.\n"
        "2. If notes do not clearly indicate escalation, return an empty list.\n"
        "3. Output JSON only, no prose.\n\n"
        "12 SCREENING QUESTIONS:\n"
        "Q1: Not breathing after airway reposition?\n"
        "Q2: Resp rate >30 or <10?\n"
        "Q3: Radial pulse absent?\n"
        "Q4: Cannot follow commands?\n"
        "Q5: Trapped/crushed >30 min?\n"
        "Q6: Abdominal pain after blunt trauma?\n"
        "Q7: Pregnant with abdominal pain/bleeding/decreased fetal movement?\n"
        "Q8: New altered mental status since injury?\n"
        "Q9: Burns to face/neck OR soot OR hoarse voice?\n"
        "Q10: Significant injury but NO PAIN?\n"
        "Q11: Elderly + head impact + confusion?\n"
        "Q12: Near explosion + currently feels fine?\n\n"
        f"CURRENT ANSWERS: {current}\n"
        f"NOTES: \"{notes}\"\n"
        f"QUESTIONS CURRENTLY ANSWERED 'No': {candidate_qs}\n\n"
        "OUTPUT JSON:\n"
        '{"changes": [{"qkey":"q5","reason":"notes mention dark urine+45min trapping"}]}\n'
    )


def _parse_review_json(raw: str, current_answers: Dict[str, str]) -> List[Dict[str, str]]:
    import json
    import re
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
                    parsed = json.loads(text[start:j + 1])
                    break
        else:
            return []
    except (ValueError, json.JSONDecodeError):
        return []

    out: List[Dict[str, str]] = []
    for chg in parsed.get("changes", []):
        qk = chg.get("qkey", "").lower()
        if qk not in SCREENING_QUESTIONS:
            continue
        if current_answers.get(qk) != ANSWER_NO:
            continue  # never override Yes/Unknown via AI
        out.append({
            "qkey": qk,
            "from": ANSWER_NO,
            "to": ANSWER_YES,
            "reason": str(chg.get("reason", ""))[:200],
        })
    return out


def normalize_suggestion_list(raw: Any) -> List[Dict[str, str]]:
    """Extract escalate-only suggestion dicts from Gradio JSON / vision / notes.

    Accepts:
      - list of dicts (may include info-only rows without qkey — skipped)
      - envelope ``{"suggestions": [...], "visual_findings": "..."}``
      - envelope ``{"changes": [...]}`` (notes-review schema)

    Each returned item has: qkey, from, to, reason (and optional rationale).
    Never raises on missing keys — info-only / malformed rows are dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, dict):
        if isinstance(raw.get("suggestions"), list):
            items = raw["suggestions"]
        elif isinstance(raw.get("changes"), list):
            items = raw["changes"]
        else:
            # Single suggestion-shaped dict
            items = [raw] if (raw.get("qkey") or raw.get("q")) else []
    elif isinstance(raw, list):
        items = raw
    else:
        return []

    out: List[Dict[str, str]] = []
    for s in items:
        if not isinstance(s, dict):
            continue
        # Skip status/info rows from vision / multilingual UI wrappers
        if "info" in s and not (s.get("qkey") or s.get("q")):
            continue
        if s.get("error") and not (s.get("qkey") or s.get("q")):
            continue
        qk = str(s.get("qkey") or s.get("q") or "").strip().lower()
        if not qk or qk not in SCREENING_QUESTIONS:
            continue
        to_val = str(s.get("to") or ANSWER_YES)
        if to_val != ANSWER_YES:
            continue
        reason = str(s.get("reason") or s.get("rationale") or "")[:200]
        out.append({
            "qkey": qk,
            "q": qk,
            "from": str(s.get("from") or ANSWER_NO),
            "to": ANSWER_YES,
            "reason": reason,
            "rationale": reason,
        })
    return out


def apply_suggestions(
    answers: Dict[str, str],
    accepted_qkeys: List[str],
    suggestions: Any,
) -> Dict[str, str]:
    """Return a new answers dict with the operator-accepted suggestions applied.

    Safe against vision UI rows like ``{"info": "..."}`` (no qkey) — those are
    ignored. ``accepted_qkeys`` are checkbox values (e.g. ``q9``).
    """
    new = dict(answers)
    accepted = {str(x).strip().lower() for x in (accepted_qkeys or []) if x}
    for s in normalize_suggestion_list(suggestions):
        qk = s["qkey"]
        if qk in accepted:
            new[qk] = s["to"]
    return new
