#!/usr/bin/env python3
"""
Aquarium Monitor - Flask Web Service
Logs and graphs data from SEAFRONT WiFi Smart Online 8-in-1 Tester
Uses VictoriaMetrics for time-series storage.
"""

import os
import json
from datetime import datetime
from io import BytesIO

import requests
import tinytuya
import pandas as pd
from flask import Flask, render_template, jsonify, send_file, request

app = Flask(__name__)

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
VM_URL = "http://localhost:8428"

# DPS mappings
DPS_MAP = {
    "8": ("temperature", "Temperature", "°C", 0.1),
    "106": ("ph", "pH", "", 0.01),
    "111": ("tds", "TDS", "ppm", 1),
    "116": ("ec", "EC (Conductivity)", "µS/cm", 1),
    "121": ("salinity", "Salinity", "ppm", 1),
    "126": ("sg", "Specific Gravity", "", 0.001),
    "131": ("orp", "ORP", "mV", 1),
}

# VictoriaMetrics metric names
VM_METRICS = {
    "temperature": "aquarium_temperature_celsius",
    "ph": "aquarium_ph",
    "tds": "aquarium_tds_ppm",
    "ec": "aquarium_ec_uscm",
    "salinity": "aquarium_salinity_ppm",
    "sg": "aquarium_specific_gravity",
    "orp": "aquarium_orp_mv",
}


def get_sensor_reading():
    """Fetch current reading from the aquarium sensor."""
    try:
        d = tinytuya.Device(DEVICE_ID, DEVICE_IP, LOCAL_KEY, version=VERSION)
        d.set_socketTimeout(5)
        result = d.status()

        if "Error" in result:
            return None, result["Error"]

        dps = result.get("dps", {})
        reading = {}
        for dp_id, (col, name, unit, scale) in DPS_MAP.items():
            if dp_id in dps:
                reading[col] = dps[dp_id] * scale

        return reading, None
    except Exception as e:
        return None, str(e)


def query_victoria(metric, hours):
    """Query VictoriaMetrics for time-series data."""
    try:
        # Calculate step based on time range for reasonable data density
        if hours <= 6:
            step = "1m"
        elif hours <= 24:
            step = "5m"
        elif hours <= 168:  # 7 days
            step = "15m"
        else:
            step = "1h"

        resp = requests.get(
            f"{VM_URL}/api/v1/query_range",
            params={
                "query": metric,
                "start": f"-{hours}h",
                "end": "now",
                "step": step,
            },
            timeout=10
        )
        data = resp.json()

        if data["status"] == "success" and data["data"]["result"]:
            result = data["data"]["result"][0]
            values = result["values"]
            return {
                "timestamps": [datetime.fromtimestamp(v[0]).strftime("%Y-%m-%d %H:%M:%S") for v in values],
                "values": [float(v[1]) for v in values],
            }
        return {"timestamps": [], "values": []}
    except Exception as e:
        app.logger.error(f"VictoriaMetrics query failed: {e}")
        return {"timestamps": [], "values": []}


def get_all_readings_from_vm():
    """Get all readings from VictoriaMetrics for Excel export."""
    try:
        # First, find out how much data we have
        resp = requests.get(
            f"{VM_URL}/api/v1/query",
            params={"query": "aquarium_temperature_celsius"},
            timeout=10
        )

        # Query all available data with appropriate step to stay under 30000 points
        # Use 5m for up to ~100 days, 15m for up to ~300 days, 1h for longer
        all_data = {}
        timestamps = None

        # Start with 30 days of 5-minute data (8640 points max)
        hours = 30 * 24
        step = "5m"

        for col, metric in VM_METRICS.items():
            resp = requests.get(
                f"{VM_URL}/api/v1/query_range",
                params={
                    "query": metric,
                    "start": f"-{hours}h",
                    "end": "now",
                    "step": step,
                },
                timeout=60
            )
            data = resp.json()

            if data.get("status") == "success" and data.get("data", {}).get("result"):
                values = data["data"]["result"][0]["values"]
                if timestamps is None:
                    timestamps = [datetime.fromtimestamp(v[0]) for v in values]
                all_data[col] = [float(v[1]) for v in values]

        if timestamps:
            df = pd.DataFrame(all_data)
            df.insert(0, "timestamp", timestamps)
            return df
        return pd.DataFrame()
    except Exception as e:
        app.logger.error(f"Failed to export from VictoriaMetrics: {e}")
        return pd.DataFrame()


@app.route("/")
def index():
    """Main dashboard page."""
    reading, error = get_sensor_reading()
    return render_template("index.html", reading=reading, error=error, dps_map=DPS_MAP)


@app.route("/api/current")
def api_current():
    """Get current sensor reading."""
    reading, error = get_sensor_reading()
    if error:
        return jsonify({"error": error}), 500
    return jsonify(reading)


@app.route("/api/history")
def api_history():
    """Get historical readings from VictoriaMetrics."""
    hours = request.args.get("hours", 24, type=int)

    result = {
        "timestamps": [],
        "temperature": [],
        "ph": [],
        "tds": [],
        "ec": [],
        "salinity": [],
        "sg": [],
        "orp": [],
    }

    # Query each metric
    for col, metric in VM_METRICS.items():
        data = query_victoria(metric, hours)
        if data["timestamps"] and not result["timestamps"]:
            result["timestamps"] = data["timestamps"]
        result[col] = data["values"]

    return jsonify(result)


@app.route("/export/excel")
def export_excel():
    """Export all readings to Excel from VictoriaMetrics."""
    df = get_all_readings_from_vm()

    if df.empty:
        return jsonify({"error": "No data available"}), 404

    # Rename columns for nicer Excel headers
    df = df.rename(columns={
        "timestamp": "Timestamp",
        "temperature": "Temperature (°C)",
        "ph": "pH",
        "tds": "TDS (ppm)",
        "ec": "EC (µS/cm)",
        "salinity": "Salinity (ppm)",
        "sg": "Specific Gravity",
        "orp": "ORP (mV)",
    })

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Aquarium Data")

        # Auto-adjust column widths
        worksheet = writer.sheets["Aquarium Data"]
        for i, col in enumerate(df.columns):
            max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + i)].width = min(max_len, 25)

    output.seek(0)
    filename = f"aquarium_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":
    app.run(host="192.168.0.180", port=5000, debug=True)
