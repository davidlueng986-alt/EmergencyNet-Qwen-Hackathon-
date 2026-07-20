# EmergencyNet 完整安裝指南

[English](SETUP_GUIDE.md) · [專案首頁](../README.zh-TW.md) · [測試 Runbook](TESTING_GUIDE.zh-TW.md)

本指南安裝的是目前可運作的人工 Mesh 原型：

`Field Gradio → 複製 hex → Meshtastic Android → Heltec V4 LoRa Mesh → Base Meshtastic Client → 複製 hex → Base Dashboard`

本指南不會把 Field 直接 RF TX 或 Base 自動擷取描述成已完成。

## 1. Checklist 與支援形態

### Hardware

- Android Tablet，建議 Android 7 或以上；初始安裝及可選 Qwen 呼叫需要 Wi-Fi。
- 兩塊或以上 Heltec LoRa 32 **V4**。兩個 Endpoint 可證明 RF；第三個節點可清楚展示 Relay/Mesh。
- 與每塊板的頻段版本及當地合法 Band 相符的 LoRa Antenna。
- 可傳資料的 USB-C Cable、Power Bank/Battery，以及作為 Base 的 Desktop/Laptop。
- 可選：第二個 Screen 或 Camera，讓評審同時看到 Field 與 Base。

### Software

- Meshtastic Firmware 與 Android App。
- 由官方來源取得的 Termux。
- Desktop 建議 Python 3.11；Tablet 建議在 Termux PRoot 內使用 Ubuntu 24.04 Python。
- Git 或已下載的完整專案 ZIP。
- 可選 Qwen Cloud／Alibaba Cloud Model Studio API Key。
- Container 部署需要 Docker Desktop 或 Docker Engine + Compose。

### Radio 上電前

1. 確認 Heltec 是 863–870 MHz 或 902–928 MHz 版本。
2. 把相符的 LoRa Antenna 接到 U.FL/IPEX Connector。
3. 不要在 LoRa Antenna 未接好時傳送或刷機；官方硬體指引警告可能損壞 Radio。
4. 按實際地點選擇合法 Meshtastic Region，不可盲目照抄本指南的某個 Region。

Heltec V4 使用 ESP32-S3R2、SX1262、USB-C 與 LoRa Antenna Connector。它提供 GNSS Interface，但這不等於板上已經有 GNSS Receiver/Fix；EmergencyNet 現在接受人工提供的 Coordinates。

## 2. 刷入 Heltec LoRa 32 V4

在 Desktop 使用 Chrome 或 Edge。

1. 先接好正確 Antenna，再以可傳資料 USB-C Cable 連接 V4。
2. 開啟官方 [Meshtastic Web Flasher](https://flasher.meshtastic.org/)。
3. 選 **Heltec LoRa 32 V4**，不要選 V3/V3.1。
4. 選目前 Stable Release。V4 Firmware File 形式為 `firmware-heltec-v4-X.X.X....bin`。
5. 按 **Flash**，允許 Browser 開啟正確 Serial Device。
6. 第一次安裝或舊設定已損壞時，可用 Full Erase/Install；先理解它會刪除 Radio Settings。
7. 等待完成，按提示重新插拔，確認 OLED 啟動 Meshtastic。

若 Browser 無法進入 Download Mode：

- 換一條已確認可傳資料的 Cable 與 USB Port。
- 關閉可能佔用 Port 的 Meshtastic Client／Serial Monitor。
- 使用 Web Flasher 的 1200-baud Reset。
- ESP32-S3 的 Fallback：拔線、按住 **USER**、重新插線，2–3 秒後放開再試。Button 行為可能因 Revision 而變；強制進入模式前先核對最新官方 Device Page。

每個 Endpoint 與 Relay 都要重複；示範前讓 Firmware Major/Minor 保持一致。

官方來源：[ESP32 Web Flasher Guide](https://meshtastic.org/docs/getting-started/flashing-firmware/esp32/web-flasher/) 與 [Heltec LoRa 32 Device Page](https://meshtastic.org/docs/hardware/devices/heltec-automation/lora32/)。

## 3. 在 Android 安裝及設定 Meshtastic

### 安裝

安裝官方 [Google Play Meshtastic Android App](https://play.google.com/store/apps/details?id=com.geeksville.mesh)，Package ID 為 `com.geeksville.mesh`。不要安裝名稱相似的其他 App。

### 配對 Field Radio

1. 接好 Antenna 後啟動 Field V4。
2. 開啟 Android Bluetooth 與 Location，批准 App 要求的權限。
3. Meshtastic → **Connect** → Scan → 選 V4 → 接受 Pairing。
4. Node 名稱設成 `FIELD-01` 等清楚識別。
5. 在 Connected Device Card 或 **Settings → LoRa** 設定合法 **Region**。
6. 所有 Node 選相同 Modem Preset；第一次測試全部保留相同預設。

未設定 Region 前 Radio 不會開始 Mesh 通訊。詳見 [Meshtastic Initial Configuration](https://meshtastic.org/docs/getting-started/initial-config/)。

### 建立 Private Incident Channel

Default Channel 使用已知 Key，不適合敏感資料。

1. 開啟 **Settings → Channels**。
2. 建立或修改 Primary Channel，使用短名稱，例如 `EN-DRILL-01`。
3. 在 App 產生獨立 32-byte/AES-256 PSK。
4. Channel QR/URL 只分享給 Base 與 Relay Node。
5. 每個 Node 匯入完全相同設定；Region、Modem Preset、Channel Index/Name 與 PSK 必須相同。
6. 除非演練明確使用 MQTT，Offline Radio Demo 應關閉 MQTT Uplink/Downlink。

Meshtastic Channel Encryption 不等同 Signal 或現代 TLS，也不能代替作業身分核對。見 [Channel Configuration](https://meshtastic.org/docs/configuration/radio/channels/) 與 [Encryption Limitations](https://meshtastic.org/docs/overview/encryption/)。

### Base 與 Relay Node

- Base Endpoint 命名 `BASE-01`，Relay 命名 `RELAY-01`。
- 套用相同 Region、Modem Preset 與 Private Channel。
- 若要展示 Multi-Hop，把 Relay 放在兩端中間。不要隨意選 Router/Repeater Role；第一次先用一般 Client，再依 Meshtastic Role 指引調整真實 Mesh。
- 從 Field 發送短訊息 `EN LINK CHECK 01`，確認 Base 收到並查看 Delivery State。

Desktop Base 可把 `BASE-01` 以 USB 連接，使用 Chrome/Edge 開啟 [Meshtastic Web Client](https://client.meshtastic.org/)，用 Serial 連線，在 Private Channel 的 Messages View 收訊；也可使用第二部手機。

## 4. 安裝 Termux 與 Field App

Termux 專案說明官方 Release Source 是 F-Droid 與 GitHub；舊 Play Store Build 不是建議的 Upstream Build。Gradio 依賴含編譯元件的科學 Python 套件，而原生 Android／Termux Wheel 不一定齊全。因此下列可重現路徑會在 Termux 的免 Root PRoot 環境內執行 Ubuntu 24.04。它仍然是 Tablet 本機運算，不需要 Root 或 Docker。

1. 從 [Termux F-Droid Page](https://f-droid.org/packages/com.termux/) 或官方 [termux/termux-app GitHub Releases](https://github.com/termux/termux-app/releases) 安裝。
2. 開啟 Termux：

```bash
pkg update
pkg upgrade
pkg install proot-distro
termux-setup-storage
proot-distro install ubuntu:24.04
```

批准 Android 的 Storage 權限。若使用專案 ZIP，先把它放入 Android **Downloads**，再複製進 Ubuntu：

```bash
proot-distro copy "$HOME/storage/downloads/EmergencyNet_Qwen_EdgeAgent_bilingual.zip" ubuntu:/root/
```

接著進入 Ubuntu；從此處開始的後續指令都在 **Ubuntu 內**執行：

```bash
proot-distro login ubuntu
```

```bash
apt update
apt install -y python3 python3-venv python3-pip git unzip nano
```

若 GitHub 已公開，Clone 會同時下載 `requirements-field.txt`、Package 與 `data/`：

```bash
cd "$HOME"
git clone https://github.com/<OWNER>/<REPO>.git emergencynet
cd emergencynet
```

若使用 ZIP，執行上面的 Copy 指令後，在 Ubuntu 內執行：

```bash
mkdir -p "$HOME/emergencynet"
cd "$HOME/emergencynet"
unzip /root/EmergencyNet_Qwen_EdgeAgent_bilingual.zip
```

找到直接包含 `requirements-field.txt`、`emergencynet/` 與 `data/` 的資料夾：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-field.txt
cp .env.example .env
nano .env
```

若 ZIP 解壓後多了一層專案資料夾，請先 `cd` 進去。Tablet 不要安裝完整 Desktop `requirements.txt`；其中包含僅供 Radio／Base 使用的套件。

### 原生 Termux 替代路徑（進階、依裝置而異）

直接把 Gradio 安裝到 Termux 的 Android Python 可能需要從 Source 編譯 NumPy／Pandas，因此**不建議作為 Demo 主路徑**。若確定要採用，請安裝 Termux 封裝的 NumPy、讓 Venv 可見系統套件，並預期仍需處理裝置特有的編譯問題：

```bash
pkg install python python-numpy git unzip nano clang rust libffi
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-field.txt
```

原生替代路徑失敗不代表本專案程式失效；請改用上面的 Ubuntu PRoot 路徑。本專案尚未在你的確切 Tablet／Android 版本完成實機驗證，務必在 Demo 前完成安裝並保留已知可用環境。

只用確定性／離線功能時，把 API Key 留白。啟用 Qwen 時編輯 `.env`：

```dotenv
DASHSCOPE_API_KEY=replace_me
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_FIELD=qwen3.7-plus
QWEN_MODEL_VISION=qwen3.7-plus
```

啟動 Field：

```bash
source .venv/bin/activate
export FIELD_GRADIO_HOST=0.0.0.0
export FIELD_GRADIO_PORT=7860
python -m emergencynet.gradio_app
```

Tablet Browser 開 `http://127.0.0.1:7860`。示範時保持 Termux 運行、關閉 Android 對 Termux 的 Battery Optimization，並勿把 7860 Port 暴露在不可信網路。

快速驗證：

1. 儲存一名生命徵象穩定、可行走的合成傷患。
2. 沒有 API Key 時仍顯示 GREEN。
3. **Outbox & Send** → **Generate hex for manual Mesh relay**。
4. 確認輸出是 Hex，Status 明確顯示 Manual Text Relay。

## 5. Desktop 安裝與運行 Base

只下載 `requirements.txt` 不足夠；Python Package 與 `data/` 也需要。請 Clone Repository 或下載／解壓完整 Release ZIP；兩者都包含 `requirements.txt`。

Windows、Linux、macOS 通用 Git 方法：

```bash
git clone https://github.com/<OWNER>/<REPO>.git emergencynet
cd emergencynet
```

ZIP 方法：在 Public GitHub Repository 選 **Code → Download ZIP**，Extract 後在該 Folder 開 Terminal。繼續前，`requirements.txt`、`requirements-field.txt`、`emergencynet/`、`data/` 必須在同一層可見。這就是所需的「下載 requirements」步驟；不要從不可信 Mirror 單獨取得 Requirements File。

### Windows Command Prompt

在 Project Directory：

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python -m emergencynet.base_dashboard
```

開啟 `http://127.0.0.1:7861`。

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m emergencynet.base_dashboard
```

`Set-ExecutionPolicy -Scope Process` 只在該 Terminal 有效。開啟 `http://127.0.0.1:7861`。

### Linux

以 Distribution Package Manager 安裝 Python、Venv 與 Git。Debian/Ubuntu 例子：

```bash
sudo apt update
sudo apt install python3 python3-venv git
```

在 Project Directory：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m emergencynet.base_dashboard
```

### macOS

使用官方 Installer 或 Homebrew 安裝 Python 3.11：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m emergencynet.base_dashboard
```

開啟 `http://127.0.0.1:7861`。

### Base Qwen 設定

在 `.env` 加入：

```dotenv
DASHSCOPE_API_KEY=replace_me
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_STRATEGY=qwen3.7-max
QWEN_MODEL_AGENT=qwen3.7-plus
QWEN_AGENT_MAX_STEPS=6
```

修改後重啟 Base，或在 **Settings** 套用 Credentials。不要在 Screenshot 或 Repository 放入 Key。

## 6. 執行現行端到端 Mesh 傳輸

只使用合成資料。

1. Field Outbox 加入最多四名傷患。
2. 按 **Generate hex for manual Mesh relay**。
3. 四人時確認 Status 不超過 164 Hex Characters。
4. 只複製 Hex Characters，不要帶 Backtick、Label、Space 或 Prefix。
5. 切到 Meshtastic Android → **Messages** → Private Incident Channel。
6. 貼上並傳送。每個 Hex Character 是一個 Text Byte；不要超過 App 約 200-byte Limit。
7. 展示 Multi-Hop 時觀察 Relay Node，等待 Delivery/Receive State。
8. 在 Base Meshtastic Web/Phone Client 複製收到的完整文字。
9. Base Dashboard → **Inject test packet** → 貼上 → **Inject**。
10. 確認 Decoded Patient Count、Patient Table、SITREP 與預期 Anomaly。

若仍有超過四人留在 Outbox，再按一次 Field Button 產生下一個獨立 Packet。不可任意把一段 Hex 從中間切開；每段 Message 都要有自己的完整 Header 與 Checksums。

## 7. Docker：Field 與 Base

Docker 供 Desktop/Server 使用，不是一般 Stock Android/Termux 路徑。

在 `docker-compose.yml` 旁建立 `.env`：

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 field base
```

- Field：`http://localhost:7860`
- Base：`http://localhost:7861`

只跑一個 Service：

```bash
docker compose up --build field
docker compose up --build base
```

停止但保留 Image：

```bash
docker compose down
```

現行人工 Hex 路徑不需要 Container 存取 USB。自動 Serial Radio Access 在 Linux 需要明確 Device Mapping，而且不屬於 Judge Path。詳見 [Docker](DOCKER.zh-TW.md) 與 [Alibaba Cloud](ALIBABA_CLOUD.zh-TW.md)。

## 8. Live Demo 前驗證

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

- [ ] 所有 Radio 已接 Antenna，Legal Region、Modem Preset、Channel、Private PSK 相符。
- [ ] 一段普通 Link Check 可經 Field → Relay → Base。
- [ ] 移除 API Key 後 Field 仍可用。
- [ ] 恢復 Key 後 Qwen Connection Check 成功。
- [ ] 測試指南 Packet A/B 各自能放入一段 Meshtastic Text。
- [ ] Base 先後 Ingest 兩段後觸發四個預期 Anomaly Type。
- [ ] Agent 可建立 Draft，但未核准時不能 Send。
- [ ] 把預設 Stub 稱作 Stub，而不是 RF Delivery。
- [ ] Browser Tab、Font、Zoom、Power、Cable 與本機 Software-Only Backup 已準備。

## 9. Troubleshooting

| 症狀 | 檢查 |
|---|---|
| Flasher 看不到 V4 | Data Cable、USB Port、關閉 Serial Client、1200-baud Reset、USER Fallback |
| Node 互相看不到 | Region、Hardware Frequency、Modem Preset、Channel Index/Name、PSK、Antenna、Distance |
| Meshtastic 顯示 Too Large | 四人或以下；只貼 Hex；使用預製 Fixture |
| Termux Compile 失敗 | 改用建議的 Ubuntu 24.04 PRoot 路徑；原生 Termux 編譯 NumPy／Pandas 會因裝置而異。Tablet 只使用 `requirements-field.txt` |
| `No module named emergencynet` | 從直接含 `emergencynet/` Package 的 Directory 執行 |
| Port 已佔用 | 設定其他 `FIELD_GRADIO_PORT` 或 `BASE_GRADIO_PORT` |
| AI Offline | 檢查 Key、Endpoint、Internet、Service Scope 可用模型，重啟／套用 Settings |
| Base 顯示 Invalid Hex | 移除 Prefix/Quotes/Newlines；逐字比對收訊文字 |
| `MALFORMED_PACKET` | Message 被截斷／損壞或不是完整 Packet；重送原始獨立 Packet |
| Send 顯示成功但沒有 RF | 預設 Base Broadcaster 是 Stub；未接 Real Transport 前屬預期行為 |

## 10. Security 與 Safety

- 公開 Demo/Judge Access 只使用合成且不可識別個人的資料。
- 使用獨立 Private Channel PSK，公開活動後 Rotate。
- 不可公開 Channel QR/URL 或 API Key。
- Radio/Tablet 遺失時視為 Key 可能外洩。
- Public ECS 應使用 HTTPS 與 Access Control；SSH 只允許 Trusted IP。
- XOR 不是 Signature；操作層仍要驗證 Sender Identity。
- 本 App 是原型，不可用作自主醫療決策軟體。

## 官方來源

- [Meshtastic Android Onboarding](https://meshtastic.org/docs/software/android/user/onboarding/)
- [Meshtastic Initial Configuration](https://meshtastic.org/docs/getting-started/initial-config/)
- [Meshtastic Messages and Channels](https://meshtastic.org/docs/software/android/user/messages-and-channels/)
- [Heltec LoRa 32 V4](https://meshtastic.org/docs/hardware/devices/heltec-automation/lora32/)
- [Termux Official Site](https://termux.dev/en/)
- [Termux Official Repository and Installation Notes](https://github.com/termux/termux-app)
- [Termux 官方 PRoot-Distro](https://github.com/termux/proot-distro)
- [Alibaba Cloud Model Studio OpenAI Compatibility](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
