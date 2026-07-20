# Agent instructions — EmergencyNet Qwen123

**Workspace only:** `EmergencyNet_v5.Qwen123/emergencynet_v5`

## Rules

1. Deterministic triage owns tags; AI escalate **No→Yes** only.  
2. Models: field/vision/agent **qwen3.7-plus**; strategy **qwen3.7-max** (+ thinking + JSON repair if needed).  
3. **No qwen-mt-lite** — plus handles multilingual notes directly.  
4. **No cite_protocol** on mesh drafts.  
5. **No base shadow** — do not reintroduce.  
6. Broadcast: draft via tools; **human_approved** to send.  
7. Non-thinking JSON paths: `json_mode=True`, **omit max_tokens**.  
8. Thinking + JSON: use `chat_json` (structured + official repair workaround).  
9. Canonical docs: **MANUAL.md** / **MANUAL.zh-TW.md**; SETUP standalone; WRITEUP standalone; this file for agents.  
10. Never commit API keys. Do not “fix” KI-01/02 unless owner asks.  
11. No Gemma/Colab primary framing in new text.
