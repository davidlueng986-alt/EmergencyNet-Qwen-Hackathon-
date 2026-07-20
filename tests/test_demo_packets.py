"""Keep public demo fixtures decodable and bilingual copies in sync."""
from __future__ import annotations

import json
from pathlib import Path

from emergencynet.bit_packer import decode_packet
from emergencynet.gateway import BaseGateway
from emergencynet.screening import form_to_patient_record, form_to_screening
from emergencynet.triage_core import triage_and_risk


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    return json.loads((ROOT / "demo_data" / name).read_text(encoding="utf-8"))


def test_bilingual_demo_hex_is_identical_and_decodable():
    en = _load("demo_packets.en.json")
    zh = _load("demo_packets.zh-TW.json")

    for key in ("diversity", "anomaly_a", "anomaly_b", "malformed_b"):
        assert en["packets"][key]["hex"] == zh["packets"][key]["hex"]

    for key in ("diversity", "anomaly_a", "anomaly_b"):
        fixture = en["packets"][key]
        raw = bytes.fromhex(fixture["hex"])
        decoded = decode_packet(raw)
        assert len(raw) == fixture["binary_bytes"]
        assert len(fixture["hex"]) == fixture["hex_characters"]
        assert [p["patient_id"] for p in decoded["patients"]] == fixture["expected_patient_ids"]
        assert [p["triage_tag"] for p in decoded["patients"]] == fixture["expected_tags"]


def test_anomaly_sequence_and_malformed_fixture():
    data = _load("demo_packets.en.json")["packets"]
    gateway = BaseGateway()

    first = gateway.handle_raw(bytes.fromhex(data["anomaly_a"]["hex"]))
    assert {a["type"] for a in first["alerts"]} == {"BURN_CLUSTER", "CRUSH_CLUSTER"}

    second = gateway.handle_raw(bytes.fromhex(data["anomaly_b"]["hex"]))
    assert {a["type"] for a in second["alerts"]} == {
        "RESP_CLUSTER", "BURN_CLUSTER", "CRUSH_CLUSTER", "RED_SURGE",
    }

    malformed = BaseGateway().handle_raw(bytes.fromhex(data["malformed_b"]["hex"]))
    assert malformed["patients_received"] == 0
    assert malformed["alerts"][0]["type"] == "MALFORMED_PACKET"


def test_bilingual_scenario_forms_match_expected_deterministic_results():
    en = _load("demo_scenarios.en.json")
    zh = _load("demo_scenarios.zh-TW.json")
    for name in ("diversity", "anomaly_a", "anomaly_b"):
        en_rows = en["scenarios"][name]["patients"]
        zh_rows = zh["scenarios"][name]["patients"]
        assert en_rows == zh_rows
        for row in en_rows:
            form = {**en["defaults"], **row}
            screening = form_to_screening(form)
            result = triage_and_risk(screening, form_to_patient_record(form))
            assert result["triage_tag"] == row["expected_tag"]
            assert [q for q, value in screening.items() if value == "Yes"] == row["expected_yes"]
