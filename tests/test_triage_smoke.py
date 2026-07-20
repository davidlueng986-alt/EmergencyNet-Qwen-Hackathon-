"""Characterization: deterministic triage + screening.

Locks behavior documented in triage_core.py / screening.py / risk_engine.py.
"""
from __future__ import annotations

from emergencynet.risk_engine import HIDDEN_RISK_RULES, evaluate_hidden_risks
from emergencynet.screening import form_to_screening, form_to_patient_record
from emergencynet.triage_core import triage_and_risk


def test_hidden_risk_rule_count_is_eight():
    # risk_engine.py:23–148 — eight keys q5–q12 (docstring may wrongly say 7)
    assert len(HIDDEN_RISK_RULES) == 8
    assert set(HIDDEN_RISK_RULES) == {f"q{i}" for i in range(5, 13)}


def test_absent_breathing_adult_black():
    # triage_core.py:97–101 — Q1 Yes → BLACK
    form = {
        "patient_id": "P1",
        "walking": False,
        "age": 40,
        "breathing_status": "absent",
        "pulse_radial": "absent",
        "mental_status": "unresponsive",
        "pain_response": "cannot_judge",
        "injury_types": ["bleeding"],
        "special_markers": [],
    }
    scr = form_to_screening(form)
    assert scr["q1"] == "Yes"  # screening.py:66–78
    res = triage_and_risk(scr, form_to_patient_record(form))
    assert res["triage_tag"] == "BLACK"


def test_rapid_weak_is_red(sample_form_red_rr):
    # screening.py:81–88 Q2; triage_core.py:105–107
    scr = form_to_screening(sample_form_red_rr)
    assert scr["q2"] == "Yes"
    res = triage_and_risk(scr, form_to_patient_record(sample_form_red_rr))
    assert res["triage_tag"] == "RED"


def test_ambulatory_stable_green(sample_form_green):
    # triage_core.py:136–138
    scr = form_to_screening(sample_form_green)
    res = triage_and_risk(scr, form_to_patient_record(sample_form_green))
    assert res["triage_tag"] == "GREEN"


def test_non_ambulatory_stable_yellow(sample_form_green):
    # triage_core.py:129–134
    form = dict(sample_form_green)
    form["walking"] = False
    scr = form_to_screening(form)
    res = triage_and_risk(scr, form_to_patient_record(form))
    assert res["triage_tag"] == "YELLOW"


def test_q9_burn_face_forces_red_via_hidden_risk():
    # risk_engine q9 RED_WITHIN_HOUR; triage_core.py:116–126
    form = {
        "patient_id": "P5",
        "walking": True,
        "age": 35,
        "breathing_status": "normal",
        "pulse_radial": "strong",
        "mental_status": "alert",
        "pain_response": "pain",
        "injury_types": ["burn"],
        "burn_location": ["face"],
        "airway_signs": ["soot"],
        "special_markers": [],
    }
    scr = form_to_screening(form)
    assert scr["q9"] == "Yes"  # screening.py:182–193
    risks = evaluate_hidden_risks(scr)
    assert any(r["qkey"] == "q9" for r in risks)
    res = triage_and_risk(scr, form_to_patient_record(form))
    assert res["triage_tag"] == "RED"


def test_ai_apply_suggestions_only_no_to_yes():
    # screening.apply_suggestions + parser contract screening.py:409–420
    from emergencynet.screening import apply_suggestions

    answers = {f"q{i}": "No" for i in range(1, 13)}
    suggestions = [
        {"qkey": "q5", "from": "No", "to": "Yes", "reason": "x"},
        {"qkey": "q6", "from": "No", "to": "Yes", "reason": "y"},
    ]
    out = apply_suggestions(answers, accepted_qkeys=["q5"], suggestions=suggestions)
    assert out["q5"] == "Yes"
    assert out["q6"] == "No"
