# SmartPyCam - Multi-Camera RTSP Display System

A Python implementation that replicates the functionality of [displaycameras](https://github.com/Anonymousdog/displaycameras) for Ubuntu Server/Intel NUC systems. Uses X11 windowed approach with individual MPV processes for each camera.

## Features

- **Individual Camera Windows**: Each camera gets its own MPV process positioned on screen
- **Automatic Placeholders**: Shows placeholder images or colored rectangles while cameras connect
- **Robust Monitoring**: Automatic camera reconnection and failure recovery
- **Grid Layout**: Configurable camera positioning and sizing
- **Hardware Acceleration**: Uses MPV with hardware decoding when available
- **Production Ready**: Proper logging, systemd service, and auto-restart functionality

## Requirements

- Ubuntu Server 20.04+ (with X11)
- Python 3.8+
- Intel NUC or similar x86-64 hardware
- RTSP camera feeds

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/aotearoait/smartpicam.git
cd smartpicam
git checkout x11-windowed-approach
```

### 2. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip mpv feh ffmpeg xorg
```

### 3. Setup Configuration

```bash
# Copy your existing config or create new one
cp config/smartpicam.json.example config/smartpicam.json
```

Edit `config/smartpicam.json` with your camera URLs and layout:

```json
{
  "display": {
    "screen_width": 2560,
    "screen_height": 1440,
    "camera_retry_interval": 30,
    "log_level": "INFO"
  },
  "cameras": [
    {
      "name": "Camera1",
      "url": "rtsp://user:pass@192.168.1.100:554/stream",
      "window_id": 0,
      "x": 0,
      "y": 0,
      "width": 1280,
      "height": 720,
      "enabled": true
    }
  ]
}
```

### 4. Add Placeholder Image (Optional)

```bash
# Add your camera offline placeholder image
cp your_placeholder.png ~/smartpicam/camera_offline.png
```

## Usage

### Manual Start

```bash
cd ~/smartpicam
python3 smartpycam.py
```

### Service Installation (Auto-Start)

Create systemd service:

```bash
sudo tee /etc/systemd/system/smartpycam.service > /dev/null << EOF
[Unit]
Description=SmartPyCam Multi-Camera Display System
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$HOME/smartpicam
ExecStart=/usr/bin/python3 $HOME/smartpicam/smartpycam.py
Restart=always
RestartSec=10
Environment=DISPLAY=:0
Environment=HOME=$HOME

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=smartpycam

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=false
ReadWritePaths=$HOME/smartpicam /var/log

[Install]
WantedBy=graphical.target
EOF
```

Enable and start the service:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable smartpycam.service

# Start service now
sudo systemctl start smartpycam.service

# Check service status
sudo systemctl status smartpycam.service

# View logs
sudo journalctl -u smartpycam.service -f
```

## Service Management

### Control Commands

```bash
# Start service
sudo systemctl start smartpycam.service

# Stop service
sudo systemctl stop smartpycam.service

# Restart service
sudo systemctl restart smartpycam.service

# Check status
sudo systemctl status smartpycam.service

# View logs (live)
sudo journalctl -u smartpycam.service -f

# View recent logs
sudo journalctl -u smartpycam.service --since "1 hour ago"

# Disable auto-start
sudo systemctl disable smartpycam.service
```

### Auto-Restart Configuration

The service is configured to automatically restart if it crashes:

- **Restart=always**: Service restarts on any exit
- **RestartSec=10**: Wait 10 seconds between restart attempts
- **Individual camera monitoring**: Each camera is monitored independently
- **Connection retry**: Failed cameras automatically retry every 30 seconds

## Configuration Options

### Display Settings

- `screen_width/height`: Monitor resolution
- `camera_retry_interval`: Seconds between connection retry attempts
- `log_level`: DEBUG, INFO, WARNING, ERROR

### Camera Settings

- `name`: Camera identifier
- `url`: RTSP stream URL
- `window_id`: Unique identifier for camera
- `x, y`: Position on screen (pixels)
- `width, height`: Camera window size (pixels)
- `enabled`: Whether to display this camera

## Troubleshooting

### Check X11 Display

```bash
# Test X11 access
export DISPLAY=:0
xset r off

# Test background change
xsetroot -solid blue
```

### Check Camera Connections

```bash
# Test RTSP stream manually
mpv --no-audio "rtsp://your-camera-url"

# Test with FFmpeg
ffmpeg -rtsp_transport tcp -i "rtsp://your-camera-url" -t 5 -f null -
```

### Service Debugging

```bash
# Check service status
sudo systemctl status smartpycam.service

# View detailed logs
sudo journalctl -u smartpycam.service --no-pager

# Manual run for debugging
cd ~/smartpicam
python3 smartpycam.py
```

### Common Issues

1. **Black Screen**: Ensure X11 is running and accessible with `DISPLAY=:0`
2. **Cameras Not Connecting**: Check RTSP URLs and network connectivity
3. **Service Won't Start**: Check file permissions and paths in service file
4. **High CPU Usage**: Reduce camera resolution or frame rate

## Logging

Logs are written to:
- **System Journal**: `sudo journalctl -u smartpycam.service`
- **Log File**: `/var/log/smartpycam.log` (or `~/smartpycam.log` if no permission)

## Performance Tips

- Use camera sub-streams (lower resolution) for better performance
- Enable hardware decoding in MPV (automatically attempted)
- Limit camera resolution to match display window size
- Use wired network connections for cameras when possible

## Architecture Comparison

### Original displaycameras (Raspberry Pi)
- Uses omxplayer with hardware video decoding
- Direct framebuffer rendering
- DBUS control for each player instance
- Pi-specific GPU acceleration

### SmartPyCam (Ubuntu/Intel NUC)
- Uses MPV with X11 windowing
- Individual positioned windows per camera
- Python-based monitoring and control
- Intel GPU acceleration support

## Migration from displaycameras

If migrating from the original displaycameras:

1. **Config format**: Convert camera definitions to JSON format
2. **URLs**: RTSP URLs remain the same
3. **Positioning**: X/Y coordinates work the same way
4. **Features**: All core functionality replicated (monitoring, restart, positioning)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Based on the excellent [displaycameras](https://github.com/Anonymousdog/displaycameras) project
- Uses [MPV](https://mpv.io/) for video playback
- Inspired by the need for reliable multi-camera display on Intel NUC hardware