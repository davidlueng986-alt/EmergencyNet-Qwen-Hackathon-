# ADR 0006：Qwen Cloud 作為可選 AI Backend

- **狀態：** 已接受，2026-07-19 修訂
- **日期：** 2026-07-17
- **Workspace：** EmergencyNet_v5.Qwen123
- **English：** [0006-qwen-cloud.md](0006-qwen-cloud.md)

## 背景

競賽版本以 Qwen Cloud EdgeAgent 為目標。本機 Gemma／llama.cpp／Ollama 預設值與平台方向不一致，也會增加 Demo 操作複雜度。

## 決策

所有可選 AI 功能都透過 `qwen_client.py` 使用 Alibaba Cloud Model Studio 的 DashScope OpenAI 相容 API：

- Field／Vision／Agent：`qwen3.7-plus`
- Strategy：`qwen3.7-max` + Thinking
- 多語 Field Notes：直接由 `qwen3.7-plus` 處理，不增加獨立翻譯模型 Hop。

確定性檢傷保留在本機，且可離線運作。AI 是可選功能，只能提出升級建議；它不擁有醫療標籤，也不能核准廣播。

## 結果

+ 操作更單純、Agent／Tool 品質更一致，並符合 Hackathon 的 Qwen Cloud 方向。
− AI 功能需要 API Key 與網路。
− Cloud 路徑不可用時 AI 功能會停止，但確定性檢傷與操作流程持續運作。
− Demo 前必須在目標 Alibaba Cloud Account 核對 Model ID 與 Service Scope 可用性。
