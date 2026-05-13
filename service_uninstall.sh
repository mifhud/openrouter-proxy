#!/bin/bash

# Kilocode Proxy Service Uninstallation Script

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script as root or with sudo"
  exit 1
fi

APP_NAME="kilocode-proxy"
SERVICE_NAME="${APP_NAME}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

echo "Uninstalling Kilocode Proxy systemd service..."

# Check if service exists
if [ ! -f "${SERVICE_FILE}" ]; then
  echo "Service ${SERVICE_NAME} not found. Nothing to uninstall."
  exit 0
fi

# Stop and disable the service
echo "Stopping and disabling ${SERVICE_NAME}..."
systemctl stop "${SERVICE_NAME}"
systemctl disable "${SERVICE_NAME}"

# Remove the service file
echo "Removing service file: ${SERVICE_FILE}"
rm -f "${SERVICE_FILE}"

# Reload systemd
echo "Reloading systemd configuration..."
systemctl daemon-reload

echo "Service uninstalled successfully!" 