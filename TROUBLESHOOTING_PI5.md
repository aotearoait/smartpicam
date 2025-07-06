# Pi 5 Video Issues Troubleshooting Guide

## Overview
You're experiencing video playback issues on Raspberry Pi 5 with your SmartPiCam setup. This guide provides step-by-step solutions based on the common problems identified.

## Quick Diagnosis

Run the troubleshooting script first:
```bash
chmod +x scripts/pi5_troubleshoot.sh
./scripts/pi5_troubleshoot.sh rtsp://127.0.0.1:8554/living_area
```

## Common Issues & Solutions

### 1. FFplay/FFmpeg Hardware Acceleration Errors

**Problem**: Error messages like "Unknown error 524" or hardware decoding failures.

**Solution**: Disable hardware acceleration and use optimized software decoding:

```bash
# Instead of this (which fails):
ffplay rtsp://127.0.0.1:8554/living_area

# Use this optimized command:
ffplay -analyzeduration 10000000 -probesize 10000000 -timeout 30000000 \
       -rtsp_transport tcp -an -framedrop rtsp://127.0.0.1:8554/living_area
```

### 2. UDP Input/Output Errors in Grid Display

**Problem**: `udp://127.0.0.1:5000?timeout=5000000: Input/output error`

**Cause**: Pi 5 hardware acceleration conflicts with UDP inputs in FFmpeg grid display.

**Solution**: The updated `smartpicam_no_reencode.py` fixes this by:
- Removing hardware acceleration from grid display
- Adding buffer size parameters
- Increasing probe/analysis duration
- Adding error resilience flags

### 3. SDL Audio Device Errors

**Problem**: `SDL_OpenAudio (1 channels, 16000 Hz): ALSA: Couldn't open audio device`

**Solution**: Disable audio in video commands:
```bash
# Add -an flag to disable audio
ffplay -an rtsp://127.0.0.1:8554/living_area
```

### 4. RTP Packet Loss

**Problem**: `RTP: missed 9 packets` messages

**Solutions**:
1. **Increase buffer sizes**:
   ```bash
   ffplay -analyzeduration 10000000 -probesize 10000000 -buffer_size 1048576 rtsp://your_url
   ```

2. **Use TCP instead of UDP for RTSP**:
   ```bash
   ffplay -rtsp_transport tcp rtsp://your_url
   ```

3. **Enable frame dropping for live streams**:
   ```bash
   ffplay -framedrop rtsp://your_url
   ```

## Testing Your RTSP Stream

### Test 1: Basic Stream Analysis
```bash
ffprobe -analyzeduration 10000000 -probesize 10000000 -timeout 10000000 \
        -rtsp_transport tcp -show_entries stream=codec_name,width,height \
        rtsp://127.0.0.1:8554/living_area
```

### Test 2: Optimized Playback
```bash
ffplay -analyzeduration 10000000 -probesize 10000000 -timeout 30000000 \
       -rtsp_transport tcp -an -framedrop -sync video \
       rtsp://127.0.0.1:8554/living_area
```

### Test 3: VLC Alternative
```bash
vlc --intf dummy --rtsp-tcp --no-audio --network-caching 1000 \
    rtsp://127.0.0.1:8554/living_area
```

## Hardware Optimizations

### 1. GPU Memory Split
Check and increase GPU memory:
```bash
# Check current split
vcgencmd get_mem gpu

# Increase to 256MB for better video performance
sudo raspi-config
# Advanced Options -> Memory Split -> 256
```

### 2. System Updates
```bash
sudo apt update && sudo apt upgrade
sudo apt install ffmpeg vlc v4l-utils
```

## Using the Test Scripts

### 1. VLC Grid Test
```bash
python3 scripts/vlc_grid_test.py
```

### 2. FFmpeg Compatibility Test
```bash
python3 scripts/ffmpeg_pi5_test.py rtsp://127.0.0.1:8554/living_area
```

### 3. Main Application with Fixes
```bash
python3 smartpicam_no_reencode.py
```

## Configuration Adjustments

For your specific setup, ensure your config includes these optimizations:

```json
{
  "display": {
    "screen_width": 1920,
    "screen_height": 1080,
    "network_timeout": 60,
    "restart_retries": 5
  }
}
```

## Recommended Command for Your Stream

Based on the error output you provided, use this optimized ffplay command:

```bash
ffplay -v info \
       -analyzeduration 10000000 \
       -probesize 10000000 \
       -timeout 30000000 \
       -rtsp_transport tcp \
       -an \
       -framedrop \
       -sync video \
       -fflags nobuffer \
       -flags low_delay \
       rtsp://127.0.0.1:8554/living_area
```

## If Nothing Works

1. **Check MediaMTX is running properly**:
   ```bash
   systemctl status mediamtx
   ```

2. **Test direct camera access**:
   ```bash
   # Test if camera is accessible
   curl -I rtsp://127.0.0.1:8554/living_area
   ```

3. **Try software-only approach**:
   ```bash
   ffplay -hwaccel none -analyzeduration 10000000 -probesize 10000000 \
          -timeout 30000000 -rtsp_transport tcp -an \
          rtsp://127.0.0.1:8554/living_area
   ```

4. **Use VLC as fallback**:
   ```bash
   vlc --intf dummy --rtsp-tcp --no-audio --fullscreen \
       rtsp://127.0.0.1:8554/living_area
   ```

## Next Steps

1. Run the troubleshooting script: `./scripts/pi5_troubleshoot.sh`
2. Test the updated `smartpicam_no_reencode.py` 
3. Try the VLC grid test: `python3 scripts/vlc_grid_test.py`
4. If issues persist, check MediaMTX logs and camera connectivity

The key fixes in the updated code should resolve the UDP I/O errors you're experiencing with the grid display.
