"""Base-station multi-turn tool agent (Qwen Cloud function calling).

Architectural rules:
  - LLM may draft mesh alerts and choose severity.
  - Model-originated send calls are always forced to human_approved=false.
  - Only the separate dashboard human control may call the send tool as approved.
  - No field-vs-shadow tools (shadow removed from product).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from .ai_config import load_ai_config
from .qwen_client import QwenClient, QwenResponse
from .sitrep_generator import build_sitrep


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_situation_snapshot",
            "description": "Get patient tag counts, hidden risks, active anomalies, recent drafts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_patients",
            "description": "List recent patients (id, tag, risks, injuries). Cap 50.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max rows, default 50"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_anomalies",
            "description": "Run anomaly detector evaluate() on current window.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "build_sitrep_md",
            "description": "Build commander SITREP markdown from current gateway state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_mesh_alert",
            "description": (
                "Draft a mesh alert (<=180 chars body). Does NOT transmit. "
                "severity must be critical|high|info."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "info"],
                    },
                    "anomaly_type": {"type": "string"},
                    "message_body": {"type": "string"},
                },
                "required": ["severity", "anomaly_type", "message_body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_send_broadcast",
            "description": (
                "Send a previously drafted alert. Requires human_approved=true. "
                "Without approval the send is blocked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "draft_id": {"type": "string"},
                    "human_approved": {"type": "boolean"},
                },
                "required": ["draft_id", "human_approved"],
            },
        },
    },
]

_SYSTEM = """You are EmergencyNet base station operations agent.
You help the Incident Commander with aggregate situation awareness and mesh alert drafts.
Hard rules:
- Never change patient triage tags (deterministic core owns tags).
- Never claim you sent a mesh message unless request_send_broadcast returned sent=true.
- Prefer draft_mesh_alert for alerts; only request_send_broadcast when commander explicitly approved.
- severity must be one of critical, high, info.
- Be concise. Use tools when you need live state.
"""


class BaseToolAgent:
    def __init__(
        self,
        gateway,
        broadcaster=None,
        client: Optional[QwenClient] = None,
        max_steps: Optional[int] = None,
    ):
        self.gateway = gateway
        self.broadcaster = broadcaster
        self.client = client or QwenClient()
        cfg = load_ai_config()
        self.max_steps = max_steps if max_steps is not None else cfg.agent_max_steps
        self.model = cfg.model_agent
        self._drafts: Dict[str, Dict[str, Any]] = {}
        self._audit: List[Dict[str, Any]] = []

    def drafts(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._drafts)

    def get_draft(self, draft_id: str) -> Optional[Dict[str, Any]]:
        return self._drafts.get(draft_id)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def _tool_get_situation_snapshot(self, **_kwargs) -> Dict[str, Any]:
        snap = self.gateway.snapshot()
        patients = snap.get("patients") or []
        tag_counts = {"RED": 0, "YELLOW": 0, "GREEN": 0, "BLACK": 0}
        risk_counts: Dict[str, int] = {}
        for p in patients:
            t = p.get("triage_tag", "UNKNOWN")
            if t in tag_counts:
                tag_counts[t] += 1
            for q in p.get("hidden_risk_qs") or []:
                key = q if isinstance(q, str) else str(q)
                risk_counts[key] = risk_counts.get(key, 0) + 1
        anomalies = []
        det = getattr(self.gateway, "detector", None)
        if det is not None:
            try:
                anomalies = det.evaluate()
            except Exception:
                anomalies = []
        return {
            "patient_count": len(patients),
            "tag_counts": tag_counts,
            "hidden_risks_fired": risk_counts,
            "active_anomalies": anomalies,
            "draft_count": len(self._drafts),
        }

    def _tool_list_patients(self, limit: int = 50, **_kwargs) -> Dict[str, Any]:
        try:
            lim = max(1, min(50, int(limit)))
        except (TypeError, ValueError):
            lim = 50
        patients = self.gateway.snapshot().get("patients") or []
        rows = []
        for p in patients[-lim:]:
            rows.append({
                "patient_id": p.get("patient_id"),
                "triage_tag": p.get("triage_tag"),
                "hidden_risk_qs": p.get("hidden_risk_qs") or [],
                "injury_types": p.get("injury_types") or [],
                "age": p.get("age"),
            })
        return {"patients": rows, "n": len(rows)}

    def _tool_list_anomalies(self, **_kwargs) -> Dict[str, Any]:
        det = getattr(self.gateway, "detector", None)
        if det is None:
            return {"alerts": []}
        try:
            return {"alerts": det.evaluate()}
        except Exception as exc:
            return {"alerts": [], "error": str(exc)}

    def _tool_build_sitrep_md(self, **_kwargs) -> Dict[str, Any]:
        snap = self.gateway.snapshot()
        det = getattr(self.gateway, "detector", None)
        alerts = []
        if det is not None:
            try:
                alerts = det.evaluate()
            except Exception:
                alerts = []
        sitrep = build_sitrep(
            snap.get("patients") or [],
            alerts,
            [],  # no disagreements (shadow removed)
            zone_breakdown=snap.get("zone_counts"),
            advice=None,
        )
        return {"markdown": sitrep.get("markdown", ""), "summary_counts": sitrep.get("summary_counts")}

    def _tool_draft_mesh_alert(
        self,
        severity: str = "info",
        anomaly_type: str = "UNKNOWN",
        message_body: str = "",
        **_kwargs,
    ) -> Dict[str, Any]:
        sev = str(severity or "info").lower()
        if sev not in ("critical", "high", "info"):
            sev = "info"
        body = str(message_body or "")[:180]
        draft_id = "d_" + uuid.uuid4().hex[:12]
        draft = {
            "draft_id": draft_id,
            "severity": sev,
            "anomaly_type": str(anomaly_type or "UNKNOWN").upper().replace(" ", "_"),
            "message_body": body,
            "ts": time.time(),
            "sent": False,
        }
        self._drafts[draft_id] = draft
        return {"ok": True, "draft_id": draft_id, "draft": draft, "sent": False}

    def _tool_request_send_broadcast(
        self,
        draft_id: str = "",
        human_approved: bool = False,
        **_kwargs,
    ) -> Dict[str, Any]:
        if not human_approved:
            return {
                "ok": False,
                "sent": False,
                "error": "human_approval_required",
            }
        draft = self._drafts.get(str(draft_id))
        if not draft:
            return {"ok": False, "sent": False, "error": "unknown_draft_id"}
        if self.broadcaster is None:
            return {"ok": False, "sent": False, "error": "no_broadcaster"}
        body = draft.get("message_body", "") or ""
        result = self.broadcaster.broadcast(
            severity=draft.get("severity", "info"),
            anomaly_type=draft.get("anomaly_type", "UNKNOWN"),
            message_body=body,
        )
        draft["sent"] = bool(result.get("sent"))
        draft["send_result"] = result
        return {"ok": True, "sent": bool(result.get("sent")), "result": result}

    def _dispatch_tool(self, name: str, args: Dict[str, Any]) -> Any:
        table: Dict[str, Callable[..., Any]] = {
            "get_situation_snapshot": self._tool_get_situation_snapshot,
            "list_patients": self._tool_list_patients,
            "list_anomalies": self._tool_list_anomalies,
            "build_sitrep_md": self._tool_build_sitrep_md,
            "draft_mesh_alert": self._tool_draft_mesh_alert,
            "request_send_broadcast": self._tool_request_send_broadcast,
        }
        fn = table.get(name)
        if fn is None:
            return {"error": f"unknown_tool:{name}"}
        # The model is never a human approval source. Even if it fabricates
        # human_approved=true in tool arguments, the agent loop forces the
        # value back to False. The dashboard's separate Approve & Send button
        # calls _tool_request_send_broadcast directly after a human click.
        if name == "request_send_broadcast":
            args = dict(args or {})
            args["human_approved"] = False
        try:
            return fn(**(args or {}))
        except TypeError:
            # ignore unexpected kwargs
            return fn()
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------
    def run(self, user_text: str, context: str = "") -> Dict[str, Any]:
        """Multi-turn tool loop. Returns final text + audit."""
        user = (user_text or "").strip()
        if context:
            user = f"{user}\n\nCONTEXT:\n{context}" if user else f"CONTEXT:\n{context}"
        if not user:
            user = "Provide a brief situation assessment using tools."

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ]
        audit: List[Dict[str, Any]] = []
        final_text = ""

        for step in range(self.max_steps):
            resp: QwenResponse = self.client.chat(
                messages,
                model=self.model,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                enable_thinking=False,
            )
            if not resp.ok:
                return {
                    "ok": False,
                    "text": f"(agent error: {resp.error})",
                    "audit": audit,
                    "drafts": list(self._drafts.values())[-5:],
                }

            if not resp.tool_calls:
                final_text = resp.content or ""
                audit.append({"step": step, "type": "final", "content": final_text[:500]})
                break

            # Append assistant message with tool_calls
            messages.append({
                "role": "assistant",
                "content": resp.content or "",
                "tool_calls": resp.tool_calls,
            })
            for tc in resp.tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch_tool(name, args if isinstance(args, dict) else {})
                audit.append({
                    "step": step,
                    "type": "tool",
                    "name": name,
                    "args": args,
                    "result": result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or "",
                    "content": json.dumps(result, ensure_ascii=False)[:4000],
                })
        else:
            final_text = "(agent reached max steps without final answer)"

        self._audit.extend(audit)
        return {
            "ok": True,
            "text": final_text,
            "audit": audit,
            "drafts": list(self._drafts.values())[-10:],
        }

    def draft_from_anomaly(self, alert: Dict[str, Any]) -> Dict[str, Any]:
        """Edge-trigger helper: ask model to draft only (no send)."""
        prompt = (
            "An anomaly was newly detected. Draft ONE mesh alert using draft_mesh_alert. "
            "Do not call request_send_broadcast.\n"
            f"anomaly={json.dumps(alert, ensure_ascii=False)}"
        )
        return self.run(prompt)
