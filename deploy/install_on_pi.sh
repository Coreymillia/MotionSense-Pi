#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/motionsense-pi}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
SERVICE_NAME="motionsense-pi"

if [[ ! -f "$APP_DIR/main.py" ]]; then
  echo "Expected app at $APP_DIR but main.py was not found."
  exit 1
fi

sudo apt update
sudo apt install -y python3-venv python3-sense-hat sense-hat i2c-tools

if command -v raspi-config >/dev/null 2>&1; then
  sudo raspi-config nonint do_i2c 0 || true
fi

rm -rf "$APP_DIR/.venv"
python3 -m venv --system-site-packages "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

sudo tee "/etc/systemd/system/${SERVICE_NAME}.service" >/dev/null <<EOF
[Unit]
Description=MotionSense Pi dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

echo "MotionSense Pi is running on port 8080."
echo "If the Sense HAT was just enabled, reboot the Pi before trusting sensor status."
