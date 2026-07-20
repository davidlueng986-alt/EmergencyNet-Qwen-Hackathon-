"""Field-team GPS position tracker.

Listens for Meshtastic ``POSITION_APP`` packets from other nodes on the
mesh and maintains a live dict of {node_id: {lat, lon, altitude, rssi,
snr, last_seen_ts, name}}.

This is the data the base dashboard map renders to show where every
field-team radio currently is. Distinct from ``gps_bridge.py`` which
only reads the LOCAL node's GPS fix.

Wiring (in BaseGateway or base_dashboard startup):

    tracker = MeshPositionTracker()
    bridge.set_on_position(tracker.handle_position_packet)
    # OR if your bridge doesn't expose set_on_position:
    bridge.set_on_packet(tracker.handle_raw_packet)

    # Then read in dashboard:
    nodes = tracker.snapshot()      # list of dicts ready for map render
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional

# Stale threshold — node hasn't broadcast position in N seconds, we
# fade or drop it from the map. 10 min covers a Meshtastic default
# position broadcast cadence (60-300s) plus margin.
STALE_AFTER_S = 600.0


class MeshPositionTracker:
    """Tracks live positions of every node on the mesh."""

    def __init__(self, stale_after_s: float = STALE_AFTER_S):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stale_after_s = stale_after_s

    # ------------------------------------------------------------------
    # Packet handlers
    # ------------------------------------------------------------------
    def handle_position_packet(
        self,
        node_id: str,
        position: Dict[str, Any],
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Direct entry point if your MeshtasticBridge already parses
        position packets and gives you (node_id, position, meta).
        """
        meta = meta or {}
        lat = self._normalise_coord(position.get("latitude") or position.get("latitudeI"))
        lon = self._normalise_coord(position.get("longitude") or position.get("longitudeI"))
        if lat is None or lon is None:
            return
        with self._lock:
            self._nodes[str(node_id)] = {
                "node_id": str(node_id),
                "name": meta.get("name") or position.get("name") or str(node_id),
                "short_name": meta.get("short_name", ""),
                "lat": lat,
                "lon": lon,
                "altitude_m": position.get("altitude"),
                "rssi": meta.get("rxRssi"),
                "snr": meta.get("rxSnr"),
                "last_seen_ts": meta.get("ts") or time.time(),
                "battery_pct": position.get("batteryLevel"),
            }

    def handle_raw_packet(
        self,
        payload: bytes,
        meta: Dict[str, Any],
    ) -> None:
        """Fallback handler if your bridge only delivers raw packets
        and you need to tell position packets apart from EmergencyNet's
        binary patient packets (APP_PORT 256).

        Position packets carry a ``portnum`` of POSITION_APP (3) in
        Meshtastic's protobuf. Raw bytes don't tell us this directly,
        so we rely on meta.portnum being set by the bridge or fall
        back to length heuristic.
        """
        portnum = meta.get("portnum") or meta.get("port_num")
        if portnum != 3:
            # not a position packet
            return
        # If your bridge has decoded the position into a dict already:
        pos = meta.get("position") or meta.get("decoded_position")
        if not pos:
            return
        node_id = (
            meta.get("from")
            or meta.get("fromId")
            or meta.get("source")
            or "unknown"
        )
        self.handle_position_packet(str(node_id), pos, meta)

    # ------------------------------------------------------------------
    # Snapshot for map rendering
    # ------------------------------------------------------------------
    def snapshot(self, include_stale: bool = False) -> List[Dict[str, Any]]:
        """Return all known node positions, sorted by most recent.

        Args:
            include_stale: if False (default), nodes whose last position
                           is older than ``stale_after_s`` are dropped.
        """
        now = time.time()
        with self._lock:
            entries = list(self._nodes.values())
        if not include_stale:
            entries = [
                e for e in entries
                if now - e["last_seen_ts"] <= self._stale_after_s
            ]
        entries.sort(key=lambda e: e["last_seen_ts"], reverse=True)
        for e in entries:
            e["age_s"] = round(now - e["last_seen_ts"], 1)
        return entries

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._nodes.get(str(node_id))

    def remove_node(self, node_id: str) -> None:
        with self._lock:
            self._nodes.pop(str(node_id), None)

    def clear(self) -> None:
        with self._lock:
            self._nodes.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_coord(v: Any) -> Optional[float]:
        """Meshtastic uses int * 1e7 for lat/lon in some packet types
        and degrees in others. Auto-detect."""
        if v is None:
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if abs(f) > 1000:
            return f / 1e7
        return f


# ---------------------------------------------------------------------------
# Convenience: hook a tracker to a MeshtasticBridge
# ---------------------------------------------------------------------------
def attach_to_bridge(
    bridge,
    tracker: Optional[MeshPositionTracker] = None,
) -> MeshPositionTracker:
    """Wire a MeshtasticBridge so its incoming position packets feed
    into a tracker. Returns the tracker (newly created if not passed).

    The bridge must expose either:
      - bridge.set_on_position(callback)  — preferred, structured
      - bridge.set_on_packet(callback)    — fallback, raw bytes + meta
    """
    if tracker is None:
        tracker = MeshPositionTracker()

    if hasattr(bridge, "set_on_position"):
        bridge.set_on_position(tracker.handle_position_packet)
    elif hasattr(bridge, "set_on_packet"):
        # Wrap so position packets feed tracker AND existing handler chain
        existing = getattr(bridge, "_on_packet", None)

        def chained(payload: bytes, meta: Dict[str, Any]) -> None:
            tracker.handle_raw_packet(payload, meta)
            if existing:
                try:
                    existing(payload, meta)
                except Exception:
                    pass
        bridge.set_on_packet(chained)
    return tracker
