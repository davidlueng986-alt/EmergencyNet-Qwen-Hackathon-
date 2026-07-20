"""GPS reader.

Pulls the most recent fix from the Heltec V4's L76K GNSS module via the
Meshtastic Python API. Falls back to operator-supplied coordinates when
no fix is available.

Public surface:

    gps = GPSBridge(meshtastic_iface=...)   # may be None for tests
    fix = gps.last_fix()      # -> {"lat": float, "lon": float, "ts": float} or None
    gps.set_manual(34.7466, 113.6253)
"""
from __future__ import annotations

import time
from typing import Optional, Dict, Any


class GPSBridge:
    def __init__(self, meshtastic_iface: Any = None):
        self._iface = meshtastic_iface
        self._manual: Optional[Dict[str, float]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def last_fix(self) -> Optional[Dict[str, Any]]:
        """Return the most recent GPS fix or None."""
        # Manual override always wins (operator typed coordinates).
        if self._manual is not None:
            return {**self._manual, "source": "manual"}

        if self._iface is None:
            return None

        # The meshtastic library exposes the local node's position under
        # ``localNode.localConfig`` / ``getMyNodeInfo()`` depending on
        # version. Try both.
        try:
            info = self._iface.getMyNodeInfo()
        except Exception:
            info = None

        if not info:
            return None

        pos = info.get("position") or {}
        lat = pos.get("latitude") or pos.get("latitudeI")
        lon = pos.get("longitude") or pos.get("longitudeI")
        if lat is None or lon is None:
            return None
        # Meshtastic transmits lat/lon as int * 1e7 sometimes; normalise.
        if isinstance(lat, int) and abs(lat) > 1000:
            lat = lat / 1e7
        if isinstance(lon, int) and abs(lon) > 1000:
            lon = lon / 1e7
        return {
            "lat": float(lat),
            "lon": float(lon),
            "ts": time.time(),
            "source": "gnss",
        }

    def set_manual(self, lat: float, lon: float) -> None:
        self._manual = {"lat": float(lat), "lon": float(lon)}

    def clear_manual(self) -> None:
        self._manual = None
