#!/bin/bash

# SmartPiCam Display Environment Fix Script
# This script fixes common display issues with VLC on Raspberry Pi

echo "=== SmartPiCam Display Environment Fix ==="

# 1. Fix PulseAudio issues
echo "1. Disabling PulseAudio for system services..."
sudo systemctl --global disable pulseaudio.service pulseaudio.socket
sudo systemctl --user disable pulseaudio.service pulseaudio.socket 2>/dev/null || true

# 2. Set up proper X11 environment for the service
echo "2. Setting up X11 environment..."

# Create X11 wrapper script
sudo tee /opt/smartpicam/start_with_display.sh > /dev/null << 'EOF'
#!/bin/bash

# Set up display environment
export DISPLAY=:0
export XAUTHORITY=/home/pi/.Xauthority

# Fix permissions for X11
xhost +local: 2>/dev/null || true

# Make sure we're using the right user's X session
if [ -f /home/pi/.Xauthority ]; then
    cp /home/pi/.Xauthority /tmp/.Xauth_smartpicam
    export XAUTHORITY=/tmp/.Xauth_smartpicam
    chmod 644 /tmp/.Xauth_smartpicam
fi

# Start smartpicam
cd /opt/smartpicam
exec python3 smartpicam.py
EOF

sudo chmod +x /opt/smartpicam/start_with_display.sh

# 3. Update systemd service to use the wrapper
echo "3. Updating systemd service..."
sudo tee /etc/systemd/system/smartpicam.service > /dev/null << 'EOF'
[Unit]
Description=SmartPiCam - Modern RTSP Camera Display System
After=multi-user.target graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
User=pi
Group=video
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=/bin/sleep 10
ExecStart=/opt/smartpicam/start_with_display.sh
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=graphical.target
EOF

# 4. Set up VLC preferences to avoid GUI issues
echo "4. Configuring VLC preferences..."
sudo mkdir -p /home/pi/.config/vlc
sudo tee /home/pi/.config/vlc/vlcrc > /dev/null << 'EOF'
# VLC preferences for headless operation
[core]
intf=dummy
audio=0
video=1

[dummy]
dummy-quiet=1

[x11]
x11-display=:0
EOF

sudo chown -R pi:pi /home/pi/.config/vlc

# 5. Install/update required packages
echo "5. Installing required packages..."
sudo apt update
sudo apt install -y vlc-bin vlc-plugin-base xvfb

# 6. Enable hardware video acceleration (if available)
echo "6. Checking hardware acceleration..."
if [ -e /dev/video10 ] || [ -e /dev/video11 ]; then
    echo "Hardware video decoder detected"
    sudo usermod -a -G video pi
else
    echo "No hardware video decoder found - using software decoding"
fi

# 7. Fix frame buffer permissions
echo "7. Setting up framebuffer permissions..."
sudo usermod -a -G video pi
echo 'SUBSYSTEM=="graphics", GROUP="video", MODE="0660"' | sudo tee /etc/udev/rules.d/99-graphics.rules

# 8. Create a test configuration
echo "8. Creating test configuration..."
sudo mkdir -p /opt/smartpicam/config

# Check if config exists, if not create a template
if [ ! -f /opt/smartpicam/config/smartpicam.json ]; then
    sudo tee /opt/smartpicam/config/smartpicam.json > /dev/null << 'EOF'
{
  "display": {
    "screen_width": 1920,
    "screen_height": 1080,
    "grid_cols": 2,
    "grid_rows": 2,
    "enable_rotation": false,
    "rotation_interval": 30,
    "network_timeout": 30,
    "restart_retries": 3,
    "log_level": "INFO"
  },
  "cameras": [
    {
      "name": "Living_Area",
      "url": "rtsp://your_living_area_camera_url",
      "window_id": 0,
      "x": 0,
      "y": 0,
      "width": 960,
      "height": 540,
      "enabled": true
    },
    {
      "name": "South_mid_right", 
      "url": "rtsp://your_garage_camera_url",
      "window_id": 1,
      "x": 960,
      "y": 0,
      "width": 960,
      "height": 540,
      "enabled": true
    }
  ]
}
EOF
    echo "Created template configuration - please edit /opt/smartpicam/config/smartpicam.json with your camera URLs"
fi

# 9. Set proper ownership
sudo chown -R pi:pi /opt/smartpicam

# 10. Reload systemd and enable service
echo "9. Reloading systemd configuration..."
sudo systemctl daemon-reload
sudo systemctl enable smartpicam.service

echo ""
echo "=== Fix Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit your camera configuration:"
echo "   sudo nano /opt/smartpicam/config/smartpicam.json"
echo ""
echo "2. Test the display fix:"
echo "   sudo systemctl restart smartpicam.service"
echo ""
echo "3. Monitor the logs:"
echo "   sudo journalctl -u smartpicam.service -f"
echo ""
echo "4. If you still have issues, try running manually first:"
echo "   cd /opt/smartpicam && python3 smartpicam.py"
echo ""

# 11. Check current display status
echo "Current display information:"
echo "DISPLAY variable: $DISPLAY"
if command -v xrandr &> /dev/null; then
    echo "Available displays:"
    DISPLAY=:0 xrandr --listmonitors 2>/dev/null || echo "Could not detect displays"
fi
