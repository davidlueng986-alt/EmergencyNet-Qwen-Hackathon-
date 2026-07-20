"""Function-calling action engine.

Glue layer between ``anomaly_detector`` (deterministic) and the base AI
(LLM, function-calling). Architectural rule:

    The anomaly detector decides which event types may produce a draft.
    A human remains the only authority that can approve transmission.

    The ACTION CONTENT (alert message text) is LLM-generated via
    Qwen Cloud function-calling. The LLM receives the anomaly
    context and any retrieved RAG chunks, and returns a structured
    JSON action with the message body it wants broadcast.

This separation means:
  - A misbehaving LLM cannot autonomously transmit a broadcast.
  - The LLM helps craft a concise operational draft.
  - Draft provenance and the configured transport result are auditable.

Function schema we expose to the LLM (OpenAI-compatible tools array):

    compose_mesh_alert(
        severity:        "critical" | "high" | "info",
        anomaly_type:    str,
        message_body:    str (<=180 chars, UTF-8),
    ) -> {sent: bool, ts: float, ...}
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Static draft policy — deterministic
# ---------------------------------------------------------------------------
# Anomaly types that may produce an AI draft. Nothing here authorises a send.
# Soft allowlist: anomaly types that may auto-DRAFT (never auto-send).
# Severity is AI-determined; exact severity match is NOT required (KI-26).
DRAFTABLE_ANOMALY_TYPES = frozenset({
    "RED_SURGE",
    "CRUSH_CLUSTER",
    "RESP_CLUSTER",
    "BURN_CLUSTER",
})

# Deprecated name kept for imports; values ignored for exact-match gating.
BROADCAST_POLICY: Dict[str, str] = {
    "RED_SURGE":     "critical",
    "CRUSH_CLUSTER": "critical",
    "RESP_CLUSTER":  "high",
    "BURN_CLUSTER":  "high",
}


# ---------------------------------------------------------------------------
# Function schema given to the LLM (OpenAI tools-array; Qwen Cloud compatible).
# ---------------------------------------------------------------------------
COMPOSE_ALERT_TOOL = {
    "type": "function",
    "function": {
        "name": "compose_mesh_alert",
        "description": (
            "Compose a single LoRa-mesh broadcast alert for incident "
            "command. The system will deliver this text over Meshtastic to "
            "every commander tablet in range. Keep message_body under 180 "
            "characters. Keep the body self-contained; do not add citations."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "info"],
                    "description": "Match the anomaly severity provided.",
                },
                "anomaly_type": {
                    "type": "string",
                    "description": "Echo the anomaly type, e.g. RED_SURGE.",
                },
                "message_body": {
                    "type": "string",
                    "maxLength": 180,
                    "description": (
                        "Concrete actionable line. Examples: 'Activate "
                        "MCM L3, request USAR & 4 BLS units, suspect "
                        "structural collapse', or 'Suspect chemical "
                        "exposure, Level B PPE for entry, halt downwind "
                        "treatment within 200 m'."
                    ),
                },
            },
            "required": ["severity", "anomaly_type", "message_body"],
        },
    },
}


# ---------------------------------------------------------------------------
# v5.3 — On-demand broadcast composer system prompt
# ---------------------------------------------------------------------------
_BROADCAST_COMPOSER_SYSTEM_PROMPT = """\
You are the Mesh Broadcast Composer for EmergencyNet. The Base Incident
Commander has typed an INTENT in plain language. Your job: turn it into a
single LoRa-mesh text alert. The deterministic anomaly detector has NOT
triggered this — it's human-initiated.

YOU MUST call the function compose_mesh_alert exactly once. Schema:

  compose_mesh_alert(
    severity: "critical" | "high" | "info",
    anomaly_type: str,      # short type tag — e.g. TEAM_WITHDRAW, RESOURCE_REQ
    message_body: str       # <=180 UTF-8 chars (CJK counts more)
  )

HARD RULES:

R1. message_body MUST be <= 180 UTF-8 bytes. Be brutally concise.

R2. severity:
      "critical" = immediate life-safety; all teams must act now
      "high"     = important coordination; act in minutes
      "info"     = situational awareness; no immediate action

R3. Do not invent protocol guide numbers. No citation field — keep body self-contained.

R4. message_body MUST be concrete instruction, not editorial:
      GOOD: "T3 withdraw, drift change W. Other teams hold. Reconvene CCP."
      BAD:  "Team 3 should probably consider withdrawing if it's safe..."

R5. Refuse unsafe intents (e.g. ordering LLM autonomous decisions) by
    returning:
      severity = "info"
      anomaly_type = "DRAFT_REJECTED"
      message_body = "Cannot draft this — <one-line reason>. Please revise."

R6. Never fabricate facts not in the intent or sitrep.
"""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class ActionEngine:
    """Bridges anomaly_detector outputs to the mesh broadcaster.

    Inject:
      - base_ai_call: function(prompt: str, tools: list) -> str
                      raw model response that may contain a tool_calls
                      block. This is what BaseAI.chat() will look like
                      after the small extension in base_ai.py.
      - rag:          optional RAGStore for grounding context
      - broadcaster:  MeshAlertBroadcaster instance
    """

    def __init__(
        self,
        base_ai_call: Callable[[str, List[Dict[str, Any]]], str],
        broadcaster,
        rag=None,
    ):
        self._base_call = base_ai_call
        self._broadcaster = broadcaster
        self._rag = rag
        self._action_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Main entry — feed in anomaly_detector.evaluate() output
    # ------------------------------------------------------------------
    def process_alerts(
        self,
        alerts: List[Dict[str, Any]],
        sitrep_context: str = "",
    ) -> List[Dict[str, Any]]:
        """For each alert that passes the static draft policy,
        ask the LLM to compose a message and retain it for human review.

        Returns a list of action records (one per processed alert).
        """
        results: List[Dict[str, Any]] = []
        for alert in alerts:
            atype = str(alert.get("type", ""))
            sev = str(alert.get("severity", "")).lower() or "info"
            # Soft allowlist: draftable types only. Severity is free within enum.
            if atype not in DRAFTABLE_ANOMALY_TYPES:
                results.append(self._record(alert, "type-skip", None))
                continue

            composed = self._compose_alert(alert, sitrep_context)
            if composed is None:
                composed = {
                    "severity": sev if sev in ("critical", "high", "info") else "high",
                    "anomaly_type": atype,
                    "message_body": alert.get("message", "")[:180],
                }
            # DRAFT only — human must Approve to send (no auto-broadcast).
            results.append(self._record(alert, "draft", composed, {
                "sent": False,
                "reason": "human_approval_required",
                "text": composed.get("message_body", ""),
            }))
        return results

    # ------------------------------------------------------------------
    # LLM composition
    # ------------------------------------------------------------------
    def _compose_alert(
        self,
        alert: Dict[str, Any],
        sitrep_context: str,
    ) -> Optional[Dict[str, Any]]:
        prompt = self._build_compose_prompt(alert, sitrep_context)
        try:
            raw = self._base_call(prompt, [COMPOSE_ALERT_TOOL])
        except Exception:
            return None
        if not raw:
            return None
        return _extract_tool_call_args(raw)

    def _build_compose_prompt(
        self,
        alert: Dict[str, Any],
        sitrep_context: str,
    ) -> str:
        rag_block = ""
        if self._rag is not None:
            try:
                cm_chunks = self._rag.query(
                    "command", alert.get("message", ""), k=3,
                )
                hz_chunks = self._rag.query(
                    "hazmat", alert.get("message", ""), k=2,
                )
                rag_block = _format_rag(cm_chunks + hz_chunks)
            except Exception:
                rag_block = ""

        return (
            "You are an Incident Command communications assistant. "
            "Compose a single LoRa-mesh broadcast alert by calling the "
            "compose_mesh_alert function. The alert will reach every "
            "commander tablet within radio range. The mesh has a 200-byte "
            "limit, so keep message_body under 180 characters. Be "
            "concrete and actionable; do not editorialize.\n\n"
            f"Anomaly trigger:\n  type: {alert.get('type')}\n"
            f"  severity: {alert.get('severity')}\n"
            f"  detail: {alert.get('message')}\n"
            f"  matches: {alert.get('matches')}/{alert.get('n')}\n\n"
            f"Sitrep context:\n{sitrep_context or '(none)'}\n\n"
            f"Reference protocols:\n{rag_block or '(no RAG hits)'}\n\n"
            "Now call compose_mesh_alert exactly once."
        )

    @staticmethod
    def _stitch_body(composed: Dict[str, Any]) -> str:
        return (composed.get("message_body", "") or "")[:200]

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------
    def _record(
        self,
        alert: Dict[str, Any],
        outcome: str,
        composed: Optional[Dict[str, Any]],
        send_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rec = {
            "ts": time.time(),
            "alert": alert,
            "outcome": outcome,
            "composed": composed,
            "send_result": send_result,
        }
        self._action_log.append(rec)
        return rec

    def action_log(self) -> List[Dict[str, Any]]:
        return list(self._action_log)

    # ------------------------------------------------------------------
    # v5.3 — commander-on-demand broadcast draft path
    # ------------------------------------------------------------------
    def compose_on_demand(
        self,
        commander_intent: str,
        sitrep: str = "",
    ) -> Dict[str, Any]:
        """Human-initiated broadcast draft. Bypasses BROADCAST_POLICY whitelist
        but the actual MeshAlertBroadcaster.broadcast() retains rate limit +
        UTF-8 truncate.

        Returns composed dict — NOT sent yet, caller decides via UI.
        """
        prompt = (
            f"COMMANDER INTENT:\n  {commander_intent.strip()}\n\n"
            f"SITREP:\n{sitrep or '  (no sitrep provided)'}\n"
        )

        try:
            raw = self._base_call(
                prompt,
                [COMPOSE_ALERT_TOOL],
                system_prompt=_BROADCAST_COMPOSER_SYSTEM_PROMPT,
            )
        except TypeError:
            raw = self._base_call(prompt, [COMPOSE_ALERT_TOOL])

        if not raw:
            return {
                "severity": "info",
                "anomaly_type": "DRAFT_FAILED",
                "message_body": "LLM unavailable. Draft manually before sending.",
                "_provenance": {"fallback_reason": "LLM unavailable"},
            }

        args = _extract_tool_call_args(raw)
        if args is None or not args.get("message_body", "").strip():
            intent = commander_intent.strip()[:160]
            args = {
                "severity": "high",
                "anomaly_type": "COMMANDER_BROADCAST",
                "message_body": intent or "Manual broadcast",
                "_provenance": {
                    "fallback_reason": "LLM empty body",
                    "intent_preview": intent[:120],
                    "human_triggered": True,
                    "policy_gate_bypassed": True,
                },
            }
            return args

        args["_provenance"] = {
            "human_triggered": True,
            "intent_preview": commander_intent[:120],
            "policy_gate_bypassed": True,
            "broadcaster_rate_limit_still_applies": True,
            "fallback_reason": None,
        }
        return args


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_TOOL_CALL_BLOCK = re.compile(r"\{[^{}]*\"name\"\s*:\s*\"compose_mesh_alert\".*?\}",
                              re.DOTALL)


def _extract_tool_call_args(raw: str) -> Optional[Dict[str, Any]]:
    """Pull function-call arguments out of the model response.

    The OpenAI-compatible API returns tool calls in
        choices[0].message.tool_calls[0].function.arguments
    But our base_ai_call returns the raw text body. We accept either:
        - a JSON object containing a tool_calls array (OpenAI shape)
        - a fenced or unfenced JSON object with the tool name + args
        - a plain JSON object matching the args schema directly
    """
    if not raw:
        return None
    raw_strip = raw.strip()
    raw_strip = re.sub(r"^```(?:json)?\s*", "", raw_strip)
    raw_strip = re.sub(r"\s*```$", "", raw_strip)

    # Try OpenAI tool_calls shape first
    try:
        parsed = json.loads(raw_strip)
        if isinstance(parsed, dict):
            tcs = (parsed.get("tool_calls")
                   or parsed.get("message", {}).get("tool_calls"))
            if isinstance(tcs, list) and tcs:
                fn = tcs[0].get("function", {})
                args_raw = fn.get("arguments", "{}")
                if isinstance(args_raw, str):
                    args = json.loads(args_raw)
                else:
                    args = args_raw
                return _normalize_args(args)

            # Direct args shape?
            if "message_body" in parsed:
                return _normalize_args(parsed)
    except json.JSONDecodeError:
        pass

    # Last-ditch — find any object with message_body in the raw text
    m = re.search(r"\{[^{}]*message_body[^{}]*\}", raw_strip, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return _normalize_args(obj)
        except json.JSONDecodeError:
            return None
    return None


def _normalize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(args, dict):
        args = {}
    body = (args.get("message_body") or args.get("text")
            or args.get("body") or args.get("alert_text")
            or args.get("message") or args.get("content") or "")
    sev = str(args.get("severity") or args.get("level") or "info").lower()
    if sev not in ("critical", "high", "info"):
        sev = "info"
    atype = (args.get("anomaly_type") or args.get("type")
             or args.get("category") or "UNKNOWN")
    return {
        "severity": sev,
        "anomaly_type": str(atype).upper().replace(" ", "_"),
        "message_body": str(body)[:180],
    }



def _format_rag(chunks: List[Dict[str, Any]]) -> str:
    if not chunks:
        return ""
    out = []
    for c in chunks[:5]:
        meta = c.get("metadata", {}) or {}
        src = meta.get("source", "?")
        sec = meta.get("section", "?")
        snippet = (c.get("text", "") or "")[:240]
        out.append(f"  - [{src} / {sec}] {snippet}")
    return "\n".join(out)
