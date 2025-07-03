# SmartPiCam 🎥

**Modern RTSP Camera Display System for Raspberry Pi 5**

A complete replacement for the deprecated `displaycameras` project, designed specifically for Raspberry Pi 5 and modern Raspberry Pi OS versions.

## 🚀 Why SmartPiCam?

The original `displaycameras` project became unusable on modern Raspberry Pi systems due to:
- **omxplayer deprecation** - No longer supported since Bullseye
- **Hardware decoder removal** - Pi 5 doesn't have dedicated H.264 hardware blocks
- **Graphics stack changes** - Legacy DispmanX replaced with modern KMS/DRM
- **64-bit incompatibility** - Old OpenMAX libraries don't work

SmartPiCam solves these issues with:
- ✅ **VLC-based playback** with DRM hardware acceleration
- ✅ **Pi 5 optimized** - Takes advantage of improved CPU performance
- ✅ **Modern architecture** - Uses standard Linux media stack
- ✅ **Better reliability** - Robust process management and error recovery
- ✅ **Easy configuration** - JSON-based config with auto-migration
- ✅ **Enhanced monitoring** - Comprehensive logging and status reporting

## 📋 Requirements

### Hardware
- **Raspberry Pi 5** (4GB RAM recommended)
- **Raspberry Pi 4** also supported
- HDMI display or touchscreen
- Network connection to camera sources

### Software
- **Raspberry Pi OS Bullseye** (11) or newer
- **Python 3.9+** (included in modern Pi OS)
- **VLC media player** (auto-installed)

## 🛠️ Installation

### Command Line Installation on Raspberry Pi

```bash
# 1. Update your Pi system
sudo apt update && sudo apt upgrade -y

# 2. Clone the repository
git clone https://github.com/aotearoait/smartpicam.git
cd smartpicam

# 3. Make install script executable
chmod +x install.sh

# 4. Run installation (requires sudo)
sudo ./install.sh

# 5. Reboot to apply system configuration changes
sudo reboot
```

### What the installer does:
- ✅ Installs VLC and dependencies
- ✅ Configures GPU memory (128MB minimum)
- ✅ Enables KMS graphics driver for Pi 5
- ✅ Sets up systemd service for auto-start
- ✅ Creates configuration directories
- ✅ Migrates legacy displaycameras config (if found)
- ✅ Disables screen blanking for always-on display

## ⚙️ Configuration

### Edit Camera Configuration

After installation, configure your cameras:

```bash
# Edit the main configuration file
sudo nano /etc/smartpicam/smartpicam.json
```

### Basic Configuration Example

```json
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
      "name": "front_door",
      "url": "rtsp://admin:password@192.168.1.100:554/stream1",
      "window_id": 0,
      "enabled": true
    },
    {
      "name": "back_yard",
      "url": "rtsp://admin:password@192.168.1.101:554/stream1",
      "window_id": 1,
      "enabled": true
    },
    {
      "name": "driveway",
      "url": "rtsp://admin:password@192.168.1.102:554/stream1",
      "window_id": 2,
      "enabled": true
    },
    {
      "name": "garage",
      "url": "rtsp://admin:password@192.168.1.103:554/stream1",
      "window_id": 3,
      "enabled": true
    }
  ]
}
```

### Camera Configuration Steps

1. **Update camera URLs**: Replace example URLs with your actual camera RTSP streams
2. **Set credentials**: Update `admin:password` with your camera login details
3. **Enable cameras**: Set `"enabled": true` for cameras you want to display
4. **Test configuration**: Run validation before starting service

```bash
# Test your camera URLs work
python3 validator.py --config /etc/smartpicam --test-streams

# Validate configuration
sudo smartpicam-manage test
```

## 🖥️ Auto-Start on Pi Boot

SmartPiCam is automatically configured to start on boot, but here's how to verify and control it:

### Enable Auto-Start (Done by installer)
```bash
# Enable service to start on boot
sudo systemctl enable smartpicam.service

# Start immediately
sudo systemctl start smartpicam.service
```

### Ensure Display on Monitor at Boot

The installer configures this automatically, but you can verify:

```bash
# Check boot configuration
cat /boot/firmware/config.txt | grep -E "(gpu_mem|dtoverlay)"

# Should show:
# gpu_mem=128
# dtoverlay=vc4-kms-v3d
```

### Configure Auto-Login (Optional)

For unattended operation, enable auto-login to desktop:

```bash
# Enable auto-login to desktop
sudo raspi-config
# Navigate to: 1 System Options > S5 Boot / Auto Login > B4 Desktop Autologin
```

Or via command line:
```bash
# Enable auto-login
sudo systemctl set-default graphical.target
sudo systemctl enable graphical.target

# Disable screen lock
mkdir -p ~/.config/lxsession/LXDE-pi
echo "@xset s off" >> ~/.config/lxsession/LXDE-pi/autostart
echo "@xset -dpms" >> ~/.config/lxsession/LXDE-pi/autostart
echo "@xset s noblank" >> ~/.config/lxsession/LXDE-pi/autostart
```

## 🎮 Service Management

### Basic Commands

```bash
# Start SmartPiCam
sudo smartpicam-manage start

# Stop SmartPiCam
sudo smartpicam-manage stop

# Restart SmartPiCam
sudo smartpicam-manage restart

# Check status and stream health
sudo smartpicam-manage status

# View live logs
sudo smartpicam-manage logs

# Edit configuration
sudo smartpicam-manage config edit
```

### Service Status Commands

```bash
# Check if service is running
sudo systemctl status smartpicam.service

# Check if auto-start is enabled
sudo systemctl is-enabled smartpicam.service

# View recent service logs
sudo journalctl -u smartpicam.service -n 50

# Follow logs in real-time
sudo journalctl -u smartpicam.service -f
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Streams Don't Start
```bash
# Test camera connectivity
ping 192.168.1.100  # Replace with your camera IP

# Test RTSP stream manually
cvlc --intf dummy rtsp://admin:password@192.168.1.100:554/stream1

# Check SmartPiCam logs
sudo smartpicam-manage logs
```

#### 2. Black Screen / No Video Output
```bash
# Check GPU memory allocation
vcgencmd get_mem gpu
# Should show at least 128MB

# Verify KMS driver is loaded
dmesg | grep vc4
# Should show vc4 driver loaded

# Check for DRM devices
ls -la /dev/dri/
# Should show card0, card1, etc.
```

#### 3. Service Won't Start
```bash
# Check service status
sudo systemctl status smartpicam.service

# View detailed error logs
sudo journalctl -u smartpicam.service --no-pager

# Test configuration manually
sudo smartpicam --config /etc/smartpicam --debug start
```

#### 4. Performance Issues
```bash
# Monitor CPU usage
htop

# Check network connectivity
ping 8.8.8.8

# Reduce stream quality or number of cameras
# Edit grid_cols/grid_rows in config file
```

### Recovery Commands

```bash
# Reset to default configuration
sudo systemctl stop smartpicam.service
sudo cp /etc/smartpicam/smartpicam.json /etc/smartpicam/smartpicam.json.backup
sudo cp config/smartpicam.json /etc/smartpicam/smartpicam.json
sudo systemctl start smartpicam.service

# Completely reinstall
cd smartpicam
sudo ./install.sh uninstall
sudo ./install.sh install
```

## 📊 Display Layout Options

### Grid Layouts

#### 2x2 Grid (4 cameras)
```json
"display": {"grid_cols": 2, "grid_rows": 2}
```
```
┌─────────┬─────────┐
│ Cam 0   │ Cam 1   │
├─────────┼─────────┤  
│ Cam 2   │ Cam 3   │
└─────────┴─────────┘
```

#### 3x3 Grid (9 cameras)
```json
"display": {"grid_cols": 3, "grid_rows": 3}
```

#### Single Large Display
```json
"display": {"grid_cols": 1, "grid_rows": 1}
```

### Camera Rotation

Enable rotation to cycle through more cameras than grid spaces:

```json
{
  "display": {
    "enable_rotation": true,
    "rotation_interval": 30
  }
}
```

## 🔄 Migration from displaycameras

SmartPiCam automatically detects and migrates legacy configurations:

1. **Automatic Detection** - Installer finds `/etc/displaycameras/` config
2. **Backup Created** - Legacy config saved to `/etc/smartpicam/backup/`
3. **URL Migration** - Camera URLs converted to JSON format
4. **Manual Review** - Check migrated settings and adjust as needed

### Manual Migration

```bash
# If auto-migration doesn't work perfectly:

# 1. Backup old config
sudo cp -r /etc/displaycameras /etc/smartpicam/backup

# 2. Extract camera URLs
grep "camera.*=" /etc/displaycameras/layout.conf.default

# 3. Add to SmartPiCam config
sudo nano /etc/smartpicam/smartpicam.json

# 4. Test new configuration
sudo smartpicam-manage test
```

## 📝 Configuration Reference

### Display Settings
- `screen_width/height`: Display resolution (1920x1080 recommended)
- `grid_cols/rows`: Grid layout (2x2, 3x3, etc.)
- `enable_rotation`: Cycle through cameras
- `rotation_interval`: Seconds between rotations
- `network_timeout`: Stream connection timeout
- `restart_retries`: Max restart attempts for failed streams
- `log_level`: DEBUG, INFO, WARNING, ERROR

### Camera Settings
- `name`: Unique identifier (alphanumeric + underscore only)
- `url`: RTSP/HTTP stream URL
- `window_id`: Position in grid (0-based, left-to-right, top-to-bottom)
- `enabled`: Whether to display this camera
- `x,y,width,height`: Manual positioning (auto-calculated if omitted)

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Configuration │    │   Stream Manager │    │   VLC Processes │
│   (JSON/Legacy) │───▶│   (Python)       │───▶│   (DRM Output)  │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                        ┌──────────────────┐
                        │   Health Monitor │
                        │   (Watchdog)     │
                        └──────────────────┘
```

## 📞 Support

- **GitHub Issues**: [Report bugs and request features](https://github.com/aotearoait/smartpicam/issues)
- **GitHub Discussions**: [Community support and questions](https://github.com/aotearoait/smartpicam/discussions)

## 📝 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Original `displaycameras` project by [Anonymousdog](https://github.com/Anonymousdog/displaycameras)
- Raspberry Pi Foundation for the amazing hardware
- VLC media player team for robust streaming support

---

**Made with ❤️ for the Raspberry Pi community**