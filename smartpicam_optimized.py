#!/usr/bin/env python3

import json
import logging
import subprocess
import time
import signal
import sys
import os
import shlex
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import threading
import concurrent.futures
from queue import Queue

@dataclass
class Camera:
    name: str
    url: str
    window_id: int
    x: int
    y: int
    width: int
    height: int
    enabled: bool = True

@dataclass 
class DisplayConfig:
    screen_width: int = 1920
    screen_height: int = 1080
    grid_cols: int = 2
    grid_rows: int = 2
    enable_rotation: bool = False
    rotation_interval: int = 30
    network_timeout: int = 30
    restart_retries: int = 3
    log_level: str = "INFO"
    # New performance options
    hardware_accel: bool = True
    low_latency: bool = True
    buffer_size: str = "64k"
    thread_count: int = 2  # Limit threads per stream
    preset: str = "ultrafast"  # For any encoding operations

class OptimizedSmartPiCam:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.running = False
        self.cursor_hidden = False
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("smartpicam")
        self.logger.info("Optimized SmartPiCam v2.1 - Performance Enhanced")
        
    def _hide_cursor(self):
        """Hide the console cursor to prevent flickering"""
        try:
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            subprocess.run(['sudo', 'sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'], 
                         capture_output=True, timeout=5)
            subprocess.run(['setterm', '-cursor', 'off'], 
                         capture_output=True, timeout=5)
            self.cursor_hidden = True
            self.logger.info("Console cursor hidden")
        except Exception as e:
            self.logger.warning(f"Could not hide cursor: {e}")
    
    def _show_cursor(self):
        """Show the console cursor again"""
        try:
            if self.cursor_hidden:
                sys.stdout.write('\033[?25h')
                sys.stdout.flush()
                subprocess.run(['sudo', 'sh', '-c', 'echo 1 > /sys/class/graphics/fbcon/cursor_blink'], 
                             capture_output=True, timeout=5)
                subprocess.run(['setterm', '-cursor', 'on'], 
                             capture_output=True, timeout=5)
                self.cursor_hidden = False
                self.logger.info("Console cursor restored")
        except Exception as e:
            self.logger.warning(f"Could not restore cursor: {e}")
        
    def load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            # Parse display config with new performance options
            display_data = config_data.get("display", {})
            self.display_config = DisplayConfig(**display_data)
            
            # Set logging level
            numeric_level = getattr(logging, self.display_config.log_level.upper(), logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            
            # Parse cameras
            cameras_data = config_data.get("cameras", [])
            enabled_cameras = [Camera(**cam_data) for cam_data in cameras_data if cam_data.get("enabled", True)]
            
            if not enabled_cameras:
                self.logger.error("No enabled cameras found in configuration")
                return False
                
            self.cameras = enabled_cameras
            self.logger.info(f"Loaded configuration with {len(self.cameras)} enabled cameras")
            
            # Performance recommendations
            if len(self.cameras) > 6:
                self.logger.warning(f"High camera count ({len(self.cameras)}) detected. Consider using lower resolution streams.")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False
    
    def _get_optimal_stream_params(self, camera: Camera) -> List[str]:
        """Get optimized parameters for each camera stream"""
        params = []
        
        # Hardware acceleration for Pi 5
        if self.display_config.hardware_accel:
            params.extend(["-hwaccel", "auto"])
        
        # Low latency options
        if self.display_config.low_latency:
            params.extend([
                "-fflags", "+genpts+discardcorrupt",
                "-flags", "low_delay",
                "-strict", "experimental"
            ])
        
        # Network and buffer optimizations
        params.extend([
            "-rtsp_transport", "tcp",  # More reliable than UDP
            "-buffer_size", self.display_config.buffer_size,
            "-max_delay", "500000",  # 0.5 second max delay
            "-reorder_queue_size", "0",  # Disable reordering for low latency
            "-thread_queue_size", "8"  # Small queue for lower memory usage
        ])
        
        # Thread limitation per stream
        params.extend(["-threads", str(self.display_config.thread_count)])
        
        return params
    
    def _build_optimized_ffmpeg_command(self) -> List[str]:
        """Build optimized FFmpeg command with better resource management"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y"]
        
        # Global optimizations
        cmd.extend([
            "-loglevel", "warning",  # Reduce log verbosity
            "-nostdin",  # Don't read from stdin
            "-err_detect", "ignore_err"  # Ignore minor errors
        ])
        
        # Add optimized input streams
        for i, camera in enumerate(self.cameras):
            stream_params = self._get_optimal_stream_params(camera)
            cmd.extend(stream_params)
            cmd.extend(["-i", camera.url])
        
        # Build optimized filter complex
        filter_parts = []
        
        # Create background
        bg_filter = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}:rate=25[bg]"
        filter_parts.append(bg_filter)
        
        # Process each camera with minimal operations
        overlay_input = "[bg]"
        for i, camera in enumerate(self.cameras):
            # Direct scale to target size with efficient scaling algorithm
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}:flags=fast_bilinear,fps=25[v{i}]"
            filter_parts.append(scale_filter)
            
            # Chain overlays
            if i == len(self.cameras) - 1:
                # Last overlay with framebuffer format
                overlay_filter = f"{overlay_input}[v{i}]overlay={camera.x}:{camera.y}:format=auto,format=rgb565le[out]"
            else:
                overlay_filter = f"{overlay_input}[v{i}]overlay={camera.x}:{camera.y}[bg{i}]"
                overlay_input = f"[bg{i}]"
            filter_parts.append(overlay_filter)
        
        # Join all filters
        filter_complex = ";".join(filter_parts)
        
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-f", "fbdev",
            "-pix_fmt", "rgb565le",
            "/dev/fb0"
        ])
        
        return cmd
    
    def _test_camera_streams_parallel(self) -> bool:
        """Test camera streams in parallel for faster startup"""
        self.logger.info("Testing camera streams in parallel...")
        
        def test_single_camera(camera):
            test_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-i", camera.url,
                "-t", "1",
                "-f", "null", "-"
            ]
            
            try:
                result = subprocess.run(test_cmd, capture_output=True, timeout=10, text=True)
                if result.returncode == 0:
                    self.logger.info(f"✓ {camera.name} stream OK")
                    return True
                else:
                    self.logger.warning(f"✗ {camera.name} stream issue: {result.stderr}")
                    return False
            except subprocess.TimeoutExpired:
                self.logger.warning(f"✗ {camera.name} stream timeout")
                return False
            except Exception as e:
                self.logger.warning(f"✗ {camera.name} stream error: {e}")
                return False
        
        # Test all cameras in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.cameras), 5)) as executor:
            future_to_camera = {executor.submit(test_single_camera, camera): camera 
                               for camera in self.cameras}
            
            working_cameras = 0
            for future in concurrent.futures.as_completed(future_to_camera, timeout=15):
                camera = future_to_camera[future]
                try:
                    if future.result():
                        working_cameras += 1
                except Exception as e:
                    self.logger.warning(f"Test error for {camera.name}: {e}")
        
        self.logger.info(f"Stream test complete: {working_cameras}/{len(self.cameras)} cameras responding")
        return working_cameras > 0
    
    def _optimize_system_for_video(self):
        """Apply system-level optimizations for video processing"""
        try:
            # Set CPU governor to performance
            subprocess.run(['sudo', 'cpufreq-set', '-g', 'performance'], 
                         capture_output=True, timeout=5)
            
            # Disable GPU memory split if needed (Pi 5 specific)
            # Note: This requires reboot to take effect
            gpu_mem_check = subprocess.run(['vcgencmd', 'get_mem', 'gpu'], 
                                         capture_output=True, text=True)
            if gpu_mem_check.returncode == 0:
                gpu_mem = gpu_mem_check.stdout.strip()
                self.logger.info(f"GPU memory: {gpu_mem}")
            
            # Increase video core frequency (if supported)
            subprocess.run(['sudo', 'vcgencmd', 'force_turbo', '1'], 
                         capture_output=True, timeout=5)
            
            self.logger.info("Applied system optimizations")
            
        except Exception as e:
            self.logger.warning(f"Could not apply system optimizations: {e}")
    
    def start_display(self) -> bool:
        """Start the optimized FFmpeg display"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        # Apply system optimizations
        self._optimize_system_for_video()
        
        # Hide cursor
        self._hide_cursor()
        
        # Test streams in parallel
        if not self._test_camera_streams_parallel():
            self.logger.error("No working camera streams found")
            return False
            
        cmd = self._build_optimized_ffmpeg_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting optimized FFmpeg display...")
        self.logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            # Optimized environment
            env = os.environ.copy()
            env.pop('DISPLAY', None)
            env['FFMPEG_THREAD_QUEUE_SIZE'] = '8'
            env['MALLOC_MMAP_THRESHOLD_'] = '128'  # Reduce memory fragmentation
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: (
                    signal.signal(signal.SIGINT, signal.SIG_IGN),
                    os.setpriority(os.PRIO_PROCESS, 0, -5)  # Higher priority
                ),
                env=env
            )
            
            # Monitor startup
            time.sleep(3)
            
            if self.ffmpeg_process.poll() is None:
                self.logger.info("Optimized FFmpeg display started successfully")
                self._log_performance_info()
                return True
            else:
                stdout, stderr = self.ffmpeg_process.communicate()
                self.logger.error(f"FFmpeg failed to start:")
                if stderr:
                    self.logger.error(f"STDERR: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start FFmpeg: {e}")
            return False
    
    def _log_performance_info(self):
        """Log performance and resource information"""
        self.logger.info("Performance configuration:")
        self.logger.info(f"  Cameras: {len(self.cameras)}")
        self.logger.info(f"  Hardware accel: {self.display_config.hardware_accel}")
        self.logger.info(f"  Low latency: {self.display_config.low_latency}")
        self.logger.info(f"  Threads per stream: {self.display_config.thread_count}")
        self.logger.info(f"  Buffer size: {self.display_config.buffer_size}")
        
        # Log camera layout
        for camera in self.cameras:
            self.logger.info(f"  {camera.name}: {camera.width}x{camera.height} at ({camera.x},{camera.y})")
    
    def stop_display(self):
        """Stop the FFmpeg display"""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.ffmpeg_process.kill()
                self.ffmpeg_process.wait()
            finally:
                self.ffmpeg_process = None
                self.logger.info("FFmpeg display stopped")
        
        self._show_cursor()
                
    def is_healthy(self) -> bool:
        """Check if display is running properly"""
        return self.ffmpeg_process is not None and self.ffmpeg_process.poll() is None
        
    def monitor_display(self):
        """Monitor and restart display if it fails"""
        restart_count = 0
        
        while self.running:
            if not self.is_healthy():
                if restart_count >= self.display_config.restart_retries:
                    self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
                    break
                
                restart_count += 1
                self.logger.warning(f"Display unhealthy, restarting ({restart_count}/{self.display_config.restart_retries})")
                
                # Log error output
                if self.ffmpeg_process:
                    try:
                        stdout, stderr = self.ffmpeg_process.communicate(timeout=1)
                        if stderr:
                            self.logger.error(f"FFmpeg error: {stderr.decode()}")
                    except:
                        pass
                
                self.stop_display()
                time.sleep(3)  # Shorter wait for restart
                
                if self.start_display():
                    restart_count = 0
                    
            time.sleep(10)
            
    def run(self):
        """Main run loop"""
        if not self.load_config():
            return False
            
        if not self.start_display():
            self.logger.error("Failed to start display")
            return False
            
        self.running = True
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_display, daemon=True)
        monitor_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
        finally:
            self.stop_display()
            
        return True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global app
    if 'app' in globals():
        app.stop_display()
    sys.exit(0)

def main():
    global app
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = OptimizedSmartPiCam()
    app.logger.info("Starting Optimized SmartPiCam...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
