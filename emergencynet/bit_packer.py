"""
Bit-packed LoRa packet codec — extended format.

v1 layout
---------
HEADER (10 bytes):
    0      version (uint8)                          = PACKET_VERSION
    1-2    team_id (uint16 LE)
    3-6    unix_timestamp (uint32 LE)
    7      patient_count (uint8)
    8      zone_code (uint8)                        0=none, 1=CHEM, ...
    9      header XOR checksum                      XOR of bytes 0..8

PER-PATIENT (18 bytes):
    0      patient_id (uint8)
    1-3    latitude (int24 LE, fixed point: (deg+90) * 93206)
    4-6    longitude (int24 LE, fixed point: (deg+180) * 46603)
    7      bits 0-1: triage tag  (0=RED, 1=YELLOW, 2=GREEN, 3=BLACK)
           bits 2-7: confidence (6 bits: 0..63 -> 0.00..1.00)
    8-10   12 x 2-bit screening answers (24 bits, MSB=q1)
              00=No, 01=Yes, 10=Unknown, 11=reserved
    11     bits 0-6: risk flags bitmask (Q5..Q11; q5->bit0)
           bit  7:   ambulatory flag (1 = can walk)
           Q12 is preserved in the 24-bit screening field and reconstructed
           during decode; there is no eighth dedicated risk bit.
    12     age_estimate (uint8; 255 = unknown)
    13     bits 0-3: injury_type bitmask compressed:
              bit0 bleeding, bit1 fracture, bit2 burn, bit3 entrapped
           bits 4-7: secondary injury bitmask:
              bit4 explosion, bit5 abdominal, bit6 head_trauma, bit7 reserved
    14     bits 0-2: special marker bitmask (preg/child/elderly)
           bits 3-4: breathing status (0=normal,1=rapid_weak,2=absent,3=unk)
           bits 5-6: pulse_radial    (0=strong,1=weak,2=absent,3=unk)
           bit  7:   mental_status hi-bit
    15     bits 0-1: mental_status (combined with byte14 bit7 = 3 bits):
              0=alert,1=confused_drowsy,2=unresponsive,3=unknown
           bits 2-3: pain_response (0=pain,1=no_pain,2=cannot_judge,3=unk)
           bits 4-7: review flag (0 none, 1 ai_suggested, 2 ai_accepted, 3 low_conf)
    16     entrapment_minutes (uint8; 255 = unknown)
    17     XOR checksum of bytes 0..16
"""

import struct
import time
from typing import Dict, Any, List, Optional, Tuple

from .constants import (
    PACKET_VERSION, PATIENT_BYTES, HEADER_BYTES, MAX_PATIENTS_PER_PACKET,
    TAG_RED, TAG_YELLOW, TAG_GREEN, TAG_BLACK,
    ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN,
    BREATHING_NORMAL, BREATHING_RAPID_WEAK, BREATHING_ABSENT,
    PULSE_STRONG, PULSE_WEAK, PULSE_ABSENT,
    MENTAL_ALERT, MENTAL_CONFUSED, MENTAL_UNRESPONSIVE,
    PAIN_YES, PAIN_NO, PAIN_UNKNOWN,
    SPECIAL_PREGNANT, SPECIAL_CHILD, SPECIAL_ELDERLY,
    INJURY_BLEEDING, INJURY_FRACTURE, INJURY_BURN, INJURY_ENTRAPPED,
    INJURY_EXPLOSION, INJURY_ABDOMINAL, INJURY_HEAD_TRAUMA,
)

# -----------------------------------------------------------------------------
# Enumeration tables
# -----------------------------------------------------------------------------
_TAG_ENC = {TAG_RED: 0, TAG_YELLOW: 1, TAG_GREEN: 2, TAG_BLACK: 3}
_TAG_DEC = {v: k for k, v in _TAG_ENC.items()}

_ANS_ENC = {ANSWER_NO: 0b00, ANSWER_YES: 0b01, ANSWER_UNKNOWN: 0b10}
_ANS_DEC = {0b00: ANSWER_NO, 0b01: ANSWER_YES, 0b10: ANSWER_UNKNOWN, 0b11: ANSWER_UNKNOWN}

_BREATH_ENC = {BREATHING_NORMAL: 0, BREATHING_RAPID_WEAK: 1, BREATHING_ABSENT: 2, None: 3}
_BREATH_DEC = {0: BREATHING_NORMAL, 1: BREATHING_RAPID_WEAK, 2: BREATHING_ABSENT, 3: None}

_PULSE_ENC = {PULSE_STRONG: 0, PULSE_WEAK: 1, PULSE_ABSENT: 2, None: 3}
_PULSE_DEC = {0: PULSE_STRONG, 1: PULSE_WEAK, 2: PULSE_ABSENT, 3: None}

_MENTAL_ENC = {MENTAL_ALERT: 0, MENTAL_CONFUSED: 1, MENTAL_UNRESPONSIVE: 2, None: 3}
_MENTAL_DEC = {0: MENTAL_ALERT, 1: MENTAL_CONFUSED, 2: MENTAL_UNRESPONSIVE, 3: None}

_PAIN_ENC = {PAIN_YES: 0, PAIN_NO: 1, PAIN_UNKNOWN: 2, None: 3}
_PAIN_DEC = {0: PAIN_YES, 1: PAIN_NO, 2: PAIN_UNKNOWN, 3: None}

_INJ_BIT = {
    INJURY_BLEEDING: 0,
    INJURY_FRACTURE: 1,
    INJURY_BURN: 2,
    INJURY_ENTRAPPED: 3,
    INJURY_EXPLOSION: 4,
    INJURY_ABDOMINAL: 5,
    INJURY_HEAD_TRAUMA: 6,
}
_INJ_LIST = [k for k, _ in sorted(_INJ_BIT.items(), key=lambda kv: kv[1])]

_SPEC_BIT = {SPECIAL_PREGNANT: 0, SPECIAL_CHILD: 1, SPECIAL_ELDERLY: 2}
_SPEC_LIST = [k for k, _ in sorted(_SPEC_BIT.items(), key=lambda kv: kv[1])]


# -----------------------------------------------------------------------------
# GPS fixed-point
# -----------------------------------------------------------------------------
# 24-bit range = 16_777_216 values
_LAT_SCALE = 16_777_215 / 180.0   # deg range = 180 (-90..+90)
_LON_SCALE = 16_777_215 / 360.0   # deg range = 360 (-180..+180)


def _encode_lat(lat: Optional[float]) -> int:
    if lat is None:
        return 0xFFFFFF  # sentinel
    lat = max(-90.0, min(90.0, float(lat)))
    return int(round((lat + 90.0) * _LAT_SCALE)) & 0xFFFFFF


def _decode_lat(raw: int) -> Optional[float]:
    if raw == 0xFFFFFF:
        return None
    return (raw / _LAT_SCALE) - 90.0


def _encode_lon(lon: Optional[float]) -> int:
    if lon is None:
        return 0xFFFFFF
    lon = max(-180.0, min(180.0, float(lon)))
    return int(round((lon + 180.0) * _LON_SCALE)) & 0xFFFFFF


def _decode_lon(raw: int) -> Optional[float]:
    if raw == 0xFFFFFF:
        return None
    return (raw / _LON_SCALE) - 180.0


def _xor_bytes(buf: bytes) -> int:
    x = 0
    for b in buf:
        x ^= b
    return x & 0xFF


# -----------------------------------------------------------------------------
# Single patient encode/decode
# -----------------------------------------------------------------------------
def encode_patient(record: Dict[str, Any]) -> bytes:
    """Encode one patient dict into 18 bytes.

    Expected fields (all optional except patient_id):
        patient_id        int 0..255
        gps               (lat, lon) or None
        triage_tag        "RED" / "YELLOW" / "GREEN" / "BLACK"
        confidence        float 0..1
        screening         dict q1..q12 -> Yes/No/Unknown
        hidden_risk_qs    list of qkeys triggered (e.g. ["q5","q9"])
        ambulatory        bool
        age               int or None
        injury_types      list of injury keys
        special_markers   list of special keys
        breathing_status  str
        pulse_radial      str
        mental_status     str
        pain_response     str
        entrapment_min    int or None
        review_flag       0..3
    """
    pid = int(record.get("patient_id", 0)) & 0xFF
    buf = bytearray(PATIENT_BYTES)
    buf[0] = pid

    # GPS
    gps = record.get("gps") or (None, None)
    lat_raw = _encode_lat(gps[0])
    lon_raw = _encode_lon(gps[1])
    buf[1] = lat_raw & 0xFF
    buf[2] = (lat_raw >> 8) & 0xFF
    buf[3] = (lat_raw >> 16) & 0xFF
    buf[4] = lon_raw & 0xFF
    buf[5] = (lon_raw >> 8) & 0xFF
    buf[6] = (lon_raw >> 16) & 0xFF

    # byte 7: tag (2 bits) + confidence (6 bits)
    tag_enc = _TAG_ENC.get(record.get("triage_tag"), 0)
    conf = record.get("confidence", 1.0)
    try:
        conf_6 = int(round(max(0.0, min(1.0, float(conf))) * 63))
    except (ValueError, TypeError):
        conf_6 = 63
    buf[7] = (tag_enc & 0b11) | ((conf_6 & 0b111111) << 2)

    # bytes 8-10: 12 x 2-bit screening (q1 in highest bits, q12 in lowest)
    screening = record.get("screening") or {}
    bits24 = 0
    for i in range(12):
        q = f"q{i + 1}"
        ans = screening.get(q, ANSWER_UNKNOWN)
        code = _ANS_ENC.get(ans, _ANS_ENC[ANSWER_UNKNOWN])
        shift = (11 - i) * 2  # q1 -> shift 22
        bits24 |= (code & 0b11) << shift
    buf[8] = bits24 & 0xFF
    buf[9] = (bits24 >> 8) & 0xFF
    buf[10] = (bits24 >> 16) & 0xFF

    # byte 11: risk flags (q5..q11 -> bits 0..6) + ambulatory (bit 7)
    risk_mask = 0
    risk_qs = set(record.get("hidden_risk_qs") or [])
    # We only transmit 7 risk bits; map q5..q11 and add q12 if space.
    # Layout: bit0=q5, bit1=q6, bit2=q7, bit3=q8, bit4=q9, bit5=q10, bit6=q11.
    # Q12 shares with q11 via screening bits anyway.
    for bit, qkey in enumerate(["q5", "q6", "q7", "q8", "q9", "q10", "q11"]):
        if qkey in risk_qs:
            risk_mask |= (1 << bit)
    if record.get("ambulatory"):
        risk_mask |= (1 << 7)
    buf[11] = risk_mask & 0xFF

    # byte 12: age
    age = record.get("age")
    try:
        age_i = int(age) if age is not None else 255
        age_i = max(0, min(255, age_i))
    except (ValueError, TypeError):
        age_i = 255
    buf[12] = age_i

    # byte 13: injury mask
    inj_mask = 0
    injuries = record.get("injury_types") or []
    for inj in injuries:
        if inj in _INJ_BIT:
            inj_mask |= (1 << _INJ_BIT[inj])
    buf[13] = inj_mask & 0xFF

    # byte 14: specials (0-2) + breathing (3-4) + pulse (5-6) + mental hi (7)
    spec_mask = 0
    for sp in record.get("special_markers") or []:
        if sp in _SPEC_BIT:
            spec_mask |= (1 << _SPEC_BIT[sp])
    breath = _BREATH_ENC.get(record.get("breathing_status"), 3)
    pulse = _PULSE_ENC.get(record.get("pulse_radial"), 3)
    mental = _MENTAL_ENC.get(record.get("mental_status"), 3)
    buf[14] = (
        (spec_mask & 0b111)
        | ((breath & 0b11) << 3)
        | ((pulse & 0b11) << 5)
        | (((mental >> 1) & 0b1) << 7)
    )

    # byte 15: mental low (0-1) + pain (2-3) + review (4-7)
    pain = _PAIN_ENC.get(record.get("pain_response"), 3)
    review = int(record.get("review_flag", 0)) & 0b1111
    buf[15] = ((mental & 0b01) | ((pain & 0b11) << 2) | ((review & 0b1111) << 4))
    # ^^ mental low-bit stored in bit 0; we use 0..1 for mental low-bit.
    # Because mental is 2-bit (0..3), bit 0 captures low bit, bit 7 of byte14
    # captures high bit.

    # byte 16: entrapment minutes
    em = record.get("entrapment_min")
    try:
        em_i = int(em) if em is not None else 255
        em_i = max(0, min(255, em_i))
    except (ValueError, TypeError):
        em_i = 255
    buf[16] = em_i

    # byte 17: XOR checksum of bytes 0..16
    buf[17] = _xor_bytes(bytes(buf[:17]))

    return bytes(buf)


def decode_patient(buf: bytes) -> Dict[str, Any]:
    """Inverse of encode_patient. Raises ValueError on checksum failure."""
    if len(buf) != PATIENT_BYTES:
        raise ValueError(f"patient record must be {PATIENT_BYTES} bytes, got {len(buf)}")
    if _xor_bytes(buf[:17]) != buf[17]:
        raise ValueError("patient checksum mismatch")

    pid = buf[0]
    lat_raw = buf[1] | (buf[2] << 8) | (buf[3] << 16)
    lon_raw = buf[4] | (buf[5] << 8) | (buf[6] << 16)
    lat = _decode_lat(lat_raw)
    lon = _decode_lon(lon_raw)

    tag_enc = buf[7] & 0b11
    conf_6 = (buf[7] >> 2) & 0b111111
    tag = _TAG_DEC.get(tag_enc)
    confidence = round(conf_6 / 63.0, 2)

    bits24 = buf[8] | (buf[9] << 8) | (buf[10] << 16)
    screening = {}
    for i in range(12):
        q = f"q{i + 1}"
        shift = (11 - i) * 2
        code = (bits24 >> shift) & 0b11
        screening[q] = _ANS_DEC.get(code, ANSWER_UNKNOWN)

    risk_mask = buf[11]
    ambulatory = bool(risk_mask & (1 << 7))
    risk_qs = [qk for bit, qk in enumerate(
        ["q5", "q6", "q7", "q8", "q9", "q10", "q11"]) if risk_mask & (1 << bit)]
    # Q12 has no dedicated risk-bit slot in the 7-bit risk_mask; the
    # field signals it via the screening bits instead. Reconstitute it
    # here so downstream consumers receive the complete risk list.
    if screening.get("q12") == ANSWER_YES:
        risk_qs.append("q12")

    age = buf[12] if buf[12] != 255 else None

    inj_mask = buf[13]
    injuries = [inj for inj, bit in _INJ_BIT.items() if inj_mask & (1 << bit)]

    b14 = buf[14]
    spec_mask = b14 & 0b111
    specials = [sp for sp, bit in _SPEC_BIT.items() if spec_mask & (1 << bit)]
    breath_code = (b14 >> 3) & 0b11
    pulse_code = (b14 >> 5) & 0b11
    mental_hi = (b14 >> 7) & 0b1

    b15 = buf[15]
    mental_lo = b15 & 0b01
    mental_code = (mental_hi << 1) | mental_lo
    pain_code = (b15 >> 2) & 0b11
    review_flag = (b15 >> 4) & 0b1111

    em = buf[16] if buf[16] != 255 else None

    return {
        "patient_id": pid,
        "gps": (lat, lon) if (lat is not None and lon is not None) else None,
        "triage_tag": tag,
        "confidence": confidence,
        "screening": screening,
        "hidden_risk_qs": risk_qs,
        "ambulatory": ambulatory,
        "age": age,
        "injury_types": injuries,
        "special_markers": specials,
        "breathing_status": _BREATH_DEC.get(breath_code),
        "pulse_radial": _PULSE_DEC.get(pulse_code),
        "mental_status": _MENTAL_DEC.get(mental_code),
        "pain_response": _PAIN_DEC.get(pain_code),
        "review_flag": review_flag,
        "entrapment_min": em,
    }


# -----------------------------------------------------------------------------
# Full-packet encode/decode
# -----------------------------------------------------------------------------
def encode_packet(
    team_id: int,
    patients: List[Dict[str, Any]],
    zone_code: int = 0,
    timestamp: Optional[int] = None,
) -> bytes:
    """Build a full LoRa packet from up to MAX_PATIENTS_PER_PACKET patients.

    Raises ValueError if patient count exceeds the LoRa MTU budget.
    """
    if len(patients) > MAX_PATIENTS_PER_PACKET:
        raise ValueError(
            f"too many patients: {len(patients)} > {MAX_PATIENTS_PER_PACKET}"
        )
    if timestamp is None:
        timestamp = int(time.time())

    header = bytearray(HEADER_BYTES)
    header[0] = PACKET_VERSION
    header[1] = team_id & 0xFF
    header[2] = (team_id >> 8) & 0xFF
    header[3] = timestamp & 0xFF
    header[4] = (timestamp >> 8) & 0xFF
    header[5] = (timestamp >> 16) & 0xFF
    header[6] = (timestamp >> 24) & 0xFF
    header[7] = len(patients) & 0xFF
    header[8] = zone_code & 0xFF
    header[9] = _xor_bytes(bytes(header[:9]))

    body = bytearray()
    for p in patients:
        body.extend(encode_patient(p))

    return bytes(header) + bytes(body)


def decode_packet(buf: bytes) -> Dict[str, Any]:
    """Decode a full LoRa packet. Raises ValueError on any checksum failure."""
    if len(buf) < HEADER_BYTES:
        raise ValueError(f"packet shorter than header: {len(buf)} bytes")

    header = buf[:HEADER_BYTES]
    if _xor_bytes(header[:9]) != header[9]:
        raise ValueError("header checksum mismatch")

    version = header[0]
    if version != PACKET_VERSION:
        raise ValueError(f"unknown packet version {version}")

    team_id = header[1] | (header[2] << 8)
    timestamp = (header[3] | (header[4] << 8)
                 | (header[5] << 16) | (header[6] << 24))
    patient_count = header[7]
    zone_code = header[8]

    expected_len = HEADER_BYTES + patient_count * PATIENT_BYTES
    if len(buf) != expected_len:
        raise ValueError(
            f"packet length {len(buf)} != expected {expected_len}"
        )

    patients = []
    offset = HEADER_BYTES
    for i in range(patient_count):
        rec_buf = buf[offset:offset + PATIENT_BYTES]
        patients.append(decode_patient(rec_buf))
        offset += PATIENT_BYTES

    return {
        "version": version,
        "team_id": team_id,
        "timestamp": timestamp,
        "zone_code": zone_code,
        "patients": patients,
    }


# -----------------------------------------------------------------------------
# Convenience: build patient record from full pipeline output
# -----------------------------------------------------------------------------
def build_patient_record_for_packet(
    pipeline_result: Dict[str, Any],
    patient_record: Dict[str, Any],
    review_flag: int = 0,
) -> Dict[str, Any]:
    """Convert one triage_and_risk() result + form patient_record into the
    flat dict that encode_patient expects."""
    screening = pipeline_result.get("screening_answers", {})
    risks = pipeline_result.get("hidden_risks", [])
    gps = patient_record.get("gps")
    # normalise patient_id to int (we can only fit 0..255)
    raw_pid = patient_record.get("patient_id", "P0")
    if isinstance(raw_pid, str) and raw_pid.upper().startswith("P"):
        try:
            pid_int = int(raw_pid[1:])
        except ValueError:
            pid_int = 0
    else:
        try:
            pid_int = int(raw_pid)
        except (ValueError, TypeError):
            pid_int = 0

    return {
        "patient_id": pid_int,
        "gps": gps,
        "triage_tag": pipeline_result.get("triage_tag"),
        "confidence": pipeline_result.get("confidence", 1.0),
        "screening": screening,
        "hidden_risk_qs": [r["qkey"] for r in risks if "qkey" in r],
        "ambulatory": patient_record.get("ambulatory", False),
        "age": patient_record.get("age_estimate") or patient_record.get("age"),
        "injury_types": patient_record.get("injury_types") or [],
        "special_markers": patient_record.get("special_markers") or [],
        "breathing_status": patient_record.get("breathing"),
        "pulse_radial": patient_record.get("pulse_radial"),
        "mental_status": patient_record.get("mental_status"),
        "pain_response": patient_record.get("pain_response"),
        "entrapment_min": patient_record.get("entrapment_duration_min"),
        "review_flag": review_flag,
    }
