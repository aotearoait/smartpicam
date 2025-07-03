#!/bin/bash
#
# SmartPiCam Installation Script
# Modern replacement for displaycameras optimized for Raspberry Pi 5
#
# Repository: https://github.com/aotearoait/smartpicam
# Author: smartpicam contributors
# License: MIT
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/smartpicam"
SERVICE_FILE="/etc/systemd/system/smartpicam.service"
LOG_FILE="/var/log/smartpicam.log"
USER="pi"

print_header() {
    echo -e "${BLUE}"
    echo "=================================================="
    echo "    SmartPiCam Installation Script"
    echo "    Modern RTSP Camera Display for Pi 5"
    echo "=================================================="
    echo -e "${NC}"
}

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_requirements() {
    print_status "Checking system requirements..."
    
    # Check if running on Raspberry Pi
    if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        print_warning "This doesn't appear to be a Raspberry Pi. Continuing anyway..."
    fi
    
    # Check Pi OS version
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        print_status "Detected OS: $PRETTY_NAME"
        
        # Check if Bullseye or newer (required for modern video stack)
        if [[ "$VERSION_ID" -lt "11" ]] 2>/dev/null; then
            print_error "SmartPiCam requires Raspberry Pi OS Bullseye (11) or newer"
            print_error "omxplayer is deprecated and not supported on this system"
            exit 1
        fi
    fi
    
    # Check if running as root
    if [ "$EUID" -ne 0 ]; then
        print_error "Please run this script as root (use sudo)"
        exit 1
    fi
    
    # Check available memory
    TOTAL_MEM=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    if [ "$TOTAL_MEM" -lt 3000000 ]; then  # Less than ~3GB
        print_warning "Less than 3GB RAM detected. Performance may be limited."
        print_warning "Consider increasing GPU memory split in raspi-config"
    fi
    
    print_status "System requirements check passed"
}

install_dependencies() {
    print_status "Installing dependencies..."
    
    # Update package list
    apt-get update
    
    # Install required packages
    PACKAGES=(
        "vlc"
        "python3"
        "python3-pip"
        "python3-venv"
        "git"
        "curl"
        "systemd"
    )
    
    for package in "${PACKAGES[@]}"; do
        if ! dpkg -l | grep -q "^ii  $package "; then
            print_status "Installing $package..."
            apt-get install -y "$package"
        else
            print_status "$package already installed"
        fi
    done
    
    # Verify VLC installation and hardware acceleration support
    print_status "Verifying VLC installation..."
    if command -v vlc >/dev/null 2>&1; then
        VLC_VERSION=$(vlc --version 2>/dev/null | head -n1 || echo "Unknown version")
        print_status "VLC installed: $VLC_VERSION"
        
        # Check for DRM support (Pi 5 requirement)
        if vlc --list 2>/dev/null | grep -q "drm"; then
            print_status "VLC DRM video output support detected"
        else
            print_warning "VLC DRM support not detected. Video output may not work properly."
        fi
    else
        print_error "VLC installation failed"
        exit 1
    fi
    
    print_status "Dependencies installed successfully"
}

configure_system() {
    print_status "Configuring system settings..."
    
    # Enable GPU memory split for video processing
    GPU_MEM=$(vcgencmd get_mem gpu | cut -d= -f2 | sed 's/M//')
    if [ "$GPU_MEM" -lt 128 ]; then
        print_status "Increasing GPU memory to 128MB..."
        echo "gpu_mem=128" >> /boot/firmware/config.txt
        print_warning "GPU memory increased. System reboot required after installation."
    fi
    
    # Ensure KMS driver is enabled (required for DRM video output)
    if ! grep -q "dtoverlay=vc4-kms-v3d" /boot/firmware/config.txt; then
        print_status "Enabling KMS graphics driver..."
        echo "dtoverlay=vc4-kms-v3d" >> /boot/firmware/config.txt
        print_warning "Graphics driver updated. System reboot required after installation."
    fi
    
    # Disable screen blanking for always-on display
    if [ -f /etc/xdg/lxsession/LXDE-pi/autostart ]; then
        if ! grep -q "@xset s off" /etc/xdg/lxsession/LXDE-pi/autostart; then
            print_status "Disabling screen blanking..."
            echo "@xset s off" >> /etc/xdg/lxsession/LXDE-pi/autostart
            echo "@xset -dpms" >> /etc/xdg/lxsession/LXDE-pi/autostart
            echo "@xset s noblank" >> /etc/xdg/lxsession/LXDE-pi/autostart
        fi
    fi
    
    # Configure console settings for framebuffer use
    if [ -f /boot/firmware/cmdline.txt ]; then
        if ! grep -q "console=tty3" /boot/firmware/cmdline.txt; then
            sed -i 's/console=tty1/console=tty3/' /boot/firmware/cmdline.txt
        fi
    fi
    
    print_status "System configuration completed"
}

create_directories() {
    print_status "Creating directories..."
    
    # Create configuration directory
    mkdir -p "$CONFIG_DIR"
    chmod 755 "$CONFIG_DIR"
    
    # Create log directory and file
    touch "$LOG_FILE"
    chown "$USER:$USER" "$LOG_FILE"
    
    # Create backup directory for legacy configs
    mkdir -p "$CONFIG_DIR/backup"
    
    print_status "Directories created"
}

install_smartpicam() {
    print_status "Installing SmartPiCam application..."
    
    # Install main script
    cp smartpicam.py "$INSTALL_DIR/smartpicam"
    chmod +x "$INSTALL_DIR/smartpicam"
    chown root:root "$INSTALL_DIR/smartpicam"
    
    # Create symlink for convenience
    ln -sf "$INSTALL_DIR/smartpicam" /usr/local/bin/smartpicam-ctl
    
    print_status "SmartPiCam application installed"
}

migrate_legacy_config() {
    print_status "Checking for legacy displaycameras configuration..."
    
    LEGACY_CONFIG_DIR="/etc/displaycameras"
    
    if [ -d "$LEGACY_CONFIG_DIR" ]; then
        print_status "Legacy configuration found, creating backup..."
        cp -r "$LEGACY_CONFIG_DIR"/* "$CONFIG_DIR/backup/" 2>/dev/null || true
        
        # The Python script will handle the actual migration
        print_status "Legacy configuration backed up to $CONFIG_DIR/backup/"
        print_status "SmartPiCam will automatically migrate settings on first run"
    else
        print_status "No legacy configuration found, will create default config"
    fi
}

create_default_config() {
    print_status "Creating default configuration..."
    
    # Create default JSON configuration
    cat > "$CONFIG_DIR/smartpicam.json" << 'EOF'
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
      "name": "camera1",
      "url": "rtsp://admin:password@192.168.1.100:554/stream1",
      "window_id": 0,
      "x": 0,
      "y": 0,
      "width": 960,
      "height": 540,
      "enabled": false
    },
    {
      "name": "camera2", 
      "url": "rtsp://admin:password@192.168.1.101:554/stream1",
      "window_id": 1,
      "x": 960,
      "y": 0,
      "width": 960,
      "height": 540,
      "enabled": false
    },
    {
      "name": "camera3",
      "url": "rtsp://admin:password@192.168.1.102:554/stream1", 
      "window_id": 2,
      "x": 0,
      "y": 540,
      "width": 960,
      "height": 540,
      "enabled": false
    },
    {
      "name": "camera4",
      "url": "rtsp://admin:password@192.168.1.103:554/stream1",
      "window_id": 3,
      "x": 960,
      "y": 540,
      "width": 960,
      "height": 540,
      "enabled": false
    }
  ]
}
EOF
    
    chown "$USER:$USER" "$CONFIG_DIR/smartpicam.json"
    chmod 644 "$CONFIG_DIR/smartpicam.json"
    
    print_status "Default configuration created at $CONFIG_DIR/smartpicam.json"
}

create_systemd_service() {
    print_status "Creating systemd service..."
    
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=SmartPiCam - Modern RTSP Camera Display System
After=network.target graphical-session.target
Wants=network.target

[Service]
Type=simple
User=root
Group=root
ExecStart=$INSTALL_DIR/smartpicam --config $CONFIG_DIR start
ExecStop=$INSTALL_DIR/smartpicam --config $CONFIG_DIR stop
Restart=always
RestartSec=10
Environment=DISPLAY=:0
Environment=HOME=/root

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$CONFIG_DIR /var/log /tmp

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=smartpicam

[Install]
WantedBy=graphical.target
EOF
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable smartpicam.service
    
    print_status "Systemd service created and enabled"
}

create_helper_scripts() {
    print_status "Creating helper scripts..."
    
    # Create management script
    cat > "$INSTALL_DIR/smartpicam-manage" << 'EOF'
#!/bin/bash
#
# SmartPiCam Management Helper Script
#

case "$1" in
    start)
        echo "Starting SmartPiCam..."
        systemctl start smartpicam.service
        ;;
    stop)
        echo "Stopping SmartPiCam..."
        systemctl stop smartpicam.service
        ;;
    restart)
        echo "Restarting SmartPiCam..."
        systemctl restart smartpicam.service
        ;;
    status)
        systemctl status smartpicam.service
        echo ""
        /usr/local/bin/smartpicam --config /etc/smartpicam status
        ;;
    logs)
        journalctl -u smartpicam.service -f
        ;;
    config)
        if [ "$2" = "edit" ]; then
            nano /etc/smartpicam/smartpicam.json
        else
            cat /etc/smartpicam/smartpicam.json
        fi
        ;;
    test)
        echo "Testing camera connections..."
        /usr/local/bin/smartpicam --config /etc/smartpicam --debug start
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|config|test}"
        echo ""
        echo "Commands:"
        echo "  start    - Start SmartPiCam service"
        echo "  stop     - Stop SmartPiCam service"
        echo "  restart  - Restart SmartPiCam service"
        echo "  status   - Show service and stream status"
        echo "  logs     - Show live service logs"
        echo "  config   - Show current configuration"
        echo "  config edit - Edit configuration file"
        echo "  test     - Test camera connections in debug mode"
        exit 1
        ;;
esac
EOF

    chmod +x "$INSTALL_DIR/smartpicam-manage"
    
    print_status "Helper scripts created"
}

show_post_install_info() {
    print_header
    print_status "SmartPiCam installation completed successfully!"
    echo ""
    
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Edit configuration: sudo nano $CONFIG_DIR/smartpicam.json"
    echo "2. Update camera URLs and credentials in the config file"
    echo "3. Enable cameras by setting 'enabled': true"
    echo "4. Test configuration: sudo smartpicam-manage test"
    echo "5. Start service: sudo smartpicam-manage start"
    echo ""
    
    echo -e "${BLUE}Management Commands:${NC}"
    echo "  smartpicam-manage start     - Start the service"
    echo "  smartpicam-manage stop      - Stop the service"
    echo "  smartpicam-manage status    - Check status"
    echo "  smartpicam-manage logs      - View logs"
    echo "  smartpicam-manage config    - View/edit config"
    echo ""
    
    echo -e "${BLUE}Configuration File:${NC}"
    echo "  Location: $CONFIG_DIR/smartpicam.json"
    echo "  Format: JSON (much easier than legacy format!)"
    echo ""
    
    if [ -d "/etc/displaycameras" ]; then
        echo -e "${YELLOW}Legacy Migration:${NC}"
        echo "  Legacy displaycameras config found and backed up"
        echo "  SmartPiCam will attempt automatic migration on first run"
        echo "  Backup location: $CONFIG_DIR/backup/"
        echo ""
    fi
    
    echo -e "${BLUE}Important Notes:${NC}"
    echo "  • SmartPiCam uses VLC instead of deprecated omxplayer"
    echo "  • Optimized for Raspberry Pi 5 with DRM video output"
    echo "  • Supports hardware acceleration on Pi 5"
    echo "  • Better error handling and automatic stream recovery"
    echo ""
    
    # Check if reboot is needed
    if grep -q "gpu_mem=128" /boot/firmware/config.txt || grep -q "dtoverlay=vc4-kms-v3d" /boot/firmware/config.txt; then
        echo -e "${YELLOW}REBOOT REQUIRED:${NC}"
        echo "  System configuration was updated. Please reboot before starting SmartPiCam:"
        echo "  sudo reboot"
        echo ""
    fi
    
    echo -e "${GREEN}Installation complete!${NC}"
    echo "Repository: https://github.com/aotearoait/smartpicam"
}

perform_uninstall() {
    print_status "Uninstalling SmartPiCam..."
    
    # Stop and disable service
    systemctl stop smartpicam.service 2>/dev/null || true
    systemctl disable smartpicam.service 2>/dev/null || true
    
    # Remove service file
    rm -f "$SERVICE_FILE"
    
    # Remove application files
    rm -f "$INSTALL_DIR/smartpicam"
    rm -f "$INSTALL_DIR/smartpicam-manage"
    rm -f "/usr/local/bin/smartpicam-ctl"
    
    # Remove configuration (with confirmation)
    if [ -d "$CONFIG_DIR" ]; then
        read -p "Remove configuration directory $CONFIG_DIR? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$CONFIG_DIR"
            print_status "Configuration removed"
        else
            print_status "Configuration preserved"
        fi
    fi
    
    # Remove log file
    rm -f "$LOG_FILE"
    
    # Reload systemd
    systemctl daemon-reload
    
    print_status "SmartPiCam uninstalled"
}

# Main installation flow
main() {
    case "${1:-install}" in
        install)
            print_header
            check_requirements
            install_dependencies
            configure_system
            create_directories
            install_smartpicam
            migrate_legacy_config
            create_default_config
            create_systemd_service
            create_helper_scripts
            show_post_install_info
            ;;
        uninstall)
            perform_uninstall
            ;;
        upgrade)
            print_status "Upgrading SmartPiCam..."
            # Stop service
            systemctl stop smartpicam.service 2>/dev/null || true
            # Install new version (preserving config)
            install_smartpicam
            create_systemd_service
            create_helper_scripts
            # Restart service
            systemctl start smartpicam.service
            print_status "Upgrade completed"
            ;;
        *)
            echo "Usage: $0 [install|uninstall|upgrade]"
            echo ""
            echo "Commands:"
            echo "  install   - Install SmartPiCam (default)"
            echo "  uninstall - Remove SmartPiCam"
            echo "  upgrade   - Upgrade SmartPiCam (preserves config)"
            exit 1
            ;;
    esac
}

# Check if script exists (for development)
if [ ! -f "smartpicam.py" ]; then
    print_error "smartpicam.py not found in current directory"
    print_error "Please run this script from the SmartPiCam source directory"
    exit 1
fi

main "$@"