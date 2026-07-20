# ADR 0001: Deterministic triage core; AI advisory only

- **Status:** Accepted (observed in code)  
- **Date:** 2026-05 (hackathon era) / documented 2026-07-14  

## Context

Disaster triage cannot depend on LLM availability or hallucination for life-critical labels.

## Decision

All START/JumpSTART tags and hidden-risk escalations are pure Python (`screening`, `risk_engine`, `triage_core`). LLMs may only suggest No→Yes escalations or non-tag advice (tactical, strategy, alert wording).

## Consequences

+ System still triages offline when models die.  
+ Safety filters required on every AI suggestion path.  
− AI cannot refine false-positive Yes answers.

## Alternatives considered

1. LLM-first triage — rejected.  
2. AI can upgrade and downgrade — rejected.

## References

- `triage_core.py`, `screening.py:398–405`, `docs/AGENTS.md`
