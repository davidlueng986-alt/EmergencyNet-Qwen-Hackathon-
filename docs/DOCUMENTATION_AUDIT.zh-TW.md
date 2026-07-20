# 文件與 Mermaid Audit

[English](DOCUMENTATION_AUDIT.md) · [文件索引](README.zh-TW.md)

Audit Scope：Root README 與 `docs/`，排除使用者指定的 `legacy file` Directory；其內容沒有被讀取或使用。

## Findings

原本現行文件共有 12 個 Mermaid Block Occurrence：EdgeAgent Write-up 四個，之後在英文 Manual 重複，再在繁體中文 Manual 重複。Diagram 與附近文字跟 Live Code 有多項衝突：

- 使用舊 Competition/Model Framing，而不是 2026 Qwen Cloud EdgeAgent Track；
- Radio 被畫成可選／自動，但現行路徑是 Meshtastic Text 內人工 Hex；
- 沒有分析 200-byte Text Envelope，令人誤以為 12 人 Hex Packet 可行；
- 把已移除 Base Shadow Inference 畫成或寫成 Live；
- 仍引用 Separate Translation Model，但現行是 `qwen3.7-plus` Direct Multilingual；
- 顯示 Alibaba Model Studio，卻沒有誠實 ECS Backend/Deployment Proof Boundary；
- Outbound AI Message 沒有分清 Draft、Human Approval、Stub Result 與 Real RF Delivery；
- Diagram 重複放進 Concatenated Manual，容易 Drift。

文件亦連到不存在的 Script/File，把 Optional Civilian/RAG Experiment 混入 Primary Story，並含 Stale Setup Command。

## Actions Taken

- 以現行 Operational Manual 取代兩份大型 Manual。
- 重寫 EdgeAgent Write-up，加入繁體中文版本。
- 依官方 2026 Devpost Page 重寫 Competition Context。
- 新增 Architecture Pair，作為唯一 Detailed Diagram Source。
- 新增 Alibaba Cloud、Testing、Docker、Setup、Story、Documentation Index 雙語版本。
- 把 Civilian Intake 重列為 Optional，移除 Broken Sibling Link。
- ADR/Optional Module 不再出現在 Primary Runtime Narrative。
- 修復 Audit Scope 內所有 Relative Markdown Link。
- 把 Root README 重寫成可獨立理解的說明，並加入逐輪讀者審查紀錄。

## 驗證時發現、仍需 Owner 決定的事項

以下不是文件錯字，因此沒有被擅自轉成醫療政策：

- `breathing_status=normal` 配 `resp_rate=0` 目前會產生 Q1=`No`、Q2=`No`；其他欄位穩定且可行走時，可保持 GREEN 且沒有 Review Flag。
- Weak Radial Pulse 會產生 Q3=`Unknown`；無效 RR 可產生 Q2=`Unknown`。Q2／Q3 目前不在 `SAFETY_CRITICAL_QS`，因此兩者都可能保持 GREEN 而不強制覆核。
- 請與合資格 Clinical Owner 決定：拒絕矛盾輸入、強制 Human Review、改變 Tag Behaviour，或組合使用。決定前 Demo Fixture 只用內部一致資料，README 亦公開此限制。
- Team Facts、實測 Radio 結果、真實開發挑戰與 Alibaba ECS Runtime Evidence 在 Archive 中不存在，因此仍保留明確 Placeholder。

## Current Diagram Inventory

目前有 24 個 Mermaid Block Occurrence：12 個英文 Diagram，以及 12 個拓撲相同的繁體中文版本。

| Location | Diagram |
|---|---|
| Root README Pair | 現行端到端總覽 |
| Root README Pair | 確定性標籤演算法 |
| Root README Pair | Base Tool Agent Loop 與人工閘門 |
| Root README Pair | 人工 Meshtastic 傳送次序 |
| Root README Pair | Alibaba Cloud Backend |
| Architecture Pair | System Context |
| Architecture Pair | Deterministic Algorithm |
| Architecture Pair | Manual Meshtastic Sequence |
| Architecture Pair | Qwen Agent Loop / Human Gate |
| Architecture Pair | Alibaba Cloud Backend |
| Alibaba Cloud Pair | Deployment/Proof Structure |
| EdgeAgent Write-up Pair | Submission Architecture |

全部 24 個 Block 已由 Mermaid `11.12.2` 成功解析；Syntax Error 為零。

## Content Source of Truth

1. `ARCHITECTURE*`：System Diagram / Technical Boundary。
2. `SETUP_GUIDE*`：Installation / Hardware Configuration。
3. `TESTING_GUIDE*`：Fixture、Prompt、Pass/Fail Criteria。
4. `MANUAL*`：Operator Workflow。
5. `ALIBABA_CLOUD*`：Deployment / Proof。
6. `PROJECT_STORY*`、`WRITEUP_EDGEAGENT*`：Competition Narrative。

Old ADR、Retained Optional Module、Internal Planning Note 與上述檔案衝突時，以 Current Source Code 與以上文件為準。
