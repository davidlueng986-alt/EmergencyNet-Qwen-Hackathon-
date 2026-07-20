# ADR 0004: LLM composes mesh alerts; trigger is policy or human

- **Status:** Superseded by [ADR 0007](0007-broadcast-ai-draft-human-send.md)  
- **Date:** v4–v5.3 / documented 2026-07-14  

## Context

Autonomous LLM broadcasts are unsafe (spam / wrong crisis message). Original design used a static type→severity map.

## Decision (as implemented today)

`BROADCAST_POLICY` maps anomaly types to required severities. `ActionEngine` only sends when policy matches or commander approves on-demand draft. LLM fills `compose_mesh_alert` arguments only.

## Owner revision (not yet coded)

Exact static match is **rejected as a bug** (KI-26 / OI-05): broadcast need/severity should be **AI-determined**. A future ADR must redefine:

1. What the LLM is allowed to decide (severity, message, whether to draft).  
2. What remains non-AI (human Approve? rate limits? hard denylist?).  
3. How this interacts with ADR “deterministic core” for **clinical tags** (tags stay deterministic; broadcast is ops messaging).

Until that ADR is written and implemented, keep characterizing current `policy-skip` behavior in tests/docs.

## Consequences

+ Misbehaving model cannot authorize a send under old design.  
− Static map drops valid alerts (e.g. wrong severity string) — owner finds this unacceptable.  
− Transport still no-op (KI-02–04).

## References

- `action_engine.py:46–51,185–224,311+`, `meshtastic_broadcaster.py`, `docs/OPEN_ISSUES.md` OI-05
