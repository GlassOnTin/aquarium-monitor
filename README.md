# Aquarium Monitor

Local monitoring dashboard for Tuya-based aquarium water quality sensors (SEAFRONT, YIERYI, and similar WiFi 8-in-1 testers).

## Features

- **Real-time readings**: Temperature, pH, TDS, EC, Salinity, ORP, Specific Gravity
- **Historical graphs**: Interactive charts with time range selection (1h to 1y)
- **Local storage**: Data stored in VictoriaMetrics time-series database
- **Excel export**: Download all historical data
- **No cloud dependency**: Reads directly from sensor over local network

## Supported Devices

- SEAFRONT R72ECM5BIQ-13 (WiFi Smart Online 8-in-1 Tester)
- YIERYI WiFi pH/TDS/EC meters
- Other Tuya-based water quality monitors with similar DPS mappings

## Requirements

- Linux system (Ubuntu/Debian tested)
- Python 3.10+
- The aquarium sensor on the same local network
- Smart Life or Tuya Smart app with the device paired

## Quick Start

### 1. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3-venv victoria-metrics
```

### 2. Clone and Setup

```bash
git clone https://github.com/yourusername/aquarium-monitor.git
cd aquarium-monitor
python3 -m venv venv
./venv/bin/pip install tinytuya flask pandas openpyxl plotly requests
```

### 3. Configure Tuya Access

Run the setup wizard:

```bash
./venv/bin/python setup-tuya.py
```

This will guide you through:
1. Creating a Tuya IoT Platform account
2. Getting API credentials
3. Linking your Smart Life app
4. Finding your device's Local Key

### 4. Install Services

```bash
sudo ./install.sh
```

Choose your data retention period (1 month to 5 years).

### 5. Access Dashboard

Open http://YOUR_IP:5000 in a browser.

## Manual Configuration

If you prefer to configure manually, create `config.json`:

```json
{
  "device_id": "your_device_id",
  "device_ip": "192.168.1.100",
  "local_key": "your_local_key",
  "protocol_version": 3.5
}
```

Then update `collector.py` and `app.py` with your device details.

## Tuya Setup Guide

### Getting Your Device Credentials

The trickiest part is obtaining the **Local Key** from Tuya's cloud. Here's the process:

#### Step 1: Tuya IoT Platform Account

1. Go to [iot.tuya.com](https://iot.tuya.com/)
2. Create a free account

#### Step 2: Create Cloud Project

1. Navigate to **Cloud** → **Development**
2. Click **Create Cloud Project**
3. Settings:
   - **Project Name**: Anything (e.g., "Aquarium")
   - **Industry**: Smart Home
   - **Development Method**: Smart Home
   - **Data Center**: Match your region (see below)

**Data Center Selection**:
| Your Location | Data Center |
|--------------|-------------|
| UK, Ireland | Central Europe (not Western!) |
| Western EU | Central Europe |
| Germany, France | Central Europe |
| US | US West or US East |
| India | India |
| China | China |

#### Step 3: Get API Credentials

In your project, find:
- **Access ID/Client ID**
- **Access Secret/Client Secret**

#### Step 4: Subscribe to APIs

Go to **Service API** tab and subscribe to:
- IoT Core
- Authorization Token Management

#### Step 5: Link Your App Account

1. Go to **Devices** tab
2. Click **Link Tuya App Account**
3. Scan the QR code with your Smart Life / Tuya Smart app
4. Your devices should appear

#### Step 6: Get Device Details

Click on your device to see:
- **Device ID**
- **Local Key** (under device details or via API Explorer)

### Troubleshooting

**"Data centers inconsistency" when linking app**
- Your app account is in a different region than your project
- Change the data center dropdown (top-right of Tuya IoT Platform)
- UK accounts are often in "Central Europe", not "Western Europe"

**Device not responding locally**
- Ensure device and computer are on same network
- Check device IP hasn't changed (set static IP in router)
- Try different protocol versions (3.1, 3.3, 3.4, 3.5)

**"permission deny" from API**
- Subscribe to required APIs in Service API tab
- Wait a few minutes for permissions to propagate

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Aquarium Sensor │────▶│    collector.py  │────▶│ VictoriaMetrics │
│  (Tuya WiFi)    │     │  (every 5 min)   │     │   (port 8428)   │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
                                                          ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │     Browser      │◀────│     app.py      │
                        │                  │     │   (port 5000)   │
                        └──────────────────┘     └─────────────────┘
```

## DPS Mappings

For SEAFRONT/YIERYI 8-in-1 sensors:

| DPS ID | Parameter | Scale | Unit |
|--------|-----------|-------|------|
| 8 | Temperature | ×0.1 | °C |
| 106 | pH | ×0.01 | - |
| 111 | TDS | ×1 | ppm |
| 116 | EC | ×1 | µS/cm |
| 121 | Salinity | ×1 | ppm |
| 126 | Specific Gravity | ×0.001 | - |
| 131 | ORP | ×1 | mV |

## Service Management

```bash
# Check status
sudo systemctl status aquarium-collector
sudo systemctl status aquarium-web

# View logs
sudo journalctl -u aquarium-collector -f
sudo journalctl -u aquarium-web -f

# Restart services
sudo systemctl restart aquarium-collector
sudo systemctl restart aquarium-web
```

## License

MIT License
