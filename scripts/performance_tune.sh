#!/bin/bash

# Performance Tuning Script for SmartPiCam on Raspberry Pi 5
# Run with sudo: sudo ./performance_tune.sh

echo "🚀 SmartPiCam Performance Tuning for Raspberry Pi 5"
echo "=================================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (sudo ./performance_tune.sh)"
    exit 1
fi

# Get the actual user who ran sudo
ACTUAL_USER=${SUDO_USER:-$(whoami)}
USER_HOME=$(eval echo ~$ACTUAL_USER)

echo "📋 System Information:"
echo "  Model: $(cat /proc/device-tree/model 2>/dev/null || echo 'Unknown')"
echo "  Memory: $(free -h | grep 'Mem:' | awk '{print $2}')"
echo "  CPU Cores: $(nproc)"
echo "  SmartPiCam Directory: $USER_HOME/smartpicam"
echo ""

# Function to backup config files
backup_config() {
    local file=$1
    if [ -f "$file" ]; then
        cp "$file" "${file}.backup.$(date +%Y%m%d_%H%M%S)"
        echo "✓ Backed up $file"
    fi
}

# 1. Configure boot settings for optimal performance
echo "⚙️  Configuring boot settings..."
backup_config "/boot/firmware/config.txt"

# Pi 5 specific optimizations
if grep -q "Pi 5" /proc/device-tree/model 2>/dev/null; then
    echo "  Detected Raspberry Pi 5 - applying Pi 5 optimizations"
    
    # Update config.txt for Pi 5
    cat >> /boot/firmware/config.txt << 'EOF'

# SmartPiCam Performance Optimizations for Pi 5
# GPU Memory (sufficient for video processing)
gpu_mem=128

# CPU Performance
arm_boost=1
over_voltage=6
arm_freq=2400

# GPU Performance  
gpu_freq=900

# Video codec performance
decode_WMV3=1
decode_WVC1=1
decode_MPG2=1
decode_MPG4=1

# Disable unused features to save resources
dtparam=audio=off
camera_auto_detect=0

# Network performance
dtparam=pcie=on
dtparam=pciex1_gen=3

# Memory performance
disable_l2cache=0
EOF
    echo "  ✓ Pi 5 boot configuration updated"
else
    echo "  ⚠️  Non-Pi 5 detected - applying generic optimizations"
    cat >> /boot/firmware/config.txt << 'EOF'

# SmartPiCam Performance Optimizations
gpu_mem=128
arm_boost=1
dtparam=audio=off
camera_auto_detect=0
EOF
fi

# 2. Configure systemd optimizations
echo "⚙️  Configuring systemd optimizations..."

# Create optimized smartpicam service
cat > /etc/systemd/system/smartpicam-optimized.service << EOF
[Unit]
Description=SmartPiCam Optimized Multi-Camera Display
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$ACTUAL_USER
Group=video
ExecStart=/usr/bin/python3 $USER_HOME/smartpicam/smartpicam_optimized.py
WorkingDirectory=$USER_HOME/smartpicam
Restart=always
RestartSec=10

# Performance optimizations
Nice=-10
IOSchedulingClass=1
IOSchedulingPriority=4
CPUSchedulingPolicy=1
CPUSchedulingPriority=50

# Resource limits
MemoryMax=2G
TasksMax=200

# Environment
Environment=DISPLAY=:0
Environment=MALLOC_MMAP_THRESHOLD_=128
Environment=MALLOC_TRIM_THRESHOLD_=128
Environment=FFMPEG_THREAD_QUEUE_SIZE=8

[Install]
WantedBy=multi-user.target
EOF

echo "  ✓ Optimized systemd service created"

# 3. Configure memory and swap optimizations
echo "⚙️  Configuring memory optimizations..."

# Update sysctl for video processing
cat > /etc/sysctl.d/99-smartpicam.conf << 'EOF'
# SmartPiCam Memory Optimizations
vm.swappiness=1
vm.dirty_ratio=15
vm.dirty_background_ratio=5
vm.vfs_cache_pressure=50
vm.min_free_kbytes=65536

# Network optimizations for RTSP
net.core.rmem_default=262144
net.core.rmem_max=16777216
net.core.wmem_default=262144
net.core.wmem_max=16777216
net.ipv4.tcp_rmem=4096 262144 16777216
net.ipv4.tcp_wmem=4096 262144 16777216
net.core.netdev_max_backlog=5000
EOF

echo "  ✓ Memory optimization settings applied"

# 4. Configure CPU governor for performance
echo "⚙️  Configuring CPU performance..."

# Install cpufrequtils if not present
if ! command -v cpufreq-set &> /dev/null; then
    echo "  Installing cpufrequtils..."
    apt-get update -qq
    apt-get install -y cpufrequtils
fi

# Set CPU governor to performance
echo "performance" > /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || true
echo "performance" > /sys/devices/system/cpu/cpu1/cpufreq/scaling_governor 2>/dev/null || true
echo "performance" > /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor 2>/dev/null || true
echo "performance" > /sys/devices/system/cpu/cpu3/cpufreq/scaling_governor 2>/dev/null || true

# Create service to set CPU governor on boot
cat > /etc/systemd/system/cpu-performance.service << 'EOF'
[Unit]
Description=Set CPU Governor to Performance
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > $cpu 2>/dev/null || true; done'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl enable cpu-performance.service
echo "  ✓ CPU performance governor configured"

# 5. Configure GPU memory split and video acceleration
echo "⚙️  Configuring GPU optimizations..."

# Check current GPU memory
current_gpu_mem=$(vcgencmd get_mem gpu | cut -d= -f2 | cut -d'M' -f1)
echo "  Current GPU memory: ${current_gpu_mem}M"

if [ "$current_gpu_mem" -lt 128 ]; then
    echo "  ⚠️  GPU memory is low for video processing"
    echo "  📝 Note: Reboot required for GPU memory changes to take effect"
fi

# 6. Install and configure video acceleration tools
echo "⚙️  Installing video acceleration tools..."

# Update package list
apt-get update -qq

# Install essential packages for video processing
apt-get install -y \
    ffmpeg \
    v4l-utils \
    mesa-utils \
    libgl1-mesa-dri \
    libraspberrypi0 \
    libraspberrypi-dev \
    libraspberrypi-doc \
    libraspberrypi-bin

echo "  ✓ Video acceleration tools installed"

# 7. Configure udev rules for video devices
echo "⚙️  Configuring device permissions..."

cat > /etc/udev/rules.d/99-smartpicam.rules << 'EOF'
# SmartPiCam device permissions
SUBSYSTEM=="video4linux", GROUP="video", MODE="0664"
KERNEL=="fb*", GROUP="video", MODE="0664"
SUBSYSTEM=="graphics", GROUP="video", MODE="0664"
EOF

# Add user to video group
usermod -a -G video $ACTUAL_USER
echo "  ✓ Device permissions configured"

# 8. Configure systemd journal limits
echo "⚙️  Configuring logging optimizations..."

mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/smartpicam.conf << 'EOF'
[Journal]
SystemMaxUse=100M
SystemMaxFileSize=10M
MaxRetentionSec=1week
MaxFileSec=1day
EOF

echo "  ✓ Journal logging optimized"

# 9. Create monitoring script
echo "⚙️  Creating monitoring script..."

cat > $USER_HOME/smartpicam/monitor_performance.sh << 'EOF'
#!/bin/bash

echo "📊 SmartPiCam Performance Monitor"
echo "================================="
echo ""

# System information
echo "🖥️  System Status:"
echo "  Uptime: $(uptime -p)"
echo "  Load: $(uptime | awk -F'load average:' '{print $2}')"
echo "  Temperature: $(vcgencmd measure_temp)"
echo "  CPU Frequency: $(vcgencmd measure_clock arm | awk -F= '{printf "%.0f MHz\n", $2/1000000}')"
echo "  GPU Frequency: $(vcgencmd measure_clock core | awk -F= '{printf "%.0f MHz\n", $2/1000000}')"
echo ""

# Memory usage
echo "💾 Memory Usage:"
free -h | grep -E "Mem:|Swap:"
echo ""

# CPU usage
echo "⚙️  CPU Usage:"
top -bn1 | grep "Cpu(s)" | awk '{print "  " $0}'
echo ""

# GPU memory
echo "🎮 GPU Memory:"
echo "  $(vcgencmd get_mem gpu)"
echo "  $(vcgencmd get_mem arm)"
echo ""

# FFmpeg processes
echo "📹 Video Processes:"
pgrep -f ffmpeg > /dev/null && {
    echo "  FFmpeg processes: $(pgrep -c ffmpeg)"
    ps aux | grep ffmpeg | grep -v grep | awk '{printf "  PID: %s, CPU: %s%%, MEM: %s%%\n", $2, $3, $4}'
} || echo "  No FFmpeg processes running"
echo ""

# Network connections
echo "🌐 Network Connections:"
echo "  Active RTSP connections: $(netstat -an | grep :554 | grep ESTABLISHED | wc -l)"
echo "  Total network connections: $(netstat -an | grep ESTABLISHED | wc -l)"
echo ""

# Disk usage
echo "💽 Storage:"
df -h / | tail -1 | awk '{printf "  Root: %s used, %s available (%s)\n", $3, $4, $5}'
echo ""

# SmartPiCam service status
echo "🔄 Service Status:"
systemctl is-active smartpicam-optimized > /dev/null && echo "  SmartPiCam: ✅ Active" || echo "  SmartPiCam: ❌ Inactive"
echo ""
EOF

chmod +x $USER_HOME/smartpicam/monitor_performance.sh
chown $ACTUAL_USER:$ACTUAL_USER $USER_HOME/smartpicam/monitor_performance.sh
echo "  ✓ Performance monitoring script created"

# 10. Create optimization verification script
echo "⚙️  Creating verification script..."

cat > $USER_HOME/smartpicam/verify_optimizations.sh << 'EOF'
#!/bin/bash

echo "🔍 SmartPiCam Optimization Verification"
echo "======================================="
echo ""

# Check CPU governor
echo "⚙️  CPU Configuration:"
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "$cpu" ]; then
        cpu_num=$(basename $(dirname "$cpu"))
        governor=$(cat "$cpu")
        echo "  $cpu_num: $governor"
    fi
done
echo ""

# Check GPU memory
echo "🎮 GPU Memory:"
vcgencmd get_mem gpu
vcgencmd get_mem arm
echo ""

# Check swap usage
echo "💾 Memory Status:"
echo "  $(free -h | grep Swap | awk '{print "Swap: " $2 " total, " $3 " used"}')"
echo "  Swappiness: $(cat /proc/sys/vm/swappiness)"
echo ""

# Check thermal throttling
echo "🌡️  Thermal Status:"
throttled=$(vcgencmd get_throttled)
if [ "$throttled" = "throttled=0x0" ]; then
    echo "  ✅ No thermal throttling detected"
else
    echo "  ⚠️  Thermal throttling detected: $throttled"
fi
echo ""

# Check network settings
echo "🌐 Network Settings:"
echo "  TCP rmem max: $(cat /proc/sys/net/core/rmem_max)"
echo "  TCP wmem max: $(cat /proc/sys/net/core/wmem_max)"
echo ""

# Check video group membership
echo "👥 User Permissions:"
if groups $USER | grep -q video; then
    echo "  ✅ User '$USER' is in video group"
else
    echo "  ❌ User '$USER' is NOT in video group"
fi
echo ""

echo "✅ Verification complete"
EOF

chmod +x $USER_HOME/smartpicam/verify_optimizations.sh
chown $ACTUAL_USER:$ACTUAL_USER $USER_HOME/smartpicam/verify_optimizations.sh
echo "  ✓ Verification script created"

# Apply sysctl settings immediately
sysctl -p /etc/sysctl.d/99-smartpicam.conf > /dev/null 2>&1

# Reload systemd
systemctl daemon-reload

echo ""
echo "🎉 Performance Tuning Complete!"
echo "==============================="
echo ""
echo "📋 Applied Optimizations:"
echo "  ✅ Boot configuration optimized"
echo "  ✅ CPU governor set to performance"
echo "  ✅ Memory settings tuned"
echo "  ✅ Network buffers increased"
echo "  ✅ GPU memory configured"
echo "  ✅ Video acceleration enabled"
echo "  ✅ Device permissions set"
echo "  ✅ Logging optimized"
echo ""
echo "📝 Next Steps:"
echo "  1. Reboot system: sudo reboot"
echo "  2. After reboot, verify: $USER_HOME/smartpicam/verify_optimizations.sh"
echo "  3. Monitor performance: $USER_HOME/smartpicam/monitor_performance.sh"
echo "  4. Test optimized version: cd $USER_HOME/smartpicam && python3 smartpicam_optimized.py"
echo ""
echo "⚠️  Important Notes:"
echo "  • A reboot is required for all changes to take effect"
echo "  • Monitor temperatures after reboot"
echo "  • Use 'sudo systemctl enable smartpicam-optimized' for the new service"
echo ""
echo "🔧 Troubleshooting:"
echo "  • Check logs: journalctl -u smartpicam-optimized -f"
echo "  • Monitor resources: htop"
echo "  • Check thermal: watch vcgencmd measure_temp"
echo ""
