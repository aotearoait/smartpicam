# SmartPiCam - Modern RTSP Camera Display System

A modern, Python-based replacement for the deprecated displaycameras project, designed specifically for Raspberry Pi 5 with improved reliability, better error handling, and VLC-based streaming.

## Features

- 🎥 **Multi-camera RTSP display** with precise positioning
- 🔧 **Flexible grid layouts** (2x2, 2x1, custom positioning)
- 🔄 **Automatic stream recovery** with configurable retry logic
- 📊 **Comprehensive logging** and health monitoring
- 🖥️ **VLC-based backend** with improved display compatibility
- 🛠️ **Easy configuration** via JSON files
- 🚀 **Systemd service integration** for automatic startup
- 🏗️ **Modular architecture** for easy customization

## Recent Updates (v2.0)

- **Fixed VLC display backend issues** - Resolved overlapping camera streams
- **Improved audio handling** - Completely disabled audio to prevent PulseAudio conflicts
- **Enhanced X11 compatibility** - Better support for headless operation
- **Better error handling** - More robust stream monitoring and recovery
- **Display environment fixes** - Automatic setup of proper X11 environment

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/aotearoait/smartpicam.git
cd smartpicam

# Run the installer (includes display fix)
sudo ./install.sh
```

### Update Existing Installation

```bash
# Navigate to your installation directory
cd /opt/smartpicam

# Stop the service
sudo systemctl stop smartpicam.service

# Pull latest changes
sudo git pull origin main

# Run the display fix script
sudo ./scripts/display_fix.sh

# Update configuration if needed
sudo nano config/smartpicam.json

# Restart the service
sudo systemctl restart smartpicam.service

# Monitor logs
sudo journalctl -u smartpicam.service -f
```

## Configuration

Edit `/opt/smartpicam/config/smartpicam.json`:

### Side-by-Side Layout (Recommended)
```json
{
  "display": {
    "screen_width": 1920,
    "screen_height": 1080,
    "grid_cols": 2,
    "grid_rows": 1,
    "network_timeout": 30,
    "restart_retries": 3,
    "log_level": "INFO"
  },
  "cameras": [
    {
      "name": "Living_Area",
      "url": "rtsp://admin:password@192.168.1.100:554/stream1",
      "window_id": 0,
      "x": 0,
      "y": 0,
      "width": 960,
      "height": 1080,
      "enabled": true
    },
    {
      "name": "Garage", 
      "url": "rtsp://admin:password@192.168.1.101:554/stream1",
      "window_id": 1,
      "x": 960,
      "y": 0,
      "width": 960,
      "height": 1080,
      "enabled": true
    }
  ]
}
```

### 2x2 Grid Layout
```json
{
  "cameras": [
    {
      "name": "camera1",
      "url": "rtsp://...",
      "x": 0, "y": 0,
      "width": 960, "height": 540,
      "enabled": true
    },
    {
      "name": "camera2",
      "url": "rtsp://...",
      "x": 960, "y": 0,
      "width": 960, "height": 540,
      "enabled": true
    },
    {
      "name": "camera3",
      "url": "rtsp://...",
      "x": 0, "y": 540,
      "width": 960, "height": 540,
      "enabled": true
    },
    {
      "name": "camera4",
      "url": "rtsp://...",
      "x": 960, "y": 540,
      "width": 960, "height": 540,
      "enabled": true
    }
  ]
}
```

## Troubleshooting

### Display Issues
If cameras are overlapping or not positioning correctly:

```bash
# Run the display fix script
sudo /opt/smartpicam/scripts/display_fix.sh

# Restart the service
sudo systemctl restart smartpicam.service
```

### Manual Testing
```bash
# Stop the service and test manually
sudo systemctl stop smartpicam.service
cd /opt/smartpicam
python3 smartpicam.py
```

### Common Issues

1. **Cameras overlapping**: Run the display fix script
2. **Audio errors**: Audio is disabled by default in v2.0
3. **Stream failures**: Check camera URLs and network connectivity
4. **Permission errors**: Ensure pi user is in video group

### Logs
```bash
# Real-time logs
sudo journalctl -u smartpicam.service -f

# Recent logs
sudo journalctl -u smartpicam.service --since "1 hour ago"

# Full logs
sudo journalctl -u smartpicam.service --no-pager
```

## Service Management

```bash
# Start service
sudo systemctl start smartpicam.service

# Stop service
sudo systemctl stop smartpicam.service

# Restart service
sudo systemctl restart smartpicam.service

# Enable auto-start
sudo systemctl enable smartpicam.service

# Check status
sudo systemctl status smartpicam.service
```

## Hardware Requirements

- **Raspberry Pi 5** (recommended) or Pi 4
- **4GB+ RAM** recommended for multiple streams
- **HDMI display** connected
- **Network connection** to cameras
- **X11 desktop environment** (Raspberry Pi OS Desktop)

## Camera Compatibility

Supports any RTSP-compatible IP camera including:
- Hikvision
- Dahua
- Reolink
- Generic ONVIF cameras
- Custom RTSP streams

## Architecture

```
SmartPiCam
├── smartpicam.py          # Main application
├── config/
│   └── smartpicam.json    # Configuration
├── scripts/
│   └── display_fix.sh     # Display environment fixes
├── install.sh             # Installation script
└── smartpicam.service     # Systemd service
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Review the logs: `sudo journalctl -u smartpicam.service -f`
3. Open an issue on GitHub with log output

---

**Note**: This project replaces the deprecated `displaycameras` project with modern Python code, better error handling, and improved display compatibility.
