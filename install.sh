#!/bin/bash

# SmartPiCam Installation Script
# Clean installation for Raspberry Pi

set -e

echo "=== SmartPiCam Installation ==="

# Variables
INSTALL_DIR="$HOME/smartpicam"
SERVICE_NAME="smartpicam.service"

# 1. Update system
echo "1. Updating system packages..."
sudo apt update
sudo apt upgrade -y

# 2. Install required packages
echo "2. Installing required packages..."
sudo apt install -y \
    python3 \
    python3-pip \
    vlc-bin \
    vlc-plugin-base \
    git \
    systemd

# 3. Clone or update repository
echo "3. Setting up SmartPiCam..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory exists, pulling latest changes..."
    cd "$INSTALL_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    git clone https://github.com/aotearoait/smartpicam.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 4. Set up permissions
echo "4. Setting up permissions..."
# Add user to video group for hardware access
sudo usermod -a -G video $USER

# Set up udev rules for graphics access
echo 'SUBSYSTEM=="graphics", GROUP="video", MODE="0660"' | sudo tee /etc/udev/rules.d/99-graphics.rules > /dev/null

# 5. Create systemd service
echo "5. Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME > /dev/null << EOF
[Unit]
Description=SmartPiCam - Modern RTSP Camera Display System
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
User=$USER
Group=video
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/1000
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 15
ExecStart=/usr/bin/python3 smartpicam.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

# 6. Set up VLC configuration
echo "6. Configuring VLC..."
mkdir -p $HOME/.config/vlc
tee $HOME/.config/vlc/vlcrc > /dev/null << 'EOF'
# VLC preferences for camera display
[core]
intf=dummy
audio=0

[dummy]
dummy-quiet=1
EOF

# 7. Create config directory if it doesn't exist
mkdir -p "$INSTALL_DIR/config"

# 8. Reload systemd and enable service
echo "7. Setting up service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Configuration file: $INSTALL_DIR/config/smartpicam.json"
echo ""
echo "To start the service:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
echo "To check logs:"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "To test manually:"
echo "  cd $INSTALL_DIR && python3 smartpicam.py"
echo ""
echo "The service will auto-start on boot once enabled."
echo ""
