"""Base-station gateway — LoRa receive -> store patients -> anomaly -> dashboard.

No field-vs-shadow dual inference (product decision: shadow removed).
Pipeline:

    1. decode_packet
    2. store patient records (capped)
    3. AnomalyDetector.add / evaluate
    4. optional on_update callback

Import-clean (no Gradio / Meshtastic) for unit tests with synthetic packets.
"""
from __future__ import annotations

import time
import threading
from collections import deque
from typing import Callable, Dict, Any, List, Optional

from .bit_packer import decode_packet
from .anomaly_detector import AnomalyDetector
from .ai_config import gateway_patient_cap


def struct_error():
    """Lazy-resolve struct.error so the except clause stays a tuple."""
    import struct
    return struct.error


class BaseGateway:
    def __init__(
        self,
        on_update: Optional[Callable[[Dict[str, Any]], None]] = None,
        patient_cap: Optional[int] = None,
    ):
        self.on_update = on_update
        self.detector = AnomalyDetector()
        self._patient_cap = patient_cap if patient_cap is not None else gateway_patient_cap()
        self._patients: deque = deque(maxlen=max(1, self._patient_cap))
        self._zone_counts: Dict[int, int] = {}
        self._lock = threading.Lock()
        self._seen_anomaly_types: set = set()

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------
    def handle_raw(self, payload: bytes, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Decode + process a raw LoRa packet.

        Bad packets MUST NOT crash the receiver.
        """
        try:
            decoded = decode_packet(payload)
        except (ValueError, IndexError, struct_error()) as exc:
            return {
                "ts": time.time(),
                "team_id": None,
                "zone_code": 0,
                "patients_received": 0,
                "alerts": [{
                    "type": "MALFORMED_PACKET",
                    "severity": "warning",
                    "message": f"Dropped {len(payload)}-byte packet: {exc}",
                }],
                "per_patient": [],
                "new_anomaly_types": [],
                "meta": meta or {},
            }
        return self.handle_decoded(decoded, meta)

    def handle_decoded(
        self,
        decoded_packet: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        zone = decoded_packet.get("zone_code", 0)
        patients = decoded_packet.get("patients") or []
        with self._lock:
            self._zone_counts[zone] = self._zone_counts.get(zone, 0) + len(patients)

        per_patient: List[Dict[str, Any]] = []
        for pat in patients:
            with self._lock:
                self._patients.append(pat)
            self.detector.add(pat)
            per_patient.append({"field": pat})

        alerts = self.detector.evaluate()
        new_types: List[str] = []
        for a in alerts:
            at = str(a.get("type", ""))
            if at and at not in self._seen_anomaly_types and at != "MALFORMED_PACKET":
                self._seen_anomaly_types.add(at)
                new_types.append(at)

        update = {
            "ts": time.time(),
            "team_id": decoded_packet.get("team_id"),
            "zone_code": zone,
            "patients_received": len(patients),
            "alerts": alerts,
            "per_patient": per_patient,
            "new_anomaly_types": new_types,
            "meta": meta or {},
        }
        if self.on_update:
            try:
                self.on_update(update)
            except Exception:
                pass
        return update

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "patients": list(self._patients),
                "disagreements": [],  # shadow removed; keep key for API stability
                "zone_counts": dict(self._zone_counts),
            }

    def reset(self) -> None:
        with self._lock:
            self._patients.clear()
            self._zone_counts.clear()
        self.detector = AnomalyDetector()
        self._seen_anomaly_types.clear()
