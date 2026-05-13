#!/bin/bash

# Kilocode Proxy Service Installation Script

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script as root or with sudo"
  exit 1
fi

# Get the absolute path of the application directory
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="kilocode-proxy"
SERVICE_NAME="${APP_NAME}.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

# Get current user (the one who ran sudo)
CURRENT_USER="${SUDO_USER:-$USER}"

# Check if config.yml exists
if [ ! -f "${APP_DIR}/config.yml" ]; then
  echo "Error: config.yml not found in ${APP_DIR}"
  echo "Please create config.yml from config.yml.example before installing the service"
  exit 1
fi

echo "Installing Kilocode Proxy as a systemd service..."
echo "Application directory: ${APP_DIR}"
echo "Service will run as user: ${CURRENT_USER}"

# Create systemd service file
cat > "${SERVICE_FILE}" << EOL
[Unit]
Description=Kilocode API Proxy Service
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOL

echo "Created systemd service file: ${SERVICE_FILE}"

# Reload systemd to recognize the new service
systemctl daemon-reload
echo "Systemd configuration reloaded"

# Enable and start the service
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo "Service installed and started successfully!"
echo "You can check the status with: systemctl status ${SERVICE_NAME}"
echo "View logs with: journalctl -u ${SERVICE_NAME} -f" 