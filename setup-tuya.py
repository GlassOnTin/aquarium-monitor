#!/usr/bin/env python3
"""
Tuya Device Setup Wizard
Guides users through obtaining device credentials for local access.
"""

import os
import sys
import json

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def print_header():
    print()
    print("=" * 60)
    print("  Aquarium Monitor - Tuya Device Setup")
    print("=" * 60)
    print()

def print_step(num, title):
    print()
    print(f"─── Step {num}: {title} ───")
    print()

def get_input(prompt, default=None):
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    return input(f"{prompt}: ").strip()

def setup_tuya_cloud():
    print_step(1, "Create Tuya IoT Platform Account")
    print("1. Go to: https://iot.tuya.com/")
    print("2. Click 'Start Free Trial' or 'Log In'")
    print("3. Create an account (or use Google/GitHub login)")
    print()
    input("Press Enter when done...")

    print_step(2, "Create a Cloud Project")
    print("1. Go to: Cloud → Development")
    print("2. Click 'Create Cloud Project'")
    print("3. Fill in:")
    print("   - Project Name: Aquarium Monitor (or anything)")
    print("   - Industry: Smart Home")
    print("   - Development Method: Smart Home")
    print("   - Data Center: Select your region:")
    print("       • Western Europe - UK, Ireland, Portugal")
    print("       • Central Europe - Germany, France, etc.")
    print("       • US West / US East - Americas")
    print("       • India - South Asia")
    print("       • China - China only")
    print()
    print("   TIP: If unsure, try Central Europe first for EU users.")
    print()
    input("Press Enter when done...")

    print_step(3, "Get API Credentials")
    print("1. Click on your project name")
    print("2. You'll see 'Access ID/Client ID' and 'Access Secret/Client Secret'")
    print("3. Copy these values:")
    print()

    api_key = get_input("Access ID/Client ID")
    api_secret = get_input("Access Secret/Client Secret")

    print()
    print("4. Select your data center region:")
    print("   eu     - Europe")
    print("   us     - United States")
    print("   cn     - China")
    print("   in     - India")
    print()
    api_region = get_input("Region code", "eu")

    print_step(4, "Subscribe to API Services")
    print("1. In your project, go to 'Service API' tab")
    print("2. Click 'Go to Authorize' for each of these:")
    print("   - IoT Core")
    print("   - Authorization Token Management")
    print("   - Smart Home Scene Linkage (if available)")
    print("3. Subscribe to each (they're free)")
    print()
    input("Press Enter when done...")

    print_step(5, "Link Your Smart Life App")
    print("1. In your project, go to 'Devices' tab")
    print("2. Click 'Link Tuya App Account'")
    print("3. A QR code will appear")
    print("4. On your phone (Smart Life or Tuya Smart app):")
    print("   - Go to 'Me' tab")
    print("   - Tap the scan icon (top right)")
    print("   - Scan the QR code")
    print("5. Confirm the linking")
    print()
    print("NOTE: The app account must be the one that has the")
    print("      aquarium sensor paired to it!")
    print()
    print("If you get 'Data centers inconsistency' error:")
    print("  → Change the data center in the top-right dropdown")
    print("  → Try: Central Europe for UK accounts")
    print()
    input("Press Enter when your device appears in the Devices tab...")

    return api_key, api_secret, api_region


def fetch_device_info(api_key, api_secret, api_region):
    print_step(6, "Fetching Device Information")

    try:
        import tinytuya
    except ImportError:
        print("Error: tinytuya not installed")
        print("Run: pip install tinytuya")
        return None

    # Write temp config for tinytuya
    config = {
        "apiKey": api_key,
        "apiSecret": api_secret,
        "apiRegion": api_region,
        "apiDeviceID": "All"
    }

    temp_config = os.path.join(os.path.dirname(__file__), "tinytuya.json")
    with open(temp_config, "w") as f:
        json.dump(config, f)

    print("Connecting to Tuya Cloud...")
    print()

    try:
        import tinytuya.wizard as wizard
        # Use tinytuya's cloud API directly
        cloud = tinytuya.Cloud(
            apiRegion=api_region,
            apiKey=api_key,
            apiSecret=api_secret
        )

        devices = cloud.getdevices()

        if not devices:
            print("No devices found. Make sure you've linked your app account.")
            return None

        print(f"Found {len(devices)} device(s):")
        print()

        aquarium_devices = []
        for i, dev in enumerate(devices):
            name = dev.get('name', 'Unknown')
            dev_id = dev.get('id', '')
            category = dev.get('category', '')
            print(f"  {i+1}. {name}")
            print(f"     ID: {dev_id}")
            print(f"     Category: {category}")
            print()

            # Look for water quality monitors
            if category in ['dgnbj', 'wsdcg'] or 'water' in name.lower() or 'aqua' in name.lower() or 'ph' in name.lower():
                aquarium_devices.append(dev)

        if not aquarium_devices:
            aquarium_devices = devices

        if len(aquarium_devices) == 1:
            selected = aquarium_devices[0]
        else:
            print("Select your aquarium sensor (enter number):")
            choice = int(input("> ")) - 1
            selected = devices[choice]

        return {
            "device_id": selected.get('id'),
            "local_key": selected.get('key'),
            "name": selected.get('name'),
            "ip": selected.get('ip', '')
        }

    except Exception as e:
        print(f"Error fetching devices: {e}")
        print()
        print("You can manually enter the Device ID from the Tuya IoT Platform:")
        print("  → Go to Devices tab → Click on your device → Copy the Device ID")
        print()
        device_id = get_input("Device ID")

        # Try to get local key via API
        try:
            cloud = tinytuya.Cloud(
                apiRegion=api_region,
                apiKey=api_key,
                apiSecret=api_secret
            )
            result = cloud.getdevices()
            for dev in result:
                if dev.get('id') == device_id:
                    return {
                        "device_id": device_id,
                        "local_key": dev.get('key'),
                        "name": dev.get('name', 'Aquarium Sensor'),
                        "ip": dev.get('ip', '')
                    }
        except:
            pass

        return {"device_id": device_id, "local_key": None, "name": "Aquarium Sensor", "ip": ""}


def scan_network():
    print_step(7, "Scanning Network for Device")

    try:
        import tinytuya
        print("Scanning local network for Tuya devices...")
        print("(This may take 20 seconds)")
        print()

        devices = tinytuya.deviceScan(verbose=False)

        if devices:
            print(f"Found {len(devices)} Tuya device(s) on network:")
            for ip, info in devices.items():
                print(f"  {ip}: {info.get('gwId', 'unknown')}")
            return devices
        else:
            print("No devices found via broadcast.")
            print("The device may not broadcast, but can still work if you know its IP.")
    except Exception as e:
        print(f"Scan error: {e}")

    return {}


def test_connection(device_id, local_key, ip):
    print()
    print("Testing connection to device...")

    try:
        import tinytuya
        d = tinytuya.Device(device_id, ip, local_key, version=3.5)
        d.set_socketTimeout(10)
        result = d.status()

        if "Error" in result:
            # Try other versions
            for ver in [3.4, 3.3, 3.1]:
                d = tinytuya.Device(device_id, ip, local_key, version=ver)
                d.set_socketTimeout(10)
                result = d.status()
                if "dps" in result:
                    print(f"✓ Connected successfully (protocol v{ver})")
                    return ver, result
            print(f"✗ Connection failed: {result.get('Error')}")
            return None, result

        print("✓ Connected successfully (protocol v3.5)")
        return 3.5, result

    except Exception as e:
        print(f"✗ Connection error: {e}")
        return None, {}


def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Configuration saved to: {CONFIG_FILE}")


def main():
    print_header()

    print("This wizard will help you set up local access to your")
    print("Tuya-based aquarium sensor (SEAFRONT, YIERYI, etc.)")
    print()
    print("You will need:")
    print("  • A Tuya IoT Platform account (free)")
    print("  • The Smart Life or Tuya Smart app with your device paired")
    print("  • Your aquarium sensor on the same network as this computer")
    print()

    proceed = input("Ready to begin? (Y/n): ").strip().lower()
    if proceed == 'n':
        print("Setup cancelled.")
        return

    # Get cloud credentials and device info
    api_key, api_secret, api_region = setup_tuya_cloud()
    device_info = fetch_device_info(api_key, api_secret, api_region)

    if not device_info:
        print("Failed to get device information. Please try again.")
        return

    print()
    print(f"Device: {device_info['name']}")
    print(f"ID: {device_info['device_id']}")
    print(f"Local Key: {device_info['local_key']}")

    # Get device IP
    if not device_info.get('ip'):
        print()
        print("Enter the device's IP address.")
        print("(Check your router's DHCP list or use a network scanner)")
        print()
        device_info['ip'] = get_input("Device IP address")

    # Test connection
    version, result = test_connection(
        device_info['device_id'],
        device_info['local_key'],
        device_info['ip']
    )

    if version and "dps" in result:
        print()
        print("Current readings:")
        dps = result['dps']
        if '8' in dps:
            print(f"  Temperature: {dps['8'] * 0.1:.1f}°C")
        if '106' in dps:
            print(f"  pH: {dps['106'] * 0.01:.2f}")
        if '116' in dps:
            print(f"  EC: {dps['116']} µS/cm")

    # Save configuration
    config = {
        "device_id": device_info['device_id'],
        "device_ip": device_info['ip'],
        "local_key": device_info['local_key'],
        "protocol_version": version or 3.5,
        "tuya_api_key": api_key,
        "tuya_api_secret": api_secret,
        "tuya_region": api_region
    }

    print()
    save_config(config)

    print()
    print("=" * 60)
    print("  Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  1. Run: sudo ./install.sh")
    print("  2. Access dashboard at: http://<your-ip>:5000")
    print()


if __name__ == "__main__":
    main()
