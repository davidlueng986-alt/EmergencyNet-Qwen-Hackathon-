"""Base-station Gradio dashboard (Qwen Cloud).

Shows live SITREP, patient list, anomaly alerts, and an Advisor panel
that calls ``StrategyAI`` (qwen3.7-max) on demand. Tool agent drafts
mesh alerts; human Approve required to send.

Designed to be driven by ``BaseGateway`` — the gateway pushes updates
into a shared state via ``handle_decoded``.

v5 additions: Live map (field-team GPS + civilian distress + patient
zones), civilian app intake (HTTPS distress from phones; AI backend is
configured on the civilian app separately).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import gradio as gr

from .gateway import BaseGateway
from .sitrep_generator import build_sitrep
from .strategy_ai import StrategyAI
from .base_ai import BaseAI
from .action_engine import ActionEngine
from .meshtastic_broadcaster import MeshAlertBroadcaster
from .mesh_positions import MeshPositionTracker, attach_to_bridge
from .lora_bridge import MeshtasticBridge
from .civilian_intake import CivilianIntake
from .map_widget import render_map_html


class DashboardState:
    def __init__(self):
        self.gateway = BaseGateway(on_update=self._on_update)
        self.last_update: Dict[str, Any] = {}
        self.advice: Optional[Dict[str, Any]] = None
        self.strategy: Optional[StrategyAI] = None
        self.base_ai: Optional[BaseAI] = None
        self.action_engine: Optional[ActionEngine] = None
        self.tool_agent = None  # BaseToolAgent, set in ensure_action_engine
        self.broadcaster: Optional[MeshAlertBroadcaster] = None
        self.broadcast_log: List[Dict[str, Any]] = []
        # v5: GPS + civilian intake
        self.position_tracker = MeshPositionTracker()
        self.lora_bridge = None
        self.civilian_intake = CivilianIntake(
            on_new_report=self._on_civilian_report,
        )
        self.incident_start_ts: Optional[float] = None

    def _on_update(self, update: Dict[str, Any]) -> None:
        self.last_update = update
        # Edge-trigger: only NEW anomaly types auto-DRAFT (never auto-send)
        new_types = set(update.get("new_anomaly_types") or [])
        alerts = [
            a for a in (update.get("alerts") or [])
            if str(a.get("type", "")) in new_types
        ]
        if alerts and self.action_engine is not None:
            try:
                actions = self.action_engine.process_alerts(
                    alerts, sitrep_context=str(update.get("zone_code", ""))
                )
                self.broadcast_log.extend(actions)
                if len(self.broadcast_log) > 200:
                    self.broadcast_log = self.broadcast_log[-200:]
            except Exception as exc:
                self.broadcast_log.append({"outcome": "error", "error": str(exc)})

    def _on_civilian_report(self, rec: Dict[str, Any]) -> None:
        """Fire when a civilian distress report arrives. Pushed into
        broadcast log so commanders see a single feed."""
        self.broadcast_log.append({
            "outcome": "civilian_distress",
            "incident_id": rec["incident_id"],
            "severity": rec["severity_hint"],
            "summary": rec["summary_en"][:120],
            "delayed": rec.get("queued_offline", False),
            "ts": rec.get("ts"),
        })

    def attach_mesh(self, bridge) -> None:
        """Call once after the LoRa bridge is created so the position
        tracker subscribes to POSITION_APP packets."""
        attach_to_bridge(bridge, self.position_tracker)
    def attach_lora(self) -> None:
        """Read MESHTASTIC_PORT env var; bind MeshtasticBridge if set.
        Supports: COM7 (Win serial), /dev/ttyUSB0 (Linux serial),
                  tcp://192.168.x.x:4403 (WiFi), loopback (no-op)."""
        import os
        port = os.getenv("MESHTASTIC_PORT", "").strip()
        if not port or port == "loopback":
            print("[base_dashboard] MESHTASTIC_PORT not set; LoRa receive DISABLED.")
            return
        if port.startswith("tcp://"):
            host = port[6:].split(":")[0]
            self.lora_bridge = MeshtasticBridge(transport="tcp", host=host)
        else:
            self.lora_bridge = MeshtasticBridge(transport="serial", device=port)
        self.lora_bridge.set_on_packet(self._on_lora_packet)
        self.attach_mesh(self.lora_bridge)
        print(f"[base_dashboard] LoRa receive ENABLED via {port}")

    def _on_lora_packet(self, payload, meta) -> None:
        try:
            result = self.gateway.handle_raw(payload, meta)
            n = result.get("patients_received", 0)
            print(f"[base_dashboard] LoRa rx {len(payload)} bytes "
                  f"from {meta.get('from','?')} rssi={meta.get('rxRssi','?')} "
                  f"-> {n} patient(s) ingested", flush=True)
        except Exception as exc:
            print(f"[base_dashboard] LoRa rx error: {exc}", flush=True)


    def ensure_strategy(self, force: bool = False) -> StrategyAI:
        from .ai_config import load_ai_config, load_dotenv_files
        load_dotenv_files()
        if self.strategy is None or force:
            cfg = load_ai_config()
            self.strategy = StrategyAI(model=cfg.model_strategy)
        return self.strategy

    def ensure_action_engine(self, force: bool = False) -> ActionEngine:
        """Wire up base_ai + broadcaster + action engine (draft path)."""
        from .ai_config import load_ai_config, load_dotenv_files
        from .base_agent import BaseToolAgent
        from .qwen_client import reset_default_client

        load_dotenv_files()
        if self.action_engine is not None and not force:
            return self.action_engine

        reset_default_client()
        cfg = load_ai_config()
        self.base_ai = BaseAI(model=cfg.model_agent, config=cfg)

        def _no_op(text: str) -> bool:
            # KI-02: default stub — records success without radio
            return True

        self.broadcaster = MeshAlertBroadcaster(transport_send_text=_no_op)

        def call_base_ai_with_tools(prompt: str, tools, system_prompt=None) -> str:
            if system_prompt is not None:
                return self.base_ai.chat_with_tools(prompt, tools, system_prompt=system_prompt)
            return self.base_ai.chat_with_tools(prompt, tools)

        self.action_engine = ActionEngine(
            base_ai_call=call_base_ai_with_tools,
            broadcaster=self.broadcaster,
            rag=None,
        )
        self.tool_agent = BaseToolAgent(
            gateway=self.gateway,
            broadcaster=self.broadcaster,
        )
        return self.action_engine


def _render_patient_table(snap: Dict[str, Any]) -> List[List[str]]:
    rows = []
    for p in snap.get("patients", []):
        rows.append([
            str(p.get("patient_id", "?")),
            str(p.get("triage_tag", "?")),
            f"{p.get('confidence', 0):.2f}",
            ",".join(p.get("hidden_risk_qs") or []) or "-",
            ",".join(p.get("injury_types") or []) or "-",
            str(p.get("age", "?")),
        ])
    return rows


def _render_disagreement_table(snap: Dict[str, Any]) -> List[List[str]]:
    rows = []
    for d in snap.get("disagreements", []):
        rows.append([
            str(d.get("patient_id", "?")),
            str(d.get("severity", "?")),
            str(d.get("field_tag", "?")),
            str(d.get("shadow_tag", "?")),
            f"answer-diffs={len(d.get('answer_diffs') or [])}",
        ])
    return rows


def build_dashboard() -> gr.Blocks:
    state = DashboardState()
    state.attach_lora()

    with gr.Blocks(title="EmergencyNet Base Station") as demo:
        gr.Markdown(
            "# EmergencyNet Base Station (Qwen Cloud)\n"
            "Live SITREP, anomaly detection, Strategy Advisor (qwen3.7-max) "
            "+ tool agent drafts (human Approve to send). No field-shadow dual inference."
        )

        with gr.Tab("SITREP"):
            sitrep_md = gr.Markdown("(no packets yet)")
            refresh_btn = gr.Button("Refresh SITREP", variant="primary")

            def _refresh():
                snap = state.gateway.snapshot()
                alerts = state.last_update.get("alerts", [])
                sitrep = build_sitrep(
                    snap.get("patients", []),
                    alerts,
                    snap.get("disagreements", []),
                    zone_breakdown=snap.get("zone_counts"),
                    advice=state.advice,
                )
                return sitrep["markdown"]

            refresh_btn.click(_refresh, outputs=sitrep_md)

        with gr.Tab("Patients"):
            patient_table = gr.Dataframe(
                headers=["ID", "Tag", "Conf", "Risks", "Injuries", "Age"],
                wrap=True,
            )
            refresh_p = gr.Button("Refresh patients")
            refresh_p.click(
                lambda: _render_patient_table(state.gateway.snapshot()),
                outputs=patient_table,
            )

        with gr.Tab("Agent / Drafts"):
            gr.Markdown(
                "BaseToolAgent drafts mesh alerts. **Approve & Send** requires human click."
            )
            agent_q = gr.Textbox(label="Ask agent / describe intent", lines=3)
            agent_btn = gr.Button("Run agent", variant="primary")
            agent_out = gr.Markdown()
            drafts_md = gr.Markdown()
            send_draft_id = gr.Textbox(label="Draft ID to send")
            send_btn = gr.Button("Approve & Send draft", variant="stop")
            send_out = gr.Markdown()

            def _run_agent(q):
                state.ensure_action_engine()
                agent = state.tool_agent
                if agent is None:
                    return "Agent not ready.", ""
                result = agent.run(q or "Assess situation and draft alerts if needed.")
                text = result.get("text", "")
                drafts = result.get("drafts") or []
                dlines = ["### Drafts"]
                for d in drafts[-5:]:
                    dlines.append(
                        f"- `{d.get('draft_id')}` [{d.get('severity')}] "
                        f"{d.get('anomaly_type')}: {d.get('message_body')}"
                    )
                return text, "\n".join(dlines)

            agent_btn.click(_run_agent, inputs=agent_q, outputs=[agent_out, drafts_md])

            def _send_draft(did):
                state.ensure_action_engine()
                agent = state.tool_agent
                if agent is None:
                    return "Agent not armed."
                r = agent._tool_request_send_broadcast(
                    draft_id=(did or "").strip(), human_approved=True,
                )
                return f"Send result: {r}"

            send_btn.click(_send_draft, inputs=send_draft_id, outputs=send_out)

        with gr.Tab("Advisor"):
            sitrep_input = gr.Textbox(
                label="SITREP / question for advisor", lines=4,
                placeholder="e.g. We have 6 burn casualties from a tanker fire. PPE?"
            )
            ask_btn = gr.Button("Ask advisor", variant="primary")
            advisor_md = gr.Markdown()

            def _on_ask(text):
                strat = state.ensure_strategy()
                if state.incident_start_ts is None:
                    state.incident_start_ts = time.time()

                advice = strat.advise(
                    gateway=state.gateway,
                    broadcaster=state.broadcaster,
                    commander_question=text,
                    incident_start_ts=state.incident_start_ts,
                )
                state.advice = advice

                lines = [f"### Summary\n{advice['summary']}"]

                if advice.get("key_findings"):
                    lines.append("\n### Key Findings")
                    for f in advice["key_findings"]:
                        lines.append(f"- {f}")

                if advice.get("recommended_actions"):
                    lines.append("\n### Recommended Actions")
                    lines.append("| Priority | Action | Rationale |")
                    lines.append("|---|---|---|")
                    for a in advice["recommended_actions"]:
                        lines.append(f"| {a['priority'].upper()} | {a['action']} | {a['rationale']} |")

                if advice.get("things_to_watch"):
                    lines.append("\n### Things to Watch")
                    for w in advice["things_to_watch"]:
                        lines.append(f"- {w}")

                if advice.get("uncertainty_notes"):
                    lines.append(f"\n### Uncertainty Notes\n_{advice['uncertainty_notes']}_")

                return "\n".join(lines)

            ask_btn.click(_on_ask, inputs=sitrep_input, outputs=advisor_md)

        with gr.Tab("Inject test packet"):
            gr.Markdown(
                "Paste the exact hex text received through Meshtastic to decode "
                "and ingest the field packet. Remove labels or punctuation."
            )
            hex_in = gr.Textbox(label="Hex packet")
            inject_btn = gr.Button("Inject")
            inject_status = gr.Markdown()

            def _inject(hexstr: str):
                try:
                    payload = bytes.fromhex((hexstr or "").strip())
                except ValueError:
                    return "Invalid hex."
                try:
                    result = state.gateway.handle_raw(payload)
                except Exception as exc:
                    return f"Decode error: {exc}"
                return (
                    f"Decoded {result.get('patients_received')} patients. "
                    f"Alerts={len(result.get('alerts') or [])}."
                )

            inject_btn.click(_inject, inputs=hex_in, outputs=inject_status)

        with gr.Tab("Map"):
            gr.Markdown(
                "Live operations map. **? Blue** = field-team radios "
                "(GPS via Meshtastic mesh). **?? Coloured pins** = civilian "
                "distress reports (severity-coded). **???** = patient "
                "triage zones. Auto-refreshes every 5 seconds."
            )
            map_html = gr.HTML(label="Live Operations Map")
            map_refresh = gr.Button("Refresh map", size="sm")

            def _render_map() -> str:
                # Build patient_zones from the latest patient list (with GPS)
                patient_zones = []
                snap = state.gateway.snapshot()
                for p in snap.get("patients", []) or []:
                    gps = p.get("gps") or p.get("location")
                    if gps and len(gps) == 2:
                        patient_zones.append({
                            "patient_id": p.get("patient_id", "?"),
                            "lat": gps[0], "lon": gps[1],
                            "tag": p.get("triage_tag", "UNKNOWN"),
                            "priority_score": p.get("priority_score"),
                            "zone": p.get("zone_code"),
                        })
                return render_map_html(
                    field_nodes=state.position_tracker.snapshot(),
                    civilian_reports=state.civilian_intake.snapshot(),
                    patient_zones=patient_zones,
                )

            map_refresh.click(_render_map, outputs=[map_html])
            # Auto-refresh ??Gradio Timer (graceful: not all versions have it)
            try:
                _timer = gr.Timer(5)
                _timer.tick(_render_map, outputs=[map_html])
            except Exception:
                pass  # older Gradio: user must press Refresh

        with gr.Tab("Civilian intake"):
            gr.Markdown(
                "Civilian distress reports from the **separate civilian "
                "first-aid app** (phone tier — optional Qwen Cloud for "
                "chat/summary when online; rules + outbox always work offline). "
                "The **Send to responders** button is internet-dependent — "
                "messages sent while offline are queued in the phone's outbox "
                "and flushed when connectivity returns. From this base's "
                "view a delayed message looks normal but is flagged "
                "`delayed=True` in the snapshot."
            )

            civ_table = gr.Dataframe(
                headers=["incident_id", "severity", "lang", "summary",
                         "delayed", "age_s", "acked"],
                wrap=True,
            )
            refresh_civ = gr.Button("Refresh civilian distress feed")

            def _render_civ() -> List[List[str]]:
                rows = []
                for r in state.civilian_intake.snapshot(
                    active_only=False, max_age_s=86400
                ):
                    rows.append([
                        r["incident_id"][:8],
                        r.get("severity_hint", "?"),
                        r.get("language", "?"),
                        r.get("summary_en", "")[:80],
                        "yes" if r.get("delayed") else "no",
                        str(r.get("age_s", "?")),
                        "yes" if r.get("acknowledged") else "no",
                    ])
                return rows

            refresh_civ.click(_render_civ, outputs=[civ_table])

            # Hidden API endpoint so the civilian app can POST distress JSON
            # via Gradio's API surface (avoids running a separate Flask app).
            api_input = gr.JSON(label="Incoming distress JSON", visible=False)
            api_output = gr.JSON(visible=False)
            api_btn = gr.Button("submit", visible=False)

            def _api_submit(report):
                return state.civilian_intake.submit(report or {})

            api_btn.click(
                _api_submit, inputs=[api_input], outputs=[api_output],
                api_name="civilian_distress",
            )

            # Manual test injection ??visible to operators for debugging
            gr.Markdown("---\n### Manual test injection (for demo / debug)")
            test_json = gr.Textbox(
                label="Distress JSON payload",
                lines=6,
                value=(
                    '{\n'
                    '  "lat": 22.3193, "lon": 114.1694,\n'
                    '  "summary_en": "person collapsed, not breathing",\n'
                    '  "raw_text": "<original language text here>",\n'
                    '  "language": "yue", "severity_hint": "critical",\n'
                    '  "queued_offline": false\n'
                    '}'
                ),
            )
            test_status = gr.Markdown()
            test_btn = gr.Button("Inject test distress report")

            def _inject_test(text: str) -> str:
                try:
                    payload = json.loads(text or "{}")
                except json.JSONDecodeError as exc:
                    return f"??Invalid JSON: {exc}"
                result = state.civilian_intake.submit(payload)
                if not result.get("ok"):
                    return f"??Rejected: {result.get('error')}"
                return (
                    f"??Accepted. incident_id=`{result['incident_id']}` "
                    f"duplicate={result.get('duplicate', False)}"
                )

            test_btn.click(_inject_test, inputs=[test_json],
                           outputs=[test_status])

        with gr.Tab("Broadcasts"):
            gr.Markdown(
                "Auto-drafts composed by the Qwen tool agent / action engine "
                "in response to gateway alerts. Requires "
                "`DASHSCOPE_API_KEY` (see **Settings**). "
                "Send still needs human Approve (KI-02: default mesh is stub)."
            )
            arm_btn = gr.Button("Arm action engine (Qwen agent + broadcaster stub)")
            arm_status = gr.Markdown()
            broadcast_md = gr.Markdown()
            refresh_b = gr.Button("Refresh broadcast log")

            def _arm():
                try:
                    state.ensure_action_engine(force=True)
                    ok = state.base_ai.available() if state.base_ai else False
                    return (
                        f"{'✅' if ok else '⚠️'} Action engine armed. "
                        f"Qwen endpoint: `{state.base_ai.endpoint}`, "
                        f"model: `{state.base_ai.model}`. "
                        f"has_key={ok}"
                        + ("" if ok else " — set DASHSCOPE_API_KEY in Settings / .env")
                    )
                except Exception as exc:
                    return f"❌ Failed to arm: {exc}"

            arm_btn.click(_arm, outputs=arm_status)

            def _render_log():
                if not state.broadcast_log:
                    return "*No broadcasts yet.*"
                lines = [f"**{len(state.broadcast_log)} broadcast(s):**\n"]
                for i, a in enumerate(state.broadcast_log[-10:], 1):
                    out = a.get("outcome", "?")
                    if out == "broadcast" and a.get("composed"):
                        c = a["composed"]
                        lines.append(
                            f"{i}. **[{c.get('severity','?').upper()}] "
                            f"{c.get('anomaly_type','?')}**: "
                            f"{c.get('message_body','')}"
                        )
                    elif out == "error":
                        lines.append(f"{i}. ??error: {a.get('error','?')}")
                    else:
                        lines.append(f"{i}. {out}")
                return "\n\n".join(lines)

            refresh_b.click(_render_log, outputs=broadcast_md)

        with gr.Tab("Compose Broadcast"):
            gr.Markdown(
                "## Commander On-Demand Broadcast\n"
                "Type your intent below. The LLM will draft a <=180-char "
                "mesh broadcast. **You must click Send to actually transmit.** "
                "The LLM cannot send autonomously."
            )
            intent_input = gr.Textbox(
                label="Commander intent (what do you want to tell all field teams?)",
                lines=3,
                placeholder="e.g. Team 3 withdraw immediately, wind shift detected, chemical drift westward",
            )
            draft_btn = gr.Button("Draft broadcast", variant="primary")
            draft_md = gr.Markdown()
            send_draft_btn = gr.Button(
                "Approve & Send this draft", variant="stop", interactive=False,
            )
            send_result_md = gr.Markdown()

            _pending_draft = {"composed": None}

            def _on_draft(intent: str):
                if not intent.strip():
                    return "Please type your intent first.", gr.update(interactive=False)
                state.ensure_action_engine()
                snap = state.gateway.snapshot()
                from .sitrep_generator import build_sitrep
                sitrep = build_sitrep(
                    snap.get("patients", []),
                    [],
                    snap.get("disagreements", []),
                )
                composed = state.action_engine.compose_on_demand(
                    commander_intent=intent,
                    sitrep=sitrep.get("markdown", ""),
                )
                _pending_draft["composed"] = composed

                sev = composed.get("severity", "?").upper()
                atype = composed.get("anomaly_type", "?")
                body = composed.get("message_body", "")
                prov = composed.get("_provenance", {})

                md = (
                    f"### Draft Preview\n\n"
                    f"**[{sev}] {atype}**\n\n"
                    f"> {body}\n\n"
                    f"---\n"
                    f"_Provenance: human_triggered={prov.get('human_triggered')}, "
                    f"fallback={prov.get('fallback_reason') or 'none'}_"
                )
                can_send = composed.get("anomaly_type") != "DRAFT_FAILED"
                return md, gr.update(interactive=can_send)

            draft_btn.click(
                _on_draft, inputs=[intent_input],
                outputs=[draft_md, send_draft_btn],
            )

            def _on_send_draft():
                composed = _pending_draft.get("composed")
                if composed is None or composed.get("anomaly_type") == "DRAFT_FAILED":
                    return "No valid draft to send."
                if state.broadcaster is None:
                    return "Broadcaster not armed. Arm the action engine first."
                result = state.broadcaster.broadcast(
                    severity=composed.get("severity", "info"),
                    anomaly_type=composed.get("anomaly_type", "MANUAL"),
                    message_body=composed.get("message_body", ""),
                )
                state.broadcast_log.append({
                    "outcome": "broadcast",
                    "composed": composed,
                    "send_result": result,
                    "human_triggered": True,
                })
                _pending_draft["composed"] = None
                return f"Human approved. Configured transport result: {result}"

            send_draft_btn.click(_on_send_draft, outputs=[send_result_md])

        with gr.Tab("Settings"):
            from .ai_config import (
                DEFAULT_MODEL_AGENT,
                DEFAULT_MODEL_STRATEGY,
                DEFAULT_QWEN_BASE_URL,
                apply_runtime_credentials,
                load_ai_config,
                load_dotenv_files,
            )

            load_dotenv_files()
            _bcfg = load_ai_config()
            gr.Markdown(
                "## Base AI — Qwen Cloud only\n\n"
                "Backend: **Qwen Cloud only** (DashScope). "
                "Use the same `DASHSCOPE_API_KEY` as Field.\n\n"
                f"Current process: key={'**set**' if _bcfg.has_api_key else '**missing**'} · "
                f"strategy=`{_bcfg.model_strategy}` · agent=`{_bcfg.model_agent}` · "
                f"base=`{_bcfg.base_url}`"
            )
            b_key = gr.Textbox(
                label="DASHSCOPE_API_KEY",
                type="password",
                value="",
                placeholder="sk-... or leave empty to use env / .env",
            )
            b_base = gr.Textbox(
                label="QWEN_BASE_URL",
                value=_bcfg.base_url or DEFAULT_QWEN_BASE_URL,
            )
            b_strategy = gr.Textbox(
                label="QWEN_MODEL_STRATEGY",
                value=_bcfg.model_strategy or DEFAULT_MODEL_STRATEGY,
            )
            b_agent = gr.Textbox(
                label="QWEN_MODEL_AGENT",
                value=_bcfg.model_agent or DEFAULT_MODEL_AGENT,
            )
            with gr.Row():
                b_apply = gr.Button("Apply credentials", variant="primary")
                b_ping = gr.Button("Test Qwen Cloud (live ping)")
            b_status = gr.Markdown()

            def _b_apply(key, base, strat, agent):
                apply_runtime_credentials(
                    api_key=(key or "").strip(),
                    base_url=(base or "").strip(),
                    model_field=(agent or "").strip(),
                )
                if (strat or "").strip():
                    import os
                    os.environ["QWEN_MODEL_STRATEGY"] = strat.strip()
                if (agent or "").strip():
                    import os
                    os.environ["QWEN_MODEL_AGENT"] = agent.strip()
                # Rebuild AI clients with new env
                state.strategy = None
                state.action_engine = None
                state.base_ai = None
                state.tool_agent = None
                state.ensure_action_engine(force=True)
                state.ensure_strategy(force=True)
                cfg = load_ai_config()
                if not cfg.has_api_key:
                    return (
                        "❌ **No API key** after Apply.\n\n"
                        "Set `DASHSCOPE_API_KEY` or create `emergencynet_v5/.env`."
                    )
                return (
                    f"✅ Applied for this process.\n"
                    f"- strategy: `{cfg.model_strategy}`\n"
                    f"- agent: `{cfg.model_agent}`\n"
                    f"- endpoint: `{state.base_ai.endpoint if state.base_ai else cfg.base_url}`\n"
                    f"- has_key: **yes**"
                )

            def _b_ping(key, base, strat, agent):
                _b_apply(key, base, strat, agent)
                if state.base_ai is None:
                    state.ensure_action_engine(force=True)
                ok, detail = state.base_ai.ping()
                return f"{'✅' if ok else '❌'} {detail}"

            b_apply.click(
                _b_apply, inputs=[b_key, b_base, b_strategy, b_agent], outputs=b_status,
            )
            b_ping.click(
                _b_ping, inputs=[b_key, b_base, b_strategy, b_agent], outputs=b_status,
            )

    return demo


def main():
    from .ai_config import gradio_base_server, load_ai_config, load_dotenv_files

    load_dotenv_files()
    cfg = load_ai_config()
    print(
        f"[base] Qwen Cloud: has_key={cfg.has_api_key} "
        f"strategy={cfg.model_strategy} agent={cfg.model_agent} base={cfg.base_url}",
        flush=True,
    )
    if not cfg.has_api_key:
        print(
            "[base] WARNING: no DASHSCOPE_API_KEY — Advisor/Agent offline until set.",
            flush=True,
        )
    host, port = gradio_base_server()
    demo = build_dashboard()
    demo.launch(server_name=host, server_port=port, show_error=True)


if __name__ == "__main__":
    main()


