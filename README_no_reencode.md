# SmartPiCam No Re-encode Branch

## 🚀 Ultra Low Latency Solution

This branch implements a solution to eliminate the 18-second delay by using conditional remuxing vs re-encoding based on the stream's codec.

## 🏗️ Key Changes

### Architecture
- **Codec Detection**: Uses `ffprobe` to detect if incoming RTSP streams are H.264
- **Conditional Processing**:
  - **H.264 streams** → Remux with `-c copy` (no transcoding)
  - **Non-H.264 streams** → Hardware encode with `h264_v4l2m2m`
- **UDP Pipeline**: Individual streams → UDP → Grid display
- **Dynamic Ports**: Cameras assigned UDP ports 5000-5009

### Benefits
- **Near-zero latency** for H.264 streams (no re-encoding delay)
- **Lower CPU usage** on Pi when using copy mode
- **Maintains compatibility** with existing config files
- **Graceful fallback** for non-H.264 streams

## 📋 Usage

### 1. Update Camera URLs
Edit your `config/smartpicam.json` with your actual Unifi & Reolink RTSP URLs:

```json
{
  "cameras": [
    {
      "name": "Camera1",
      "url": "rtsp://username:password@192.168.1.100:554/stream",
      "enabled": true,
      ...
    }
  ]
}
```

### 2. Run the No Re-encode Version
```bash
python3 smartpicam_no_reencode.py
```

### 3. Monitor Performance
- Check CPU usage: `top` (should show <50% total across ffmpeg processes)
- Monitor logs for latency measurements
- Look for "COPY mode" vs "HARDWARE ENCODE mode" in logs

## 🔧 Expected Results

### Latency Reduction
- **H.264 streams**: Sub-second latency (down from 18 seconds)
- **Non-H.264 streams**: Reduced to ~2-3 seconds (hardware encoding)

### CPU Impact
- **Copy mode**: ~5-10% CPU per stream
- **Encode mode**: ~15-25% CPU per stream
- **Total**: Should support 8-10 streams on Pi 4

## 📊 Testing Steps

1. **Start with 1-2 cameras** to verify functionality
2. **Measure latency** using timestamp logs
3. **Monitor CPU usage** with `top`
4. **Gradually scale** to all 8-10 feeds
5. **Compare** with original implementation

## 🐛 Troubleshooting

### No Video Output
- Check camera URLs are accessible
- Verify ffprobe can detect codec
- Monitor UDP port availability (5000-5009)

### High CPU Usage
- Confirm H.264 streams are using "COPY mode"
- Check for codec detection failures
- Consider reducing bitrate for encode mode streams

### Stream Failures
- Check network connectivity to cameras
- Verify RTSP credentials
- Monitor ffmpeg error logs

## 🔄 Fallback

To revert to the original implementation:
```bash
git checkout main
python3 smartpicam.py
```

## 📈 Performance Monitoring

The script logs:
- Codec detection results
- Stream startup times
- Processing mode (COPY vs ENCODE)
- UDP port assignments
- Error conditions and restarts

Monitor these logs to verify optimal performance and troubleshoot issues.
