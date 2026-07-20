"""Field-side Gradio UI for an Android tablet or desktop browser.

Implements the operator triage form with conditional sections for pregnancy,
burn details, and entrapment duration.

The UI flow is:

    1. Operator fills the form
    2. ``form_to_screening`` runs (pure Python) -> 12 answers
    3. ``triage_and_risk`` runs -> tag + hidden risks + score
    4. (optional) operator clicks "Ask AI" to review free-text notes;
       AI suggestions appear with checkboxes; operator must accept each.
    5. Operator saves patients to the outbox and generates a four-patient
       hex packet for manual relay through the Meshtastic text app.

All UI labels and AI outputs are pure English per user requirement.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from .constants import (
    ANSWER_YES, ANSWER_NO, ANSWER_UNKNOWN,
    BREATHING_NORMAL, BREATHING_RAPID_WEAK, BREATHING_ABSENT,
    PULSE_STRONG, PULSE_WEAK, PULSE_ABSENT,
    MENTAL_ALERT, MENTAL_CONFUSED, MENTAL_UNRESPONSIVE,
    PAIN_YES, PAIN_NO, PAIN_UNKNOWN,
    INJURY_BLEEDING, INJURY_FRACTURE, INJURY_BURN, INJURY_ENTRAPPED,
    INJURY_EXPLOSION, INJURY_ABDOMINAL, INJURY_HEAD_TRAUMA,
    BURN_FACE, BURN_NECK, BURN_OTHER,
    AIRWAY_SOOT, AIRWAY_HOARSE, AIRWAY_NONE,
    SPECIAL_PREGNANT, SPECIAL_CHILD, SPECIAL_ELDERLY,
    PREG_ABDOMINAL, PREG_BLEEDING, PREG_FETAL,
    REVIEW_NONE, REVIEW_AI_ACCEPTED,
)
from .screening import (
    form_to_screening, form_to_patient_record,
    review_notes_with_ai, apply_suggestions, normalize_suggestion_list,
)
from .triage_core import triage_and_risk, rank_patients
from .risk_engine import HIDDEN_RISK_RULES
from .bit_packer import build_patient_record_for_packet, encode_packet
from .field_ai import FieldAI
from .gps_bridge import GPSBridge
from .multilingual import translate_and_review, SUPPORTED_LANGUAGES


# ---------------------------------------------------------------------------
# Option tables (label shown -> value submitted)
# ---------------------------------------------------------------------------
BREATHING_CHOICES = [
    ("Normal", BREATHING_NORMAL),
    ("Rapid / weak", BREATHING_RAPID_WEAK),
    ("Absent", BREATHING_ABSENT),
]
PULSE_CHOICES = [
    ("Strong", PULSE_STRONG),
    ("Weak", PULSE_WEAK),
    ("Absent", PULSE_ABSENT),
]
MENTAL_CHOICES = [
    ("Alert", MENTAL_ALERT),
    ("Confused / drowsy", MENTAL_CONFUSED),
    ("Unresponsive", MENTAL_UNRESPONSIVE),
]
PAIN_CHOICES = [
    ("Reports pain", PAIN_YES),
    ("Reports no pain", PAIN_NO),
    ("Cannot judge", PAIN_UNKNOWN),
]
INJURY_CHOICES = [
    ("Bleeding", INJURY_BLEEDING),
    ("Fracture", INJURY_FRACTURE),
    ("Burn", INJURY_BURN),
    ("Entrapped / crushed", INJURY_ENTRAPPED),
    ("Near explosion", INJURY_EXPLOSION),
    ("Abdominal pain (blunt trauma)", INJURY_ABDOMINAL),
    ("Head impact / trauma", INJURY_HEAD_TRAUMA),
]
BURN_LOC_CHOICES = [
    ("Face", BURN_FACE), ("Neck", BURN_NECK), ("Other", BURN_OTHER),
]
AIRWAY_CHOICES = [
    ("Soot in mouth/nose", AIRWAY_SOOT),
    ("Hoarse voice", AIRWAY_HOARSE),
    ("None", AIRWAY_NONE),
]
SPECIAL_CHOICES = [
    ("Pregnant", SPECIAL_PREGNANT),
    ("Child (<8 yrs)", SPECIAL_CHILD),
    ("Elderly (>65 yrs)", SPECIAL_ELDERLY),
]
PREG_SYM_CHOICES = [
    ("Abdominal pain", PREG_ABDOMINAL),
    ("Vaginal bleeding", PREG_BLEEDING),
    ("Decreased fetal movement", PREG_FETAL),
]


# ---------------------------------------------------------------------------
# State container
# ---------------------------------------------------------------------------
class FieldState:
    def __init__(self):
        self.gps = GPSBridge(meshtastic_iface=None)
        self.field_ai: Optional[FieldAI] = None
        self.patients: List[Dict[str, Any]] = []   # list of {"form","screening","result"}
        self.last_eval_out: Optional[Dict[str, Any]] = None

    def use_field_ai(
        self,
        enabled: bool,
        endpoint: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """Enable Field AI against **Qwen Cloud only** (no llama.cpp / Gemma).

        Credentials: DASHSCOPE_API_KEY / QWEN_API_KEY env, emergencynet_v5/.env,
        or values passed from Settings.
        """
        if not enabled:
            self.field_ai = None
            return
        from .ai_config import apply_runtime_credentials, load_ai_config, load_dotenv_files
        from .field_ai import reset_default
        from .qwen_client import reset_default_client

        load_dotenv_files()
        if api_key or endpoint or model:
            apply_runtime_credentials(
                api_key=api_key or "",
                base_url=endpoint or "",
                model_field=model or "",
            )
        # Drop any cached clients that may have been created without a key
        reset_default_client()
        reset_default()
        cfg = load_ai_config()
        self.field_ai = FieldAI(
            endpoint=endpoint,
            model=model,
            api_key=api_key,
            config=cfg,
        )


# ---------------------------------------------------------------------------
# Form -> result helpers
# ---------------------------------------------------------------------------
def evaluate_form(form: Dict[str, Any]) -> Dict[str, Any]:
    screening = form_to_screening(form)
    record = form_to_patient_record(form)
    result = triage_and_risk(screening, patient_record=record)
    return {
        "form": form,
        "screening": screening,
        "result": result,
        "patient_record": record,
    }


def _format_result_md(eval_out: Dict[str, Any]) -> str:
    r = eval_out["result"]
    risks = r.get("hidden_risks", [])
    md = [
        f"### Triage tag: **{r['triage_tag']}**",
        f"Priority score: **{r['priority_score']}**  |  "
        f"Confidence: **{r['confidence']}**  |  "
        f"Needs human review: **{r['needs_human_review']}**",
        "",
        "**Rationale:**",
    ]
    for line in r.get("rationale", []):
        md.append(f"- {line}")
    md.append("")
    md.append("**12-Q answers:**")
    for q in [f"q{i}" for i in range(1, 13)]:
        md.append(f"- {q.upper()}: {eval_out['screening'].get(q)}")
    if risks:
        md.append("")
        md.append("**Hidden risks (with citations):**")
        for risk in risks:
            md.append(f"- **{risk['risk']}** ({risk['risk_level']})")
            md.append(f"  - Detail: {risk['detail']}")
            md.append(f"  - Timeline: {risk['timeline']}")
            md.append(f"  - Action: {risk['action']}")
            md.append(f"  - Source: {risk['source']}")
    return "\n".join(md)


# ---------------------------------------------------------------------------
# UI builder
# ---------------------------------------------------------------------------
def build_app() -> gr.Blocks:
    state = FieldState()

    with gr.Blocks(title="EmergencyNet Field — Qwen Edge") as demo:
        gr.Markdown(
            "# EmergencyNet — Field Triage (Qwen Cloud)\n"
            "Pure-Python deterministic engine. AI (qwen3.7-plus with direct multilingual support) is "
            "optional and may only *escalate* answers (No → Yes) — never reverse."
        )

        with gr.Tab("Patient form"):
            patient_id = gr.Textbox(label="Patient ID", value="P001")
            with gr.Row():
                team_id = gr.Number(label="Team ID (packet)", precision=0, value=1)
                zone_code = gr.Number(label="Zone code (0=none)", precision=0, value=0)
            with gr.Row():
                walking = gr.Checkbox(label="Patient can walk (ambulatory)")
                age = gr.Number(label="Estimated age", precision=0, value=30)

            specials = gr.CheckboxGroup(
                choices=SPECIAL_CHOICES, label="Special markers"
            )

            preg_symptoms = gr.CheckboxGroup(
                choices=PREG_SYM_CHOICES,
                label="Pregnancy symptoms (only used if 'Pregnant' is checked)",
                visible=False,
            )

            with gr.Row():
                breathing = gr.Radio(
                    choices=BREATHING_CHOICES,
                    label="Breathing", value=BREATHING_NORMAL,
                )
                resp_rate = gr.Number(
                    label="Resp rate (breaths/min, optional)", precision=0,
                )
            with gr.Row():
                pulse = gr.Radio(
                    choices=PULSE_CHOICES, label="Radial pulse", value=PULSE_STRONG,
                )
                mental = gr.Radio(
                    choices=MENTAL_CHOICES, label="Mental status", value=MENTAL_ALERT,
                )

            pain = gr.Radio(
                choices=PAIN_CHOICES, label="Pain response", value=PAIN_YES,
            )

            injuries = gr.CheckboxGroup(
                choices=INJURY_CHOICES, label="Injury types"
            )

            burn_loc = gr.CheckboxGroup(
                choices=BURN_LOC_CHOICES, label="Burn location",
                visible=False,
            )
            airway = gr.CheckboxGroup(
                choices=AIRWAY_CHOICES, label="Airway signs",
                visible=False,
            )
            entrap_min = gr.Number(
                label="Entrapment minutes", precision=0, visible=False,
            )

            notes = gr.Textbox(label="Free-text notes (optional)", lines=2)
            photo = gr.Image(label="Wound/scene photo (optional)", type="filepath")

            # GPS controls
            with gr.Accordion("GPS", open=False):
                gps_lat = gr.Number(label="Latitude (manual)", precision=6)
                gps_lon = gr.Number(label="Longitude (manual)", precision=6)

            evaluate_btn = gr.Button("Evaluate (deterministic)", variant="primary")
            ai_review_btn = gr.Button("Ask field AI to review notes")
            multilingual_btn = gr.Button("Multilingual notes review (qwen3.7-plus)")
            photo_btn = gr.Button("Vision review (qwen3.7-plus)")

            result_md = gr.Markdown()
            ai_suggestion_box = gr.JSON(
                label="AI review result (visual_findings + suggestions with qkey)",
            )
            accept_qs = gr.CheckboxGroup(
                choices=[(q.upper(), q) for q in [f"q{i}" for i in range(1, 13)]],
                label="Accept these AI escalations (tick qkeys, then Apply)",
                value=[],
            )
            apply_btn = gr.Button("Apply accepted escalations & re-evaluate")

            send_btn = gr.Button("Save patient → outbox", variant="stop")

            # Conditional renders
            def _toggle_preg(specials_val: List[str]):
                return gr.update(visible=SPECIAL_PREGNANT in (specials_val or []))

            def _toggle_burn(injuries_val: List[str]):
                show = INJURY_BURN in (injuries_val or [])
                return (gr.update(visible=show), gr.update(visible=show))

            def _toggle_entrap(injuries_val: List[str]):
                return gr.update(visible=INJURY_ENTRAPPED in (injuries_val or []))

            specials.change(_toggle_preg, inputs=specials, outputs=preg_symptoms)
            injuries.change(_toggle_burn, inputs=injuries, outputs=[burn_loc, airway])
            injuries.change(_toggle_entrap, inputs=injuries, outputs=entrap_min)

            # Evaluate handler
            def _gather_form(*vals):
                (pid, team, zone, walking, age, specials, preg_sym, breathing, resp_rate,
                 pulse, mental, pain, injuries, burn_loc, airway,
                 entrap_min, notes, gps_lat, gps_lon) = vals

                gps = None
                if gps_lat is not None and gps_lon is not None:
                    try:
                        if float(gps_lat) != 0 or float(gps_lon) != 0:
                            gps = (float(gps_lat), float(gps_lon))
                    except (TypeError, ValueError):
                        gps = None

                try:
                    team_i = int(team) if team is not None else 1
                except (TypeError, ValueError):
                    team_i = 1
                try:
                    zone_i = int(zone) if zone is not None else 0
                except (TypeError, ValueError):
                    zone_i = 0

                form = {
                    "patient_id": pid,
                    "team_id": team_i,
                    "zone_code": zone_i,
                    "walking": walking,
                    "age": age,
                    "special_markers": specials,
                    "preg_symptoms": preg_sym,
                    "breathing_status": breathing,
                    "resp_rate": resp_rate,
                    "pulse_radial": pulse,
                    "mental_status": mental,
                    "pain_response": pain,
                    "injury_types": injuries,
                    "burn_location": burn_loc,
                    "airway_signs": airway,
                    "entrapment_min": entrap_min,
                    "notes": notes,
                    "gps": gps,
                }
                return form

            inputs_all = [
                patient_id, team_id, zone_code, walking, age, specials, preg_symptoms,
                breathing, resp_rate, pulse, mental, pain, injuries, burn_loc, airway,
                entrap_min, notes, gps_lat, gps_lon,
            ]

            def _ai_envelope(
                *,
                findings: str = "",
                suggestions: Any = None,
                error: str = "",
                extra: Optional[Dict[str, Any]] = None,
            ) -> Tuple[Dict[str, Any], List[str]]:
                """Uniform JSON for Gradio: findings separate from escalate list.

                Returns (envelope, accepted_qkey_defaults) so Apply never sees
                info-only rows as suggestion objects (fixes qkey KeyError).
                """
                suggs = normalize_suggestion_list(suggestions)
                env: Dict[str, Any] = {
                    "visual_findings": findings or "",
                    "suggestions": suggs,
                }
                if error:
                    env["error"] = error
                if extra:
                    env.update(extra)
                preselect = [s["qkey"] for s in suggs]
                return env, preselect

            def _on_evaluate(*vals):
                form = _gather_form(*vals)
                eval_out = evaluate_form(form)
                state.patients_pending = eval_out  # type: ignore[attr-defined]
                state.last_eval_out = eval_out
                empty, _ = _ai_envelope()
                return _format_result_md(eval_out), empty, []

            evaluate_btn.click(
                _on_evaluate, inputs=inputs_all,
                outputs=[result_md, ai_suggestion_box, accept_qs],
            )

            def _on_ai_review(*vals):
                form = _gather_form(*vals)
                screening = form_to_screening(form)
                if state.field_ai is None:
                    state.use_field_ai(True)
                if state.field_ai is None or not state.field_ai.available():
                    err = (
                        state.field_ai.last_error
                        if state.field_ai is not None
                        else "no-api-key"
                    )
                    return _ai_envelope(
                        error=(
                            "AI offline — no Qwen API key. "
                            "Set DASHSCOPE_API_KEY / open Settings → Apply. "
                            f"({err or 'no-api-key'})"
                        ),
                    )
                review = review_notes_with_ai(form, screening,
                                              state.field_ai.as_callable())
                if not review.get("ai_used"):
                    err = state.field_ai.last_error or "notes empty or empty model reply"
                    return _ai_envelope(error=f"AI returned no suggestions ({err}).")
                return _ai_envelope(suggestions=review.get("suggestions", []))

            ai_review_btn.click(
                _on_ai_review, inputs=inputs_all,
                outputs=[ai_suggestion_box, accept_qs],
            )

            def _on_multilingual_review(*vals):
                form = _gather_form(*vals)
                notes = form.get("notes", "")
                if not notes.strip():
                    return _ai_envelope(error="No notes to review.")
                screening = form_to_screening(form)
                if state.field_ai is None:
                    state.use_field_ai(True)
                if state.field_ai is None or not state.field_ai.available():
                    return _ai_envelope(error="AI offline — configure Qwen API key in Settings.")
                result = translate_and_review(
                    notes=notes,
                    current_answers=screening,
                    ai_callable=state.field_ai.as_callable(),
                )
                if not result.get("ok"):
                    return _ai_envelope(
                        error=result.get("error", "Multilingual call failed"),
                    )
                extra = {}
                if result.get("detected_lang"):
                    extra["detected_lang"] = result["detected_lang"]
                if result.get("translation_en"):
                    extra["translation_en"] = result["translation_en"]
                return _ai_envelope(
                    suggestions=result.get("suggestions", []),
                    extra=extra,
                )

            multilingual_btn.click(
                _on_multilingual_review, inputs=inputs_all,
                outputs=[ai_suggestion_box, accept_qs],
            )

            def _on_photo(img_path, *vals):
                form = _gather_form(*vals)
                if not img_path:
                    return _ai_envelope(error="No photo selected.")
                from .multimodal import MultimodalReviewer
                if state.field_ai is None:
                    state.use_field_ai(True)
                screening = form_to_screening(form)
                rev = MultimodalReviewer()
                result = rev.review_photo(img_path, form, screening)
                if not result.get("ok"):
                    return _ai_envelope(
                        error=result.get("error", "vision failed"),
                        extra={"raw": (result.get("raw") or "")[:500]},
                    )
                return _ai_envelope(
                    findings=result.get("visual_findings") or "",
                    suggestions=result.get("suggestions") or [],
                    extra={
                        "image_useful": result.get("image_useful"),
                        "latency_ms": result.get("latency_ms"),
                    },
                )

            photo_btn.click(
                _on_photo, inputs=[photo] + inputs_all,
                outputs=[ai_suggestion_box, accept_qs],
            )

            def _on_apply(*vals_and_accepted):
                *vals, accepted, suggestions = vals_and_accepted
                form = _gather_form(*vals)
                screening = form_to_screening(form)
                suggs = normalize_suggestion_list(suggestions)
                if suggs and accepted:
                    screening = apply_suggestions(screening, accepted or [], suggs)
                elif suggs and not accepted:
                    # clear message path — still re-eval without escalations
                    pass
                record = form_to_patient_record(form)
                result = triage_and_risk(screening, patient_record=record)
                eval_out = {
                    "form": form, "screening": screening,
                    "result": result, "patient_record": record,
                }
                state.patients_pending = eval_out  # type: ignore[attr-defined]
                state.last_eval_out = eval_out
                applied = [
                    s["qkey"] for s in suggs
                    if s["qkey"] in {str(x).lower() for x in (accepted or [])}
                ]
                note = (
                    f"\n\n_Applied escalations: {', '.join(applied) or '(none selected)'}_"
                )
                return _format_result_md(eval_out) + note

            apply_btn.click(
                _on_apply,
                inputs=inputs_all + [accept_qs, ai_suggestion_box],
                outputs=result_md,
            )

            outbox_md = gr.Markdown(label="Outbox")

            def _on_save(*vals):
                form = _gather_form(*vals)
                eval_out = evaluate_form(form)
                state.patients.append(eval_out)
                lines = [f"## Outbox ({len(state.patients)} patients)"]
                for i, p in enumerate(state.patients, 1):
                    r = p["result"]
                    lines.append(
                        f"{i}. {p['form'].get('patient_id')} — "
                        f"**{r['triage_tag']}** (score {r['priority_score']}, "
                        f"conf {r['confidence']})"
                    )
                return "\n".join(lines)

            send_btn.click(_on_save, inputs=inputs_all, outputs=outbox_md)

        with gr.Tab("Tactical Advice"):
            gr.Markdown(
                "## AI Tactical Advisor (Qwen Cloud · qwen3.7-plus)\n"
                "Synthesizes per-patient tactical guidance from local lookup "
                "tables + Qwen Cloud. **Evaluate a patient first**, then "
                "select environment and visible injuries below."
            )

            ENV_CHOICES = [
                ("Clear (no special hazard)", "clear"),
                ("Active structural collapse", "structural_collapse_active"),
                ("Stabilized collapse footprint", "structural_collapse_stabilized"),
                ("Active fire", "fire_active"),
                ("Chemical suspected (unknown agent)", "chemical_suspected"),
                ("Chemical known: chlorine", "chemical_known_chlorine"),
                ("Chemical known: ammonia", "chemical_known_ammonia"),
                ("Chemical known: H2S", "chemical_known_hydrogen_sulfide"),
                ("Chemical known: CO", "chemical_known_carbon_monoxide"),
                ("Flood / water", "flood"),
                ("Dark / low visibility", "dark_low_visibility"),
            ]

            INJURY_CHOICES_TACTICAL = [
                ("Major hemorrhage", "major_hemorrhage"),
                ("Burn major (>10% TBSA or face/airway)", "burn_major"),
                ("Burn minor", "burn_minor"),
                ("Open fracture", "open_fracture"),
                ("Closed fracture", "closed_fracture"),
                ("Amputation", "amputation"),
                ("Chest trauma", "chest_trauma"),
                ("Head trauma", "head_trauma"),
                ("Spinal suspected", "spinal_suspected"),
                ("Pediatric <8", "pediatric_under_8"),
            ]

            env_dd = gr.Dropdown(
                choices=ENV_CHOICES,
                value="clear",
                label="Current environment",
            )
            visible_cb = gr.CheckboxGroup(
                choices=INJURY_CHOICES_TACTICAL,
                label="Visible injuries (multi-select)",
            )
            advice_btn = gr.Button("Get Tactical Advice", variant="primary")
            advice_md = gr.Markdown()

            with gr.Accordion("Provenance (audit trail)", open=False):
                provenance_md = gr.Markdown()

            def _on_tactical(env, visible):
                if state.last_eval_out is None:
                    return "Please evaluate a patient first (Patient form tab).", ""
                if state.field_ai is None:
                    state.use_field_ai(True)
                advice = state.field_ai.generate_tactical_advice(
                    patient_result=state.last_eval_out["result"],
                    environment=env,
                    visible_injuries=visible or [],
                )
                md = []
                md.append(f"### Tactical Advice\n{advice['tactical_advice']}")
                md.append("\n### Equipment Needs")
                if advice["equipment_needs"]:
                    md.append("| Item | Qty | Rationale |")
                    md.append("|---|---:|---|")
                    for e in advice["equipment_needs"]:
                        md.append(f"| {e['item']} | {e['qty']} | {e.get('rationale', '')} |")
                else:
                    md.append("_(no specific equipment recommended)_")
                md.append(f"\n### Transport: **{advice['transport_class']}**")
                md.append(f"_{advice['transport_reasoning']}_")
                md.append("\n### Scene Safety")
                sn = advice["safety_note"]
                md.append(f"- **PPE:** {', '.join(sn['ppe']) or '(none specified)'}")
                md.append(f"- **Perimeter:** {sn['perimeter_m']} m")
                md.append(f"- **Directive:** {sn['directive']}")

                prov = advice.get("_provenance", {})
                prov_md = "\n".join([
                    f"- LLM model: `{prov.get('llm_model')}`",
                    f"- LLM latency: {prov.get('llm_latency_ms')} ms",
                    f"- Tables consulted: {prov.get('tables_used')}",
                    f"- Equipment whitelist size: {prov.get('whitelist_size')}",
                    f"- Baseline transport class: {prov.get('baseline_transport_class')}",
                    f"- Baseline perimeter (m): {prov.get('baseline_perimeter_m')}",
                    f"- Fallback reason: {prov.get('fallback_reason') or '(none — LLM responded)'}",
                ])
                return "\n".join(md), prov_md

            advice_btn.click(
                _on_tactical,
                inputs=[env_dd, visible_cb],
                outputs=[advice_md, provenance_md],
            )

        with gr.Tab("Outbox & Send"):
            gr.Markdown(
                "Current radio path is manual: generate hex, copy it into the "
                "Meshtastic Android app, receive it over the LoRa mesh, then "
                "paste it into the Base dashboard. To remain below the "
                "Meshtastic text limit, this UI emits at most **4 patients per "
                "message** and keeps the rest in the outbox."
            )
            send_status = gr.Markdown("Outbox is empty.")
            refresh_btn = gr.Button("Refresh outbox")
            send_lora_btn = gr.Button("Generate hex for manual Mesh relay", variant="primary")
            packet_preview = gr.Textbox(label="Copy this hex into Meshtastic", lines=4)

            def _refresh():
                if not state.patients:
                    return "Outbox is empty.", ""
                ranked = rank_patients([p["result"] for p in state.patients])
                lines = [f"## {len(ranked)} patients (ranked)"]
                for r in ranked:
                    lines.append(
                        f"- rank {r.get('evacuation_rank')}: "
                        f"**{r['triage_tag']}** "
                        f"score {r['priority_score']} conf {r['confidence']}"
                    )
                return "\n".join(lines), ""

            refresh_btn.click(_refresh, outputs=[send_status, packet_preview])

            def _encode_only():
                if not state.patients:
                    return "Outbox empty.", ""
                # Meshtastic text messages are limited to about 200 bytes.
                # 10-byte header + 4*18-byte records = 82 bytes = 164 hex chars.
                # Five records consumes the full 200-byte budget, so four keeps
                # a safety margin for client behaviour.
                batch = state.patients[:4]
                flat = []
                team = 1
                zone = 0
                for p in batch:
                    form = p.get("form") or {}
                    try:
                        team = int(form.get("team_id", team))
                    except (TypeError, ValueError):
                        pass
                    try:
                        zone = int(form.get("zone_code", zone))
                    except (TypeError, ValueError):
                        pass
                    flat.append(build_patient_record_for_packet(
                        p["result"], p["patient_record"],
                        review_flag=REVIEW_NONE,
                    ))

                pkt = encode_packet(team_id=team, patients=flat, zone_code=zone)
                state.patients = state.patients[len(batch):]
                remaining = len(state.patients)
                return (
                    f"Encoded {len(flat)} patients ({len(pkt)} bytes / "
                    f"{len(pkt.hex())} hex characters), team={team}, zone={zone}. "
                    f"Copy the hex into Meshtastic. {remaining} patient(s) remain "
                    f"in the outbox. (Manual text relay; no direct RF TX.)",
                    pkt.hex(),
                )

            send_lora_btn.click(_encode_only, outputs=[send_status, packet_preview])

        with gr.Tab("Settings"):
            from .ai_config import (
                DEFAULT_MODEL_FIELD,
                DEFAULT_QWEN_BASE_URL,
                load_ai_config,
                load_dotenv_files,
            )

            load_dotenv_files()
            _cfg0 = load_ai_config()
            gr.Markdown(
                "## Field AI — Qwen Cloud only\n\n"
                "Backend: **Qwen Cloud only** (DashScope OpenAI-compatible). "
                "Set `DASHSCOPE_API_KEY` in the shell, put it in "
                "`emergencynet_v5/.env`, or paste below and **Apply**.\n\n"
                f"Current process: key={'**set**' if _cfg0.has_api_key else '**missing**'} · "
                f"model=`{_cfg0.model_field}` · base=`{_cfg0.base_url}`"
            )
            ai_key = gr.Textbox(
                label="DASHSCOPE_API_KEY (not stored to disk from UI)",
                type="password",
                value="",
                placeholder="sk-... or leave empty to use env / .env",
            )
            ai_base = gr.Textbox(
                label="QWEN_BASE_URL",
                value=_cfg0.base_url or DEFAULT_QWEN_BASE_URL,
            )
            ai_model = gr.Textbox(
                label="QWEN_MODEL_FIELD",
                value=_cfg0.model_field or DEFAULT_MODEL_FIELD,
            )
            with gr.Row():
                apply_btn = gr.Button("Apply credentials", variant="primary")
                check_btn = gr.Button("Test Qwen Cloud (live ping)")
            ai_status = gr.Markdown()

            def _apply_ai(key, base, model):
                state.use_field_ai(
                    True,
                    endpoint=(base or "").strip() or None,
                    api_key=(key or "").strip() or None,
                    model=(model or "").strip() or None,
                )
                fa = state.field_ai
                if fa is None:
                    return "Field AI disabled."
                if not fa.available():
                    return (
                        "❌ **No API key** after Apply.\n\n"
                        "Set `DASHSCOPE_API_KEY` in PowerShell before launch, or "
                        "create `emergencynet_v5/.env` with:\n"
                        "```\nDASHSCOPE_API_KEY=sk-...\n"
                        f"QWEN_BASE_URL={DEFAULT_QWEN_BASE_URL}\n"
                        f"QWEN_MODEL_FIELD={DEFAULT_MODEL_FIELD}\n```"
                    )
                return (
                    f"✅ Credentials applied for this process.\n"
                    f"- model: `{fa.model}`\n"
                    f"- endpoint: `{fa.endpoint}`\n"
                    f"- has_key: **yes**\n\n"
                    "Click **Test Qwen Cloud** for a live round-trip."
                )

            def _check_ai(key, base, model):
                state.use_field_ai(
                    True,
                    endpoint=(base or "").strip() or None,
                    api_key=(key or "").strip() or None,
                    model=(model or "").strip() or None,
                )
                ok, detail = state.field_ai.ping()
                return f"{'✅' if ok else '❌'} {detail}"

            apply_btn.click(
                _apply_ai, inputs=[ai_key, ai_base, ai_model], outputs=ai_status,
            )
            check_btn.click(
                _check_ai, inputs=[ai_key, ai_base, ai_model], outputs=ai_status,
            )

    return demo


def main():
    from .ai_config import gradio_field_server, load_dotenv_files, load_ai_config

    load_dotenv_files()
    cfg = load_ai_config()
    print(
        f"[field] Qwen Cloud: has_key={cfg.has_api_key} "
        f"model={cfg.model_field} base={cfg.base_url}",
        flush=True,
    )
    if not cfg.has_api_key:
        print(
            "[field] WARNING: no DASHSCOPE_API_KEY / QWEN_API_KEY — "
            "AI buttons will stay offline until you set env, .env, or Settings.",
            flush=True,
        )
    host, port = gradio_field_server()
    demo = build_app()
    demo.launch(server_name=host, server_port=port, show_error=True)


if __name__ == "__main__":
    main()
