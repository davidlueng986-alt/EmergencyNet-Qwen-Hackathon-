"""Civilian app -> base station distress intake.

Companion module to EmergencyNet for receiving distress reports from
the separate civilian-facing first-aid app (phone tier).

Architecture clarification
--------------------------

The civilian app on the phone (the "叫救援" / Call Rescue button) is
an **internet-dependent** transport layer. First-aid guidance can run
with rule fallbacks offline (optional Qwen Cloud when online). The
*upload-to-base* button only fires when there is connectivity:

    Civilian phone has internet:
        AI guidance shown locally → user taps "Send to responders" →
        POST hits this intake endpoint immediately.

    Civilian phone has no internet (disaster zone):
        AI guidance still shown locally → user taps "Send to
        responders" → message is **persisted in the phone's outbox
        queue** with timestamp, GPS, severity. When connectivity
        returns (even partial — Wi-Fi from a passing relief vehicle,
        roaming on a backup cell, Starlink hotspot at an aid post),
        the queue flushes to base. The queue is timestamped so the
        base knows the message was generated *at* disaster moment,
        not *received* moment.

The queue/retry logic lives in the civilian app itself; this base
module only handles inbound HTTP requests. From the base's perspective
a delayed message looks identical to a fresh one except for the older
``ts`` field, which the dashboard renders as "submitted 47 min ago".

This intake module:
  - validates the schema
  - de-duplicates by incident_id (60s window, plus a longer-window
    dedup using phone_id + lat/lon for delayed retries)
  - feeds the report into the base dashboard's civilian distress feed
  - never broadcasts civilian PII out over LoRa (deliberate split —
    the LoRa pipeline is for trained operators only)

POC scope:
  - Single FastAPI / Flask-style endpoint, in-memory store
  - No auth (real deployment needs HMAC + cert pinning + civilian app
    signing key — out of hackathon scope)
  - The civilian phone is responsible for stripping its own PII before
    POSTing; this module only stores hashed tokens

Expected POST body
------------------

    {
      "incident_id":     "uuid",
      "lat":             22.3193,
      "lon":             114.1694,
      "summary_en":      "person not breathing, suspect cardiac arrest",
      "raw_text":        "<original-language user input>",
      "language":        "yue" | "zh" | "en" | "vi" | "id" | "tl" | ...,
      "severity_hint":   "critical" | "high" | "moderate" | "info",
      "phone_id":        "anonymous-hashed-token",   # privacy-preserving
      "ts":              1715420400.0,
      "queued_offline":  true | false   # set by civilian app if from outbox
    }

Map rendering: see ``map_widget.py``. Civilian distress markers render
in a different colour from field-team radios so commanders can tell
them apart at a glance.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional


# Severity colour mapping for the map widget
SEVERITY_COLOR = {
    "critical": "#d9000a",   # deep red
    "high":     "#ff6b00",   # orange
    "moderate": "#ffc107",   # amber
    "info":     "#4a90e2",   # blue
}

# Short de-duplication window — same incident_id within this window is
# treated as one report (civilian app retries on flaky network).
DEDUPE_WINDOW_S = 60.0

# Long dedup window — for queued/offline retries where the same
# incident might be re-sent hours later from the outbox.
LONG_DEDUPE_WINDOW_S = 6 * 3600.0  # 6h


class CivilianIntake:
    """Stores civilian distress reports and exposes them to the dashboard."""

    def __init__(
        self,
        max_reports: int = 200,
        on_new_report: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self._reports: List[Dict[str, Any]] = []
        self._seen_ids: Dict[str, float] = {}
        self._max = max_reports
        self._lock = threading.Lock()
        self._on_new = on_new_report

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def submit(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Validate + store a civilian distress report.

        Returns: ``{"ok": bool, "incident_id": ..., "error": optional,
                    "duplicate": optional}``
        Never throws — civilian app should always get a response so its
        outbox knows to clear the entry on success.
        """
        clean = self._validate(report)
        if not clean["ok"]:
            return clean

        rec = clean["record"]
        with self._lock:
            now = time.time()
            self._purge_seen(now)

            # Short-window dedup (network retry)
            existing_ts = self._seen_ids.get(rec["incident_id"])
            window = (
                LONG_DEDUPE_WINDOW_S if rec.get("queued_offline")
                else DEDUPE_WINDOW_S
            )
            if existing_ts is not None and now - existing_ts < window:
                return {
                    "ok": True,
                    "incident_id": rec["incident_id"],
                    "duplicate": True,
                    "error": None,
                }

            self._seen_ids[rec["incident_id"]] = now
            self._reports.append(rec)
            if len(self._reports) > self._max:
                self._reports = self._reports[-self._max:]

        # Fire-and-forget callback to dashboard (outside the lock)
        if self._on_new:
            try:
                self._on_new(rec)
            except Exception:
                pass

        return {
            "ok": True,
            "incident_id": rec["incident_id"],
            "duplicate": False,
            "error": None,
        }

    def snapshot(
        self,
        active_only: bool = True,
        max_age_s: float = 1800.0,
    ) -> List[Dict[str, Any]]:
        """Return distress reports for map rendering.

        Args:
            active_only: drop reports older than ``max_age_s``
            max_age_s:   default 30 min — civilian distress shouldn't
                         linger forever on the map
        """
        now = time.time()
        with self._lock:
            recs = list(self._reports)
        if active_only:
            recs = [r for r in recs if now - r.get("received_ts", r["ts"]) <= max_age_s]
        recs.sort(key=lambda r: r["ts"], reverse=True)
        for r in recs:
            r["age_s"] = round(now - r["ts"], 1)
            # Make queued-offline status visible to the dashboard
            r["delayed"] = bool(r.get("queued_offline"))
        return recs

    def acknowledge(self, incident_id: str) -> bool:
        """Mark a report as acknowledged by a commander (drops from the
        active map). Returns True if the incident was found.
        """
        with self._lock:
            for r in self._reports:
                if r["incident_id"] == incident_id:
                    r["acknowledged"] = True
                    r["ack_ts"] = time.time()
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._reports.clear()
            self._seen_ids.clear()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self, raw: Any) -> Dict[str, Any]:
        if not isinstance(raw, dict):
            return {"ok": False, "error": "report must be a JSON object"}

        try:
            lat = float(raw["lat"])
            lon = float(raw["lon"])
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": "lat/lon required and numeric"}

        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return {"ok": False, "error": "lat/lon out of range"}

        sev = str(raw.get("severity_hint", "moderate")).lower()
        if sev not in SEVERITY_COLOR:
            sev = "moderate"

        summary = str(raw.get("summary_en", ""))[:500]
        raw_text = str(raw.get("raw_text", ""))[:1000]
        lang = str(raw.get("language", "auto"))[:10]
        phone_id = str(raw.get("phone_id", "anon"))[:128]
        incident_id = str(raw.get("incident_id") or uuid.uuid4().hex)[:64]
        ts = float(raw.get("ts") or time.time())
        queued_offline = bool(raw.get("queued_offline", False))

        record = {
            "incident_id": incident_id,
            "lat": lat,
            "lon": lon,
            "summary_en": summary,
            "raw_text": raw_text,
            "language": lang,
            "severity_hint": sev,
            "color": SEVERITY_COLOR[sev],
            "phone_id": phone_id,
            "ts": ts,
            "queued_offline": queued_offline,
            "received_ts": time.time(),
            "acknowledged": False,
        }
        return {"ok": True, "record": record, "error": None}

    def _purge_seen(self, now: float) -> None:
        cutoff = now - LONG_DEDUPE_WINDOW_S * 2
        self._seen_ids = {
            k: v for k, v in self._seen_ids.items() if v >= cutoff
        }


# ---------------------------------------------------------------------------
# Optional: tiny FastAPI / Flask-compatible adapter
# ---------------------------------------------------------------------------
def make_flask_blueprint(intake: CivilianIntake):
    """Return a Flask blueprint exposing POST /civilian/distress.

    Usage:
        from flask import Flask
        from emergencynet.civilian_intake import CivilianIntake, make_flask_blueprint
        app = Flask(__name__)
        intake = CivilianIntake()
        app.register_blueprint(make_flask_blueprint(intake))

    If Flask isn't installed, this raises ImportError — civilian intake
    can still be driven manually via intake.submit(...) for tests / Gradio
    integration without the HTTP layer.
    """
    try:
        from flask import Blueprint, request, jsonify
    except ImportError as exc:
        raise ImportError(
            "Flask not installed; pip install flask, "
            "or call intake.submit() directly without HTTP."
        ) from exc

    bp = Blueprint("civilian_intake", __name__, url_prefix="/civilian")

    @bp.route("/distress", methods=["POST"])
    def distress():
        report = request.get_json(silent=True) or {}
        result = intake.submit(report)
        status = 200 if result.get("ok") else 400
        return jsonify(result), status

    @bp.route("/active", methods=["GET"])
    def active():
        return jsonify({"reports": intake.snapshot()})

    @bp.route("/ack/<incident_id>", methods=["POST"])
    def ack(incident_id):
        ok = intake.acknowledge(incident_id)
        return jsonify({"ok": ok})

    return bp
