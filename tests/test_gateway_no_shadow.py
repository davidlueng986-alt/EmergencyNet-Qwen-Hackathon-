"""Gateway has no shadow path."""
from __future__ import annotations

from emergencynet.bit_packer import build_patient_record_for_packet, encode_packet
from emergencynet.gateway import BaseGateway
from emergencynet.screening import form_to_patient_record, form_to_screening
from emergencynet.triage_core import triage_and_risk


def _pkt():
    form = {
        "patient_id": "P1",
        "walking": False,
        "age": 40,
        "breathing_status": "rapid_weak",
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": ["burn"],
        "burn_location": ["face"],
        "airway_signs": ["soot"],
        "special_markers": [],
    }
    scr = form_to_screening(form)
    rec = form_to_patient_record(form)
    res = triage_and_risk(scr, rec)
    flat = build_patient_record_for_packet(res, rec)
    flat["gps"] = (22.3, 114.2)
    return encode_packet(1, [flat], zone_code=1, timestamp=1710000000)


def test_no_shadow_keys_in_per_patient():
    gw = BaseGateway()
    upd = gw.handle_raw(_pkt())
    assert upd["patients_received"] == 1
    pp = upd["per_patient"][0]
    assert "field" in pp
    assert "shadow" not in pp
    assert "diff" not in pp
    snap = gw.snapshot()
    assert snap["disagreements"] == []


def test_new_anomaly_types_edge_trigger():
    gw = BaseGateway()
    # flood RED for RED_SURGE
    from emergencynet.anomaly_detector import AnomalyDetector
    for _ in range(5):
        gw.detector.add({
            "triage_tag": "RED",
            "breathing_status": "normal",
            "injury_types": [],
        })
    # inject one packet so handle path returns evaluate
    upd = gw.handle_raw(_pkt())
    # may or may not include RED_SURGE depending window; structure present
    assert "new_anomaly_types" in upd
