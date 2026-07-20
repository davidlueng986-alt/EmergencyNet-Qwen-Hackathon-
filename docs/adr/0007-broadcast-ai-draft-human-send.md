# ADR 0007: AI drafts mesh alerts; human approves send

- **Status:** Accepted (supersedes static severity exact-match policy intent)  
- **Date:** 2026-07-17  

## Context

Static `BROADCAST_POLICY` exact type+severity matching silently skipped valid alerts (KI-26). Owner wants AI to determine need/severity.

## Decision

1. Soft allowlist of anomaly **types** may auto-**draft**.  
2. Severity is model-chosen within `{critical, high, info}`.  
3. Model-originated `request_send_broadcast` calls are forced to `human_approved=false`; **send** is reachable only from the separate UI Approve control, which calls the tool directly after a human click.  
4. Rate limit still applies on actual send.

## Consequences

+ No silent policy-skip on severity mismatch.  
+ Aligns with Qwen tool-calling best practice for write ops.  
− Default transport may still be stub (KI-02).
