"""Base-station strategy advisor — v5.3 (no RAG, snapshot-injection).

Uses Qwen Cloud ``qwen3.7-max`` with thinking. Snapshot injection only
(no runtime Chroma RAG). Output is 5-field structured JSON for the
base dashboard. Thinking content is handled by the client / parse path.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional
from urllib import request, error

DEFAULT_MODEL = "qwen3.7-max"
# Historical alias (unused on live path; thinking via enable_thinking)
THINK_TOKEN = "<|think|>"
GEMMA4_THINK_TOKEN = THINK_TOKEN  # backward-compat import name


_ADVISOR_SYSTEM_PROMPT = """\
You are the Strategic Advisor AI for EmergencyNet, serving the Base
Incident Commander. EmergencyNet is an offline-first disaster medical triage
system for weak/no cellular conditions. TWO primary tiers in this fork:

  Field: OnePlus Pad / PC — deterministic Python triage (12-Q START + 8
         hidden-risk rules). Optional Qwen Cloud: notes review (escalate-only),
         direct multilingual review, vision, tactical synthesis (qwen3.7-plus).
  Base:  PC (+ optional LoRa gateway) — aggregates patients, anomaly detection,
         YOU (qwen3.7-max) for strategy, and a separate tool agent for mesh
         alert DRAFTS (human Approve to send — not automatic).

YOUR ROLE — Strategic Decision Support

The Commander asks YOU when they need organized analysis of aggregate
state. You DO NOT make decisions. You DO NOT trigger broadcasts. You DO
NOT modify triage tags. You provide structured analysis that supports
the Commander's judgment.

INPUTS YOU RECEIVE:
  - SITUATION SNAPSHOT (auto-injected, structured):
    * Patient count by triage tag (RED/YELLOW/GREEN/BLACK)
    * Hidden risks fired across patients (Q5..Q12 counts)
    * Active anomalies from the deterministic detector
    * Recent broadcasts (last 3)
    * Elapsed time since incident start
  - COMMANDER QUESTION (free text, may be empty for SITREP-only request)

OUTPUT STRICT JSON (no markdown wrapper, no prose outside):
{
  "summary": "<1-3 sentence direct answer>",
  "key_findings": ["<top 3-5 things commander should know>"],
  "recommended_actions": [
    {"action": "<concrete>", "priority": "high|medium|low", "rationale": "<1 sentence>"}
  ],
  "things_to_watch": ["<emerging patterns>"],
  "uncertainty_notes": "<what you don't know — be explicit>"
}

HARD RULES:
R1. Never invent patient counts, anomalies, or broadcasts not in the snapshot.
    If you don't have data, say so in uncertainty_notes.
R2. Never recommend modifying triage tags. They are deterministic.
    Recommend "request clinician re-assessment" if uncertain.
R3. Never recommend auto-firing a broadcast. Recommend the Commander
    DRAFT one — the Commander uses the on-demand broadcast UI which
    has its own deterministic rate-limit gate.
R4. Cite protocols at CATEGORY level, not specific guide numbers, unless
    you are confident. "Per general MCI scene-safety practice" >
    "Per WHO MCM Section 22.3" if you don't know Section 22.3 specifically.
R5. Brevity. Commander is under stress. summary <= 60 words.
R6. If snapshot shows zero patients and zero anomalies, summary should
    acknowledge "no incident data yet" rather than confabulate.
"""


class StrategyAI:
    """Snapshot-injection advisor via Qwen Cloud (default qwen3.7-max + thinking)."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_sec: float | None = None,
        client=None,
        api_key: str | None = None,
    ):
        from .ai_config import chat_completions_url, load_ai_config
        from .field_ai import _is_legacy_local_endpoint
        from .qwen_client import QwenClient

        if endpoint and _is_legacy_local_endpoint(endpoint):
            endpoint = None
        cfg = load_ai_config()
        cfg = cfg.with_overrides(api_key=api_key, base_url=endpoint, model_field=model)
        self.endpoint = chat_completions_url(cfg.base_url)
        self.model = model or cfg.model_strategy or DEFAULT_MODEL
        self.timeout_sec = timeout_sec if timeout_sec is not None else max(cfg.timeout_sec, 120.0)
        self._client = client or QwenClient(cfg)
        self._last_latency_ms: Optional[float] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Snapshot extraction — pure Python from gateway state
    # ------------------------------------------------------------------
    @staticmethod
    def build_situation_snapshot(
        gateway,
        broadcaster=None,
        incident_start_ts: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Read live state from BaseGateway + MeshAlertBroadcaster, return
        structured dict ready for prompt assembly. Pure data extraction —
        no LLM call, no I/O."""
        snap = gateway.snapshot()
        patients = snap.get("patients", [])

        tag_counts = {"RED": 0, "YELLOW": 0, "GREEN": 0, "BLACK": 0}
        for p in patients:
            tag = p.get("triage_tag", "UNKNOWN")
            if tag in tag_counts:
                tag_counts[tag] += 1

        risk_counts: Dict[str, int] = {}
        for p in patients:
            # Wire patients store hidden_risk_qs (not risk_flags)
            flags = p.get("hidden_risk_qs") or p.get("risk_flags") or []
            for q in flags:
                key = q if isinstance(q, str) else str(q)
                risk_counts[key] = risk_counts.get(key, 0) + 1

        anomalies: List[Dict[str, Any]] = []
        detector = getattr(gateway, "detector", None)
        if detector is not None:
            try:
                anomalies = detector.evaluate()
            except Exception:
                anomalies = []

        recent_broadcasts: List[Dict[str, Any]] = []
        if broadcaster is not None:
            try:
                log = broadcaster.sent_log()[-3:]
                for e in log:
                    recent_broadcasts.append({
                        "ts": e.get("ts"),
                        "severity": e.get("severity"),
                        "anomaly_type": e.get("anomaly_type", "?"),
                        "text_preview": (e.get("text") or "")[:120],
                    })
            except Exception:
                pass

        if incident_start_ts:
            elapsed_sec = int(time.time() - incident_start_ts)
        else:
            elapsed_sec = 0
        elapsed_str = f"T+{elapsed_sec // 60:02d}:{elapsed_sec % 60:02d}"

        return {
            "elapsed_sec": elapsed_sec,
            "elapsed_str": elapsed_str,
            "patient_count": len(patients),
            "tag_counts": tag_counts,
            "hidden_risks_fired": risk_counts,
            "disagreement_count": 0,  # shadow inference removed from product
            "active_anomalies": anomalies,
            "recent_broadcasts": recent_broadcasts,
        }

    # ------------------------------------------------------------------
    # Prompt assembly — user message body
    # ------------------------------------------------------------------
    def build_advisor_user_prompt(
        self,
        snapshot: Dict[str, Any],
        commander_question: str,
    ) -> str:
        tag_summary = ", ".join(
            f"{tag}={n}" for tag, n in snapshot["tag_counts"].items() if n > 0
        ) or "(no patients yet)"

        if snapshot["hidden_risks_fired"]:
            risk_summary = ", ".join(
                f"{q.upper()}={n}"
                for q, n in snapshot["hidden_risks_fired"].items()
            )
        else:
            risk_summary = "(none)"

        if snapshot["active_anomalies"]:
            anomaly_lines = [
                f"  - {a['type']} ({a['severity']}): {a.get('message', '')}"
                for a in snapshot["active_anomalies"]
            ]
            anomaly_summary = "\n".join(anomaly_lines)
        else:
            anomaly_summary = "  (none active)"

        if snapshot["recent_broadcasts"]:
            broadcast_lines = [
                f"  - [{b['severity']}] {b['anomaly_type']}: {b['text_preview']}"
                for b in snapshot["recent_broadcasts"]
            ]
            broadcast_summary = "\n".join(broadcast_lines)
        else:
            broadcast_summary = "  (none in window)"

        question = (commander_question or "").strip()
        if not question:
            question = "(no specific question — provide a brief SITREP based on snapshot)"

        return (
            f"SITUATION SNAPSHOT (elapsed {snapshot['elapsed_str']}):\n"
            f"  Patient count: {snapshot['patient_count']}\n"
            f"  Triage tags:   {tag_summary}\n"
            f"  Hidden risks:  {risk_summary}\n"
            f"  Active anomalies:\n{anomaly_summary}\n"
            f"  Recent broadcasts (last 3):\n{broadcast_summary}\n"
            f"\n"
            f"COMMANDER QUESTION:\n"
            f"  {question}\n"
        )

    # ------------------------------------------------------------------
    # Public entry — top-level advise()
    # ------------------------------------------------------------------
    def advise(
        self,
        gateway=None,
        broadcaster=None,
        commander_question: str = "",
        incident_start_ts: Optional[float] = None,
        snapshot_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Top-level advisor call.

        Args:
            gateway: BaseGateway (live state source)
            broadcaster: MeshAlertBroadcaster (recent broadcasts source)
            commander_question: free-text from UI
            incident_start_ts: optional absolute ts for elapsed calc
            snapshot_override: for tests — supply a pre-built snapshot

        Returns 5-field dict + _provenance.
        """
        if snapshot_override is not None:
            snapshot = snapshot_override
        elif gateway is not None:
            snapshot = self.build_situation_snapshot(
                gateway, broadcaster, incident_start_ts
            )
        else:
            raise ValueError("Need gateway or snapshot_override")

        user_prompt = self.build_advisor_user_prompt(snapshot, commander_question)
        raw = self._call_llm(_ADVISOR_SYSTEM_PROMPT, user_prompt)

        if not raw:
            return self._fallback(snapshot, "LLM unavailable")

        parsed = self._parse(raw)
        if parsed is None:
            return self._fallback(snapshot, "LLM output unparseable")

        parsed["_provenance"] = {
            "llm_model": self.model,
            "llm_latency_ms": self._last_latency_ms,
            "thinking_mode_used": True,
            "snapshot_summary": {
                "patient_count": snapshot["patient_count"],
                "tag_counts": snapshot["tag_counts"],
                "anomaly_count": len(snapshot["active_anomalies"]),
            },
            "fallback_reason": None,
        }
        return parsed

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        # Thinking + JSON: chat_json enables json_object and repairs via
        # official two-step workaround if needed (see qwen_client.chat_json).
        sys = system_prompt
        if "json" not in sys.lower():
            sys = sys + "\nOutput STRICT JSON only."
        messages = [
            {"role": "system", "content": sys},
            {"role": "user", "content": user_prompt},
        ]
        resp = self._client.chat_json(
            messages,
            model=self.model,
            enable_thinking=True,
        )
        self._last_latency_ms = resp.latency_ms
        self._last_error = resp.error
        if not resp.ok:
            return ""
        return resp.content or ""

    # ------------------------------------------------------------------
    # Parse strict JSON + strip thinking trace
    # ------------------------------------------------------------------
    def _parse(self, raw: str) -> Optional[Dict[str, Any]]:
        text = re.sub(
            r"<\|channel\|?>\s*thought.*?<\|?channel\|>",
            "", raw, flags=re.DOTALL,
        )
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        try:
            start = text.index("{")
            depth = 0
            for j in range(start, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        obj = json.loads(text[start:j + 1])
                        break
            else:
                return None
        except (ValueError, json.JSONDecodeError):
            return None

        return {
            "summary": str(obj.get("summary", ""))[:600],
            "key_findings": [str(x)[:300] for x in (obj.get("key_findings") or [])[:7]],
            "recommended_actions": self._normalize_actions(
                obj.get("recommended_actions") or []
            ),
            "things_to_watch": [str(x)[:300] for x in (obj.get("things_to_watch") or [])[:5]],
            "uncertainty_notes": str(obj.get("uncertainty_notes", ""))[:400],
        }

    @staticmethod
    def _normalize_actions(raw_list: List[Any]) -> List[Dict[str, str]]:
        out = []
        for a in raw_list[:7]:
            if not isinstance(a, dict):
                continue
            prio = str(a.get("priority", "medium")).lower()
            if prio not in ("high", "medium", "low"):
                prio = "medium"
            out.append({
                "action": str(a.get("action", ""))[:300],
                "priority": prio,
                "rationale": str(a.get("rationale", ""))[:200],
            })
        return out

    # ------------------------------------------------------------------
    # Offline fallback
    # ------------------------------------------------------------------
    def _fallback(self, snapshot: Dict[str, Any], reason: str) -> Dict[str, Any]:
        anomaly_types = [a["type"] for a in snapshot["active_anomalies"]]
        tag_counts = snapshot["tag_counts"]
        red = tag_counts.get("RED", 0)
        yel = tag_counts.get("YELLOW", 0)

        findings = []
        if red > 0:
            findings.append(f"{red} RED, {yel} YELLOW currently tracked")
        for a in snapshot["active_anomalies"]:
            findings.append(f"{a['type']} anomaly active ({a['severity']})")
        if not findings:
            findings.append("Snapshot empty — awaiting Field input")

        return {
            "summary": f"(LLM offline — {reason}) Showing snapshot summary only.",
            "key_findings": findings,
            "recommended_actions": [],
            "things_to_watch": anomaly_types,
            "uncertainty_notes": (
                f"LLM advisor unavailable. Snapshot reflects state at "
                f"{snapshot['elapsed_str']}. No strategic analysis available "
                f"until LLM is reachable."
            ),
            "_provenance": {
                "llm_model": "(offline)",
                "llm_latency_ms": None,
                "fallback_reason": reason,
            },
        }
