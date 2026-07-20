# Docker 部署

[English](DOCKER.md) · [完整安裝](SETUP_GUIDE.zh-TW.md) · [Alibaba Cloud](ALIBABA_CLOUD.zh-TW.md)

同一 Image 可運行 Field Gradio 或 Base Dashboard。現行 Radio Path 是人工 Hex Text，因此正常 Container 不需要 USB Radio Access。

## Prerequisites

- Docker Engine 24+ 或 Docker Desktop
- Docker Compose v2（`docker compose`）
- 至少 2 GB 可用 Memory 與 Image Disk Space
- 完整 Repository，包括 `requirements*.txt`、`emergencynet/`、`data/`

## Configuration

在 `docker-compose.yml` 旁建立不受版本控制的 `.env`：

```dotenv
DASHSCOPE_API_KEY=
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_FIELD=qwen3.7-plus
QWEN_MODEL_VISION=qwen3.7-plus
QWEN_MODEL_STRATEGY=qwen3.7-max
QWEN_MODEL_AGENT=qwen3.7-plus
QWEN_AGENT_MAX_STEPS=6
QWEN_TIMEOUT_SEC=60
GATEWAY_PATIENT_CAP=500
```

Offline Test 時 Key 留白。不可把 Key Bake Into Image 或 Commit `.env`。

## Build / Run Both

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 field base
```

- Field：`http://localhost:7860`
- Base：`http://localhost:7861`

Dockerfile 安裝 Lean Runtime Requirements，只複製 Application Code 與 Offline Tables；Tests 與 Deprecated RAG Dependencies 已排除 Runtime Image。

## 只運行一個 Service

```bash
docker compose up --build field
docker compose up --build base
```

Detached：

```bash
docker compose up -d --build base
```

## Verify

```bash
curl -I http://127.0.0.1:7860
curl -I http://127.0.0.1:7861
docker compose exec base python -c "from emergencynet.gateway import BaseGateway; print('gateway-ok')"
```

Full Test Suite 請在 Host Development Venv 安裝 `requirements-dev.txt` 後執行，再使用 [TESTING_GUIDE.zh-TW.md](TESTING_GUIDE.zh-TW.md) Packet A/B。

## Lifecycle

```bash
# Follow logs
docker compose logs -f base

# Restart 並清除 In-Memory Incident State
docker compose restart base

# Stop/Remove Container/Network；保留 Image
docker compose down

# Source/Requirements 改變後 Rebuild
docker compose build --no-cache
docker compose up -d
```

Base Data 刻意只在記憶體；Restart 會清除 Patient/Anomaly Window。沒有保存 Incident State 的 Volume。

## Ports / Security

Compose Publish 7860/7861。Development Machine 由 Host Firewall 限制；Cloud Host：

- 不公開 7861；
- Base 放在 Port 443 的 HTTPS/Authentication 後；
- SSH 只允許 Trusted CIDR；
- Judge Instance 只用 Synthetic Data。

Reverse Proxy Pattern 與 Evidence Checklist 見 [ALIBABA_CLOUD.zh-TW.md](ALIBABA_CLOUD.zh-TW.md)。

## Radio／USB Boundary

現行 Judge Path：

1. Field Container 顯示 Hex。
2. Operator Copy 到 Android Meshtastic App。
3. Base Meshtastic Client 收到。
4. Operator Paste 到 Base Container UI。

不需要 Docker Device Mapping。

`MESHTASTIC_PORT` / `lora_bridge.py` 是 Experimental Direct Raw-Packet Path，不是現行 Field Transport。在 Linux 開發時 Serial Device 需要例如 `--device=/dev/serial/by-id/<EXACT-ID>`、正確 Permission，並在兩端用 App Port 256。Windows/macOS Docker Desktop 沒有相同簡單 Serial Pass-Through。未完成 E2E Validation 前不要在 Live Demo 啟用。

Docker 內的 Base Outbound Broadcaster 預設仍是 Stub。

## Troubleshooting

| 症狀 | Resolution |
|---|---|
| 舊 Archive 有 `COPY scripts` Build Failure | 使用本 Dockerfile；不存在的 `scripts/` Copy 已移除 |
| Build 找不到 Requirement File | 從 Repository Root Build，保留所有 `requirements*.txt` |
| Port Conflict | 修改 Host Side，例如 `17861:7861` |
| Base Lost Patients | Restart 後屬預期；Current Store In-Memory |
| AI Unavailable | 檢查 `.env`、Outbound HTTPS、Endpoint、Model Scope，Recreate Service |
| Code Change 不可見 | `docker compose build base && docker compose up -d base` |
| 沒有 RF Send | Default Broadcaster Stub 的預期行為；Docker Success 不是 Radio Proof |

## Termux Note

本專案不要在一般 Non-Rooted Android Tablet 嘗試正常 Docker Engine；請用 Termux + Ubuntu PRoot 與 `requirements-field.txt`。直接安裝到 Android／Termux Python 只屬進階、依裝置而異的後備路徑。
