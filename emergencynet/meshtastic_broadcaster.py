"""Meshtastic mesh broadcaster for incident alerts.

Distinct from ``lora_bridge.py`` (which sends compact 226-byte binary
patient packets on APP_PORT 256). This module sends *human-readable
alert text* on Meshtastic's standard text channel so it appears in the
regular Meshtastic Android app on every node — commanders see alerts
without running a custom client.

Outbound alerts are:
    - SHORT (LoRa MTU is ~237 bytes; we cap at 200 bytes payload to
      leave Meshtastic packet overhead room)
    - PLAIN UTF-8 (no JSON structure on the wire — that lives in the
      base-station log; the wire form is a one-line summary)
    - PRIORITY-TAGGED at the start so commanders can filter at a glance:
        [CRIT] / [HIGH] / [INFO]

Trigger discipline (intentional, see CODE_REVIEW.md):
    - Broadcasting is gated behind ``anomaly_detector`` flagging an
      alert at severity 'critical'.
    - The LLM (function-calling) is allowed to *compose* the message
      text but NOT to *trigger the send*. The decision to broadcast is
      deterministic, made by anomaly_detector + an outbound policy.
    - This preserves EmergencyNet's "deterministic core, AI advisory"
      principle even at the action layer.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

# Severity prefix tags for at-a-glance filtering
PRIORITY_CRITICAL = "[CRIT]"
PRIORITY_HIGH     = "[HIGH]"
PRIORITY_INFO     = "[INFO]"

# Hard cap on outgoing alert text. Meshtastic LongFast ~237 byte MTU,
# subtract framing overhead, leave ourselves margin.
def _limits():
    try:
        from .ai_config import mesh_alert_limits
        return mesh_alert_limits()
    except Exception:
        return 30.0, 200


MIN_INTERVAL_S, MAX_ALERT_BYTES = _limits()


class MeshAlertBroadcaster:
    """Pushes short alert text into the Meshtastic primary channel.

    The transport object must expose either:
        - ``send_text(text: str) -> bool``  (preferred — uses the
          standard text channel so the Meshtastic Android app shows it
          in its usual Messages tab), OR
        - ``send_packet(payload: bytes, ...) -> bool`` (fallback —
          our own APP_PORT, requires custom listener on the receiver)

    For real deployment we wire this to the meshtastic Python library
    via ``meshtastic.SerialInterface(...).sendText(text)``. For dev /
    test we accept any callable.
    """

    def __init__(
        self,
        transport_send_text: Optional[Callable[[str], bool]] = None,
        transport_send_packet: Optional[Callable[[bytes], bool]] = None,
        clock: Callable[[], float] = time.time,
    ):
        if transport_send_text is None and transport_send_packet is None:
            raise ValueError(
                "MeshAlertBroadcaster needs either transport_send_text "
                "or transport_send_packet"
            )
        self._send_text = transport_send_text
        self._send_packet = transport_send_packet
        self._clock = clock
        self._last_sent_at: float = 0.0
        self._sent_log: List[Dict[str, Any]] = []
        self._suppressed_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def broadcast(
        self,
        severity: str,
        anomaly_type: str,
        message_body: str,
    ) -> Dict[str, Any]:
        """Send one alert. Returns dict with status info; never throws.

        Args:
            severity:     "critical" | "high" | "info"
            anomaly_type: e.g. "RESP_CLUSTER", "RED_SURGE"
            message_body: composed text (likely from base AI function
                          calling). Will be truncated to fit MTU.
        """
        prefix = _priority_prefix(severity)
        head = f"{prefix} {anomaly_type}: "
        budget = MAX_ALERT_BYTES - len(head.encode("utf-8")) - 4
        body = _truncate_utf8(message_body, max(20, budget))
        text = head + body

        now = self._clock()
        if now - self._last_sent_at < MIN_INTERVAL_S and severity != "critical":
            self._suppressed_count += 1
            return {
                "sent": False,
                "reason": f"rate-limited ({MIN_INTERVAL_S}s window)",
                "text": text,
                "ts": now,
            }

        ok = self._dispatch(text)
        if ok:
            self._last_sent_at = now
            entry = {
                "sent": True,
                "ts": now,
                "severity": severity,
                "anomaly_type": anomaly_type,
                "text": text,
                "bytes": len(text.encode("utf-8")),
            }
            self._sent_log.append(entry)
            return entry
        return {
            "sent": False,
            "reason": "transport-failure",
            "text": text,
            "ts": now,
        }

    def _dispatch(self, text: str) -> bool:
        if self._send_text is not None:
            try:
                return bool(self._send_text(text))
            except Exception:
                return False
        # fallback path — pack as bytes and use APP_PORT sender
        try:
            return bool(self._send_packet(text.encode("utf-8")))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Audit / introspection
    # ------------------------------------------------------------------
    def sent_log(self) -> List[Dict[str, Any]]:
        return list(self._sent_log)

    def suppressed_count(self) -> int:
        return self._suppressed_count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _priority_prefix(sev: str) -> str:
    sev = (sev or "").lower()
    if sev == "critical":
        return PRIORITY_CRITICAL
    if sev == "high":
        return PRIORITY_HIGH
    return PRIORITY_INFO


def _truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate a string to a UTF-8 byte budget without breaking
    multibyte characters mid-codepoint. Critical for CJK / Arabic /
    Vietnamese alert bodies. Reserves 3 bytes for the ellipsis "…"
    (which is itself U+2026, encoded as 3 bytes in UTF-8).
    """
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    # Reserve 3 bytes for the ellipsis we will append. If the budget is
    # smaller than 4 bytes we can't fit any content + ellipsis cleanly,
    # so fall back to plain "..." if even that fits, else empty.
    ellipsis = "…"
    ell_bytes = len(ellipsis.encode("utf-8"))  # 3
    if max_bytes < ell_bytes + 1:
        # Fall back to ASCII "..." if it fits, else empty
        if max_bytes >= 3:
            return "..."
        return ""
    # errors='ignore' drops a partial trailing codepoint cleanly
    trimmed = encoded[: max_bytes - ell_bytes].decode("utf-8", errors="ignore")
    return trimmed + ellipsis


# ---------------------------------------------------------------------------
# Convenience: build a text-sender from a MeshtasticBridge
# ---------------------------------------------------------------------------
def from_meshtastic_bridge(bridge) -> MeshAlertBroadcaster:
    """Wire an existing MeshtasticBridge into a broadcaster.

    Tries iface.sendText() first (standard text channel) and falls
    back to bridge.send_packet() if not available.
    """
    iface = getattr(bridge, "_iface", None)

    if iface is not None and hasattr(iface, "sendText"):
        def _send_text(t: str) -> bool:
            try:
                iface.sendText(t)
                return True
            except Exception:
                return False
        return MeshAlertBroadcaster(transport_send_text=_send_text)

    # Fallback to APP_PORT path on the bridge
    def _send_packet(b: bytes) -> bool:
        return bridge.send_packet(b, destination="^all", want_ack=False)
    return MeshAlertBroadcaster(transport_send_packet=_send_packet)
