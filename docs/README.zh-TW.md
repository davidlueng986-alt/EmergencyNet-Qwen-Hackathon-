# EmergencyNet 文件中心

[English](README.md) · [專案首頁](../README.zh-TW.md)

本索引把現行操作文件與可選／歷史內容分開。現行文件只描述此 Repository 已真正接通的程式路徑。

## 從這裡開始

| 文件 | 用途 |
|---|---|
| [安裝指南](SETUP_GUIDE.zh-TW.md) | Heltec V4、Meshtastic、Android/Termux、桌面、Docker 與驗證 |
| [測試與現場示範](TESTING_GUIDE.zh-TW.md) | 合成情境、精確 hex Fixture、AI Prompt、預期結果與評審 Runbook |
| [系統架構](ARCHITECTURE.zh-TW.md) | 現行系統邊界、確定性演算法、封包、Mesh Sequence、Agent Loop 與 Alibaba Cloud 圖 |
| [操作手冊](MANUAL.zh-TW.md) | 安全操作流程、Field/Base Checklist、失敗模式與限制 |
| [文件 Audit](DOCUMENTATION_AUDIT.zh-TW.md) | Legacy Findings、Mermaid Replacement Inventory 與 Source-of-Truth Rules |
| [讀者審查](DOCUMENTATION_REVIEW.zh-TW.md) | 普通讀者／評審逐輪審查、失敗原因、修正及最終品質閘門 |

## 競賽文件

| 文件 | 用途 |
|---|---|
| [Qwen Cloud 競賽脈絡](COMPETITION_CONTEXT.zh-TW.md) | 官方 EdgeAgent 要求、日期、評分準則與提交 Checklist |
| [EdgeAgent Write-up](WRITEUP_EDGEAGENT.zh-TW.md) | 可直接整理到提交頁的技術敘述 |
| [Alibaba Cloud 部署](ALIBABA_CLOUD.zh-TW.md) | ECS 部署、Code/Runtime Proof、架構圖與證據 Checklist |
| [專案故事與 Pitches](PROJECT_STORY.zh-TW.md) | Elevator Pitch、靈感、建造歷程、學習、影響與未核實資訊 Placeholder |

上述每份使用者文件均有對應英文版本。

## 支援與歷史內容

- [`adr/`](adr/) 記錄架構決策；部分舊 ADR 提及已移除實驗，若有衝突，以現行架構文件為準。
- [Civilian App Integration](CIVILIAN_APP_INTEGRATION.md) 是可選、非核心整合概念，不是 EdgeAgent 示範必要路徑。
- [Cleanup Plan](CLEANUP_PLAN.md) 是內部歷史規劃，不是操作指南。
- `data/json_cleaned/`、`strategy_rag.py`、`shadow_inference.py`、`comparator.py` 是保留的可選／舊程式，不在現行 Runtime Path。
- 被排除的 `legacy file` 目錄不是 Source of Truth，因此不列入索引。

## 文件真實性規則

1. 檢傷標籤只由確定性程式決定。
2. AI 只能建議 No → Yes 升級，且必須由人接受。
3. 現行傷患 Radio Transport 是 Meshtastic 內的人工 hex 文字接力。
4. 除非明確接上真實 Transport，Base 出站 Sender 目前是 Stub。
5. 沒有人工核准，AI 不可發出任何廣播。
6. EmergencyNet 是原型，不是獲認證醫療器材。
7. Placeholder URL、團隊事實、部署識別碼與效能數據，提交前必須換成已驗證資訊。
