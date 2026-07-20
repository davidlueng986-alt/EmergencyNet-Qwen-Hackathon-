# EmergencyNet: pitches and project story

[繁體中文](PROJECT_STORY.zh-TW.md) · [README](../README.md) · [Technical write-up](WRITEUP_EDGEAGENT.md)

> **Fact rule:** text in square brackets is information that cannot be verified from this repository. Replace it with real team, deployment, hardware, and test facts before submission. Do not turn a plan into a claim.

## Elevator pitches

Each pitch below is under 200 English words. Choose one for the form or video; do not combine all three into one speech.

### 1. 30-second pitch

EmergencyNet helps a disaster team keep triage and reporting alive when mobile internet fails. A responder records a patient on an Android tablet. A fixed 12-question check assigns a triage tag and catches less obvious risks, even offline. The tablet turns the result into hex text; the operator pastes it into Meshtastic, and Heltec V4 radios relay it over a LoRa mesh. At Base, a dashboard combines many reports and warns about respiratory, burn, crush, or RED-patient clusters. Qwen can review notes and staged images, explain the overall situation, and draft a short alert. It cannot lower a risk, change a tag, or send a message by itself. People make the decisions; the software reduces what they must remember.

### 2. Judge pitch

After a building collapse, a field team may have one minute per patient and no reliable internet. EmergencyNet gives them a repeatable workflow: enter observations, run a local 12-question check, see the exact reason for the BLACK/RED/YELLOW/GREEN tag, and send a compact report through a Heltec V4 Meshtastic LoRa mesh. The current demo uses an honest manual bridge—copy the generated hex into Meshtastic, then paste the received hex into the Base dashboard. Base reconstructs the patient records, produces a SITREP, and detects patterns across the incident. Qwen Cloud handles the jobs where language and synthesis are useful: multilingual note review, staged-image review, tactical guidance, strategy, and alert drafting. It is boxed in by code: suggestions can only raise a currently absent concern, a responder must accept them, the agent has no tag-changing tool, and only a separate human control can approve a broadcast. The Base is containerized for Alibaba Cloud ECS and uses Model Studio APIs; real runtime proof still has to be attached before submission.

### 3. Technical pitch

EmergencyNet is an offline-first field-to-command system. Its deterministic Python core converts structured observations into 12 ternary answers, eight hidden-risk checks, a triage tag, confidence, review flag, and priority score. Twelve two-bit answers fit in three bytes; each complete patient record is 18 bytes. Because hex doubles the text length, the current Field app sends independent four-patient packets rather than claiming that a 12-patient hex message fits Meshtastic. At Base, strict decoding, a capped incident window, deterministic SITREP generation, and four aggregate detectors work without Qwen. `qwen3.7-plus` reviews multilingual notes and staged images and runs a six-tool command agent; `qwen3.7-max` produces structured strategy from the exact live snapshot. The model cannot change patient data or authorize transmission. Base is packaged for Alibaba Cloud ECS and calls Alibaba Cloud Model Studio through its OpenAI-compatible API. The remaining transport gaps—automatic radio ingestion and a real outbound sender—are stated as roadmap work.

## Project story

### The situation we designed for

Picture the first hour after a building collapse. The mobile network is overloaded or gone. A small field team finds dozens of casualties. Some are clearly critical; others can speak and walk but have warning signs that may become serious later. Each responder is trying to assess patients, remember details, decide who moves first, and report to command at the same time.

The command post has the opposite problem. It receives short messages from several teams but cannot see the whole incident. One breathing problem may be an individual case. Five breathing problems in ten minutes may point to smoke or another shared hazard. The important fact is often the pattern across reports, not one report by itself.

We started EmergencyNet to join those two views without assuming that cellular data would survive. The goal is practical: help a small team miss fewer facts, carry a small amount of structured data over radio, and give the commander a clearer picture. We deliberately do not claim that this prototype saves a particular number of lives. That would require clinical validation and field evidence we do not have.

If there is a verified personal or community event behind the project, add it here in the team's own words: **[TEAM-SUPPLIED INSPIRATION]**.

### Why we did not begin with a chatbot

The easiest hackathon version would have been a form connected to a large model. It would also have failed in exactly the conditions we care about: weak internet, a missing API key, an ambiguous note, or an unpredictable answer.

So we gave different jobs to different parts of the system:

- fixed code owns the repeatable triage calculation;
- Qwen looks at language, staged images, and multi-patient context;
- the radio mesh moves the minimum useful record;
- Base looks for incident-level patterns;
- people accept changes and authorize external actions.

This split is not mainly about making the architecture look sophisticated. It is about failure. If Qwen is unavailable, the team loses extra review and synthesis, but it does not lose the 12-question check, packet creation, radio relay, decoding, detectors, or SITREP. If a model gives a bad suggestion, a human can reject it. If a radio packet is damaged, the decoder rejects it instead of inventing a patient.

### Why there are 12 questions

A responder under pressure should not have to remember every branch in a long document. EmergencyNet therefore turns the assessment into 12 answers: `Yes`, `No`, or `Unknown`.

Questions 1–4 cover immediate signs used by the prototype's START/JumpSTART-inspired path: no breathing after airway repositioning, abnormal breathing, absent radial pulse, and inability to follow a command. Questions 5–12 cover risks that may be less visible at first: prolonged entrapment, blunt abdominal trauma, pregnancy warning signs, altered mental status, airway-burn clues, a serious painless injury, an older adult with head injury and confusion, and close blast exposure.

We chose a fixed set for three reasons:

1. **It reduces memory load.** The operator sees the same short sequence for every patient instead of improvising from free text.
2. **It is auditable.** A BLACK or RED result points back to a named answer and rule; it is not a model score that nobody can reproduce.
3. **It fits the radio format.** Each ternary answer uses two bits, so all 12 answers occupy exactly three bytes.

Twelve is an engineering choice for this prototype, not a claim that these questions are a complete worldwide medical protocol. The thresholds and action text need review by qualified local clinical and incident-command owners.

### Why hidden risks are shown separately

An immediate triage branch asks who needs attention now. It does not fully answer who may deteriorate soon or need a different resource. A person with soot around the mouth may still be talking before airway swelling develops. Someone released after long entrapment may look more stable than the release risk suggests. An older person with a head impact may need repeated checks even when the first assessment does not force RED.

We kept those risks visible instead of hiding them inside one final tag. When Q5–Q12 fires, the interface shows the risk name, level, reason, timeline, and prototype action. Most RED-level hidden risks override the normal walk/non-walk branch; Q11 is a monitoring flag and does not force RED by itself. This lets the responder see both the immediate tag and the reason for extra caution.

`Unknown` is also a real answer. The confidence value is `1 − Unknown/12`. Unknown values in Q1, Q5, Q6, Q7, or Q9 cap confidence at `0.4` and mark the record for human review; confidence below `0.6` also requests review. The point is not to pretend that a formula knows how uncertain medicine is. The point is to stop missing data from looking like reassuring data.

The code still has a known input-validation gap: Q2/Q3 being Unknown does not always force review, and contradictory input such as normal breathing with a respiratory rate of zero is not hard-blocked. We document this because changing clinical behaviour without an owner would be less responsible than exposing the limitation.

### Why AI may raise a concern but may not lower one

Useful clues often appear in notes rather than checkboxes: “voice becoming hoarse,” “near the blast but says he is fine,” or the same observation written in another language. A staged exercise image can also contain a visible clue the form did not capture. This is where Qwen adds value.

The model returns proposed question changes with reasons. The parser only keeps a change if the current answer is `No` and the proposal is `Yes`. A responder then selects which proposals to accept; only after that does the fixed engine calculate again.

We chose this one-way rule because deleting an already recorded danger is a stronger action than drawing attention to a possible omission. Model interpretation is not reliable enough to erase structured evidence silently. Even an upward suggestion can be wrong, so it remains pending until a person accepts it. This is a conservative product rule, not a clinical statement that every escalation is correct.

The same idea shapes the other AI features:

- `qwen3.7-plus` reads multilingual notes directly, avoiding a separate translation step that could lose meaning;
- the staged-image review suggests observations but never puts an image into the LoRa patient packet;
- field tactical advice starts from local lookup tables and enforces equipment, transport, PPE, and perimeter limits; if Qwen fails, the table result remains;
- `qwen3.7-max` receives the exact Base snapshot and returns structured strategy with uncertainties; it does not re-triage patients;
- the `qwen3.7-plus` Base agent reads live state through six named tools instead of guessing from conversation history.

### Why the agent uses tools and stops before sending

The Base agent can read the situation snapshot, list recent patients, list active anomalies, build a deterministic SITREP, create a radio-alert draft, and request a broadcast. It has no tool for changing a tag or editing a patient. Its loop is capped at six model steps, and unknown tool names or invalid arguments are rejected.

Tool calling matters because the answer should use the current patient counts in the program, not numbers remembered from an old chat turn. The cap matters because an operational interface should not enter an open-ended reasoning loop. The draft/send split matters because writing plausible text is not the same as deciding that it is correct and safe to transmit.

We enforce that last boundary in code. If the model includes `human_approved=true`, the dispatcher overwrites it to false. The commander must review the draft in a separate part of the dashboard and press the approval control. The default broadcaster is still a stub, so the current repository demonstrates the approval gate but does not claim a completed Base-to-radio link.

### Why the radio path is small—and currently manual

LoRa provides long-range, low-bandwidth communication and Meshtastic lets Heltec V4 nodes relay messages through a mesh. That makes it useful when teams cannot rely on cellular towers. It also means every byte matters.

EmergencyNet stores one patient in 18 bytes behind a 10-byte packet header. During testing, we found an easy-to-miss problem: twelve binary records produce a 226-byte packet, but the current demo copies the packet as hexadecimal text. Hex uses two characters per byte, so the message becomes 452 characters—too large for the normal text path. The Field app therefore produces independent packets of at most four patients, each 164 hex characters, and keeps the rest in the outbox for the next message.

The current end-to-end path has two human copy steps:

1. Field creates hex; the operator pastes it into the Meshtastic Android app.
2. Heltec V4 nodes carry the text over the LoRa mesh.
3. The Base Meshtastic client receives it; the operator pastes it into **Inject test packet**.

We kept this boundary visible because it is reproducible with the hardware now and easy for judges to inspect. Calling it “automatic integration” would hide unfinished work. Direct binary transmission, automatic Base ingestion, authenticated packets, replay protection, and deduplication belong in the next transport iteration.

### Why Base looks across patients

A field record answers “what happened to this patient?” Command also needs “what is happening to this incident?” Base therefore keeps a capped patient window and runs four deterministic detectors:

- once the window has at least five patients, at least 50% show rapid/weak or absent breathing;
- once the window has at least three patients, at least 60% have a burn injury;
- at least three entrapped patients;
- at least five RED patients received within ten minutes.

The thresholds are visible and testable. A detector raises an incident flag; it does not alter any patient's tag. Qwen can then explain the live snapshot or draft a compact alert, while the commander decides whether the pattern is real and what resource action is appropriate.

### Why Alibaba Cloud is part of the backend

Base is packaged as a Docker service for Alibaba Cloud ECS. The Qwen client calls Alibaba Cloud Model Studio through DashScope's OpenAI-compatible endpoint. We use `qwen3.7-plus` for frequent note, image, tactical, and tool-calling work, and reserve `qwen3.7-max` with thinking for the on-demand strategy view.

That division keeps the common path simpler while giving the command view a stronger synthesis model. It also makes the cloud role specific: ECS hosts the reachable Base service; Model Studio supplies optional language and reasoning. The deterministic mission path remains local.

The supplied repository proves the client code, container definition, and deployment procedure. It does **not** prove that an ECS instance is currently running. Before submission, the team must add the real region, public code link, HTTPS demo URL, and runtime evidence: **[VERIFIED ALIBABA CLOUD DETAILS]**.

### What the complete demo shows

A good demonstration is one continuous story, not a tour of tabs:

1. Enter a synthetic collapse patient on the tablet and show why the local rules produce the tag.
2. Add a multilingual note or staged image and show a pending Qwen escalation—not an automatic change.
3. Accept or reject it as the responder.
4. Create a four-patient hex packet, paste it into Meshtastic, and show it crossing at least one Heltec V4 relay.
5. Paste the received hex into Base and show the reconstructed patients.
6. Inject the second prepared packet so the respiratory, burn, crush, and RED-surge detectors become visible.
7. Ask the agent for exact counts and an alert draft.
8. Attempt model-originated approval, show that it is blocked, and finish with the separate human decision.

This sequence explains the whole product: observe, decide locally, transmit minimally, combine reports, use cloud assistance, and keep authority with people.

### What we accomplished

The repository contains:

- a deterministic 12-question engine, eight hidden-risk rules, confidence/review handling, and priority sorting;
- an 18-byte patient record, checksummed packet header, strict decoder, and bilingual test fixtures;
- a four-patient manual Meshtastic text flow designed around the real hex budget;
- offline Field and Base functions plus six bounded Qwen feature groups;
- four incident-level detectors, a deterministic SITREP, and a six-tool Base agent;
- a programmatic barrier against model-fabricated human approval;
- separate Field and Base containers, an Alibaba ECS runbook, tests, demo data, and bilingual documentation.

Do not add radio range, latency, loss rate, clinical accuracy, field-deployment, or lives-saved numbers until they have been measured and recorded: **[VERIFIED METRICS]**.

### What challenged us, and why it mattered

The verified engineering challenges are not dramatic anecdotes; they are design corrections visible in the repository:

1. **A small packet was not automatically a sendable message.** Measuring the hex text, rather than only the binary, forced the four-patient batching change.
2. **A prompt was not a permission boundary.** Testing a fabricated approval showed why the dispatcher had to force model-originated approval to false.
3. **Fallback needed useful output.** We separated fixed rules and lookup tables from model synthesis so an API failure does not empty the screen.
4. **More detail could exceed the radio budget.** We kept images and long notes out of the patient packet and transmitted compact signals instead.
5. **Honest integration status is part of safety.** The manual copy steps, broadcaster stub, in-memory storage, and missing ECS proof are stated instead of hidden behind architecture arrows.

Add the team's real development experience—hardware failures, debugging sessions, rejected approaches, time pressure, and individual contributions—only after confirming it: **[TEAM-SUPPLIED CHALLENGES]**.

### What we learned

**Reliability is a product feature.** The best model is irrelevant if the core workflow disappears with the network. That is why the tag, packet, detector, and SITREP paths are deterministic.

**Human-in-the-loop must describe an actual mechanism.** “A human stays in control” means little unless the model lacks mutation tools, suggestions wait for acceptance, and approval comes from a separate UI path. We implemented and tested those conditions.

**Unknown must stay visible.** Missing answers should not quietly become `No`. Confidence and review flags make incompleteness part of the record.

**The real transport envelope decides the design.** LoRa capacity, Meshtastic text limits, and hex expansion are different layers. Testing only the first would have produced a demo that could not be sent through the actual app.

**Good safety documentation includes unfinished work.** Readers need to know where automation stops, what evidence is missing, and which claims still require qualified review.

### What comes next

The next priority is to close the transport and evidence gaps, not to add a larger model:

- direct binary Meshtastic PortNum transmission and automatic Base ingestion;
- a real, human-approved outbound radio sender;
- authenticated envelopes, replay protection, deduplication, persistent storage, and audit logs;
- measured multi-hop range, delay, loss, and recovery tests;
- accessible field testing across supported languages;
- supervised clinical and incident-command review under local protocols;
- a real ECS deployment with reproducible runtime evidence.

The design rule should remain simple: AI can widen the team's view, but it should not erase observed risk, take an unreviewed action, or make the system useless when the cloud is gone.

## Facts to complete before submission

| Item | Required verified value |
|---|---|
| Team name | `[TEAM NAME]` |
| Members, roles, and contributions | `[NAMES / ROLES / CONTRIBUTIONS]` |
| Public repository | `[PUBLIC GITHUB URL]` |
| Competition-period change dates | `[VERIFIED GIT DATES AFTER THE ELIGIBILITY START]` |
| ECS region, instance, and runtime evidence | `[VERIFIED ALIBABA DETAILS]` |
| Judge-accessible demo | `[HTTPS URL / ACCESS METHOD]` |
| Hardware topology | `[NUMBER OF HELTEC V4 NODES AND ROLES]` |
| Measured radio/runtime results | `[TEST RECORD LINK]` |
| Personal inspiration | `[OPTIONAL VERIFIED STORY]` |
| Team-specific challenges | `[TEAM-SUPPLIED FACTS]` |
