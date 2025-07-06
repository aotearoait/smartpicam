#!/bin/bash
# SmartPiCam Pi 5 Troubleshooting Script
# Diagnose and fix common issues with video playback on Raspberry Pi 5

echo "=== SmartPiCam Pi 5 Troubleshooting ==="
echo "Date: $(date)"
echo

# Check Pi version
echo "1. Hardware Detection:"
if [ -f /proc/device-tree/model ]; then
    echo "   Hardware: $(cat /proc/device-tree/model)"
else
    echo "   Hardware: Unknown"
fi

# Check memory split
echo
echo "2. GPU Memory:"
GPU_MEM=$(vcgencmd get_mem gpu 2>/dev/null | cut -d= -f2)
ARM_MEM=$(vcgencmd get_mem arm 2>/dev/null | cut -d= -f2)
if [ -n "$GPU_MEM" ]; then
    echo "   GPU: $GPU_MEM"
    echo "   ARM: $ARM_MEM"
    GPU_NUM=$(echo $GPU_MEM | sed 's/M//')
    if [ "$GPU_NUM" -lt 128 ]; then
        echo "   ⚠️  WARNING: GPU memory is low. Consider increasing to 256MB:"
        echo "      sudo raspi-config -> Advanced Options -> Memory Split -> 256"
    fi
else
    echo "   Cannot detect memory split"
fi

# Check V4L2 devices
echo
echo "3. V4L2 Hardware Support:"
V4L2_DEVICES=$(ls /dev/video* 2>/dev/null)
if [ -n "$V4L2_DEVICES" ]; then
    echo "   Found V4L2 devices: $V4L2_DEVICES"
    for device in $V4L2_DEVICES; do
        if command -v v4l2-ctl >/dev/null; then
            echo "   $device capabilities:"
            v4l2-ctl --device=$device --list-formats 2>/dev/null | head -3 | sed 's/^/     /'
        fi
    done
else
    echo "   ⚠️  No V4L2 devices found"
    echo "      Hardware acceleration may not be available"
fi

# Check FFmpeg
echo
echo "4. FFmpeg Status:"
if command -v ffmpeg >/dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>/dev/null | head -1)
    echo "   ✓ $FFMPEG_VERSION"
    
    # Check hardware acceleration
    HW_ACCELS=$(ffmpeg -hwaccels 2>/dev/null | grep -v "^Hardware" | grep -v "^$")
    if echo "$HW_ACCELS" | grep -q "v4l2m2m\|drm"; then
        echo "   ✓ Hardware acceleration available:"
        echo "$HW_ACCELS" | sed 's/^/     /'
    else
        echo "   ⚠️  Limited hardware acceleration"
    fi
    
    # Check H.264 codec support
    if ffmpeg -encoders 2>/dev/null | grep -q "h264_v4l2m2m"; then
        echo "   ✓ H.264 hardware encoder available"
    else
        echo "   ⚠️  H.264 hardware encoder not found"
    fi
    
    if ffmpeg -decoders 2>/dev/null | grep -q "h264_v4l2m2m"; then
        echo "   ✓ H.264 hardware decoder available"
    else
        echo "   ⚠️  H.264 hardware decoder not found"
    fi
else
    echo "   ✗ FFmpeg not found"
    echo "      Install with: sudo apt update && sudo apt install ffmpeg"
fi

# Check VLC
echo
echo "5. VLC Status:"
if command -v vlc >/dev/null; then
    VLC_VERSION=$(vlc --version 2>/dev/null | head -1)
    echo "   ✓ $VLC_VERSION"
    
    # Check VLC modules (sample a few key ones)
    if vlc --list 2>/dev/null | grep -q "v4l2"; then
        echo "   ✓ V4L2 support detected"
    fi
    if vlc --list 2>/dev/null | grep -q "mmal\|drm"; then
        echo "   ✓ Hardware acceleration modules found"
    fi
else
    echo "   ✗ VLC not found"
    echo "      Install with: sudo apt update && sudo apt install vlc"
fi

# Test RTSP stream if provided
echo
if [ $# -eq 1 ]; then
    RTSP_URL="$1"
    echo "6. Testing RTSP Stream: $RTSP_URL"
    
    # Test with ffprobe
    echo "   Testing stream analysis..."
    if timeout 10 ffprobe -v error -analyzeduration 10000000 -probesize 10000000 \
       -timeout 10000000 -rtsp_transport tcp -show_entries stream=codec_name,width,height \
       -of default=noprint_wrappers=1 "$RTSP_URL" >/tmp/stream_info.txt 2>/tmp/stream_error.txt; then
        echo "   ✓ Stream analysis successful:"
        cat /tmp/stream_info.txt | sed 's/^/     /'
    else
        echo "   ✗ Stream analysis failed:"
        head -3 /tmp/stream_error.txt | sed 's/^/     /'
    fi
    
    # Test playback with optimized settings
    echo "   Testing optimized playback (5 seconds)..."
    if timeout 8 ffmpeg -y -v error -analyzeduration 10000000 -probesize 10000000 \
       -timeout 10000000 -rtsp_transport tcp -i "$RTSP_URL" -t 3 -f null - \
       >/dev/null 2>/tmp/playback_error.txt; then
        echo "   ✓ Playback test successful"
    else
        echo "   ✗ Playback test failed:"
        head -3 /tmp/playback_error.txt | sed 's/^/     /'
    fi
    
    # Clean up temp files
    rm -f /tmp/stream_info.txt /tmp/stream_error.txt /tmp/playback_error.txt
else
    echo "6. RTSP Stream Test:"
    echo "   To test an RTSP stream, run: $0 <rtsp_url>"
fi

# System recommendations
echo
echo "=== RECOMMENDATIONS ==="

# Audio issues fix
echo "• Fix SDL audio errors (common with Pi 5):"
echo "  Add '-an' flag to disable audio in FFmpeg/FFplay commands"

# Hardware acceleration
echo "• For Pi 5 hardware acceleration issues:"
echo "  Try '-hwaccel auto' instead of '-hwaccel drm'"
echo "  Use software decoding if hardware fails"

# RTSP optimization
echo "• For RTSP stream issues:"
echo "  Increase analysis: -analyzeduration 10000000 -probesize 10000000"
echo "  Force TCP: -rtsp_transport tcp"
echo "  Add timeout: -timeout 10000000"

# VLC alternative
echo "• If FFmpeg fails consistently:"
echo "  Try VLC with: vlc --intf dummy --rtsp-tcp --no-audio <rtsp_url>"

# Memory optimization
if [ -n "$GPU_MEM" ] && [ "${GPU_MEM%M}" -lt 256 ]; then
    echo "• Increase GPU memory to 256MB for better video performance"
fi

echo
echo "=== QUICK FIXES ==="
echo "1. Update system:"
echo "   sudo apt update && sudo apt upgrade"
echo
echo "2. Install/reinstall video packages:"
echo "   sudo apt install ffmpeg vlc v4l-utils"
echo
echo "3. Test your RTSP stream with optimized command:"
echo "   ffplay -analyzeduration 10000000 -probesize 10000000 -timeout 30000000 \\"
echo "          -rtsp_transport tcp -an -framedrop <your_rtsp_url>"
echo
echo "4. If hardware acceleration fails, force software:"
echo "   ffplay -analyzeduration 10000000 -probesize 10000000 -timeout 30000000 \\"
echo "          -rtsp_transport tcp -an -framedrop -hwaccel none <your_rtsp_url>"

echo
echo "=== TROUBLESHOOTING COMPLETE ==="
