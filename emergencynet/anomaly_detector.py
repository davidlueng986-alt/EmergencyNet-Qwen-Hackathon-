"""Aggregate-level anomaly detection.

Watches the running stream of decoded patients and surfaces statistical
patterns the commander should investigate. None of these conclusions
override individual triage decisions — they are advisory.

Triggers (defaults from constants.py, all configurable):
    - Mass respiratory distress: >=50% of recent patients (n>=5) show
      abnormal breathing -> possible airborne / chemical event
    - Burn cluster: >=60% with INJURY_BURN (n>=3) -> possible thermal
      / explosive event
    - Crush cluster: >=3 entrapped patients -> structural collapse
    - RED surge: >=5 RED tags within a 10-minute window -> mass
      casualty escalation
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Any, List, Tuple

from .constants import (
    BREATHING_RAPID_WEAK, BREATHING_ABSENT,
    INJURY_BURN, INJURY_ENTRAPPED,
    TAG_RED,
    ANOMALY_RESP_PCT, ANOMALY_RESP_MIN,
    ANOMALY_BURN_PCT, ANOMALY_BURN_MIN,
    ANOMALY_CRUSH_MIN,
    ANOMALY_RED_WINDOW_MIN, ANOMALY_RED_COUNT,
)


class AnomalyDetector:
    def __init__(self, window_size: int = 30):
        self.window: Deque[Tuple[float, Dict[str, Any]]] = deque(maxlen=window_size)

    def add(self, patient: Dict[str, Any]) -> None:
        self.window.append((time.time(), patient))

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------
    def evaluate(self) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        if not self.window:
            return alerts
        rows = [p for _, p in self.window]
        n = len(rows)

        # 1) respiratory cluster
        resp_bad = sum(
            1 for r in rows
            if r.get("breathing_status") in (BREATHING_RAPID_WEAK, BREATHING_ABSENT)
        )
        if n >= ANOMALY_RESP_MIN and resp_bad / n >= ANOMALY_RESP_PCT:
            alerts.append({
                "type": "RESP_CLUSTER",
                "severity": "high",
                "message": (
                    f"{resp_bad}/{n} patients show respiratory distress. "
                    "Consider airborne / chemical agent."
                ),
                "n": n, "matches": resp_bad,
            })

        # 2) burn cluster
        burns = sum(1 for r in rows if INJURY_BURN in (r.get("injury_types") or []))
        if n >= ANOMALY_BURN_MIN and burns / n >= ANOMALY_BURN_PCT:
            alerts.append({
                "type": "BURN_CLUSTER",
                "severity": "high",
                "message": (
                    f"{burns}/{n} patients have burns. Possible thermal / "
                    "explosive event."
                ),
                "n": n, "matches": burns,
            })

        # 3) crush cluster
        crush = sum(1 for r in rows if INJURY_ENTRAPPED in (r.get("injury_types") or []))
        if crush >= ANOMALY_CRUSH_MIN:
            alerts.append({
                "type": "CRUSH_CLUSTER",
                "severity": "high",
                "message": (
                    f"{crush} entrapped patients. Likely structural collapse — "
                    "request USAR team."
                ),
                "n": n, "matches": crush,
            })

        # 4) RED surge
        cutoff = time.time() - (ANOMALY_RED_WINDOW_MIN * 60)
        recent_red = sum(
            1 for ts, r in self.window
            if ts >= cutoff and r.get("triage_tag") == TAG_RED
        )
        if recent_red >= ANOMALY_RED_COUNT:
            alerts.append({
                "type": "RED_SURGE",
                "severity": "critical",
                "message": (
                    f"{recent_red} RED tags in last {ANOMALY_RED_WINDOW_MIN} min. "
                    "Mass casualty escalation in progress."
                ),
                "n": n, "matches": recent_red,
            })

        return alerts
