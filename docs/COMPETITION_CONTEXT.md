# Qwen Cloud EdgeAgent competition context

[繁體中文](COMPETITION_CONTEXT.zh-TW.md) · [Official overview](https://qwencloud-hackathon.devpost.com/) · [Official rules](https://qwencloud-hackathon.devpost.com/rules) · [Official resources](https://qwencloud-hackathon.devpost.com/resources)

Research checked on **July 19, 2026 (Pacific Time)**. The official pages are authoritative and can change; verify them again immediately before submission.

## Event facts

| Item | Official information |
|---|---|
| Event | Global AI Hackathon Series with Qwen Cloud |
| Sponsor | Alibaba Cloud |
| Administrator | Devpost |
| Track | Track 5: EdgeAgent |
| Submission period | May 26, 2026 8:00 AM PT through July 20, 2026 2:00 PM PT |
| Judging | July 28, 2026 8:00 AM PT through August 11, 2026 2:00 PM PT |
| Winner announcement | On or around August 17, 2026 2:00 PM PT |

The overview currently describes EdgeAgent as Qwen-powered physical devices—robots, IoT agents, or smart hardware—that perceive through edge sensors, reason through cloud APIs/Skills, and act locally. Entries should show robust edge-cloud orchestration under bandwidth/latency constraints, privacy-aware handling, and graceful degradation in weak or offline conditions.

## Required submission components

- A public code repository with the source, assets, and instructions required to run the project.
- An open-source license visible at the top of the repository page, including the GitHub **About** area.
- Proof that the backend runs on Alibaba Cloud. The official overview says the proof must include a link to a repository code file that demonstrates Alibaba Cloud services/APIs.
- A clear architecture diagram connecting Qwen Cloud, backend, data, frontend, and physical edge.
- A public demonstration video of about three minutes on an accepted platform; the rules say it must show the project functioning on its intended platform.
- A text description of features and functionality.
- Explicit identification of the EdgeAgent track.
- A working demo or test build available through judging; provide credentials in the submission if access is restricted.
- English content or English translations for material required by the judges.
- If the project existed before May 26, explain the significant updates made during the submission period.

The optional public build-journey post can qualify for the Blog Post prize if its link is included in the submission.

## Judging weights

| Criterion | Weight | What to make visible in EmergencyNet |
|---|---:|---|
| Technical Depth & Engineering | 30% | Qwen API roles, function-calling agent, deterministic codec/rules, error handling, tests, edge/cloud boundaries |
| Innovation & AI Creativity | 30% | Human-governed No → Yes review, offline-first safety split, constrained mesh transport, aggregate intelligence |
| Problem Value & Impact | 25% | Authentic disaster communication gap, cognitive-load reduction, global deployment potential, honest safety governance |
| Presentation & Documentation | 15% | Three-minute story, physical-device footage, readable diagrams, reproducible setup, exact judge fixtures |

The official page's explanatory sentences appear under these labels; both 30% categories should be addressed rather than optimizing for the wording of only one.

## Why EmergencyNet fits EdgeAgent

| EdgeAgent expectation | EmergencyNet evidence |
|---|---|
| Physical device | Heltec LoRa 32 V4 radios and Android tablet |
| Perception | Structured responder observations, free text, optional image, manually supplied GPS |
| Cloud reasoning | Model Studio OpenAI-compatible API using `qwen3.7-plus` and `qwen3.7-max` |
| Local action | Deterministic triage/risk decision, packet creation, operator guidance |
| Constrained orchestration | 18-byte patient records, four-patient hex batches, LoRa mesh, explicit human handoffs |
| Offline degradation | Deterministic field and base logic works without an API key |
| Privacy awareness | Compact data, no image over LoRa, custom mesh PSK guidance, synthetic judge data |
| Safe autonomy | No AI tag mutation, no AI de-escalation, human-approved broadcast gate |

## Evidence mapped to code

| Claim | Repository evidence |
|---|---|
| Qwen Cloud API | `emergencynet/qwen_client.py`, `emergencynet/ai_config.py` |
| Multilingual/vision review | `emergencynet/multilingual.py`, `emergencynet/multimodal.py` |
| Tool agent | `emergencynet/base_agent.py` |
| Human send gate | `emergencynet/base_agent.py`, `emergencynet/action_engine.py` |
| Deterministic fallback | `emergencynet/screening.py`, `triage_core.py`, `risk_engine.py` |
| Compact transport | `emergencynet/bit_packer.py` |
| Aggregate detection | `emergencynet/anomaly_detector.py` |
| Alibaba deployment | `Dockerfile`, `docker-compose.yml`, `docs/ALIBABA_CLOUD.md` |

## Submission checklist

- [ ] Replace every `<OWNER>`, `<REPO>`, `<YOUR-DEMO-HOST>`, team, and metric placeholder.
- [ ] Push the final commit to a public repository.
- [ ] Add Apache-2.0 to the GitHub About panel.
- [ ] Deploy Base to Alibaba Cloud ECS and verify it from a clean browser.
- [ ] Link directly to `emergencynet/qwen_client.py` as Alibaba service/API code evidence.
- [ ] Record redacted runtime proof: ECS identity, container, public URL, and Model Studio request.
- [ ] Record a public ≤3-minute demo with Android, Heltec hardware, real mesh relay, Base dashboard, Qwen features, offline fallback, and approval gate.
- [ ] Provide judge steps and the exact fixtures in `docs/TESTING_GUIDE.md`.
- [ ] State current limitations: two manual hex copy steps and outbound sender stub.
- [ ] Test every public link without being signed into the owner account.
- [ ] Confirm eligibility, dates, accepted video host, and all submission fields against the live rules.

## Claims not to make

- Do not say a full 12-patient hex packet fits one Meshtastic text message.
- Do not say the Field app transmits RF automatically.
- Do not call the default Base stub an actual Meshtastic delivery.
- Do not claim clinical certification, field deployment, saved lives, performance metrics, or Alibaba runtime deployment without evidence.
- Do not describe retained shadow/RAG experiment files as part of the current live pipeline.
