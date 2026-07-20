"""
Hidden risk engine — 8 prototype risk rules that can override START decisions.

The prototype records source labels from the design research:
- ATLS 11th Ed (Advanced Trauma Life Support)
- PHTLS 10th Ed (Pre-Hospital Trauma Life Support)
- 2024 AHA/Red Cross First Aid Guidelines
- WHO EMT Standards 2021
- CDC Blast Injury Guidelines
- ALSO (Advanced Life Support in Obstetrics)
- Geriatric Trauma Guidelines

A risk fires when its corresponding screening question is answered "Yes".
Risks at level RED_NOW or RED_WITHIN_HOUR force the triage tag to RED. Source
labels, thresholds, timelines, and responder-action wording still require
review and localization by qualified medical/incident-command leadership
before any real exercise or deployment.
"""

from typing import Dict, List, Optional
from .constants import (
    RISK_RED_NOW, RISK_RED_WITHIN_HOUR, RISK_MONITORING,
    ANSWER_YES,
)

HIDDEN_RISK_RULES: Dict[str, Dict[str, str]] = {
    "q5": {
        "risk": "CRUSH RELEASE SYNDROME",
        "detail": (
            "Rhabdomyolysis risk. Myoglobin release on decompression -> "
            "renal failure + fatal hyperkalemia."
        ),
        "timeline": (
            "Cardiac arrhythmia: 0-60 min post-extraction. "
            "Renal failure: 2-6 hours."
        ),
        "responder_action": (
            "IV access BEFORE release if possible. Monitor ECG for peaked T-waves. "
            "Dark/cola-colored urine = immediate transport for dialysis."
        ),
        "source": "PHTLS 10th Ed; WHO EMT Standards 2021",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
    "q6": {
        "risk": "OCCULT INTERNAL HEMORRHAGE",
        "detail": (
            "Splenic / hepatic laceration may present with tenderness only. "
            "Children compensate until sudden cardiovascular collapse."
        ),
        "timeline": "Decompensation can occur 30-120 min post-injury without warning.",
        "responder_action": (
            "Serial abdominal exam every 10 min. Rising HR with stable BP = early shock. "
            "Immediate transport on any change."
        ),
        "source": "ATLS 11th Ed; JumpSTART Pediatric Triage",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
    "q7": {
        "risk": "PLACENTAL ABRUPTION",
        "detail": (
            "Trauma in late pregnancy -> placental separation. "
            "Maternal vitals stay stable until >30% blood volume lost."
        ),
        "timeline": "Fetal distress precedes maternal shock by 30-60 min.",
        "responder_action": (
            "LEFT LATERAL POSITION now. Monitor vaginal bleeding + uterine rigidity. "
            "Needs obstetric surgical capability at receiving hospital."
        ),
        "source": "ALSO; WHO EMT Standards",
        "risk_level": RISK_RED_NOW,
    },
    "q8": {
        "risk": "PROGRESSIVE NEUROLOGICAL DETERIORATION",
        "detail": (
            "New-onset altered mental status post-trauma suggests intracranial pathology. "
            "May have lucid interval before crash."
        ),
        "timeline": (
            "Epidural hematoma: minutes to hours. "
            "Subdural hematoma: hours. Deterioration can be sudden."
        ),
        "responder_action": (
            "GCS + pupil check every 10 min. Any decline = highest transport priority. "
            "Avoid hypoxia and hypotension."
        ),
        "source": "ATLS 11th Ed",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
    "q9": {
        "risk": "DELAYED AIRWAY OBSTRUCTION",
        "detail": (
            "Thermal / inhalation injury -> progressive airway edema. "
            "Patient may speak normally now but airway can close within 30-90 min."
        ),
        "timeline": (
            "Edema peak: 30-90 min. Once airway occludes, "
            "field intubation is nearly impossible."
        ),
        "responder_action": (
            "Monitor voice every 5 min. Increasing hoarseness = transport NOW "
            "for early intubation while airway is still patent."
        ),
        "source": "2024 AHA/Red Cross Guidelines; ATLS 11th Ed",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
    "q10": {
        "risk": "NEUROGENIC SHOCK / SPINAL CORD INJURY",
        "detail": (
            "Painless significant injury = spinal cord compromise or severe shock. "
            "Patient may look stable initially but is decompensating."
        ),
        "timeline": "Neurogenic shock: progressive bradycardia + hypotension over 30-60 min.",
        "responder_action": (
            "Full spinal precautions. Monitor HR — bradycardia in trauma context "
            "= neurogenic shock until proven otherwise. Keep warm to prevent the lethal triad."
        ),
        "source": "ATLS 11th Ed; PHTLS 10th Ed",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
    "q11": {
        "risk": "ELDERLY SUBDURAL HEMATOMA",
        "detail": (
            "Brain atrophy + frequent anticoagulant use = high subdural risk "
            "from minor head impact. Lucid interval is common."
        ),
        "timeline": (
            "Acute subdural: deterioration 1-4 hours. "
            "Presents as increasing drowsiness -> unconsciousness."
        ),
        "responder_action": (
            "Neuro checks every 10 min (GCS, pupils). Any decline = immediate transport. "
            "Always ask about blood thinners (warfarin, DOACs, antiplatelets)."
        ),
        "source": "ATLS 11th Ed; Geriatric Trauma Guidelines",
        "risk_level": RISK_MONITORING,
    },
    "q12": {
        "risk": "PRIMARY BLAST LUNG INJURY",
        "detail": (
            "Blast overpressure damages alveoli. Patient appears normal for hours "
            "before acute respiratory failure (delayed pulmonary edema, ARDS)."
        ),
        "timeline": "Symptom onset: 1-4 hours. Can progress to ARDS within 6-12 hours.",
        "responder_action": (
            "Monitor SpO2 + resp rate every 15 min even if currently normal. "
            "Any new dyspnea or hemoptysis = immediate transport."
        ),
        "source": "CDC Blast Injury Guidelines; ATLS 11th Ed",
        "risk_level": RISK_RED_WITHIN_HOUR,
    },
}


def evaluate_hidden_risks(screening_answers: Dict[str, str]) -> List[Dict[str, str]]:
    """Return list of triggered risk dicts (in screening-question order)."""
    triggered = []
    for qkey in sorted(HIDDEN_RISK_RULES.keys(), key=lambda k: int(k[1:])):
        if screening_answers.get(qkey) == ANSWER_YES:
            info = HIDDEN_RISK_RULES[qkey]
            triggered.append({
                "qkey": qkey,
                "risk": info["risk"],
                "detail": info["detail"],
                "timeline": info["timeline"],
                "action": info["responder_action"],
                "source": info["source"],
                "risk_level": info["risk_level"],
            })
    return triggered


def risks_force_red(triggered_risks: List[Dict[str, str]]) -> bool:
    """Return True if any triggered risk should escalate to RED."""
    return any(r["risk_level"] in (RISK_RED_NOW, RISK_RED_WITHIN_HOUR)
               for r in triggered_risks)
