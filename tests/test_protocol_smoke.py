"""Characterization: bit_packer sizes and roundtrip.

Locks constants.py PATIENT_BYTES / bit_packer encode_packet.
"""
from __future__ import annotations

import pytest

from emergencynet.bit_packer import (
    build_patient_record_for_packet,
    decode_packet,
    encode_packet,
    encode_patient,
)
from emergencynet.constants import HEADER_BYTES, MAX_PATIENTS_PER_PACKET, PATIENT_BYTES
from emergencynet.screening import form_to_patient_record, form_to_screening
from emergencynet.triage_core import triage_and_risk


def _flat_patient():
    form = {
        "patient_id": "P9",
        "walking": True,
        "age": 40,
        "breathing_status": "normal",
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": ["burn"],
        "burn_location": ["face"],
        "airway_signs": ["soot"],
        "special_markers": [],
        "gps": (22.3, 114.2),
    }
    scr = form_to_screening(form)
    rec = form_to_patient_record(form)
    res = triage_and_risk(scr, rec)
    flat = build_patient_record_for_packet(res, rec)
    flat["gps"] = (22.3, 114.2)
    return flat


def test_patient_record_is_18_bytes():
    # constants.py:145; bit_packer.encode_patient
    one = encode_patient(_flat_patient())
    assert len(one) == PATIENT_BYTES == 18


def test_packet_header_plus_one_patient():
    # bit_packer.encode_packet: header 10 + 18
    pkt = encode_packet(team_id=7, patients=[_flat_patient()], zone_code=1, timestamp=1710000000)
    assert len(pkt) == HEADER_BYTES + PATIENT_BYTES
    dec = decode_packet(pkt)
    assert dec["team_id"] == 7
    assert dec["zone_code"] == 1
    assert dec["patients"][0]["triage_tag"] == "RED"
    assert dec["patients"][0]["screening"]["q9"] == "Yes"


def test_max_twelve_patients_226_bytes():
    # constants.py:149 — 10 + 12*18 = 226
    flat = _flat_patient()
    recs = []
    for i in range(MAX_PATIENTS_PER_PACKET):
        r = dict(flat)
        r["patient_id"] = i
        recs.append(r)
    pkt = encode_packet(1, recs, timestamp=1)
    assert len(pkt) == 226


def test_thirteen_patients_raises():
    flat = _flat_patient()
    recs = [dict(flat, patient_id=i) for i in range(13)]
    with pytest.raises(ValueError, match="too many patients"):
        encode_packet(1, recs)


def test_bad_checksum_raises_on_decode():
    pkt = bytearray(encode_packet(1, [_flat_patient()], timestamp=1))
    pkt[-1] ^= 0xFF
    with pytest.raises(ValueError, match="checksum"):
        decode_packet(bytes(pkt))


def test_trailing_bytes_are_rejected():
    """A pasted concatenation must not silently ignore an extra payload."""
    pkt = encode_packet(1, [_flat_patient()], timestamp=1)
    with pytest.raises(ValueError, match="packet length"):
        decode_packet(pkt + b"\x00")
