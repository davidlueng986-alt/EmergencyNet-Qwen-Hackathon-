"""Shadow inference at the base station.

Goal: independently re-derive the 12 screening answers from the *raw*
form fields shipped in the LoRa packet (breathing/pulse/mental/pain
plus injury bitmask) and re-run the deterministic triage engine. The
26B-A4B base AI then optionally re-reviews the patient with full
clinical reasoning.

Disagreements between the field decision and the shadow decision are
flagged for the commander (see ``comparator.py``).
"""
from __future__ import annotations

from typing import Dict, Any, Optional, Callable, Set

from .screening import form_to_screening
from .triage_core import triage_and_risk
from .constants import SCREENING_QUESTIONS


# Questions whose screening result depends on form fields that are NOT
# shipped over the LoRa wire (preg_symptoms, burn_location, airway_signs).
# For these, the shadow layer trusts the field's transmitted bits rather
# than re-deriving them from incomplete data — otherwise every pregnant
# patient with vaginal bleeding would be falsely flagged as disagreement
# because the wire-side form has an empty preg_symptoms list.
_NONDERIVABLE_FROM_WIRE: Set[str] = {"q7", "q9"}


def shadow_from_decoded_patient(
    decoded: Dict[str, Any],
    base_ai: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    """Re-screen + re-triage from the LoRa-decoded patient dict.

    Args:
        decoded: a record from ``bit_packer.decode_patient`` or
                 ``decode_packet``. Must contain raw form fields.
        base_ai: optional callable for AI-side notes review (called only
                 if the field's notes were also transmitted, which we
                 currently do NOT — placeholder for future telemetry).

    Returns:
        ``{"shadow_screening": {...}, "shadow_result": {...}}``
        Where ``shadow_screening`` is the 12-Q answer dict and
        ``shadow_result`` is the full triage_and_risk output.
    """
    form = _decoded_to_form(decoded)
    raw_shadow = form_to_screening(form)

    # For questions that cannot be fairly re-derived from the LoRa-carried
    # fields alone, fall back to the field's own transmitted answer. This
    # keeps the comparator honest — a disagreement on Q7/Q9 here would
    # have meant "base is missing data", not "field made a bad call".
    field_screening = decoded.get("screening") or {}
    shadow_screening: Dict[str, str] = {}
    for qk in SCREENING_QUESTIONS:
        if qk in _NONDERIVABLE_FROM_WIRE and qk in field_screening:
            shadow_screening[qk] = field_screening[qk]
        else:
            shadow_screening[qk] = raw_shadow.get(qk, "Unknown")

    patient_record = {
        "patient_id": f"P{decoded.get('patient_id', 0):03d}",
        "ambulatory": decoded.get("ambulatory", False),
        "age_estimate": decoded.get("age"),
        "special_markers": decoded.get("special_markers") or [],
        "gps": decoded.get("gps"),
    }
    shadow_result = triage_and_risk(shadow_screening, patient_record=patient_record)
    return {
        "shadow_screening": shadow_screening,
        "shadow_result": shadow_result,
        "base_ai_used": False,  # reserved for future expansion
        "nonderivable_from_wire": sorted(_NONDERIVABLE_FROM_WIRE),
    }


def _decoded_to_form(d: Dict[str, Any]) -> Dict[str, Any]:
    """Map LoRa-decoded fields into the form-shape that ``form_to_screening``
    expects. Anything missing in the LoRa transmission is left empty so
    the deterministic engine returns Unknown (and confidence drops)."""
    return {
        "breathing_status": d.get("breathing_status"),
        "pulse_radial": d.get("pulse_radial"),
        "mental_status": d.get("mental_status"),
        "pain_response": d.get("pain_response"),
        "injury_types": d.get("injury_types") or [],
        "burn_location": [],   # not transmitted; omits burn-location detail
        "airway_signs": [],    # not transmitted
        "preg_symptoms": [],   # field encodes Q7 directly via screening bits
        "special_markers": d.get("special_markers") or [],
        "age": d.get("age"),
        "entrapment_min": d.get("entrapment_min"),
        # ``resp_rate`` is not transmitted; engine relies on breathing_status
    }
