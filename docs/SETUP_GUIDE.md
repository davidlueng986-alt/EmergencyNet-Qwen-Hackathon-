# EmergencyNet complete setup guide

[繁體中文](SETUP_GUIDE.zh-TW.md) · [Project README](../README.md) · [Test runbook](TESTING_GUIDE.md)

This guide installs the current manual-mesh prototype:

`Field Gradio → copy hex → Meshtastic Android → Heltec V4 LoRa mesh → Base Meshtastic client → copy hex → Base dashboard`

It does not claim direct RF transmission from the Field app or automatic ingestion at Base.

## 1. Checklist and supported shape

### Hardware

- Android tablet, Android 7 or later recommended, with Wi-Fi for initial setup and optional Qwen calls.
- Two or more Heltec LoRa 32 **V4** boards. Two endpoints prove radio transfer; a third node makes the relay/mesh behaviour visible.
- LoRa antennas that match each board's frequency version and the legal band in the deployment country.
- Data-capable USB-C cables, power banks/batteries, and a desktop/laptop for Base.
- Optional: second screen or camera so judges can see both Field and Base.

### Software

- Meshtastic firmware and Android app.
- Termux from an official source.
- Python 3.11 recommended for desktop; the recommended tablet path uses Ubuntu 24.04 Python inside Termux PRoot.
- Git or the downloaded project ZIP.
- Optional Qwen Cloud / Alibaba Cloud Model Studio API key.
- Docker Desktop or Docker Engine with Compose for container deployment.

### Before powering a radio

1. Confirm whether each Heltec board is the 863–870 MHz or 902–928 MHz version.
2. Attach a matching LoRa antenna to the U.FL/IPEX connector.
3. Never transmit or flash while the LoRa antenna is absent; the official hardware guidance warns of possible radio damage.
4. Choose a legal Meshtastic region for the physical location. Do not copy a region from this guide without checking local rules.

Heltec V4 uses ESP32-S3R2, SX1262, USB-C, and a LoRa antenna connector. It exposes a GNSS interface, but that is not the same as an onboard GNSS receiver/fix. EmergencyNet currently accepts manually supplied coordinates.

## 2. Flash each Heltec LoRa 32 V4

Use Chrome or Edge on a desktop.

1. Attach the correct antenna, then connect the V4 with a data-capable USB-C cable.
2. Open the official [Meshtastic Web Flasher](https://flasher.meshtastic.org/).
3. Select **Heltec LoRa 32 V4**. Do not select V3/V3.1.
4. Select the current stable release. The V4 firmware filename is shaped like `firmware-heltec-v4-X.X.X....bin`.
5. Click **Flash**. Allow the browser to open the correct serial device.
6. For a first install or a corrupted prior configuration, use the flasher's full erase/install option after noting that it removes radio settings.
7. Wait for completion, disconnect/reconnect if requested, and confirm that the OLED boots Meshtastic.

If the browser cannot enter download mode:

- Try another known data cable and USB port.
- Close Meshtastic clients or serial monitors that may own the port.
- Use the Web Flasher's 1200-baud reset option.
- As an ESP32-S3 fallback, unplug the board, hold **USER**, plug it in, release after two to three seconds, then retry. Button behaviour can change by hardware revision; confirm against the current official device page before forcing a mode.

Repeat for every endpoint and relay. Keep firmware major/minor versions aligned for the demo.

Official references: [ESP32 Web Flasher guide](https://meshtastic.org/docs/getting-started/flashing-firmware/esp32/web-flasher/) and [Heltec LoRa 32 device page](https://meshtastic.org/docs/hardware/devices/heltec-automation/lora32/).

## 3. Install and configure Meshtastic on Android

### Install

Install the official [Meshtastic Android app on Google Play](https://play.google.com/store/apps/details?id=com.geeksville.mesh). The package ID is `com.geeksville.mesh`. Do not install an unrelated app with a similar name.

### Pair the Field radio

1. Power the Field V4 with its antenna attached.
2. Enable Bluetooth and Location on Android and grant the app's requested permissions.
3. In Meshtastic, open **Connect**, scan, select the V4, and accept pairing.
4. Give the node a clear name such as `FIELD-01`.
5. Under the connected device card or **Settings → LoRa**, set the legal **Region**.
6. Choose the same modem preset on every node; keep the default on all nodes for the first test.

The radio does not communicate until its region is set. See [Meshtastic initial configuration](https://meshtastic.org/docs/getting-started/initial-config/).

### Create a private incident channel

The default channel uses a known key and is not suitable for sensitive data.

1. Open **Settings → Channels**.
2. Create or edit the Primary channel; use a short exercise name such as `EN-DRILL-01`.
3. Generate a unique 32-byte/AES-256 PSK in the app.
4. Share the channel QR or URL only with the Base and relay nodes.
5. Import that exact configuration into every node. Region, modem preset, channel index/name, and PSK must match.
6. Keep MQTT uplink/downlink off for the offline radio demo unless MQTT is intentionally part of the exercise.

Meshtastic channel encryption is not equivalent to Signal or modern TLS and does not replace operational identity checks. See [channel configuration](https://meshtastic.org/docs/configuration/radio/channels/) and [encryption limitations](https://meshtastic.org/docs/overview/encryption/).

### Configure Base and relay nodes

- Name the Base endpoint `BASE-01` and a relay `RELAY-01`.
- Apply the same region, modem preset, and private channel.
- Put the relay physically between endpoints for a visible multi-hop test. Do not choose Router/Repeater roles casually; start with the normal Client role and follow Meshtastic's role guidance if tuning a real mesh.
- Send a short `EN LINK CHECK 01` message from Field. Confirm it appears at Base and inspect the delivery state.

For a desktop Base client, attach `BASE-01` over USB and open [Meshtastic Web Client](https://client.meshtastic.org/) in Chrome/Edge. Connect by Serial, select the private channel, and use its Messages view. A second phone can also be used.

## 4. Install Termux and run the Field app

Termux's project states that its official release sources are F-Droid and GitHub; the legacy Play Store build is not the recommended upstream build. Gradio depends on compiled scientific-Python packages. Native Android/Termux wheels are not consistently available, so the reproducible route below runs Ubuntu 24.04 inside Termux's rootless PRoot environment. This is still local, on-device execution; it does not require root or Docker.

1. Install from the [Termux F-Droid page](https://f-droid.org/packages/com.termux/) or the official [termux/termux-app GitHub releases](https://github.com/termux/termux-app/releases).
2. Open Termux and run:

```bash
pkg update
pkg upgrade
pkg install proot-distro
termux-setup-storage
proot-distro install ubuntu:24.04
```

Approve Android's storage prompt. If using the supplied ZIP, first place it in Android **Downloads** and copy it into Ubuntu:

```bash
proot-distro copy "$HOME/storage/downloads/EmergencyNet_Qwen_EdgeAgent_bilingual.zip" ubuntu:/root/
```

Then enter Ubuntu (the following commands after this point run **inside Ubuntu**):

```bash
proot-distro login ubuntu
```

```bash
apt update
apt install -y python3 python3-venv python3-pip git unzip nano
```

If GitHub is public, clone the complete repository; this downloads `requirements-field.txt`, the package, and `data/` together:

```bash
cd "$HOME"
git clone https://github.com/<OWNER>/<REPO>.git emergencynet
cd emergencynet
```

For a ZIP, after using the copy command above, run inside Ubuntu:

```bash
mkdir -p "$HOME/emergencynet"
cd "$HOME/emergencynet"
unzip /root/EmergencyNet_Qwen_EdgeAgent_bilingual.zip
```

Find the directory that directly contains `requirements-field.txt`, `emergencynet/`, and `data/`, then:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-field.txt
cp .env.example .env
nano .env
```

If the project is nested one level after ZIP extraction, `cd` into that folder first. Do not install the full desktop `requirements.txt` on the tablet; it includes radio/base-only packages.

### Native Termux alternative (advanced, device-dependent)

Directly installing Gradio into Termux's Android Python can require source builds of NumPy/Pandas and is therefore **not the recommended demo path**. If you intentionally use it, install Termux's packaged NumPy, expose system packages to the virtual environment, and expect device-specific build work:

```bash
pkg install python python-numpy git unzip nano clang rust libffi
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements-field.txt
```

Failure of this native alternative is not evidence that the application is broken; return to the Ubuntu PRoot path above. The project has not been physically verified on your exact tablet/Android version, so complete this installation before demo day and keep a known-good environment.

For deterministic/offline use, leave the API key blank. For Qwen features, edit `.env`:

```dotenv
DASHSCOPE_API_KEY=replace_me
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_FIELD=qwen3.7-plus
QWEN_MODEL_VISION=qwen3.7-plus
```

Launch Field:

```bash
source .venv/bin/activate
export FIELD_GRADIO_HOST=0.0.0.0
export FIELD_GRADIO_PORT=7860
python -m emergencynet.gradio_app
```

Open `http://127.0.0.1:7860` in the tablet browser. Keep Termux running, disable Android battery optimization for Termux during the demo, and do not expose port 7860 to an untrusted network.

Quick verification:

1. Save one stable ambulatory synthetic patient.
2. Confirm a GREEN tag without an API key.
3. Open **Outbox & Send** and click **Generate hex for manual Mesh relay**.
4. Confirm the output is hex and the status says manual text relay.

## 5. Install and run Base on desktop

Downloading only `requirements.txt` is insufficient—the Python package and `data/` are also required. Clone the repository or download/extract the complete release ZIP. Both methods include `requirements.txt`.

Common Git method on Windows, Linux, or macOS:

```bash
git clone https://github.com/<OWNER>/<REPO>.git emergencynet
cd emergencynet
```

ZIP method: open the public GitHub repository, choose **Code → Download ZIP**, extract it, and open a terminal in the extracted folder. Before continuing, `requirements.txt`, `requirements-field.txt`, `emergencynet/`, and `data/` must be visible together. This is the required “download requirements” step; do not fetch an isolated requirements file from an untrusted mirror.

### Windows Command Prompt

From the project directory:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python -m emergencynet.base_dashboard
```

Open `http://127.0.0.1:7861`.

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

`Set-ExecutionPolicy -Scope Process` lasts only for that terminal. Open `http://127.0.0.1:7861`.

### Linux

Install Python, its venv package, and Git with the distribution package manager. On Debian/Ubuntu, for example:

```bash
sudo apt update
sudo apt install python3 python3-venv git
```

Then from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m emergencynet.base_dashboard
```

### macOS

Install Python 3.11 with the official installer or Homebrew, then:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -m emergencynet.base_dashboard
```

Open `http://127.0.0.1:7861`.

### Base Qwen configuration

Add these values to `.env` for Strategy and Agent features:

```dotenv
DASHSCOPE_API_KEY=replace_me
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL_STRATEGY=qwen3.7-max
QWEN_MODEL_AGENT=qwen3.7-plus
QWEN_AGENT_MAX_STEPS=6
```

Restart Base after editing `.env`, or apply credentials through **Settings**. Do not put a key in screenshots or the repository.

## 6. Perform the current end-to-end mesh transfer

Use synthetic data only.

1. In Field, add at most four patients to the outbox.
2. Click **Generate hex for manual Mesh relay**.
3. Confirm the status reports at most 164 hex characters for four patients.
4. Select and copy only the hex characters—no backticks, label, spaces, or prefix.
5. Switch to Meshtastic Android → **Messages** → private incident channel.
6. Paste and send. A hex character is one text byte; do not exceed the app's approximately 200-byte limit.
7. Observe a relay node if demonstrating multi-hop, and wait for a delivery/receive state.
8. At Base, open the Meshtastic Web/phone client and copy the exact received text.
9. Open Base Dashboard → **Inject test packet**, paste, and click **Inject**.
10. Confirm the decoded patient count, Patient table, SITREP, and any expected anomalies.

If more than four patients remain, click the Field button again to produce the next independent packet. Never split one hex string arbitrarily; every message needs its own valid header and checksums.

## 7. Docker: Field and Base

Docker is intended for desktop/server use, not normal stock Android/Termux.

Create `.env` beside `docker-compose.yml`, then:

```bash
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail=100 field base
```

- Field: `http://localhost:7860`
- Base: `http://localhost:7861`

Run only one service:

```bash
docker compose up --build field
docker compose up --build base
```

Stop without deleting images:

```bash
docker compose down
```

The current manual hex route does not require the container to access USB. Automatic serial radio access would require an explicit device mapping on Linux and is not part of the judge path. See [Docker details](DOCKER.md) and [Alibaba Cloud deployment](ALIBABA_CLOUD.md).

## 8. Verification before a live demo

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Then verify:

- [ ] All radios have antennas, matching legal region, modem preset, channel, and private PSK.
- [ ] A normal text link check travels Field → relay → Base.
- [ ] Field works with the API key removed.
- [ ] Qwen connection check succeeds when the key is restored.
- [ ] Packet A and Packet B in the testing guide each fit one Meshtastic text message.
- [ ] Base ingest triggers the four expected anomaly types after both packets.
- [ ] Agent can draft but cannot send without approval.
- [ ] The default stub is described as a stub, not RF delivery.
- [ ] Browser tabs, fonts, zoom, power, cables, and a backup local software-only path are ready.

## 9. Troubleshooting

| Symptom | Check |
|---|---|
| V4 not visible to flasher | Data cable, different USB port, close serial clients, 1200-baud reset, USER-button fallback |
| Nodes cannot see each other | Region, hardware frequency, modem preset, channel index/name, PSK, antenna, distance |
| Meshtastic says Too Large | Use four or fewer patients; paste hex only; use the prepared fixtures |
| Termux install fails compiling | Use the recommended Ubuntu 24.04 PRoot path; native Termux builds of NumPy/Pandas are device-dependent. Use only `requirements-field.txt` on the tablet |
| `No module named emergencynet` | Run from the directory containing the `emergencynet/` package |
| Port already in use | Set `FIELD_GRADIO_PORT` or `BASE_GRADIO_PORT` to a free port |
| AI offline | Check key, endpoint, internet, model availability in the chosen service scope, then restart/apply Settings |
| Invalid hex at Base | Remove prefix/quotes/newlines; compare received text character-for-character |
| `MALFORMED_PACKET` | Message was truncated/corrupted or is not a complete packet; resend the original independent packet |
| Send says success but no RF message | Default Base broadcaster is a stub; this is expected until a real transport is wired |

## 10. Security and safety

- Use synthetic, non-identifying data in public demos and judge access.
- Use a unique private channel PSK; rotate it after public events.
- Never publish the channel QR/URL or API key.
- Treat lost radios/tablets as potential key compromise.
- Keep public ECS deployment behind HTTPS and access control; restrict SSH to trusted IPs.
- XOR checks are not signatures; verify sender identity operationally.
- The application is a prototype and must not be used as autonomous medical decision-making software.

## Official sources

- [Meshtastic Android onboarding](https://meshtastic.org/docs/software/android/user/onboarding/)
- [Meshtastic initial configuration](https://meshtastic.org/docs/getting-started/initial-config/)
- [Meshtastic messages and channels](https://meshtastic.org/docs/software/android/user/messages-and-channels/)
- [Heltec LoRa 32 V4](https://meshtastic.org/docs/hardware/devices/heltec-automation/lora32/)
- [Termux official site](https://termux.dev/en/)
- [Termux official repository and installation notes](https://github.com/termux/termux-app)
- [Official Termux PRoot-Distro](https://github.com/termux/proot-distro)
- [Alibaba Cloud Model Studio OpenAI compatibility](https://www.alibabacloud.com/help/en/model-studio/compatibility-of-openai-with-dashscope)
