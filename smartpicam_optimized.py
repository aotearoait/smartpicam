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
    buffer_size: str = "32k"
    thread_count: int = 1  # Limit threads per stream
    preset: str = "ultrafast"  # For any encoding operations
    skip_failed_cameras: bool = True  # Skip cameras that fail testing
    # Placeholder options
    show_placeholders: bool = True  # Show placeholders for failed/disabled cameras
    placeholder_image: str = "assets/camera_offline.png"  # Path to placeholder image
    placeholder_text_color: str = "white"  # Text color for camera name
    placeholder_bg_color: str = "black"  # Background color for placeholder

class OptimizedSmartPiCam:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.working_cameras: List[Camera] = []  # Only cameras that pass testing
        self.failed_cameras: List[Camera] = []   # Cameras that failed testing
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
        self.logger.info("Optimized SmartPiCam v2.1 - Performance Enhanced with Placeholders")
        
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
    
    def _create_placeholder_for_camera(self, camera: Camera, reason: str = "offline") -> str:
        """Create a placeholder input for a failed or disabled camera"""
        if self.display_config.show_placeholders:
            # Check if placeholder image exists
            placeholder_path = self.display_config.placeholder_image
            if os.path.exists(placeholder_path):
                # Use image file as placeholder
                return f"-loop 1 -i {placeholder_path}"
            else:
                # Create text-based placeholder using FFmpeg's color and drawtext filters
                text = f"{camera.name}\\n({reason.upper()})"
                placeholder = (f"-f lavfi -i color=c={self.display_config.placeholder_bg_color}:"
                             f"s={camera.width}x{camera.height}:r=25")
                return placeholder
        else:
            # Return black screen
            return f"-f lavfi -i color=c=black:s={camera.width}x{camera.height}:r=25"
    
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
        """Build optimized FFmpeg command with placeholders for failed cameras"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y"]
        
        # Global optimizations
        cmd.extend([
            "-loglevel", "warning",  # Reduce log verbosity
            "-nostdin",  # Don't read from stdin
            "-err_detect", "ignore_err"  # Ignore minor errors
        ])
        
        # Build input list with both working cameras and placeholders
        input_sources = []
        camera_map = {}  # Maps input index to camera
        
        for camera in self.cameras:
            input_index = len(input_sources)
            camera_map[input_index] = camera
            
            if camera in self.working_cameras:
                # Working camera - use actual stream
                stream_params = self._get_optimal_stream_params(camera)
                cmd.extend(stream_params)
                cmd.extend(["-i", camera.url])
                input_sources.append(("camera", camera))
                self.logger.debug(f"Input {input_index}: Working camera {camera.name}")
            else:
                # Failed camera - use placeholder
                reason = "timeout" if camera in self.failed_cameras else "offline"
                placeholder_input = self._create_placeholder_for_camera(camera, reason)
                cmd.extend(placeholder_input.split())
                input_sources.append(("placeholder", camera))
                self.logger.debug(f"Input {input_index}: Placeholder for {camera.name} ({reason})")
        
        # Build optimized filter complex
        filter_parts = []
        
        # Create background
        bg_filter = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}:rate=25[bg]"
        filter_parts.append(bg_filter)
        
        # Process each input (camera or placeholder)
        overlay_input = "[bg]"
        for i, (source_type, camera) in enumerate(input_sources):
            if source_type == "camera":
                # Normal camera processing
                scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}:flags=fast_bilinear,fps=25[v{i}]"
            else:
                # Placeholder processing with text overlay
                if self.display_config.show_placeholders and not os.path.exists(self.display_config.placeholder_image):
                    # Add text overlay for camera name and status
                    reason = "TIMEOUT" if camera in self.failed_cameras else "OFFLINE"
                    text_filter = (f"[{i}:v]scale={camera.width}:{camera.height},"
                                 f"drawtext=text='{camera.name}\\n({reason})':fontsize=24:"
                                 f"fontcolor={self.display_config.placeholder_text_color}:"
                                 f"x=(w-text_w)/2:y=(h-text_h)/2[v{i}]")
                    scale_filter = text_filter
                else:
                    # Just scale the placeholder
                    scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}[v{i}]"
            
            filter_parts.append(scale_filter)
            
            # Chain overlays
            if i == len(input_sources) - 1:
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
        """Test camera streams in parallel and filter out failed ones"""
        self.logger.info("Testing camera streams in parallel...")
        
        def test_single_camera(camera):
            test_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-timeout", "10000000",  # 10 second timeout in microseconds
                "-i", camera.url,
                "-t", "1",
                "-f", "null", "-"
            ]
            
            try:
                result = subprocess.run(test_cmd, capture_output=True, timeout=12, text=True)
                if result.returncode == 0:
                    self.logger.info(f"✓ {camera.name} stream OK")
                    return camera, True
                else:
                    self.logger.warning(f"✗ {camera.name} stream failed: {result.stderr}")
                    return camera, False
            except subprocess.TimeoutExpired:
                self.logger.warning(f"✗ {camera.name} stream timeout")
                return camera, False
            except Exception as e:
                self.logger.warning(f"✗ {camera.name} stream error: {e}")
                return camera, False
        
        # Test all cameras in parallel
        working_cameras = []
        failed_cameras = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.cameras), 5)) as executor:
            future_to_camera = {executor.submit(test_single_camera, camera): camera 
                               for camera in self.cameras}
            
            for future in concurrent.futures.as_completed(future_to_camera, timeout=20):
                try:
                    camera, success = future.result()
                    if success:
                        working_cameras.append(camera)
                    else:
                        failed_cameras.append(camera)
                except Exception as e:
                    camera = future_to_camera[future]
                    self.logger.warning(f"Test error for {camera.name}: {e}")
                    failed_cameras.append(camera)
        
        # Update camera lists
        self.working_cameras = working_cameras
        self.failed_cameras = failed_cameras
        
        self.logger.info(f"Stream test complete: {len(working_cameras)}/{len(self.cameras)} cameras working")
        
        if failed_cameras:
            failed_names = [cam.name for cam in failed_cameras]
            if self.display_config.show_placeholders:
                self.logger.info(f"Will show placeholders for failed cameras: {', '.join(failed_names)}")
            else:
                self.logger.warning(f"Skipping failed cameras: {', '.join(failed_names)}")
        
        return len(self.cameras) > 0  # Continue if we have any cameras (working or placeholders)
    
    def _optimize_system_for_video(self):
        """Apply system-level optimizations for video processing"""
        try:
            # Set CPU governor to performance
            subprocess.run(['sudo', 'cpufreq-set', '-g', 'performance'], 
                         capture_output=True, timeout=5)
            
            # Check GPU memory
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
    
    def _setup_ffmpeg_preexec(self):
        """Setup function to be called before FFmpeg execution"""
        # Ignore SIGINT for FFmpeg process
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        
        # Try to set higher priority, but don't fail if it doesn't work
        try:
            os.setpriority(os.PRIO_PROCESS, 0, -5)
        except (OSError, PermissionError):
            # Not critical if this fails
            pass
    
    def start_display(self) -> bool:
        """Start the optimized FFmpeg display"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        # Apply system optimizations
        self._optimize_system_for_video()
        
        # Hide cursor
        self._hide_cursor()
        
        # Test streams in parallel and identify working/failed cameras
        if not self._test_camera_streams_parallel():
            self.logger.error("No cameras configured")
            return False
        
        # Show status of all cameras
        working_names = [cam.name for cam in self.working_cameras]
        failed_names = [cam.name for cam in self.failed_cameras]
        
        if working_names:
            self.logger.info(f"Working cameras: {', '.join(working_names)}")
        if failed_names:
            if self.display_config.show_placeholders:
                self.logger.info(f"Showing placeholders for: {', '.join(failed_names)}")
            else:
                self.logger.info(f"Skipping failed cameras: {', '.join(failed_names)}")
            
        cmd = self._build_optimized_ffmpeg_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting optimized FFmpeg display with placeholders...")
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
                preexec_fn=self._setup_ffmpeg_preexec,
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
        self.logger.info(f"  Total cameras: {len(self.cameras)}")
        self.logger.info(f"  Working cameras: {len(self.working_cameras)}")
        self.logger.info(f"  Failed cameras: {len(self.failed_cameras)}")
        self.logger.info(f"  Show placeholders: {self.display_config.show_placeholders}")
        self.logger.info(f"  Hardware accel: {self.display_config.hardware_accel}")
        self.logger.info(f"  Low latency: {self.display_config.low_latency}")
        self.logger.info(f"  Threads per stream: {self.display_config.thread_count}")
        self.logger.info(f"  Buffer size: {self.display_config.buffer_size}")
        
        # Log camera layout for all cameras
        for camera in self.cameras:
            status = "WORKING" if camera in self.working_cameras else "PLACEHOLDER"
            self.logger.info(f"  {camera.name}: {camera.width}x{camera.height} at ({camera.x},{camera.y}) [{status}]")
    
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
