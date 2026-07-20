"""Characterization: gateway + anomaly (no shadow)."""
from __future__ import annotations

from emergencynet.action_engine import DRAFTABLE_ANOMALY_TYPES, ActionEngine
from emergencynet.anomaly_detector import AnomalyDetector
from emergencynet.bit_packer import build_patient_record_for_packet, encode_packet
from emergencynet.gateway import BaseGateway
from emergencynet.meshtastic_broadcaster import MeshAlertBroadcaster
from emergencynet.screening import form_to_patient_record, form_to_screening
from emergencynet.strategy_ai import StrategyAI
from emergencynet.triage_core import triage_and_risk


def _red_packet():
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


def test_gateway_handle_raw_ingests_patient():
    gw = BaseGateway()
    upd = gw.handle_raw(_red_packet())
    assert upd["patients_received"] == 1
    assert "shadow" not in upd["per_patient"][0]


def test_malformed_packet_does_not_raise():
    gw = BaseGateway()
    pkt = bytearray(_red_packet())
    pkt[-1] ^= 0xFF
    upd = gw.handle_raw(bytes(pkt))
    assert upd["patients_received"] == 0
    assert upd["alerts"][0]["type"] == "MALFORMED_PACKET"


def test_red_surge_anomaly():
    ad = AnomalyDetector()
    for _ in range(5):
        ad.add({"triage_tag": "RED", "breathing_status": "normal", "injury_types": []})
    types = [a["type"] for a in ad.evaluate()]
    assert "RED_SURGE" in types


def test_strategy_snapshot_risks_from_hidden_risk_qs():
    gw = BaseGateway()
    gw.handle_raw(_red_packet())
    snap = StrategyAI.build_situation_snapshot(gw)
    assert snap["tag_counts"]["RED"] == 1
    # q9 burn face should have hidden risk on wire
    assert snap["hidden_risks_fired"]  # non-empty after KI-05 fix


def test_broadcast_draft_not_auto_send_and_no_severity_policy_skip():
    sent = []
    b = MeshAlertBroadcaster(transport_send_text=lambda t: sent.append(t) or True)

    def fake_ai(prompt, tools, system_prompt=None):
        return (
            '{"message_body":"Deploy USAR","severity":"critical",'
            '"anomaly_type":"RED_SURGE"}'
        )

    ae = ActionEngine(base_ai_call=fake_ai, broadcaster=b)
    out = ae.process_alerts(
        [{"type": "RED_SURGE", "severity": "critical", "message": "5 RED", "matches": 5, "n": 5}]
    )
    assert out[0]["outcome"] == "draft"
    assert out[0]["send_result"]["sent"] is False
    assert not sent

    # RESP with "wrong" severity vs old policy still drafts (not policy-skip)
    out2 = ae.process_alerts(
        [{"type": "RESP_CLUSTER", "severity": "critical", "message": "x"}]
    )
    assert out2[0]["outcome"] == "draft"
    assert "RESP_CLUSTER" in DRAFTABLE_ANOMALY_TYPES
