"""team_id / zone_code from form, not hardcoded 1/0 only."""
from __future__ import annotations

from emergencynet.bit_packer import (
    build_patient_record_for_packet,
    decode_packet,
    encode_packet,
)
from emergencynet.screening import form_to_patient_record, form_to_screening
from emergencynet.triage_core import triage_and_risk


def test_encode_uses_team_and_zone():
    form = {
        "patient_id": "P9",
        "team_id": 42,
        "zone_code": 2,
        "walking": True,
        "age": 30,
        "breathing_status": "normal",
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": ["fracture"],
        "special_markers": [],
    }
    scr = form_to_screening(form)
    rec = form_to_patient_record(form)
    res = triage_and_risk(scr, rec)
    flat = build_patient_record_for_packet(res, rec)
    pkt = encode_packet(
        team_id=int(form["team_id"]),
        patients=[flat],
        zone_code=int(form["zone_code"]),
        timestamp=1,
    )
    dec = decode_packet(pkt)
    assert dec["team_id"] == 42
    assert dec["zone_code"] == 2
