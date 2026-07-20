# ADR 0003: Shadow inference trusts field bits for q7 and q9

- **Status:** **Superseded / product-removed (2026-07-17)** — base shadow inference removed from live gateway path (owner: feature not useful). Module may remain on disk unreferenced.  
- **Date:** post wire-format extension / documented 2026-07-14; retired 2026-07-17  

## Context

Wire format does not carry `preg_symptoms`, `burn_location`, or `airway_signs`. Re-deriving q7/q9 from incomplete form fields false-flags field/shadow disagreements.

## Decision

`shadow_from_decoded_patient` overwrites q7 and q9 with the field’s transmitted screening answers (`_NONDERIVABLE_FROM_WIRE`).

## Consequences

+ Comparator stays honest for pregnancy/airway-burn cases.  
− Base cannot independently verify those two questions from raw fields alone.

## Alternatives considered

1. Expand packet to carry those fields — size tradeoff.  
2. Always Unknown on base for q7/q9 — noisy disagreements.

## References

- `shadow_inference.py:27–61`, `bit_packer.py` layout
