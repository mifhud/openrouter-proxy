#!/bin/bash

# Kilocode Proxy Service Installation Script (Venv Version)

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
VENV_DIR="${APP_DIR}/venv"

# Get current user (the one who ran sudo)
CURRENT_USER="${SUDO_USER:-$USER}"

# Check if config.yml exists
if [ ! -f "${APP_DIR}/config.yml" ]; then
  echo "Error: config.yml not found in ${APP_DIR}"
  echo "Please create config.yml from config.yml.example before installing the service"
  exit 1
fi

# Check if venv exists
if [ ! -d "${VENV_DIR}" ] || [ ! -f "${VENV_DIR}/bin/python" ]; then
  echo "Error: Python virtual environment not found or incomplete in ${VENV_DIR}"
  echo "Please create and activate the venv first:"
  echo "  python3 -m venv ${APP_DIR}/venv"
  echo "  source ${APP_DIR}/venv/bin/activate"
  echo "  pip install -r ${APP_DIR}/requirements.txt"
  exit 1
fi


echo "Installing Kilocode Proxy (Venv) as a systemd service..."
echo "Application directory: ${APP_DIR}"
echo "Virtual environment: ${VENV_DIR}"
echo "Service will run as user: ${CURRENT_USER}"

# Create systemd service file
cat > "${SERVICE_FILE}" << EOL
[Unit]
Description=Kilocode API Proxy Service (Venv)
After=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${APP_DIR}
# Use python from the virtual environment
ExecStart=${VENV_DIR}/bin/python ${APP_DIR}/main.py
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