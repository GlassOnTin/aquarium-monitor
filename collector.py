#!/usr/bin/env python3
"""
Aquarium Data Collector
Reads sensor data and writes to VictoriaMetrics every 5 minutes.
"""

import os
import json
import time
import logging
import requests
import tinytuya

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Load configuration
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    DEVICE_ID = config.get("device_id", "")
    DEVICE_IP = config.get("device_ip", "")
    LOCAL_KEY = config.get("local_key", "")
    VERSION = config.get("protocol_version", 3.5)
else:
    # Fallback to hardcoded values (for backwards compatibility)
    DEVICE_ID = "bfe0cad26f6fbd00c8v7dn"
    DEVICE_IP = "192.168.0.215"
    LOCAL_KEY = "v.X0.aJ~eBK/5ruE"
    VERSION = 3.5

# VictoriaMetrics configuration
VM_URL = "http://localhost:8428/api/v1/import/prometheus"

# Collection interval (seconds)
INTERVAL = 300  # 5 minutes

# DPS mappings: dp_id -> (metric_name, scale_factor)
DPS_MAP = {
    "8": ("aquarium_temperature_celsius", 0.1),
    "106": ("aquarium_ph", 0.01),
    "111": ("aquarium_tds_ppm", 1),
    "116": ("aquarium_ec_uscm", 1),
    "121": ("aquarium_salinity_ppm", 1),
    "126": ("aquarium_specific_gravity", 0.001),
    "131": ("aquarium_orp_mv", 1),
}


def get_sensor_reading():
    """Fetch current reading from the aquarium sensor."""
    try:
        d = tinytuya.Device(DEVICE_ID, DEVICE_IP, LOCAL_KEY, version=VERSION)
        d.set_socketTimeout(10)
        result = d.status()

        if "Error" in result:
            log.error(f"Sensor error: {result['Error']}")
            return None

        return result.get("dps", {})
    except Exception as e:
        log.error(f"Failed to read sensor: {e}")
        return None


def write_to_victoria(dps):
    """Write metrics to VictoriaMetrics in Prometheus format."""
    lines = []
    timestamp_ms = int(time.time() * 1000)

    for dp_id, (metric_name, scale) in DPS_MAP.items():
        if dp_id in dps:
            value = dps[dp_id] * scale
            # Prometheus exposition format: metric_name{labels} value timestamp
            lines.append(f'{metric_name}{{sensor="seafront_8in1"}} {value} {timestamp_ms}')

    if not lines:
        log.warning("No data points to write")
        return False

    payload = "\n".join(lines)

    try:
        resp = requests.post(VM_URL, data=payload, timeout=10)
        if resp.status_code == 204:
            log.info(f"Wrote {len(lines)} metrics to VictoriaMetrics")
            return True
        else:
            log.error(f"VictoriaMetrics error: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        log.error(f"Failed to write to VictoriaMetrics: {e}")
        return False


def collect_once():
    """Single collection cycle."""
    dps = get_sensor_reading()
    if dps:
        write_to_victoria(dps)
        # Log current values
        readings = []
        for dp_id, (name, scale) in DPS_MAP.items():
            if dp_id in dps:
                readings.append(f"{name.split('_')[1]}={dps[dp_id] * scale:.2f}")
        log.info(f"Current: {', '.join(readings)}")


def main():
    """Main collection loop."""
    log.info(f"Starting aquarium collector (interval: {INTERVAL}s)")
    log.info(f"Device: {DEVICE_IP}, VictoriaMetrics: {VM_URL}")

    while True:
        try:
            collect_once()
        except Exception as e:
            log.error(f"Collection error: {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
