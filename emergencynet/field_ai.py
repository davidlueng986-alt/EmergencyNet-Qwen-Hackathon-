"""Field-side LLM via Qwen Cloud (qwen3.7-plus).

Optional AI for notes review and tactical synthesis. Deterministic triage
never depends on this module. Offline / missing API key → empty suggestions
or table-only tactical fallback.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ============================================================================
# v5.3 — Field tactical advisor system prompt + mixin
# ============================================================================

_TACTICAL_SYSTEM_PROMPT = """\
You are a field tactical medical advisor for disaster triage. A deterministic
engine has already assigned a triage tag (RED/YELLOW/GREEN/BLACK) and may have
flagged hidden risks (Q5 crush, Q6 occult bleed, Q7 pregnancy, Q8 AMS,
Q9 airway burn, Q10 neurogenic shock, Q11 geriatric head injury, Q12 blast lung).
The operator also provided environment and visible injuries.

Pre-retrieved lookup fragments:
  - care_directives: care notes for risks + injuries
  - equipment_pool: WHITELIST — only output items from here
  - transport_match: transport class baseline — equal or escalate only
  - scene_safety: PPE + perimeter baseline — may add PPE / increase perimeter

Task: synthesize advice for the next 5 minutes.

OUTPUT STRICT JSON (no markdown wrapper, no prose outside JSON):
{
  "tactical_advice": "<2-3 sentences, specific action for this patient>",
  "equipment_needs": [
    {"item": "<EXACT string from equipment_pool>", "qty": <int>, "rationale": "<1 sentence>"}
  ],
  "transport_class": "<exact class from transport_match OR a higher-priority class>",
  "transport_reasoning": "<1 sentence>",
  "safety_note": {
    "ppe": [<list — must include all baseline ppe, may add>],
    "perimeter_m": <int — must be >= baseline>,
    "directive": "<1 sentence>"
  }
}

HARD RULES (the safety filter will reject your output if you violate):
R1. equipment_needs items must EXACTLY match strings in equipment_pool.
    Set membership check enforced. Misspellings, brand names, or invented
    items are silently dropped.
R2. transport_class must be the baseline OR one of:
      walking_or_bus < BLS < ALS < ALS_decon_required < helicopter_if_available
    Special classes allowed any time: refuse_transport_treat_in_place,
    team_withdraw_recall, no_transport_marker_only (BLACK only).
R3. safety_note.ppe must be a SUPERSET of baseline. perimeter_m must be >=.
R4. tactical_advice must reference at least one care_directive. Do not
    invent procedures absent from the directives.
R5. Use exact strings for drug/equipment names (e.g. "TXA 1g IV" not
    "tranexamic acid 1 gram intravenous push").
R6. You see ONLY this one patient. Do not reference other patients.
R7. If care_directives is empty AND visible_injuries is empty, output
    minimal observation-only advice based on triage_tag general directive.
"""

_TRANSPORT_ORDER = {
    "walking_or_bus": 0,
    "BLS": 1,
    "ALS": 2,
    "ALS_decon_required": 3,
    "helicopter_if_available": 4,
}
_TRANSPORT_SPECIAL = {
    "refuse_transport_treat_in_place",
    "team_withdraw_recall",
    "no_transport_marker_only",
}


class TacticalAdvisorMixin:
    """Mixin appended to FieldAI. Adds tactical-advice synthesis path."""

    def _load_field_tables(self, tables_dir: str | Path | None = None):
        if getattr(self, "_care_table", None) is not None:
            return
        if tables_dir is None:
            # Package parent / data/field_tables (not CWD-dependent)
            root = Path(__file__).resolve().parents[1]
            d = root / "data" / "field_tables"
        else:
            d = Path(tables_dir)
        with open(d / "care.json", encoding="utf-8") as f:
            self._care_table = json.load(f)
        with open(d / "equipment.json", encoding="utf-8") as f:
            self._equipment_table = json.load(f)
        with open(d / "transport.json", encoding="utf-8") as f:
            self._transport_table = json.load(f)
        with open(d / "scene_safety.json", encoding="utf-8") as f:
            self._scene_safety_table = json.load(f)

    def lookup_fragments(
        self,
        patient_result: Dict[str, Any],
        environment: str,
        visible_injuries: List[str],
    ) -> Dict[str, Any]:
        self._load_field_tables()
        screening = patient_result.get("screening_answers") or {}
        triage_tag = patient_result.get("triage_tag", "UNKNOWN")

        fired_q_codes = [
            q for q, v in screening.items()
            if q in ("q5", "q6", "q7", "q8", "q9", "q10", "q11", "q12")
            and str(v).lower() == "yes"
        ]

        # 1. CARE DIRECTIVES
        care_entries: List[Dict[str, Any]] = []
        seen_care_keys: set = set()
        for q in fired_q_codes:
            prefix = q.upper() + "_"
            for key, val in self._care_table["entries"].items():
                if key.startswith(prefix) and key not in seen_care_keys:
                    care_entries.append({"key": key, **val})
                    seen_care_keys.add(key)
        for inj in visible_injuries:
            if inj in self._care_table["entries"] and inj not in seen_care_keys:
                care_entries.append({"key": inj, **self._care_table["entries"][inj]})
                seen_care_keys.add(inj)
        tag_key = f"{triage_tag}_general"
        if tag_key in self._care_table["entries"] and tag_key not in seen_care_keys:
            care_entries.append({"key": tag_key, **self._care_table["entries"][tag_key]})
            seen_care_keys.add(tag_key)

        # 2. EQUIPMENT POOL (WHITELIST)
        equip_pool: List[Dict[str, Any]] = []
        seen_items: set = set()

        def _add_equip_for(key: str):
            for item in self._equipment_table["entries"].get(key, []):
                name = item.get("item", "")
                if name and name not in seen_items:
                    equip_pool.append(item)
                    seen_items.add(name)

        for q in fired_q_codes:
            prefix = q.upper() + "_"
            for key in self._equipment_table["entries"]:
                if key.startswith(prefix):
                    _add_equip_for(key)
        for inj in visible_injuries:
            _add_equip_for(inj)
        _add_equip_for(tag_key)

        # 3. TRANSPORT MATCH
        transport_match = None
        for rule in self._transport_table["rules"]:
            m = rule.get("match", {})
            if "triage_tag" in m and m["triage_tag"] != triage_tag:
                continue
            if "any_risk" in m:
                wanted = [q.lower() for q in m["any_risk"]]
                if not any(q in fired_q_codes for q in wanted):
                    continue
            if "environment" in m:
                env_list = m["environment"] if isinstance(m["environment"], list) \
                    else [m["environment"]]
                matched = any(
                    env == environment or environment.startswith(env + "_")
                    for env in env_list
                )
                if not matched:
                    continue
            if "any_injury" in m:
                if not any(inj in visible_injuries for inj in m["any_injury"]):
                    continue
            transport_match = {
                "id": rule.get("id", "?"),
                "class": rule["class"],
                "reasoning": rule.get("reasoning", ""),
                "ref_category": rule.get("ref_category", ""),
            }
            break

        if transport_match is None:
            transport_match = {
                "id": "fallback",
                "class": "BLS",
                "reasoning": "No rule matched. Manual review recommended.",
                "ref_category": "Defensive default",
            }

        # 4. SCENE SAFETY
        scene = self._scene_safety_table["entries"].get(environment)
        if scene is None and environment.startswith("chemical_known"):
            scene = self._scene_safety_table["entries"].get("chemical_suspected")
        if scene is None:
            scene = self._scene_safety_table["entries"].get("clear", {
                "ppe": [], "perimeter_m": 0,
                "directive": "Standard scene safety.",
                "ref_category": "",
            })

        return {
            "care_directives": care_entries,
            "equipment_pool": equip_pool,
            "transport_match": transport_match,
            "scene_safety": scene,
        }

    def build_tactical_prompt(
        self,
        patient_result: Dict[str, Any],
        environment: str,
        visible_injuries: List[str],
        fragments: Dict[str, Any],
    ) -> str:
        screening = patient_result.get("screening_answers") or {}
        fired_qs = [q.upper() for q, v in screening.items()
                    if str(v).lower() == "yes"]
        risks = patient_result.get("hidden_risks") or []
        risk_names = [r.get("risk", "?") for r in risks]
        rationale = patient_result.get("rationale") or []

        if fragments["care_directives"]:
            care_lines = []
            for c in fragments["care_directives"]:
                care_lines.append(f"  - [{c['key']}]")
                care_lines.append(f"    directive: {c.get('directive', '')}")
                if c.get('do_not'):
                    care_lines.append(f"    do NOT: {'; '.join(c['do_not'])}")
                if c.get('ref_category'):
                    care_lines.append(f"    ref: {c['ref_category']}")
            care_str = "\n".join(care_lines)
        else:
            care_str = "  (no specific directives — use triage_tag general care)"

        if fragments["equipment_pool"]:
            equip_str = "\n".join(
                f"  - {e['item']} (qty {e['qty']}) — {e.get('rationale', '')}"
                for e in fragments["equipment_pool"]
            )
        else:
            equip_str = "  (empty pool — keep equipment_needs empty)"

        tm = fragments["transport_match"]
        transport_str = (
            f"  baseline_class: {tm['class']}\n"
            f"  reasoning: {tm['reasoning']}\n"
            f"  ref: {tm.get('ref_category', '')}"
        )

        sc = fragments["scene_safety"]
        scene_str = (
            f"  baseline_ppe: {sc.get('ppe', [])}\n"
            f"  baseline_perimeter_m: {sc.get('perimeter_m', 0)}\n"
            f"  baseline_directive: {sc.get('directive', '')}\n"
            f"  ref: {sc.get('ref_category', '')}"
        )

        return (
            f"PATIENT (from deterministic triage engine):\n"
            f"  triage_tag: {patient_result.get('triage_tag', 'UNKNOWN')}\n"
            f"  fired_screening_questions: {fired_qs}\n"
            f"  hidden_risks_named: {risk_names}\n"
            f"  engine_rationale: {rationale}\n"
            f"\n"
            f"OPERATOR ADDITIONAL INPUT:\n"
            f"  environment: {environment}\n"
            f"  visible_injuries: {visible_injuries}\n"
            f"\n"
            f"PRE-RETRIEVED FRAGMENTS (from local JSON lookup tables):\n"
            f"\n"
            f"care_directives:\n{care_str}\n"
            f"\n"
            f"equipment_pool (WHITELIST — equipment_needs items must come from here):\n{equip_str}\n"
            f"\n"
            f"transport_match (BASELINE — your transport_class must equal or escalate):\n{transport_str}\n"
            f"\n"
            f"scene_safety (BASELINE — your safety_note.ppe must contain all baseline_ppe, perimeter_m >= baseline):\n{scene_str}\n"
        )

    def _chat_with_system(self, system_prompt: str, user_prompt: str) -> str:
        """Like chat() but with custom system prompt (Qwen Cloud)."""
        return self.chat(
            user_prompt,
            temperature=0.0,
            system=system_prompt,
        )

    def filter_tactical_response(
        self,
        raw_response: str,
        fragments: Dict[str, Any],
        triage_tag: str,
    ) -> Optional[Dict[str, Any]]:
        text = raw_response.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        try:
            start = text.index("{")
            depth = 0
            parsed = None
            for j in range(start, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        parsed = json.loads(text[start:j + 1])
                        break
            if parsed is None:
                return None
        except (ValueError, json.JSONDecodeError):
            return None

        # Equipment whitelist
        whitelist = {e["item"] for e in fragments["equipment_pool"]}
        raw_equip = parsed.get("equipment_needs", [])
        if not isinstance(raw_equip, list):
            raw_equip = []
        clean_equipment: List[Dict[str, Any]] = []
        for item in raw_equip:
            if not isinstance(item, dict):
                continue
            name = str(item.get("item", "")).strip()
            if name not in whitelist:
                continue
            try:
                qty = int(item.get("qty", 1))
            except (ValueError, TypeError):
                qty = 1
            clean_equipment.append({
                "item": name,
                "qty": max(1, qty),
                "rationale": str(item.get("rationale", ""))[:200],
            })

        # Transport class
        proposed_tc = str(parsed.get("transport_class", "")).strip()
        baseline_tc = fragments["transport_match"]["class"]
        if proposed_tc == baseline_tc:
            final_tc = proposed_tc
        elif proposed_tc in _TRANSPORT_SPECIAL:
            if (proposed_tc == "no_transport_marker_only"
                    and triage_tag != "BLACK"):
                final_tc = baseline_tc
            else:
                final_tc = proposed_tc
        elif proposed_tc in _TRANSPORT_ORDER and baseline_tc in _TRANSPORT_ORDER:
            if _TRANSPORT_ORDER[proposed_tc] >= _TRANSPORT_ORDER[baseline_tc]:
                final_tc = proposed_tc
            else:
                final_tc = baseline_tc
        else:
            final_tc = baseline_tc

        # Safety note: PPE superset, perimeter increase-only
        safety_in = parsed.get("safety_note") or {}
        baseline_ppe = list(fragments["scene_safety"].get("ppe", []))
        proposed_ppe_raw = safety_in.get("ppe", [])
        if not isinstance(proposed_ppe_raw, list):
            proposed_ppe_raw = []
        final_ppe = list(baseline_ppe)
        for item in proposed_ppe_raw:
            if isinstance(item, str) and item not in final_ppe:
                final_ppe.append(item)
        baseline_perim = int(fragments["scene_safety"].get("perimeter_m", 0))
        try:
            proposed_perim = int(safety_in.get("perimeter_m", baseline_perim))
        except (ValueError, TypeError):
            proposed_perim = baseline_perim
        final_perim = max(baseline_perim, proposed_perim)
        safety_clean = {
            "ppe": final_ppe,
            "perimeter_m": final_perim,
            "directive": str(safety_in.get("directive",
                fragments["scene_safety"].get("directive", "")))[:200],
        }

        return {
            "tactical_advice": str(parsed.get("tactical_advice", "")).strip()[:600],
            "equipment_needs": clean_equipment,
            "transport_class": final_tc,
            "transport_reasoning": str(parsed.get("transport_reasoning", "")).strip()[:200],
            "safety_note": safety_clean,
        }

    def generate_tactical_advice(
        self,
        patient_result: Dict[str, Any],
        environment: str = "clear",
        visible_injuries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        visible_injuries = visible_injuries or []
        triage_tag = patient_result.get("triage_tag", "UNKNOWN")

        fragments = self.lookup_fragments(
            patient_result, environment, visible_injuries
        )
        user_prompt = self.build_tactical_prompt(
            patient_result, environment, visible_injuries, fragments
        )
        raw = self._chat_with_system(_TACTICAL_SYSTEM_PROMPT, user_prompt)

        if not raw:
            return self._tactical_fallback(fragments, triage_tag,
                                           reason="LLM unavailable")
        clean = self.filter_tactical_response(raw, fragments, triage_tag)
        if clean is None:
            return self._tactical_fallback(fragments, triage_tag,
                                           reason="LLM output unparseable")

        clean["_provenance"] = {
            "llm_model": self.model,
            "llm_latency_ms": self._last_latency_ms,
            "tables_used": [c["key"] for c in fragments["care_directives"]],
            "whitelist_size": len(fragments["equipment_pool"]),
            "baseline_transport_class": fragments["transport_match"]["class"],
            "baseline_perimeter_m": fragments["scene_safety"].get("perimeter_m", 0),
            "baseline_ppe_count": len(fragments["scene_safety"].get("ppe", [])),
            "fallback_reason": None,
        }
        return clean

    def _tactical_fallback(
        self,
        fragments: Dict[str, Any],
        triage_tag: str,
        reason: str,
    ) -> Dict[str, Any]:
        care = fragments.get("care_directives", [])
        advice_lines = [c.get("directive", "") for c in care[:3]]
        tactical = " ".join(advice_lines)[:600] or \
            f"({triage_tag}) Follow standard triage protocol. " \
            f"Re-assess vitals per tag-standard interval."

        return {
            "tactical_advice": f"(LLM offline) {tactical}",
            "equipment_needs": fragments.get("equipment_pool", [])[:6],
            "transport_class": fragments["transport_match"]["class"],
            "transport_reasoning": fragments["transport_match"]["reasoning"],
            "safety_note": {
                "ppe": list(fragments["scene_safety"].get("ppe", [])),
                "perimeter_m": fragments["scene_safety"].get("perimeter_m", 0),
                "directive": fragments["scene_safety"].get("directive", ""),
            },
            "_provenance": {
                "llm_model": "(offline)",
                "llm_latency_ms": None,
                "tables_used": [c["key"] for c in care],
                "fallback_reason": reason,
            },
        }


class FieldAI(TacticalAdvisorMixin):
    """Field LLM via Qwen Cloud (default model: qwen3.7-plus).

    llama.cpp / Gemma local endpoints are **not** used. All traffic goes
    through ``QwenClient`` → DashScope OpenAI-compatible Chat Completions.
    """

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_sec: float | None = None,
        max_tokens: int | None = None,
        client: Optional[Any] = None,
        api_key: str | None = None,
        config: Optional[Any] = None,
    ):
        from .ai_config import chat_completions_url, load_ai_config
        from .qwen_client import QwenClient

        # Reject leftover llama.cpp / local defaults if caller still passes them
        if endpoint and _is_legacy_local_endpoint(endpoint):
            endpoint = None

        cfg = config or load_ai_config()
        cfg = cfg.with_overrides(
            api_key=api_key,
            base_url=endpoint,
            model_field=model,
        )
        self.config = cfg
        self.endpoint = chat_completions_url(cfg.base_url)
        self.model = model or cfg.model_field
        self.timeout_sec = timeout_sec if timeout_sec is not None else cfg.timeout_sec
        self.max_tokens = max_tokens if max_tokens is not None else min(cfg.max_tokens, 1024)
        self._client = client or QwenClient(cfg)
        self._last_latency_ms: Optional[float] = None
        self._last_error: Optional[str] = None
        self._care_table = None
        self._equipment_table = None
        self._transport_table = None
        self._scene_safety_table = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def available(self) -> bool:
        """True if API key is configured (network not probed deeply)."""
        return self._client.available()

    def ping(self) -> tuple[bool, str]:
        """Live Qwen Cloud round-trip. Returns (ok, detail)."""
        if not self.available():
            return False, (
                "No API key. Set DASHSCOPE_API_KEY (or QWEN_API_KEY) in the "
                "environment, put it in emergencynet_v5/.env, or enter it in "
                "Settings and click Apply."
            )
        text = self._client.chat_text(
            "Reply with exactly: pong",
            system="You are a connectivity probe. Reply with exactly: pong",
            model=self.model,
            enable_thinking=False,
            json_mode=False,
        )
        self._last_latency_ms = self._client.last_latency_ms
        self._last_error = self._client.last_error
        if not text:
            err = self._last_error or "empty response"
            return False, f"Qwen call failed: {err} (url={self.endpoint}, model={self.model})"
        ms = self._last_latency_ms
        latency = f"{ms:.0f} ms" if ms is not None else "?"
        return True, (
            f"OK — Qwen Cloud reachable ({latency}). "
            f"model=`{self.model}` url=`{self.endpoint}` reply={text[:80]!r}"
        )

    @property
    def last_latency_ms(self) -> Optional[float]:
        return self._last_latency_ms if self._last_latency_ms is not None else self._client.last_latency_ms

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error or self._client.last_error

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------
    def chat(
        self,
        prompt: str,
        temperature: float = 0.0,
        system: Optional[str] = None,
    ) -> str:
        """Send a single prompt; return assistant text or \"\" on failure."""
        sys_msg = system or (
            "You are a disaster triage screening reviewer. "
            "Output JSON only. Never invent symptoms not in the notes."
        )
        # Non-thinking + structured JSON when prompt asks for JSON
        want_json = "json" in (sys_msg + prompt).lower()
        text = self._client.chat_text(
            prompt,
            system=sys_msg if "json" in sys_msg.lower() else (
                sys_msg + " Output JSON only." if want_json else sys_msg
            ),
            model=self.model,
            enable_thinking=False,
            json_mode=want_json,
        )
        self._last_latency_ms = self._client.last_latency_ms
        self._last_error = self._client.last_error
        return text or ""

    # ------------------------------------------------------------------
    # Compatibility callable
    # ------------------------------------------------------------------
    def as_callable(self) -> Callable[[str], str]:
        return self.chat


def _is_legacy_local_endpoint(endpoint: str) -> bool:
    """True for old Gemma/llama.cpp localhost URLs that must not be used."""
    e = (endpoint or "").strip().lower()
    if not e:
        return False
    if "127.0.0.1:8080" in e or "localhost:8080" in e:
        return True
    if "11434" in e:  # Ollama default
        return True
    if e.endswith("/v1/chat/completions") and (
        "127.0.0.1" in e or "localhost" in e
    ):
        return True
    return False


# Module-level convenience: a singleton with default settings used by the UI.
_default: Optional[FieldAI] = None


def get_default() -> FieldAI:
    global _default
    if _default is None:
        _default = FieldAI()
    return _default


def reset_default() -> None:
    global _default
    _default = None
