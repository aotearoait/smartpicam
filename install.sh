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
    systemd \
    x11-xserver-utils \
    xvfb

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

# 5. Create a startup script that handles display detection
echo "5. Creating startup script..."
tee "$INSTALL_DIR/start_smartpicam.sh" > /dev/null << 'EOF'
#!/bin/bash

# SmartPiCam startup script with display detection

echo "$(date): Starting SmartPiCam with display detection..."

# Wait for desktop session to be available
for i in {1..30}; do
    if DISPLAY=:0 xdpyinfo >/dev/null 2>&1; then
        echo "$(date): Display :0 is available"
        break
    elif DISPLAY=:1 xdpyinfo >/dev/null 2>&1; then
        echo "$(date): Display :1 is available, using that"
        export DISPLAY=:1
        break
    else
        echo "$(date): Waiting for display... attempt $i/30"
        sleep 2
    fi
done

# Check if display is available
if ! xdpyinfo >/dev/null 2>&1; then
    echo "$(date): No display available, starting virtual display"
    # Start virtual display as fallback
    Xvfb :99 -screen 0 1920x1080x24 &
    export DISPLAY=:99
    sleep 2
fi

# Set up X11 permissions
xhost +local: 2>/dev/null || true

# Set up environment
export XAUTHORITY=/home/pi/.Xauthority

echo "$(date): Using DISPLAY=$DISPLAY"
echo "$(date): Starting SmartPiCam..."

# Start SmartPiCam
cd /home/pi/smartpicam
exec python3 smartpicam.py
EOF

chmod +x "$INSTALL_DIR/start_smartpicam.sh"

# 6. Create systemd service with better display handling
echo "6. Creating systemd service..."
sudo tee /etc/systemd/system/$SERVICE_NAME > /dev/null << EOF
[Unit]
Description=SmartPiCam - Modern RTSP Camera Display System
After=graphical-session.target
Wants=graphical-session.target
StartLimitIntervalSec=0

[Service]
Type=simple
User=$USER
Group=video
Environment=XDG_RUNTIME_DIR=/run/user/1000
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 20
ExecStart=$INSTALL_DIR/start_smartpicam.sh
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical.target
EOF

# 7. Set up VLC configuration
echo "7. Configuring VLC..."
mkdir -p $HOME/.config/vlc
tee $HOME/.config/vlc/vlcrc > /dev/null << 'EOF'
# VLC preferences for camera display
[core]
intf=dummy
audio=0

[dummy]
dummy-quiet=1

[x11]
x11-display=:0
EOF

# 8. Create config directory if it doesn't exist
mkdir -p "$INSTALL_DIR/config"

# 9. Ensure desktop auto-login is enabled (for Pi 5)
echo "8. Checking desktop auto-login..."
if command -v raspi-config >/dev/null 2>&1; then
    echo "Enabling auto-login to desktop (required for display access)..."
    sudo raspi-config nonint do_boot_behaviour B4 2>/dev/null || true
fi

# 10. Reload systemd and enable service
echo "9. Setting up service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo ""
echo "=== Installation Complete ==="
echo ""
echo "IMPORTANT NOTES:"
echo "- Make sure your Pi is set to boot to desktop (not CLI)"
echo "- Cameras will display on the Pi's physical monitor"
echo "- If no physical display, a virtual display will be created"
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
echo "  cd $INSTALL_DIR && ./start_smartpicam.sh"
echo ""
echo "RECOMMENDED: Reboot the Pi after installation:"
echo "  sudo reboot"
echo ""
