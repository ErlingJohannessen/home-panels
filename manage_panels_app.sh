#!/bin/bash
set -euo pipefail

SERVICE_NAME="panels-app.service"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"
log_file="/var/log/panels.log"

# -----------------------------
# Determine "present user"
# - If run via sudo, use SUDO_USER (the original user)
# - Otherwise, use current user
# -----------------------------
detect_user() {
  if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    echo "${SUDO_USER}"
  else
    id -un
  fi
}

# Get home directory robustly
home_of_user() {
  local u="$1"
  getent passwd "$u" | cut -d: -f6
}

deploy_service() {
  echo "Deploying service..."

  local user
  user="$(detect_user)"
  local user_home
  user_home="$(home_of_user "$user")"

  if [[ -z "$user_home" ]]; then
    echo "ERROR: Could not determine home directory for user: $user"
    exit 1
  fi

  local working_directory="${user_home}/home-panels"
  local python_path="${working_directory}/.venv/bin/python"

  # App paths (kept as in your script, but based on user's home)
  local app_paths="${working_directory}/src/home.py \
${working_directory}/src/vehiclemap.py \
${working_directory}/src/imageviewer.py \
${working_directory}/src/charts.py"

  # Create systemd service file
  sudo tee "$SERVICE_FILE_PATH" >/dev/null <<EOF
[Unit]
Description=Panel apps service
After=network.target

[Service]
Type=simple
User=${user}
WorkingDirectory=${working_directory}

ExecStart=${python_path} -m panel serve ${app_paths} \\
  --address 0.0.0.0 \\
  --port 5010 \\
  --log-level info \\
  --root-path /restricted/panels \\
  --index=home \\
  --allow-websocket-origin accretiosolutions.com \\
  --allow-websocket-origin www.accretiosolutions.com

Restart=always
StandardOutput=append:${log_file}
StandardError=append:${log_file}

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  echo "Service deployed as user: ${user}"
  echo "WorkingDirectory: ${working_directory}"
}

undeploy_service() {
  echo "Undeploying service..."
  sudo systemctl stop "$SERVICE_NAME" || true
  sudo systemctl disable "$SERVICE_NAME" || true
  sudo rm -f "$SERVICE_FILE_PATH"
  sudo systemctl daemon-reload
  echo "Service undeployed."
}

start_service() {
  echo "Starting service..."
  sudo systemctl start "$SERVICE_NAME"
  echo "Service started."
}

stop_service() {
  echo "Stopping service..."
  sudo systemctl stop "$SERVICE_NAME"
  echo "Service stopped."
}

status_service() {
  sudo systemctl status "$SERVICE_NAME"
}

show_help() {
  echo "Usage: $0 {deploy|undeploy|start|stop|status}"
  echo "Runs the service as the user who invoked this script (SUDO_USER when using sudo)."
}

case "${1:-}" in
  deploy)    deploy_service ;;
  undeploy)  undeploy_service ;;
  start)     start_service ;;
  stop)      stop_service ;;
  status)    status_service ;;
  *)         show_help; exit 1 ;;
esac