# Documentation and Mermaid audit

[繁體中文](DOCUMENTATION_AUDIT.zh-TW.md) · [Documentation index](README.md)

Audit scope: root README and `docs/`, excluding the user-specified `legacy file` directory. Its contents were not read or used.

## Findings

The supplied current documentation contained 12 Mermaid block occurrences: four in the EdgeAgent write-up, duplicated in the English manual and again in the Traditional Chinese manual. The diagrams and surrounding text had several conflicts with the live code:

- older competition/model framing rather than the 2026 Qwen Cloud EdgeAgent track;
- radio shown as optional/automatic while the current path is manual hex through Meshtastic text;
- no 200-byte text-envelope analysis, so a 12-patient hex packet appeared viable when it is not;
- removed Base shadow inference shown or described as live;
- separate translation-model references despite direct `qwen3.7-plus` multilingual handling;
- Alibaba Model Studio shown, but no honest ECS backend/deployment proof boundary;
- outbound AI messages depicted without clearly separating draft, human approval, stub result, and real RF delivery;
- diagrams duplicated inside concatenated manuals, making drift likely.

The documentation also linked to nonexistent scripts/files, mixed optional civilian/RAG experiments into the primary story, and included stale setup commands.

## Actions taken

- Replaced both large manuals with current operational manuals.
- Rewrote the EdgeAgent write-up and added its Traditional Chinese pair.
- Rewrote the competition context against the official 2026 Devpost pages.
- Added a dedicated architecture pair as the single detailed diagram source.
- Added Alibaba Cloud, testing, Docker, setup, story, and documentation-index pairs.
- Reclassified civilian intake as optional and removed broken sibling links.
- Kept retained ADR/optional modules out of the primary runtime narrative.
- Fixed all relative Markdown links in the audited scope.
- Rewrote the root README as a standalone explanation and added an iterative reader-review record.

## Open owner decisions found during verification

These are not documentation defects and were not silently converted into medical policy:

- `breathing_status=normal` with `resp_rate=0` currently produces Q1=`No`, Q2=`No`; an otherwise stable ambulatory record can remain GREEN with no review flag.
- A weak radial pulse produces Q3=`Unknown`, and an invalid RR can produce Q2=`Unknown`; Q2/Q3 are not currently in `SAFETY_CRITICAL_QS`, so either case can remain GREEN without mandatory review.
- Decide with a qualified clinical owner whether to reject contradictory input, force human review, change tag behaviour, or combine these controls. Until then, demo fixtures use internally consistent values and the README states the limitation.
- Team facts, measured radio results, real development challenges, and Alibaba ECS runtime evidence were absent and remain explicit placeholders.

## Current diagram inventory

There are 24 Mermaid block occurrences: 12 English diagrams and 12 topology-matched Traditional Chinese versions.

| Location | Diagram |
|---|---|
| Root README pair | Current end-to-end overview |
| Root README pair | Deterministic tag algorithm |
| Root README pair | Base tool-agent loop and human gate |
| Root README pair | Manual Meshtastic sequence |
| Root README pair | Alibaba Cloud backend |
| Architecture pair | System context |
| Architecture pair | Deterministic algorithm |
| Architecture pair | Manual Meshtastic sequence |
| Architecture pair | Qwen agent loop and human gate |
| Architecture pair | Alibaba Cloud backend |
| Alibaba Cloud pair | Deployment/proof structure |
| EdgeAgent write-up pair | Submission architecture |

All 24 blocks were parsed successfully with Mermaid `11.12.2`; zero syntax errors were reported.

## Content source of truth

1. `ARCHITECTURE*` owns system diagrams and technical boundaries.
2. `SETUP_GUIDE*` owns installation and hardware configuration.
3. `TESTING_GUIDE*` owns fixtures, prompts, and pass/fail criteria.
4. `MANUAL*` owns operator workflow.
5. `ALIBABA_CLOUD*` owns deployment and proof.
6. `PROJECT_STORY*` and `WRITEUP_EDGEAGENT*` own competition narrative.

If an old ADR, retained optional module, or internal planning note conflicts with these files, the current source code and the documents above win.
