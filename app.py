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
PRESETS_FILE = os.path.join(os.path.dirname(__file__), "tank_presets.json")
DIARY_FILE = os.path.join(os.path.dirname(__file__), "diary.json")

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    DEVICE_ID = config.get("device_id", "")
    DEVICE_IP = config.get("device_ip", "")
    LOCAL_KEY = config.get("local_key", "")
    VERSION = config.get("protocol_version", 3.5)
    TANK_TYPE = config.get("tank_type", "freshwater_tropical")
else:
    # Fallback to hardcoded values (for backwards compatibility)
    DEVICE_ID = "bfe0cad26f6fbd00c8v7dn"
    DEVICE_IP = "192.168.0.215"
    LOCAL_KEY = "v.X0.aJ~eBK/5ruE"
    VERSION = 3.5
    TANK_TYPE = "freshwater_tropical"

# Load tank presets
if os.path.exists(PRESETS_FILE):
    with open(PRESETS_FILE) as f:
        TANK_PRESETS = json.load(f)
else:
    TANK_PRESETS = {}

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


@app.route("/api/presets")
def api_presets():
    """Get available tank type presets."""
    presets_summary = {}
    for key, preset in TANK_PRESETS.items():
        presets_summary[key] = {
            "name": preset["name"],
            "description": preset["description"]
        }
    return jsonify({
        "current": TANK_TYPE,
        "presets": presets_summary
    })


@app.route("/api/ranges")
def api_ranges():
    """Get safe parameter ranges for current tank type."""
    tank_type = request.args.get("type", TANK_TYPE)
    if tank_type not in TANK_PRESETS:
        return jsonify({"error": f"Unknown tank type: {tank_type}"}), 404

    preset = TANK_PRESETS[tank_type]
    ranges = dict(preset["ranges"])

    # Calculate dynamic ranges based on 7-day rolling mean
    # This adapts to local water conditions automatically

    # pH: ±0.5 around mean (stability matters more than absolute value)
    ph_data = query_victoria(VM_METRICS["ph"], 168)  # 7 days
    if ph_data["values"]:
        ph_values = [v for v in ph_data["values"] if v is not None]
        if ph_values:
            ph_mean = sum(ph_values) / len(ph_values)
            ranges["ph"] = {
                "min": 6.5,  # Absolute low limit
                "max": 8.5,  # Absolute high limit
                "ideal_min": max(6.5, ph_mean - 0.5),
                "ideal_max": min(8.5, ph_mean + 0.5),
                "unit": "",
                "dynamic": True,
                "mean": round(ph_mean, 2)
            }

    # EC: ±20% around mean (varies with water source)
    ec_data = query_victoria(VM_METRICS["ec"], 168)
    if ec_data["values"]:
        ec_values = [v for v in ec_data["values"] if v is not None]
        if ec_values:
            ec_mean = sum(ec_values) / len(ec_values)
            ranges["ec"] = {
                "min": max(0, ec_mean * 0.5),    # Absolute: 50% of mean
                "max": ec_mean * 1.5,             # Absolute: 150% of mean
                "ideal_min": ec_mean * 0.8,       # Ideal: ±20%
                "ideal_max": ec_mean * 1.2,
                "unit": "µS/cm",
                "dynamic": True,
                "mean": round(ec_mean, 0)
            }

    # TDS: ±20% around mean (tracks with EC)
    tds_data = query_victoria(VM_METRICS["tds"], 168)
    if tds_data["values"]:
        tds_values = [v for v in tds_data["values"] if v is not None]
        if tds_values:
            tds_mean = sum(tds_values) / len(tds_values)
            ranges["tds"] = {
                "min": max(0, tds_mean * 0.5),
                "max": tds_mean * 1.5,
                "ideal_min": tds_mean * 0.8,
                "ideal_max": tds_mean * 1.2,
                "unit": "ppm",
                "dynamic": True,
                "mean": round(tds_mean, 0)
            }

    # Salinity: ±20% around mean (for freshwater, tracks minerals)
    sal_data = query_victoria(VM_METRICS["salinity"], 168)
    if sal_data["values"]:
        sal_values = [v for v in sal_data["values"] if v is not None]
        if sal_values:
            sal_mean = sum(sal_values) / len(sal_values)
            ranges["salinity"] = {
                "min": max(0, sal_mean * 0.5),
                "max": sal_mean * 1.5,
                "ideal_min": sal_mean * 0.8,
                "ideal_max": sal_mean * 1.2,
                "unit": "ppm",
                "dynamic": True,
                "mean": round(sal_mean, 0)
            }

    # ORP: ±15% around mean (indicates water quality/oxidation)
    orp_data = query_victoria(VM_METRICS["orp"], 168)
    if orp_data["values"]:
        orp_values = [v for v in orp_data["values"] if v is not None]
        if orp_values:
            orp_mean = sum(orp_values) / len(orp_values)
            ranges["orp"] = {
                "min": max(0, orp_mean * 0.7),    # Wider absolute range
                "max": orp_mean * 1.3,
                "ideal_min": orp_mean * 0.85,     # Tighter ideal: ±15%
                "ideal_max": orp_mean * 1.15,
                "unit": "mV",
                "dynamic": True,
                "mean": round(orp_mean, 0)
            }

    return jsonify({
        "tank_type": tank_type,
        "name": preset["name"],
        "ranges": ranges
    })


# Common event types with suggested emojis
EVENT_TYPES = {
    "water_change": {"emoji": "💧", "label": "Water Change"},
    "feed": {"emoji": "🍽️", "label": "Feeding"},
    "medication": {"emoji": "💊", "label": "Medication"},
    "fertilizer": {"emoji": "🌱", "label": "Fertilizer"},
    "filter_clean": {"emoji": "🧹", "label": "Filter Cleaned"},
    "fish_added": {"emoji": "🐟", "label": "Fish Added"},
    "fish_removed": {"emoji": "😢", "label": "Fish Removed"},
    "plant_added": {"emoji": "🌿", "label": "Plant Added"},
    "maintenance": {"emoji": "🔧", "label": "Maintenance"},
    "test": {"emoji": "🧪", "label": "Water Test"},
    "observation": {"emoji": "👁️", "label": "Observation"},
    "other": {"emoji": "📝", "label": "Note"},
}


def load_diary():
    """Load diary entries from JSON file."""
    if os.path.exists(DIARY_FILE):
        try:
            with open(DIARY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_diary(entries):
    """Save diary entries to JSON file."""
    with open(DIARY_FILE, "w") as f:
        json.dump(entries, f, indent=2)


@app.route("/api/diary")
def api_diary_list():
    """Get diary entries, optionally filtered by time range."""
    entries = load_diary()

    # Optional time filtering
    start = request.args.get("start")
    end = request.args.get("end")
    hours = request.args.get("hours", type=int)

    if hours:
        cutoff = datetime.now().timestamp() - (hours * 3600)
        entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]).timestamp() >= cutoff]
    elif start:
        entries = [e for e in entries if e["timestamp"] >= start]
        if end:
            entries = [e for e in entries if e["timestamp"] <= end]

    return jsonify({
        "entries": entries,
        "event_types": EVENT_TYPES
    })


@app.route("/api/diary", methods=["POST"])
def api_diary_add():
    """Add a new diary entry."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    event_type = data.get("event_type", "other")
    note = data.get("note", "")
    timestamp = data.get("timestamp", datetime.now().isoformat())
    emoji = data.get("emoji") or EVENT_TYPES.get(event_type, {}).get("emoji", "📝")

    entry = {
        "id": int(datetime.now().timestamp() * 1000),  # Simple unique ID
        "timestamp": timestamp,
        "event_type": event_type,
        "emoji": emoji,
        "note": note,
    }

    entries = load_diary()
    entries.append(entry)
    entries.sort(key=lambda x: x["timestamp"], reverse=True)  # Most recent first
    save_diary(entries)

    return jsonify({"success": True, "entry": entry})


@app.route("/api/diary/<int:entry_id>", methods=["DELETE"])
def api_diary_delete(entry_id):
    """Delete a diary entry."""
    entries = load_diary()
    entries = [e for e in entries if e["id"] != entry_id]
    save_diary(entries)
    return jsonify({"success": True})


@app.route("/api/event_types")
def api_event_types():
    """Get available event types with emojis."""
    return jsonify(EVENT_TYPES)


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
