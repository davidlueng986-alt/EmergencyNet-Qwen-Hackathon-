# ADR 0006: Qwen Cloud as the optional AI backend

- **Status:** Accepted, amended 2026-07-19  
- **Date:** 2026-07-17  
- **Workspace:** EmergencyNet_v5.Qwen123  
- **Traditional Chinese:** [0006-qwen-cloud.zh-TW.md](0006-qwen-cloud.zh-TW.md)

## Context

Competition fork targets Qwen Cloud EdgeAgent. Local Gemma/llama.cpp/Ollama defaults conflict with platform requirements and complicate demos.

## Decision

All optional AI uses Alibaba Cloud Model Studio's DashScope OpenAI-compatible API via `qwen_client.py`:

- Field / vision / agent: `qwen3.7-plus`  
- Strategy: `qwen3.7-max` + thinking  
- Multilingual field notes: handled directly by `qwen3.7-plus`; there is no separate translation-model hop.

Deterministic triage remains local and offline-capable. AI is optional, may suggest escalation only, and does not own the medical tag or broadcast approval.

## Consequences

+ Simpler ops, stronger agent/tool quality, hackathon-compliant.  
− Requires API key and network for AI features.  
− AI features stop when the cloud path is unavailable; deterministic triage and operations continue.
− Model identifiers and service-scope availability must be checked in the target Alibaba Cloud account before the demo.
