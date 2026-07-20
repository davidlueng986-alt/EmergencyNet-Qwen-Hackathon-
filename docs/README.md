# EmergencyNet documentation

[繁體中文](README.zh-TW.md) · [Project README](../README.md)

This index separates current, operator-facing documentation from optional or historical material. Files in the current set describe the code path that is actually connected in this repository.

## Start here

| Document | Purpose |
|---|---|
| [Setup guide](SETUP_GUIDE.md) | Heltec V4, Meshtastic, Android/Termux, desktop, Docker, and verification |
| [Testing and live demo](TESTING_GUIDE.md) | Synthetic scenarios, exact hex fixtures, AI prompts, expected results, and judge runbook |
| [Architecture](ARCHITECTURE.md) | Current system boundary, deterministic algorithm, packet, mesh sequence, agent loop, and Alibaba Cloud diagrams |
| [Operator manual](MANUAL.md) | Safe operating flow, field/base checklists, failure modes, and limitations |
| [Documentation audit](DOCUMENTATION_AUDIT.md) | Legacy findings, Mermaid replacement inventory, and source-of-truth rules |
| [Reader review](DOCUMENTATION_REVIEW.md) | Iterative ordinary-reader/judge review, failed drafts, corrections, and final quality gate |

## Competition package

| Document | Purpose |
|---|---|
| [Qwen Cloud competition context](COMPETITION_CONTEXT.md) | Official EdgeAgent requirements, dates, judging criteria, and submission checklist |
| [EdgeAgent write-up](WRITEUP_EDGEAGENT.md) | Copy-ready technical submission narrative |
| [Alibaba Cloud deployment](ALIBABA_CLOUD.md) | ECS deployment, code/runtime proof, diagram, and evidence checklist |
| [Project story and pitches](PROJECT_STORY.md) | Elevator pitches, inspiration, build journey, learning, impact, and placeholders for unverified facts |

Every user-facing document above has a matching `.zh-TW.md` Traditional Chinese version.

## Supporting material

- [`adr/`](adr/) records architectural decisions. Some older ADRs mention removed experiments; the live architecture document wins if they conflict.
- [Civilian app integration](CIVILIAN_APP_INTEGRATION.md) is an optional, non-core integration concept and is not required for the EdgeAgent demo.
- [Cleanup plan](CLEANUP_PLAN.md) is an internal historical planning note, not an operator guide.
- `data/json_cleaned/`, `strategy_rag.py`, `shadow_inference.py`, and `comparator.py` are retained optional/legacy code and are not in the current runtime path.
- The excluded `legacy file` directory is not a source of truth and is intentionally absent from this index.

## Documentation truth rules

1. Deterministic code owns triage tags.
2. AI may suggest only No → Yes escalation, and a person accepts it.
3. Current patient radio transport is manual hex text through Meshtastic.
4. Current outbound Base sender is a stub unless a real transport is explicitly wired.
5. No AI broadcast is sent without human approval.
6. EmergencyNet is a prototype, not a certified medical device.
7. Placeholder URLs, team facts, deployment identifiers, and performance metrics must be replaced with verified facts before submission.
