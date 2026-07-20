"""Shared fixtures — offline, no hardware, no network required."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_form_red_rr():
    """Adult rapid breathing → RED via Q2. Locks screening+triage path."""
    return {
        "patient_id": "P2",
        "walking": False,
        "age": 30,
        "breathing_status": "rapid_weak",
        "resp_rate": 40,
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": [],
        "special_markers": [],
        "notes": "",
    }


@pytest.fixture
def sample_form_green():
    return {
        "patient_id": "P3",
        "walking": True,
        "age": 25,
        "breathing_status": "normal",
        "resp_rate": 16,
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": ["fracture"],
        "special_markers": [],
        "notes": "",
    }
