# EmergencyNet operator manual

[繁體中文](MANUAL.zh-TW.md) · [Setup](SETUP_GUIDE.md) · [Testing](TESTING_GUIDE.md) · [Architecture](ARCHITECTURE.md)

> **Prototype safety notice:** EmergencyNet is not a certified medical device and does not replace local incident-command, triage, medical, privacy, or radio regulations. Only trained personnel under local authority should evaluate any real operational use. Public demos must use synthetic data.

## 1. Current operating concept

EmergencyNet has three human roles:

| Role | Responsibility |
|---|---|
| Field responder | Observe, enter data, review deterministic output, accept/reject AI suggestions, relay packet hex |
| Base operator | Receive Mesh text, verify/copy hex, ingest packets, monitor data quality and dashboard |
| Incident commander | Interpret aggregate information, approve operational decisions and every outbound message |

Current patient-data flow:

`Field form → deterministic result → four-patient packet → hex → Meshtastic text → Heltec V4 mesh → Base Meshtastic text → hex inject → gateway/SITREP/anomalies`

AI is optional enrichment. It is not the owner of tags or broadcasts.

## 2. Pre-incident readiness

### Daily/start-of-demo check

- [ ] Confirm every Heltec V4 has a matching antenna attached before power.
- [ ] Confirm legal region, modem preset, private channel, and PSK match.
- [ ] Label nodes and devices physically: `FIELD-01`, `RELAY-01`, `BASE-01`.
- [ ] Send `EN LINK CHECK <sequence>` and confirm Base receipt.
- [ ] Start Field on port 7860 and Base on 7861.
- [ ] Run one GREEN synthetic evaluation without AI.
- [ ] Run `python -m pytest -q` on the release build.
- [ ] If using Qwen, run connection checks without exposing the key.
- [ ] Keep Packet A/B fixtures, chargers, cables, and a software-only backup available.
- [ ] Confirm the public/Alibaba deployment contains only synthetic data and is access controlled.

### Incident identifiers

Set a consistent Team ID and Zone code before adding patients. The demo uses Team `7`, Zone `4`; real exercises must define identifiers in the incident plan. Patient IDs are stored as one byte, so use numeric IDs `0–255` and avoid accidental reuse inside a test.

## 3. Field operation

### A. Enter observations

1. Open Field Gradio.
2. Enter patient ID, Team ID, Zone, walking status, estimated age, breathing/RR, radial pulse, mental status, pain, injuries, special markers, and relevant conditional fields.
3. Add manually verified latitude/longitude only if available. Heltec V4's GNSS interface is not an automatic location source in this application.
4. Use notes for concise observations, not names or unnecessary identifiers.
5. Use an image only for a staged/synthetic exercise unless a lawful, approved operational policy exists.

### B. Evaluate deterministically

Press **Evaluate (deterministic)** and review:

- tag;
- Q1–Q12 answers;
- hidden risks;
- confidence;
- `needs_human_review`;
- rationale and priority score.

If a safety-critical answer is `Unknown`, stop and obtain the missing observation or escalate to the responsible human. Do not use AI to conceal uncertainty.

### C. Optional Qwen review

Use **Ask field AI to review notes**, **Multilingual notes review**, or **Vision review** only after the deterministic result exists.

The allowed sequence is:

1. Qwen returns findings and candidate qkeys.
2. The operator checks the evidence.
3. The operator selects only justified qkeys.
4. The operator clicks **Apply accepted escalations & re-evaluate**.
5. The deterministic core recalculates.

AI can propose only No → Yes. It cannot change Yes to No, silently apply a result, or directly send radio messages. If AI is unavailable or questionable, ignore it and continue with the deterministic path.

### D. Save and make a packet

1. Press **Save patient → outbox** after reviewing the result.
2. Repeat for up to four patients.
3. Open **Outbox & Send** and verify rank/count.
4. Press **Generate hex for manual Mesh relay**.
5. Confirm the status shows at most four patients and at most 164 hex characters.

If more patients remain, the UI retains them. Generate another independent packet after the first is relayed. Never cut one hex string into arbitrary pieces.

## 4. Field-to-Base Meshtastic relay

1. Copy only the generated lowercase/uppercase hex characters; no label or punctuation.
2. Open Meshtastic Android → **Messages** → the private incident channel.
3. Paste and send.
4. Wait for the client delivery state. Record time/status if collecting metrics.
5. At Base, use the Meshtastic Web Client or a second mobile client connected to `BASE-01`.
6. Copy the exact received text. Do not copy from the original Field screen when claiming a real RF test.
7. Compare length if needed: one patient 56, three 128, four 164 hex characters.
8. If the message is truncated or marked Too Large, discard it and resend a smaller complete packet.

Use a custom private PSK. The default Meshtastic channel key is publicly known. Channel encryption does not remove the need to identify operators/nodes and protect lost devices.

## 5. Base operation

### A. Ingest

1. Open Base → **Inject test packet**.
2. Paste only received hex.
3. Click **Inject**.
4. Confirm decoded count matches the Field batch.
5. On error, do not repeatedly paste random variants; compare the original and received text and resend the complete packet.

`MALFORMED_PACKET` is a safe rejection. It should not terminate the gateway.

### B. Review state

- **Patients:** check ID, tag, confidence, risk qkeys, injuries, age.
- **SITREP:** refresh after packet ingestion.
- **Map:** treat locations as approximate/manual unless a verified source is connected.
- **Broadcasts:** new anomaly types may create drafts after the action engine is armed.
- **Advisor:** ask for structured support; distinguish facts, advice, and uncertainty.

The gateway keeps a capped in-memory list. Restart clears it. Replaying the same packet currently creates duplicates.

### C. Interpret aggregate alerts

| Alert | Current trigger | Operator action |
|---|---|---|
| `RESP_CLUSTER` | ≥5 patients and ≥50% respiratory distress | Verify data quality and escalate the pattern to command |
| `BURN_CLUSTER` | ≥3 patients and ≥60% burns | Verify source/scene context and notify command |
| `CRUSH_CLUSTER` | ≥3 entrapped patients | Verify reports and notify command |
| `RED_SURGE` | ≥5 RED within 10 minutes | Verify time window and notify command |

Alerts are advisory and do not alter patient tags. Follow local protocols rather than treating the generic software message as an order.

## 6. Strategy and agent operation

### Strategy Advisor

Ask narrowly scoped questions using live state. A useful prompt is:

```text
Using only the live snapshot, separate observed facts, recommended next actions, and uncertainties for the next 10 minutes. Do not invent resources or outcomes.
```

Verify all model-supplied facts against the dashboard. Strategy output is advice, not execution.

### Tool Agent

The agent may read snapshot/patients/anomalies, build a SITREP, and create a draft. It has no tool that changes tags.

Recommended prompt:

```text
Inspect live state with tools, report exact counts, and create one concise alert draft. Do not send it.
```

The agent loop forcibly treats all model-originated send requests as unapproved, even if the model places `human_approved=true` in its arguments.

### Human approval

1. Read the exact draft, severity, anomaly type, and live evidence.
2. Edit/redraft if it is ambiguous, unsafe, or unsupported.
3. Copy the draft ID into the separate send control.
4. The Incident Commander—not the model—clicks **Approve & Send draft**.
5. Record the configured transport result.

In the supplied dashboard, the configured broadcaster is a demo stub. A success result proves the approval path and application audit only; it does not prove a radio message left the Base. For a real exercise, either manually copy the approved text into Meshtastic or wire and validate a real sender before claiming transmission.

## 7. Offline mode

If Qwen or internet fails:

1. Keep Field/Base running.
2. Continue deterministic Field evaluation.
3. Continue four-patient packet generation and Meshtastic relay.
4. Continue Base decode, patient lists, SITREP, and anomaly detection.
5. Mark AI advice/drafts unavailable; do not repeatedly retry and congest the link.
6. Use local incident-command procedures and ordinary radio voice/text for coordination.

Offline is a designed mode, not a permission to bypass human review.

## 8. Failure response

| Failure | Response |
|---|---|
| Radio node missing | Check power, antenna, region/channel/PSK, distance, and relay placement |
| Text too large | Use at most four patients; send independent packets |
| Invalid hex | Remove labels/quotes/spaces; copy exact received text |
| Malformed packet | Discard; resend the original complete packet; do not repair by guesswork |
| Duplicate patients | Restart before a demo scenario; in operations flag replay limitation and reconcile manually |
| AI timeout/error | Continue deterministic path; retry only when useful |
| AI suggests de-escalation | Reject; parser/core should prevent it; record as a test failure |
| Agent claims it sent | Verify tool/audit result; do not trust prose |
| Stub returns success | Do not call it RF delivery |
| Public ECS unavailable | Use local Base and retain deployment evidence separately |

## 9. End-of-incident/demo

- Record build SHA, device/firmware versions, region, topology, packet delivery evidence, errors, and operator actions.
- Export/capture only synthetic or properly authorized data.
- Stop public access or rotate judge credentials after the judging period.
- Rotate the Meshtastic PSK after a public event.
- Remove API keys from shared devices and rotate any key that appeared on screen.
- Restart Base to clear in-memory demo records.
- Log defects and separate verified facts from proposed roadmap changes.

## 10. Non-negotiable limitations

- Manual hex copy at Field and Base is part of the current workflow.
- A 12-patient binary packet does not fit one Meshtastic text message as hex.
- Base outbound radio is not connected by default.
- XOR checks are not authentication.
- No replay protection or deduplication.
- No durable database or persistent audit log.
- No clinical certification or validation is claimed.
- Retained `shadow_inference.py`, `comparator.py`, and optional RAG files are not active product layers.

Use the [testing guide](TESTING_GUIDE.md) for exact packets and acceptance criteria.
