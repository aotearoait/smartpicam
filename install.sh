#!/bin/bash

# SmartPiCam Installation Script
# Works with both Pi OS Lite and Pi OS Desktop

set -e

echo "=== SmartPiCam Installation ==="

# Variables
INSTALL_DIR="$HOME/smartpicam"
SERVICE_NAME="smartpicam.service"

# Detect Pi OS type
if [ -f /usr/bin/startx ]; then
    OS_TYPE="desktop"
    echo "Detected: Pi OS Desktop"
else
    OS_TYPE="lite"
    echo "Detected: Pi OS Lite (headless)"
fi

# 1. Update system
echo "1. Updating system packages..."
sudo apt update
sudo apt upgrade -y

# 2. Install required packages including FFmpeg
echo "2. Installing required packages..."
if [ "$OS_TYPE" = "desktop" ]; then
    sudo apt install -y \
        python3 \
        python3-pip \
        vlc-bin \
        vlc-plugin-base \
        ffmpeg \
        git \
        systemd \
        x11-xserver-utils
else
    # Pi OS Lite - FFmpeg for grid display
    sudo apt install -y \
        python3 \
        python3-pip \
        ffmpeg \
        git \
        systemd
fi

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

# Set up udev rules for graphics/framebuffer access
echo 'SUBSYSTEM=="graphics", GROUP="video", MODE="0660"' | sudo tee /etc/udev/rules.d/99-graphics.rules > /dev/null
echo 'KERNEL=="fb*", GROUP="video", MODE="0660"' | sudo tee -a /etc/udev/rules.d/99-graphics.rules > /dev/null

# 5. Create systemd service based on OS type
echo "5. Creating systemd service for $OS_TYPE..."
if [ "$OS_TYPE" = "desktop" ]; then
    # Desktop version
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
Environment=XAUTHORITY=/home/$USER/.Xauthority
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
else
    # Lite version - FFmpeg grid display
    sudo tee /etc/systemd/system/$SERVICE_NAME > /dev/null << EOF
[Unit]
Description=SmartPiCam - Modern RTSP Camera Display System
After=multi-user.target

[Service]
Type=simple
User=$USER
Group=video
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 smartpicam.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
fi

# 6. Test FFmpeg installation
echo "6. Testing FFmpeg installation..."
if command -v ffmpeg >/dev/null 2>&1; then
    echo "FFmpeg version: $(ffmpeg -version | head -n1)"
else
    echo "ERROR: FFmpeg installation failed!"
    exit 1
fi

# 7. Create config directory if it doesn't exist
mkdir -p "$INSTALL_DIR/config"

# 8. Set framebuffer resolution for Pi OS Lite
if [ "$OS_TYPE" = "lite" ]; then
    echo "7. Configuring framebuffer for optimal display..."
    # Ensure framebuffer is configured for 1920x1080
    if ! grep -q "framebuffer_width=1920" /boot/firmware/config.txt 2>/dev/null; then
        echo "Adding framebuffer configuration to config.txt..."
        echo "" | sudo tee -a /boot/firmware/config.txt
        echo "# SmartPiCam framebuffer configuration" | sudo tee -a /boot/firmware/config.txt
        echo "framebuffer_width=1920" | sudo tee -a /boot/firmware/config.txt
        echo "framebuffer_height=1080" | sudo tee -a /boot/firmware/config.txt
        echo "framebuffer_depth=32" | sudo tee -a /boot/firmware/config.txt
        REBOOT_REQUIRED=true
    fi
fi

# 9. Reload systemd and enable service
echo "8. Setting up service..."
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

echo ""
echo "=== Installation Complete ==="
echo ""
if [ "$OS_TYPE" = "lite" ]; then
    echo "Pi OS Lite Configuration:"
    echo "- Uses FFmpeg for grid display on framebuffer"
    echo "- Supports custom camera positioning and sizing"
    echo "- Hardware accelerated where possible"
    if [ "$REBOOT_REQUIRED" = "true" ]; then
        echo "- REBOOT REQUIRED for framebuffer changes"
    fi
else
    echo "Pi OS Desktop Configuration:"
    echo "- Cameras will display in X11 windows"
    echo "- Desktop environment required"
fi
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
if [ "$REBOOT_REQUIRED" = "true" ]; then
    echo "IMPORTANT: Reboot required for framebuffer configuration:"
    echo "  sudo reboot"
fi
echo ""
