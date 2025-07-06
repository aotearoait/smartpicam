#!/bin/bash
# MediaMTX + VLC Test Script for Pi 5
# Test individual streams before trying the grid

PI_IP="127.0.0.1"

echo "=== MediaMTX + VLC Pi 5 Test ==="
echo

# Test MediaMTX status
echo "1. Testing MediaMTX status..."
if curl -s -I http://127.0.0.1:8889 >/dev/null 2>&1; then
    echo "✓ MediaMTX WebRTC interface responding"
else
    echo "⚠️ MediaMTX may not be running"
fi

# Test individual streams
streams=("living_area" "garage" "entrance" "driveway" "aria" "hillmorton_entrance" "hillmorton_side" "timaru")

echo
echo "2. Testing individual RTSP streams..."
for stream in "${streams[@]}"; do
    echo -n "Testing $stream... "
    if timeout 5 ffprobe -v quiet -rtsp_transport tcp rtsp://$PI_IP:8554/$stream >/dev/null 2>&1; then
        echo "✓ Working"
    else
        echo "✗ Failed"
    fi
done

echo
echo "3. Testing single VLC stream (will play for 10 seconds)..."
echo "Testing living_area stream with Pi 5 optimizations..."

timeout 10 vlc \
  --intf dummy \
  --rtsp-tcp \
  --no-audio \
  --network-caching=1000 \
  --live-caching=1000 \
  --rtsp-caching=1000 \
  --avcodec-hw=none \
  --avcodec-skiploopfilter=4 \
  --verbose=1 \
  rtsp://$PI_IP:8554/living_area \
  vlc://quit

echo
echo "4. If single stream worked, try the grid:"
echo "   chmod +x scripts/vlc_grid_pi5.sh"
echo "   ./scripts/vlc_grid_pi5.sh"

echo
echo "5. If streams fail, check MediaMTX logs:"
echo "   sudo journalctl -u mediamtx -f"

echo
echo "6. Common Pi 5 fixes:"
echo "   - Increase GPU memory: sudo raspi-config -> Advanced -> Memory Split -> 256"
echo "   - Update system: sudo apt update && sudo apt upgrade"
echo "   - Restart MediaMTX: sudo systemctl restart mediamtx"
