"""Meshtastic LoRa raw-bytes bridge.

Wraps the official ``meshtastic`` Python library so the rest of our code
doesn't have to know whether the device is connected via USB serial or
Wi-Fi (the Meshtastic Android app exposes a TCP server on port 4403).

Public surface:

    bridge = MeshtasticBridge(transport="serial", device="/dev/ttyUSB0")
    bridge = MeshtasticBridge(transport="tcp", host="192.168.1.20")
    bridge.send_packet(payload_bytes)
    bridge.set_on_packet(callback)        # callback(bytes, meta_dict)
    bridge.close()

If the meshtastic library isn't installed (e.g. running in dev), the
bridge degrades to a loopback mode that simply stores sent packets so
unit tests can exercise the calling code.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional, List, Tuple, Dict, Any

# Constant private app port for our protocol — keep in sync with base
# station's expected portnum.
def _app_port() -> int:
    try:
        from .ai_config import meshtastic_app_port
        return meshtastic_app_port()
    except Exception:
        return 256


APP_PORT = _app_port()


class MeshtasticBridge:
    def __init__(
        self,
        transport: str = "serial",
        device: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 4403,
        loopback: bool = False,
    ):
        self.transport = transport
        self.device = device
        self.host = host
        self.port = port
        self._loopback = loopback
        self._iface = None
        self._on_packet: Optional[Callable[[bytes, Dict[str, Any]], None]] = None
        self._loopback_log: List[Tuple[bytes, Dict[str, Any]]] = []
        self._lock = threading.Lock()

        if not loopback:
            self._connect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def _connect(self) -> None:
        try:
            import meshtastic                       # type: ignore
            import meshtastic.serial_interface      # type: ignore
            import meshtastic.tcp_interface         # type: ignore
            from pubsub import pub                  # type: ignore
        except ImportError:
            # Library missing — fall back to loopback so callers still work.
            self._loopback = True
            return

        if self.transport == "tcp":
            self._iface = meshtastic.tcp_interface.TCPInterface(
                hostname=self.host or "127.0.0.1", portNumber=self.port,
            )
        else:
            self._iface = meshtastic.serial_interface.SerialInterface(
                devPath=self.device,
            )

        # Wire up incoming-packet hook
        try:
            from pubsub import pub  # type: ignore
            pub.subscribe(self._on_recv, "meshtastic.receive.data")
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # Send / receive
    # ------------------------------------------------------------------
    def send_packet(
        self,
        payload: bytes,
        destination: str = "^all",
        want_ack: bool = False,
    ) -> bool:
        meta = {"ts": time.time(), "destination": destination,
                "len": len(payload)}
        if self._loopback or self._iface is None:
            with self._lock:
                self._loopback_log.append((payload, meta))
            if self._on_packet:
                self._on_packet(payload, meta)
            return True

        try:
            self._iface.sendData(
                payload,
                destinationId=destination,
                portNum=APP_PORT,
                wantAck=want_ack,
            )
            return True
        except Exception:
            return False

    def set_on_packet(
        self, callback: Callable[[bytes, Dict[str, Any]], None]
    ) -> None:
        self._on_packet = callback

    def _on_recv(self, packet=None, interface=None):  # pragma: no cover
        try:
            data = packet["decoded"]["payload"]  # bytes
        except Exception:
            return
        meta = {
            "from": packet.get("fromId"),
            "to": packet.get("toId"),
            "rxRssi": packet.get("rxRssi"),
            "rxSnr": packet.get("rxSnr"),
            "ts": time.time(),
        }
        if self._on_packet:
            self._on_packet(bytes(data), meta)

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------
    def loopback_log(self) -> List[Tuple[bytes, Dict[str, Any]]]:
        with self._lock:
            return list(self._loopback_log)

    def close(self) -> None:
        if self._iface is not None:
            try:
                self._iface.close()
            except Exception:
                pass
        self._iface = None
