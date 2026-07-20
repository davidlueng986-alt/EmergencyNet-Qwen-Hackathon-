"""
EmergencyNet shared constants — used by both field and base stations.
Keep this file free of heavy imports so it can be loaded in any context.
"""

# =============================================================================
# Triage tags (single source of truth)
# =============================================================================
TAG_RED = "RED"
TAG_YELLOW = "YELLOW"
TAG_GREEN = "GREEN"
TAG_BLACK = "BLACK"
TAG_UNKNOWN = "UNKNOWN"  # for edge cases

ALL_TAGS = (TAG_RED, TAG_YELLOW, TAG_GREEN, TAG_BLACK)

# Tag ordering for sorting (lower = higher priority for evacuation)
TAG_RANK = {TAG_RED: 0, TAG_YELLOW: 1, TAG_GREEN: 2, TAG_BLACK: 3}

# Base priority scores per tag
TAG_BASE_SCORE = {TAG_RED: 100, TAG_YELLOW: 50, TAG_GREEN: 10, TAG_BLACK: 0}


# =============================================================================
# 12 screening question keys
# =============================================================================
SCREENING_QUESTIONS = [f"q{i}" for i in range(1, 13)]

# Safety-critical questions — Unknown on any of these forces human review
SAFETY_CRITICAL_QS = ("q1", "q5", "q6", "q7", "q9")

# Valid answer values
ANSWER_YES = "Yes"
ANSWER_NO = "No"
ANSWER_UNKNOWN = "Unknown"
VALID_ANSWERS = (ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN)


# =============================================================================
# Form field canonical values (what gradio_app writes, what screening reads)
# =============================================================================
# Breathing status
BREATHING_NORMAL = "normal"
BREATHING_RAPID_WEAK = "rapid_weak"
BREATHING_ABSENT = "absent"

# Pulse radial
PULSE_STRONG = "strong"
PULSE_WEAK = "weak"
PULSE_ABSENT = "absent"

# Mental status
MENTAL_ALERT = "alert"
MENTAL_CONFUSED = "confused_drowsy"
MENTAL_UNRESPONSIVE = "unresponsive"

# Pain response
PAIN_YES = "pain"
PAIN_NO = "no_pain"
PAIN_UNKNOWN = "cannot_judge"

# Injury types
INJURY_BLEEDING = "bleeding"
INJURY_FRACTURE = "fracture"
INJURY_BURN = "burn"
INJURY_ENTRAPPED = "entrapped"
INJURY_EXPLOSION = "explosion"
INJURY_ABDOMINAL = "abdominal_pain"
INJURY_HEAD_TRAUMA = "head_trauma"

ALL_INJURIES = (
    INJURY_BLEEDING, INJURY_FRACTURE, INJURY_BURN, INJURY_ENTRAPPED,
    INJURY_EXPLOSION, INJURY_ABDOMINAL, INJURY_HEAD_TRAUMA,
)

# Burn locations
BURN_FACE = "face"
BURN_NECK = "neck"
BURN_OTHER = "other"

# Airway signs
AIRWAY_SOOT = "soot"
AIRWAY_HOARSE = "hoarse_voice"
AIRWAY_NONE = "none"

# Special markers
SPECIAL_PREGNANT = "pregnant"
SPECIAL_CHILD = "child_under_8"
SPECIAL_ELDERLY = "elderly_over_65"

# Pregnant-specific symptoms (conditional UI)
PREG_ABDOMINAL = "abdominal_pain"
PREG_BLEEDING = "vaginal_bleeding"
PREG_FETAL = "decreased_fetal_movement"


# =============================================================================
# Hidden risk levels
# =============================================================================
RISK_RED_NOW = "RED_NOW"
RISK_RED_WITHIN_HOUR = "RED_WITHIN_HOUR"
RISK_MONITORING = "MONITORING_REQUIRED"

RISK_LEVEL_SCORE = {
    RISK_RED_NOW: 20,
    RISK_RED_WITHIN_HOUR: 15,
    RISK_MONITORING: 5,
}


# =============================================================================
# Geo-fence zone codes
# =============================================================================
ZONE_NONE = 0
ZONE_CHEM = 1
ZONE_QUAKE = 2
ZONE_FLOOD = 3
ZONE_STRUCT = 4
ZONE_RADIATION = 5

ZONE_NAME = {
    ZONE_NONE: "NONE",
    ZONE_CHEM: "ZONE_CHEM",
    ZONE_QUAKE: "ZONE_QUAKE",
    ZONE_FLOOD: "ZONE_FLOOD",
    ZONE_STRUCT: "ZONE_STRUCT",
    ZONE_RADIATION: "ZONE_RADIATION",
}
ZONE_CODE = {v: k for k, v in ZONE_NAME.items()}

ZONE_PPE_ADVICE = {
    ZONE_CHEM: "Wear chemical respirator. Avoid skin contact. Decontaminate before evac.",
    ZONE_QUAKE: "Watch for aftershocks. Avoid damaged structures. Hard hat required.",
    ZONE_FLOOD: "Waterborne pathogen risk. Waterproof boots. Monitor for hypothermia.",
    ZONE_STRUCT: "Structural collapse risk. USAR team required. Do not enter building.",
    ZONE_RADIATION: "Radiation exposure risk. Dosimeter required. Limit exposure time.",
}


# =============================================================================
# Bit-packing packet version
# =============================================================================
PACKET_VERSION = 1
# Bytes per patient record in LoRa packet (extended format: includes raw fields)
PATIENT_BYTES = 18
# Header bytes
HEADER_BYTES = 10
# Max patients per packet (constrained by LoRa MTU 237 bytes)
MAX_PATIENTS_PER_PACKET = 12  # 10 + 12*18 = 226 bytes

# Field AI review flags (transported in byte 7 high bits of patient record)
REVIEW_NONE = 0
REVIEW_AI_SUGGESTED = 1
REVIEW_AI_ACCEPTED = 2
REVIEW_LOW_CONF = 3


# =============================================================================
# Pediatric thresholds (JumpSTART)
# =============================================================================
PEDIATRIC_RR_HIGH = 45  # RR > 45 triggers Q2 for pediatric
PEDIATRIC_RR_LOW = 15   # RR < 15 triggers Q2 for pediatric
ADULT_RR_HIGH = 30
ADULT_RR_LOW = 10

PEDIATRIC_AGE_THRESHOLD = 8  # < 8 years old = pediatric
ELDERLY_AGE_THRESHOLD = 65

# Entrapment threshold for Q5 (crush syndrome)
CRUSH_MIN_THRESHOLD = 30  # minutes


# =============================================================================
# Anomaly detection thresholds
# =============================================================================
ANOMALY_RESP_PCT = 0.50
ANOMALY_RESP_MIN = 5
ANOMALY_BURN_PCT = 0.60
ANOMALY_BURN_MIN = 3
ANOMALY_CRUSH_MIN = 3
ANOMALY_RED_WINDOW_MIN = 10
ANOMALY_RED_COUNT = 5
