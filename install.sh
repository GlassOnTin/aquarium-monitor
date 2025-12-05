#!/bin/bash
#
# Aquarium Monitor Installer
# Installs systemd services for the collector and web interface
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="/etc/systemd/system"

echo "=================================="
echo "  Aquarium Monitor Installer"
echo "=================================="
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run with sudo"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Check VictoriaMetrics is installed
if ! systemctl list-unit-files | grep -q victoria-metrics; then
    echo "Error: VictoriaMetrics is not installed."
    echo "Install it with: sudo apt install victoria-metrics"
    exit 1
fi

# Ask for retention period
echo "How long should sensor data be retained?"
echo
echo "  1) 1 month (default)"
echo "  2) 3 months"
echo "  3) 6 months"
echo "  4) 1 year"
echo "  5) 2 years"
echo "  6) 5 years"
echo "  7) Custom"
echo
read -p "Select option [1-7]: " RETENTION_CHOICE

case $RETENTION_CHOICE in
    1|"") RETENTION="1" ;;
    2) RETENTION="3" ;;
    3) RETENTION="6" ;;
    4) RETENTION="12" ;;
    5) RETENTION="24" ;;
    6) RETENTION="60" ;;
    7)
        read -p "Enter retention period in months: " RETENTION
        if ! [[ "$RETENTION" =~ ^[0-9]+$ ]]; then
            echo "Invalid number. Using default (1 month)."
            RETENTION="1"
        fi
        ;;
    *)
        echo "Invalid choice. Using default (1 month)."
        RETENTION="1"
        ;;
esac

echo
echo "Setting retention period to $RETENTION month(s)..."

# Configure VictoriaMetrics retention - write a clean config
VM_DEFAULT="/etc/default/victoria-metrics"
echo "ARGS=\"-storageDataPath=/var/lib/victoria-metrics -retentionPeriod=$RETENTION\"" > "$VM_DEFAULT"

echo "VictoriaMetrics retention configured."

# Install service files
echo
echo "Installing systemd services..."

cp "$SCRIPT_DIR/aquarium-collector.service" "$SERVICE_DIR/"
cp "$SCRIPT_DIR/aquarium-web.service" "$SERVICE_DIR/"

# Reload systemd
systemctl daemon-reload

# Enable and start services
echo "Enabling services..."
systemctl enable victoria-metrics
systemctl enable aquarium-collector
systemctl enable aquarium-web

echo "Starting services..."
systemctl restart victoria-metrics
sleep 2
systemctl start aquarium-collector
systemctl start aquarium-web

# Wait for services to start
sleep 3

# Check status
echo
echo "=================================="
echo "  Service Status"
echo "=================================="
echo
echo -n "VictoriaMetrics: "
systemctl is-active victoria-metrics || true

echo -n "Aquarium Collector: "
systemctl is-active aquarium-collector || true

echo -n "Aquarium Web: "
systemctl is-active aquarium-web || true

echo
echo "=================================="
echo "  Installation Complete!"
echo "=================================="
echo
echo "Web dashboard: http://192.168.0.180:5000"
echo "VictoriaMetrics: http://192.168.0.180:8428/vmui"
echo
echo "Data retention: $RETENTION month(s)"
echo
echo "Useful commands:"
echo "  sudo systemctl status aquarium-collector"
echo "  sudo systemctl status aquarium-web"
echo "  sudo journalctl -u aquarium-collector -f"
echo "  sudo journalctl -u aquarium-web -f"
echo
