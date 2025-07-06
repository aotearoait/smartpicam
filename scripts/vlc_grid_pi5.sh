#!/bin/bash
# VLC Grid Display - Pi 5 Optimized Version
# Fixes for hardware decoding and buffering issues

PI_IP="127.0.0.1"

echo "Starting VLC Grid Display - Pi 5 Optimized"
echo "Cameras: 8 streams in 3x3 grid"

vlc \
  --intf dummy \
  --no-video-title-show \
  --video-filter=wall \
  --wall-cols=3 \
  --wall-rows=3 \
  --wall-active=111111110 \
  --fullscreen \
  --no-audio \
  --network-caching=1000 \
  --live-caching=1000 \
  --rtsp-caching=1000 \
  --avcodec-hw=none \
  --avcodec-skiploopfilter=4 \
  --avcodec-skip-frame=0 \
  --avcodec-skip-idct=0 \
  --rtsp-tcp \
  --no-drop-late-frames \
  --no-skip-frames \
  --clock-jitter=0 \
  --network-synchronisation \
  --verbose=2 \
  rtsp://$PI_IP:8554/living_area \
  rtsp://$PI_IP:8554/garage \
  rtsp://$PI_IP:8554/entrance \
  rtsp://$PI_IP:8554/driveway \
  rtsp://$PI_IP:8554/aria \
  rtsp://$PI_IP:8554/hillmorton_entrance \
  rtsp://$PI_IP:8554/hillmorton_side \
  rtsp://$PI_IP:8554/timaru \
  vlc://quit
