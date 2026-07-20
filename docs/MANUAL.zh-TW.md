# EmergencyNet 操作手冊

[English](MANUAL.md) · [安裝](SETUP_GUIDE.zh-TW.md) · [測試](TESTING_GUIDE.zh-TW.md) · [架構](ARCHITECTURE.zh-TW.md)

> **原型安全聲明：**EmergencyNet 不是獲認證醫療器材，也不取代當地 Incident Command、Triage、Medical、Privacy 或 Radio Regulation。任何真實操作評估都只能由當地 Authority 下受訓人員進行；Public Demo 必須使用合成資料。

## 1. 現行 Operating Concept

EmergencyNet 有三個 Human Role：

| Role | Responsibility |
|---|---|
| Field Responder | 觀察、輸入資料、覆核 Deterministic Output、接受／拒絕 AI Suggestion、Relay Packet Hex |
| Base Operator | 接收 Mesh Text、驗證／複製 Hex、Ingest Packet、監控 Data Quality/Dashboard |
| Incident Commander | 解讀 Aggregate Information，核准 Operational Decision 與所有 Outbound Message |

現行 Patient Data Flow：

`Field Form → Deterministic Result → Four-patient Packet → Hex → Meshtastic Text → Heltec V4 Mesh → Base Meshtastic Text → Hex Inject → Gateway/SITREP/Anomalies`

AI 是可選 Enrichment，不擁有 Tag 或 Broadcast。

## 2. Pre-Incident Readiness

### 每日／Demo 開始前

- [ ] 每塊 Heltec V4 上電前已接 Matching Antenna。
- [ ] Legal Region、Modem Preset、Private Channel、PSK 相同。
- [ ] 實體標籤：`FIELD-01`、`RELAY-01`、`BASE-01`。
- [ ] 發 `EN LINK CHECK <sequence>`，確認 Base Receipt。
- [ ] Field 7860、Base 7861 已啟動。
- [ ] 無 AI 跑一次 GREEN Synthetic Evaluation。
- [ ] Release Build 執行 `python -m pytest -q`。
- [ ] 使用 Qwen 時完成 Connection Check，畫面不暴露 Key。
- [ ] 準備 Packet A/B Fixture、Charger、Cable 與 Software-Only Backup。
- [ ] Public/Alibaba Deployment 只含 Synthetic Data，並有 Access Control。

### Incident Identifier

加入 Patient 前統一 Team ID 與 Zone Code。Demo 用 Team `7`、Zone `4`；真實 Exercise 由 Incident Plan 定義。Patient ID 只存一個 Byte，因此使用 `0–255` Numeric ID，並避免同一測試重複。

## 3. Field Operation

### A. 輸入觀察

1. 開 Field Gradio。
2. 輸入 Patient ID、Team、Zone、Walking、Age、Breathing/RR、Radial Pulse、Mental、Pain、Injury、Special Marker 與相關 Conditional Field。
3. 只有取得已驗證 Latitude/Longitude 時才輸入。Heltec V4 GNSS Interface 不會自動把位置送進此 App。
4. Notes 只寫簡潔 Observation，不寫姓名或不必要 Identifier。
5. 除非已有合法批准的 Operational Policy，Image 只用 Staged/Synthetic Exercise。

### B. Deterministic Evaluate

按 **Evaluate (deterministic)**，檢查：

- Tag；
- Q1–Q12；
- Hidden Risk；
- Confidence；
- `needs_human_review`；
- Rationale / Priority Score。

Safety-Critical Answer 為 `Unknown` 時，先取得缺失 Observation 或升級給 Responsible Human。不可用 AI 隱藏 Uncertainty。

### C. 可選 Qwen Review

Deterministic Result 存在後，才使用 **Ask field AI to review notes**、**Multilingual notes review**、**Vision review**。

允許 Sequence：

1. Qwen 回傳 Findings / Candidate qkey。
2. Operator 檢查 Evidence。
3. 只選有根據 qkey。
4. 按 **Apply accepted escalations & re-evaluate**。
5. Deterministic Core 重新計算。

AI 只可 No → Yes，不可 Yes → No、Silently Apply 或 Direct Radio Send。AI 不可用或可疑時，忽略並繼續 Deterministic Path。

### D. Save / Packet

1. 覆核後按 **Save patient → outbox**。
2. 重複，最多四人。
3. **Outbox & Send** 檢查 Rank/Count。
4. 按 **Generate hex for manual Mesh relay**。
5. Status 應顯示最多四人、最多 164 Hex Characters。

超過四人時 UI 會保留剩餘 Patient；第一段 Relay 後再產生下一個 Independent Packet。不可任意切開一段 Hex。

## 4. Field-to-Base Meshtastic Relay

1. 只複製生成 Hex，不帶 Label/Punctuation。
2. Meshtastic Android → **Messages** → Private Incident Channel。
3. Paste / Send。
4. 等待 Client Delivery State；量度 Metrics 時記錄時間／狀態。
5. Base 使用連接 `BASE-01` 的 Meshtastic Web Client 或第二 Mobile Client。
6. 複製真正收到的 Text。聲稱 Real RF Test 時，不可從原 Field Screen Copy。
7. 必要時比對 Length：1 人 56、3 人 128、4 人 164 Hex Characters。
8. Message Truncated 或 Too Large 時丟棄，改用較小完整 Packet 重送。

使用 Custom Private PSK。Default Meshtastic Channel Key 已公開；Channel Encryption 不能取代 Operator/Node Identity 與 Lost Device Protection。

## 5. Base Operation

### A. Ingest

1. Base → **Inject test packet**。
2. Paste 只含 Received Hex。
3. 按 **Inject**。
4. Decoded Count 應等於 Field Batch。
5. Error 時不要隨機修改後重貼；比對 Original/Received Text，重送完整 Packet。

`MALFORMED_PACKET` 是 Safe Rejection，不應終止 Gateway。

### B. Review State

- **Patients：**ID、Tag、Confidence、Risk qkey、Injury、Age。
- **SITREP：**Packet Ingest 後 Refresh。
- **Map：**除非接上 Verified Source，Location 視為 Approximate/Manual。
- **Broadcasts：**Arm Action Engine 後，New Anomaly Type 可產生 Draft。
- **Advisor：**要求 Structured Support；分清 Fact、Advice、Uncertainty。

Gateway 保留 Capped In-Memory List；Restart 會清除。重播同一 Packet 目前會產生 Duplicate。

### C. Aggregate Alert

| Alert | Current Trigger | Operator Action |
|---|---|---|
| `RESP_CLUSTER` | ≥5 人且 ≥50% 呼吸異常 | 驗證 Data Quality，向 Command 升級 Pattern |
| `BURN_CLUSTER` | ≥3 人且 ≥60% Burns | 驗證 Source/Scene Context，通知 Command |
| `CRUSH_CLUSTER` | ≥3 Entrapped | 驗證 Report，通知 Command |
| `RED_SURGE` | 10 分鐘內 ≥5 RED | 驗證 Time Window，通知 Command |

Alert 是 Advisory，不改 Patient Tag。依 Local Protocol，不可把 Generic Software Message 當作命令。

## 6. Strategy / Agent

### Strategy Advisor

以 Live State 問 Narrowly Scoped Question：

```text
Using only the live snapshot, separate observed facts, recommended next actions, and uncertainties for the next 10 minutes. Do not invent resources or outcomes.
```

Model-Supplied Fact 必須跟 Dashboard 核對。Strategy Output 是 Advice，不是 Execution。

### Tool Agent

Agent 可讀 Snapshot/Patients/Anomalies、Build SITREP、Create Draft；沒有改 Tag Tool。

```text
Inspect live state with tools, report exact counts, and create one concise alert draft. Do not send it.
```

Agent Loop 會把所有 Model-Originated Send Request 視為未核准，即使 Model Argument 寫 `human_approved=true`。

### Human Approval

1. 閱讀完整 Draft、Severity、Anomaly Type、Live Evidence。
2. Ambiguous/Unsafe/Unsupported 時 Edit 或 Redraft。
3. 把 Draft ID Copy 到獨立 Send Control。
4. 由 Incident Commander—not Model—按 **Approve & Send draft**。
5. 記錄 Configured Transport Result。

本 Dashboard 的 Configured Broadcaster 是 Demo Stub。Success 只證明 Approval Path/Application Audit，不證明 Radio Message 已離開 Base。真實 Exercise 應人工 Copy Approved Text 到 Meshtastic，或先接通／驗證 Real Sender 才聲稱 Transmission。

## 7. Offline Mode

Qwen／Internet 失效：

1. Field/Base 保持運行。
2. 繼續 Deterministic Field Evaluation。
3. 繼續 Four-Patient Packet / Meshtastic Relay。
4. 繼續 Base Decode、Patient List、SITREP、Anomaly Detection。
5. 標示 AI Advice/Draft Unavailable；不要反覆 Retry 擁塞 Link。
6. 依 Local Incident-Command Procedure 與普通 Radio Voice/Text 協調。

Offline 是 Designed Mode，不代表可繞過 Human Review。

## 8. Failure Response

| Failure | Response |
|---|---|
| Radio Node Missing | Power、Antenna、Region/Channel/PSK、Distance、Relay Placement |
| Text Too Large | 最多四人；送 Independent Packet |
| Invalid Hex | 移除 Label/Quote/Space；Copy Exact Received Text |
| Malformed Packet | Discard；重送 Original Complete Packet；不可猜測修復 |
| Duplicate Patients | Demo 前 Restart；Operations 中標示 Replay Limitation 並人工 Reconcile |
| AI Timeout/Error | 繼續 Deterministic Path；只在有用時 Retry |
| AI Suggests De-escalation | Reject；Parser/Core 應阻擋；記錄為 Test Failure |
| Agent Claims Sent | 查 Tool/Audit Result，不信 Prose |
| Stub Returns Success | 不可稱為 RF Delivery |
| Public ECS Unavailable | 使用 Local Base，Deployment Evidence 分開保留 |

## 9. End-of-Incident/Demo

- 記錄 Build SHA、Device/Firmware Version、Region、Topology、Packet Delivery Evidence、Error、Operator Action。
- 只 Export/Capture Synthetic 或 Properly Authorized Data。
- Judging Period 後停止 Public Access 或 Rotate Judge Credential。
- Public Event 後 Rotate Meshtastic PSK。
- Shared Device 移除 API Key；畫面曾顯示的 Key 必須 Rotate。
- Restart Base 清除 In-Memory Demo Record。
- Log Defect，分開 Verified Fact 與 Proposed Roadmap。

## 10. Non-Negotiable Limitations

- Field/Base 人工 Hex Copy 是現行 Workflow。
- 12 人 Binary Packet 轉 Hex 後不能放入一段 Meshtastic Text。
- Base Outbound Radio 預設未接通。
- XOR 不是 Authentication。
- 沒有 Replay Protection/Deduplication。
- 沒有 Durable Database/Persistent Audit Log。
- 不聲稱 Clinical Certification/Validation。
- 保留的 `shadow_inference.py`、`comparator.py`、Optional RAG File 不屬於 Active Product Layer。

精確 Packet 與 Acceptance Criteria 見[測試指南](TESTING_GUIDE.zh-TW.md)。
