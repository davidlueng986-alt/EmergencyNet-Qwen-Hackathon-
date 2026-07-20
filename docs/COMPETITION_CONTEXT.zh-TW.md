# Qwen Cloud EdgeAgent 競賽脈絡

[English](COMPETITION_CONTEXT.md) · [官方總覽](https://qwencloud-hackathon.devpost.com/) · [官方規則](https://qwencloud-hackathon.devpost.com/rules) · [官方資源](https://qwencloud-hackathon.devpost.com/resources)

資料於 **2026 年 7 月 19 日（Pacific Time）**核對。官方頁面才是最終權威且可能更新，提交前必須立即再查一次。

## 活動事實

| 項目 | 官方資訊 |
|---|---|
| 活動 | Global AI Hackathon Series with Qwen Cloud |
| Sponsor | Alibaba Cloud |
| Administrator | Devpost |
| Track | Track 5: EdgeAgent |
| Submission Period | 2026-05-26 08:00 PT 至 2026-07-20 14:00 PT |
| Judging | 2026-07-28 08:00 PT 至 2026-08-11 14:00 PT |
| Winner Announcement | 約 2026-08-17 14:00 PT |

官方總覽目前把 EdgeAgent 定義為由 Qwen 驅動的實體裝置，例如 Robot、IoT Agent 或 Smart Hardware：透過 Edge Sensor 感知、利用 Cloud API／Skills 推理，並在本地行動。作品應展示在頻寬／延遲限制下穩健的 Edge-Cloud Orchestration、Privacy-Aware Handling，以及弱網或離線時的 Graceful Degradation。

## 必交內容

- 公開 Code Repository，包含執行專案所需 Source、Assets 與 Instructions。
- 開源 License，且要在 Repository 頁面頂部（包括 GitHub **About**）可見。
- Backend 運行於 Alibaba Cloud 的證明。官方總覽明確要求提供指向 Repository 內、展示 Alibaba Cloud Service/API 用法的 Code File Link。
- 清楚的 Architecture Diagram，連接 Qwen Cloud、Backend、Data、Frontend 與實體 Edge。
- 約三分鐘的公開 Demo Video，放在接受的平台；規則要求影片展示專案在目標平台上實際運作。
- 說明功能與行為的文字敘述。
- 明確標示 EdgeAgent Track。
- Judging Period 內可用的 Working Demo 或 Test Build；如有限制存取，須在 Submission 提供 Credentials。
- 評審所需內容使用英文或附英文翻譯。
- 若專案在 5 月 26 日前已存在，須解釋 Submission Period 內完成的重大更新。

公開 Build Journey Post 為可選；若把連結加到 Submission，可競逐 Blog Post Prize。

## 評分權重

| 準則 | 比例 | EmergencyNet 應明確展示 |
|---|---:|---|
| Technical Depth & Engineering | 30% | Qwen API 分工、Function-Calling Agent、確定性 Codec/Rules、Error Handling、Tests、Edge/Cloud Boundary |
| Innovation & AI Creativity | 30% | 人類治理的 No → Yes Review、Offline-First Safety Split、受限 Mesh Transport、Aggregate Intelligence |
| Problem Value & Impact | 25% | 真實災害通訊缺口、降低認知負荷、全球部署潛力、誠實安全治理 |
| Presentation & Documentation | 15% | 三分鐘故事、實體裝置畫面、易讀圖、可重現安裝、精確 Judge Fixtures |

官方頁面的說明句目前分列在這些 Label 下；兩個 30% 項目都要完整回答，不應只針對其中一段措辭最佳化。

## EmergencyNet 為何符合 EdgeAgent

| EdgeAgent 期待 | EmergencyNet 證據 |
|---|---|
| 實體裝置 | Heltec LoRa 32 V4 與 Android Tablet |
| 感知 | 救援人員結構化觀察、Free Text、可選 Image、人工提供 GPS |
| 雲端推理 | Model Studio OpenAI-Compatible API；`qwen3.7-plus` 與 `qwen3.7-max` |
| 本地行動 | 確定性檢傷／風險決策、Packet Creation、Operator Guidance |
| 受限協調 | 18-byte Patient Record、四人 Hex Batch、LoRa Mesh、明確 Human Handoff |
| 離線降級 | 沒有 API Key 時，Field/Base 的確定性邏輯仍運作 |
| Privacy Awareness | 精簡資料、不把 Image 放上 LoRa、自訂 Mesh PSK、合成 Judge Data |
| 安全自主性 | AI 不可改 Tag、不可 De-escalate、廣播有 Human Approval Gate |

## Code Evidence 對照

| Claim | Repository Evidence |
|---|---|
| Qwen Cloud API | `emergencynet/qwen_client.py`、`emergencynet/ai_config.py` |
| Multilingual/Vision Review | `emergencynet/multilingual.py`、`emergencynet/multimodal.py` |
| Tool Agent | `emergencynet/base_agent.py` |
| Human Send Gate | `emergencynet/base_agent.py`、`emergencynet/action_engine.py` |
| Deterministic Fallback | `emergencynet/screening.py`、`triage_core.py`、`risk_engine.py` |
| Compact Transport | `emergencynet/bit_packer.py` |
| Aggregate Detection | `emergencynet/anomaly_detector.py` |
| Alibaba Deployment | `Dockerfile`、`docker-compose.yml`、`docs/ALIBABA_CLOUD.zh-TW.md` |

## 提交 Checklist

- [ ] 替換全部 `<OWNER>`、`<REPO>`、`<YOUR-DEMO-HOST>`、團隊與 Metrics Placeholder。
- [ ] 把最終 Commit 推到 Public Repository。
- [ ] 在 GitHub About 加入 Apache-2.0。
- [ ] 把 Base 部署到 Alibaba Cloud ECS，並用乾淨 Browser 驗證。
- [ ] 直接連結 `emergencynet/qwen_client.py` 作為 Alibaba Service/API Code Evidence。
- [ ] 錄製已遮蔽敏感資料的 Runtime Proof：ECS Identity、Container、Public URL、Model Studio Request。
- [ ] 錄製公開且不超過三分鐘的 Demo，包含 Android、Heltec Hardware、真實 Mesh Relay、Base Dashboard、Qwen 功能、Offline Fallback 與 Approval Gate。
- [ ] 提供 Judge Steps 與 `docs/TESTING_GUIDE.zh-TW.md` 的精確 Fixture。
- [ ] 明確交代兩個人工 Hex Copy Step 與 Outbound Sender Stub。
- [ ] 在未登入 Owner Account 的情況下測試每個 Public Link。
- [ ] 依即時規則確認 Eligibility、Dates、Accepted Video Host 與所有 Submission Fields。

## 不應使用的說法

- 不可說 12 人 Hex Packet 能放進一段 Meshtastic Text。
- 不可說 Field App 已自動 RF TX。
- 不可把 Base 預設 Stub 稱為真實 Meshtastic Delivery。
- 沒有證據時，不可聲稱臨床認證、實地部署、已拯救生命、效能數據或 Alibaba Runtime Deployment。
- 不可把保留的 Shadow/RAG Experiment File 描述成現行 Live Pipeline。
