# ADR 0002: 18-byte patient records on Meshtastic APP_PORT 256

- **Status:** Accepted  
- **Date:** v3–v5 era / documented 2026-07-14  

## Context

Meshtastic usable payload is on the order of ~237 bytes; multi-patient batches needed.

## Decision

Fixed layout: 10-byte header + 18 bytes/patient, max 12 (226 bytes). Binary on private app port 256. Version byte = 1. XOR checksums for integrity only.

## Consequences

+ Predictable MTU fit.  
− Lossy: no notes, no burn_location/airway/preg_symptoms lists, no resp_rate.  
− patient_id only 0–255.

## Alternatives considered

1. JSON over mesh — too large.  
2. One patient per packet always — more airtime.

## References

- `constants.py:143–149`, `bit_packer.py`, `lora_bridge.APP_PORT`, `docs/PROTOCOL.md`
