#!/bin/bash

SERVICE_NAME="panels-app.service"
SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME"
user="ubuntu" # Default user; can be overridden by parameter
working_directory="/home/ubuntu/home-panels"
python_path="/home/ubuntu/home-panels/.venv/bin/python"

app_paths="/home/ubuntu/home-panels/src/home.py \
/home/ubuntu/home-panels/src/vehiclemap.py \
/home/ubuntu/home-panels/src/imageviewer.py"

log_file="/var/log/panels.log"

deploy_service() {
    echo "Deploying service..."

    # Create systemd service file
    cat <<EOF | sudo tee $SERVICE_FILE_PATH
[Unit]
Description=A simple service
After=network.target

[Service]
User=$user
WorkingDirectory=$working_directory

# Run Panel server with the same settings as startup.sh

ExecStart=$python_path -m panel serve $app_paths \
  --address 0.0.0.0 \
  --port 5010 \
  --log-level info \
  --root-path /restricted/panels \
  --index=home \
  --allow-websocket-origin accretiosolutions.com \
  --allow-websocket-origin www.accretiosolutions.com


Restart=always
StandardOutput=append:$log_file
StandardError=append:$log_file

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd and enable the service
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE_NAME

    echo "service deployed."
}

undeploy_service() {
    echo "Undeploying service..."

    # Stop the service
    sudo systemctl stop $SERVICE_NAME

    # Disable the service
    sudo systemctl disable $SERVICE_NAME

    # Remove the systemd service file
    sudo rm -f $SERVICE_FILE_PATH

    # Reload systemd
    sudo systemctl daemon-reload

    echo "service undeployed."
}

start_service() {
    echo "Starting service..."
    sudo systemctl start $SERVICE_NAME
    echo "service started."
}

stop_service() {
    echo "Stopping service..."
    sudo systemctl stop $SERVICE_NAME
    echo "service stopped."
}

status_service() {
    sudo systemctl status $SERVICE_NAME
}

show_help() {
    echo "Usage: $0 {deploy|undeploy|start|stop|status} [username]"
    echo "Commands:"
    echo "  deploy          Deploy the service"
    echo "  undeploy        Undeploy the service"
    echo "  start           Start the service"
    echo "  stop            Stop the service"
    echo "  status          Check the status of the service"
    echo "Options:"
    echo "  username        Specify the user to run the service (default: your_user)"
}

if [ $# -eq 2 ]; then
    user=$2
fi

case "$1" in
    deploy)
        deploy_service
        ;;
    undeploy)
        undeploy_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    status)
        status_service
        ;;
    *)
        show_help
        exit 1
esac