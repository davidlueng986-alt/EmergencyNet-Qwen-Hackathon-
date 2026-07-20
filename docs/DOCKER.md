# Docker deployment

[繁體中文](DOCKER.zh-TW.md) · [Complete setup](SETUP_GUIDE.md) · [Alibaba Cloud](ALIBABA_CLOUD.md)

The same image runs either the Field Gradio app or Base dashboard. The current radio path is manual hex text, so normal containers do not need USB radio access.

## Prerequisites

- Docker Engine 24+ or Docker Desktop
- Docker Compose v2 (`docker compose`)
- At least 2 GB free memory and disk space for image layers
- Complete repository, including `requirements*.txt`, `emergencynet/`, and `data/`

## Configuration

Create an untracked `.env` beside `docker-compose.yml`:

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

Leave keys blank for offline tests. Never bake a key into the image or commit `.env`.

## Build and run both services

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 field base
```

- Field: `http://localhost:7860`
- Base: `http://localhost:7861`

The Dockerfile installs the lean runtime requirements and copies only application code and offline tables. Tests and deprecated RAG dependencies are excluded from the runtime image.

## Run one service

```bash
docker compose up --build field
docker compose up --build base
```

Or detached:

```bash
docker compose up -d --build base
```

## Verify

```bash
curl -I http://127.0.0.1:7860
curl -I http://127.0.0.1:7861
docker compose exec base python -c "from emergencynet.gateway import BaseGateway; print('gateway-ok')"
```

Run the full test suite in the host development venv with `requirements-dev.txt`, then use Packet A/B from [TESTING_GUIDE.md](TESTING_GUIDE.md).

## Lifecycle

```bash
# Follow logs
docker compose logs -f base

# Restart and clear in-memory incident state
docker compose restart base

# Stop/remove containers and network; keep images
docker compose down

# Rebuild after source/requirements changes
docker compose build --no-cache
docker compose up -d
```

Base data is intentionally in memory; restart resets patients and anomaly windows. There is no volume to preserve incident state.

## Ports and security

The compose file publishes 7860 and 7861. On a development machine, bind access through the host firewall. On a cloud host:

- do not expose 7861 directly to the public internet;
- put Base behind HTTPS and authentication on port 443;
- restrict SSH to trusted CIDRs;
- use only synthetic data in the judge instance.

See [ALIBABA_CLOUD.md](ALIBABA_CLOUD.md) for the reverse-proxy pattern and evidence checklist.

## Radio/USB boundary

Current judge path:

1. Field container renders hex.
2. Operator copies it into the Android Meshtastic app.
3. Base Meshtastic client receives it.
4. Operator pastes it into the Base container UI.

No Docker device mapping is needed.

`MESHTASTIC_PORT` and `lora_bridge.py` are an experimental direct raw-packet path, not the current Field transport. If developing it on Linux, a serial device would need a mapping such as `--device=/dev/serial/by-id/<EXACT-ID>`, matching permissions, and App Port 256 on both ends. Docker Desktop on Windows/macOS does not provide the same simple serial pass-through. Do not enable this for the live demo without end-to-end validation.

The Base outbound broadcaster is a stub by default even inside Docker.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| `COPY scripts` build failure from an older archive | Use this Dockerfile; the nonexistent `scripts/` copy was removed |
| Build cannot find a referenced requirement file | Build from repository root; retain every `requirements*.txt` file |
| Port conflict | Change the host side, for example `17861:7861` |
| Base loses patients | Expected after restart; current store is in memory |
| AI unavailable | Check `.env`, outbound HTTPS, endpoint, model scope, then recreate the service |
| Code change not visible | `docker compose build base && docker compose up -d base` |
| RF send missing | Expected with default broadcaster stub; Docker success is not radio proof |

## Termux note

Do not try to run normal Docker Engine on a stock non-rooted Android tablet for this project. Use the Termux + Ubuntu PRoot instructions and `requirements-field.txt` instead; direct Android/Termux Python installation is an advanced, device-dependent fallback.
