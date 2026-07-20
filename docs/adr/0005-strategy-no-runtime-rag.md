# ADR 0005: Strategy advisor drops runtime RAG (v5.3)

- **Status:** Accepted  
- **Date:** 2026-05-17 (CHANGELOG) / documented 2026-07-14  

## Context

~100+ RAG chunks were AI-generated and not real PDF extractions; weak grounding narrative.

## Decision

`StrategyAI` injects a live gateway snapshot and uses model knowledge only. Chroma `strategy_rag` retained for offline build scripts, not dashboard (`rag=None`).

## Consequences

+ Honest about grounding.  
− UI markdown may still mention dual RAG (stale string).  
− `data/chroma_db` is dead weight for live path unless re-enabled with real sources.

## References

- `strategy_ai.py` module docstring, `base_dashboard.ensure_action_engine` rag=None
