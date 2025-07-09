#!/usr/bin/env python3
"""
SmartPyCam - Multi-Camera RTSP Display System
A Python implementation that replicates displaycameras functionality for Ubuntu/Intel NUC
Uses X11 windowed approach with individual MPV processes for each camera
"""

import json
import logging
import subprocess
import time
import signal
import sys
import os
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

__version__ = "1.0.0"
__author__ = "SmartPiCam Project"

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
    status: str = "placeholder"  # placeholder, testing, connected, failed
    last_test: float = 0
    retry_count: int = 0
    player_process: Optional[subprocess.Popen] = field(default=None, init=False)
    placeholder_process: Optional[subprocess.Popen] = field(default=None, init=False)

@dataclass 
class DisplayConfig:
    screen_width: int = 2560
    screen_height: int = 1440
    grid_cols: int = 2
    grid_rows: int = 2
    enable_rotation: bool = False
    rotation_interval: int = 30
    network_timeout: int = 30
    restart_retries: int = 3
    log_level: str = "INFO"
    camera_retry_interval: int = 30

class SmartPyCam:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.running = False
        self.camera_threads: Dict[int, threading.Thread] = {}
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        try:
            # Create log directory if it doesn't exist
            os.makedirs('/var/log', exist_ok=True)
            
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('/var/log/smartpycam.log'),
                    logging.StreamHandler()
                ]
            )
        except PermissionError:
            # Fallback to user directory if can't write to /var/log
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(os.path.expanduser('~/smartpycam.log')),
                    logging.StreamHandler()
                ]
            )
        
        self.logger = logging.getLogger("smartpycam")
        self.logger.info(f"SmartPyCam v{__version__} - Multi-Camera RTSP Display System")
        
    def setup_x11_environment(self) -> bool:
        """Setup X11 environment"""
        try:
            # Check if X11 is already running
            if 'DISPLAY' not in os.environ:
                # Look for running X11
                result = subprocess.run(['pgrep', '-f', 'Xorg'], capture_output=True, text=True)
                if result.returncode == 0:
                    # X11 is running, try common displays
                    for display in [':0', ':1']:
                        os.environ['DISPLAY'] = display
                        try:
                            subprocess.run(['xset', 'r', 'off'], check=True, capture_output=True, timeout=5)
                            self.logger.info(f"Connected to X11 display {display}")
                            break
                        except:
                            continue
                    else:
                        self.logger.error("X11 is running but not accessible")
                        return False
                else:
                    self.logger.error("No X11 display found")
                    return False
            
            # Test X11 access
            try:
                subprocess.run(['xset', 'r', 'off'], check=True, capture_output=True, timeout=5)
                self.logger.info(f"X11 display {os.environ.get('DISPLAY')} is accessible")
            except Exception as e:
                self.logger.error(f"Cannot access X11 display: {e}")
                return False
            
            # Install required packages if missing
            try:
                subprocess.run(['which', 'mpv'], check=True, capture_output=True)
                subprocess.run(['which', 'feh'], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                self.logger.info("Installing required packages...")
                subprocess.run(['sudo', 'apt', 'update'], capture_output=True)
                subprocess.run(['sudo', 'apt', 'install', '-y', 'mpv', 'feh'], capture_output=True)
            
            return True
            
        except Exception as e:
            self.logger.error(f"X11 setup failed: {e}")
            return False
        
    def load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            display_data = config_data.get("display", {})
            self.display_config = DisplayConfig(**display_data)
            
            numeric_level = getattr(logging, self.display_config.log_level.upper(), logging.INFO)
            logging.getLogger().setLevel(numeric_level)
            
            cameras_data = config_data.get("cameras", [])
            enabled_cameras = [Camera(**cam_data) for cam_data in cameras_data if cam_data.get("enabled", True)]
            
            if not enabled_cameras:
                self.logger.error("No enabled cameras found in configuration")
                return False
                
            self.cameras = enabled_cameras
            self.logger.info(f"Loaded configuration with {len(self.cameras)} enabled cameras")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False

    def clear_screen(self) -> bool:
        """Clear screen to black"""
        try:
            self.logger.info("Clearing screen to black...")
            
            # Use xsetroot to set black background
            result = subprocess.run(['xsetroot', '-solid', 'black'], capture_output=True, timeout=10)
            if result.returncode == 0:
                self.logger.info("✓ Screen cleared with xsetroot")
                return True
            
            self.logger.warning("Could not clear screen")
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to clear screen: {e}")
            return False

    def show_placeholder_image(self, camera: Camera) -> bool:
        """Show placeholder image for camera"""
        try:
            placeholder_path = os.path.expanduser("~/smartpicam/camera_offline.png")
            
            if os.path.exists(placeholder_path):
                return self.show_placeholder_with_feh(camera, placeholder_path)
            else:
                self.logger.warning(f"Placeholder image not found: {placeholder_path}")
                return self.show_colored_placeholder(camera)
                
        except Exception as e:
            self.logger.warning(f"Failed to show placeholder for {camera.name}: {e}")
            return False
    
    def show_placeholder_with_feh(self, camera: Camera, image_path: str) -> bool:
        """Show placeholder image using feh"""
        try:
            # Kill any existing placeholder for this camera
            if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
                try:
                    camera.placeholder_process.terminate()
                    camera.placeholder_process.wait(timeout=3)
                except:
                    pass
            
            # Use feh to display image at specific position and size
            cmd = [
                'feh', '--borderless', '--geometry', f'{camera.width}x{camera.height}+{camera.x}+{camera.y}',
                '--scale-down', '--auto-zoom', image_path
            ]
            
            camera.placeholder_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            
            time.sleep(1)
            
            # Check if process is still running
            if camera.placeholder_process.poll() is None:
                self.logger.info(f"✓ Showed placeholder image for {camera.name}")
                return True
            else:
                self.logger.warning(f"✗ Placeholder image failed for {camera.name}")
                return self.show_colored_placeholder(camera)
                
        except Exception as e:
            self.logger.warning(f"Feh placeholder failed for {camera.name}: {e}")
            return self.show_colored_placeholder(camera)

    def show_colored_placeholder(self, camera: Camera) -> bool:
        """Show colored rectangle as placeholder using xterm"""
        try:
            # Kill any existing placeholder
            if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
                try:
                    camera.placeholder_process.terminate()
                    camera.placeholder_process.wait(timeout=3)
                except:
                    pass
            
            # Define colors for each camera position
            colors = ["red", "blue", "green", "yellow", "orange", "purple", "cyan", "pink"]
            color = colors[camera.window_id % len(colors)]
            
            # Calculate terminal size (approximate)
            term_width = max(10, camera.width // 8)
            term_height = max(5, camera.height // 16)
            
            # Use xterm to show colored window
            cmd = [
                'xterm', '-geometry', f'{term_width}x{term_height}+{camera.x}+{camera.y}',
                '-bg', color, '-fg', color, '-title', f'{camera.name}_placeholder',
                '-e', 'sleep 999999'
            ]
            
            camera.placeholder_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            
            time.sleep(1)
            
            if camera.placeholder_process.poll() is None:
                self.logger.info(f"✓ Showed {color} placeholder for {camera.name}")
                return True
            else:
                self.logger.warning(f"✗ Colored placeholder failed for {camera.name}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Failed to show colored placeholder for {camera.name}: {e}")
            return False

    def start_camera_player(self, camera: Camera) -> bool:
        """Start MPV player for camera"""
        if camera.player_process and camera.player_process.poll() is None:
            return True  # Already running
            
        self.logger.info(f"Starting MPV player for {camera.name}")
        
        # Kill placeholder first
        if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
            try:
                camera.placeholder_process.terminate()
                camera.placeholder_process.wait(timeout=3)
            except:
                pass
            camera.placeholder_process = None
        
        # MPV command for windowed playback
        cmd = [
            'mpv', '--no-audio', '--no-input-terminal', '--no-osc', '--no-osd-bar',
            '--geometry={}x{}+{}+{}'.format(camera.width, camera.height, camera.x, camera.y),
            '--title={}'.format(camera.name), '--keep-open=yes', '--loop-file=yes',
            '--cache=yes', '--rtsp-transport=tcp', '--network-timeout=30',
            '--hwdec=auto',  # Try hardware decoding
            camera.url
        ]
        
        try:
            camera.player_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
            )
            
            # Give it time to start
            time.sleep(5)
            
            if camera.player_process.poll() is None:
                camera.status = "connected"
                self.logger.info(f"✓ {camera.name} MPV player started")
                return True
            else:
                _, stderr = camera.player_process.communicate()
                self.logger.error(f"✗ {camera.name} MPV failed: {stderr.decode() if stderr else 'Unknown error'}")
                camera.status = "failed"
                camera.player_process = None
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start MPV for {camera.name}: {e}")
            camera.status = "failed"
            camera.player_process = None
            return False

    def stop_camera_player(self, camera: Camera):
        """Stop camera player"""
        if camera.player_process:
            try:
                camera.player_process.terminate()
                camera.player_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                camera.player_process.kill()
                camera.player_process.wait()
            finally:
                camera.player_process = None
                camera.status = "placeholder"
                self.logger.info(f"Stopped player for {camera.name}")
        
        # Stop placeholder too
        if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
            try:
                camera.placeholder_process.terminate()
                camera.placeholder_process.wait(timeout=3)
            except:
                pass
            camera.placeholder_process = None

    def test_camera_connection(self, camera: Camera) -> bool:
        """Test camera connection"""
        try:
            cmd = [
                'ffmpeg', '-rtsp_transport', 'tcp', '-i', camera.url,
                '-t', '3', '-f', 'null', '-'
            ]
            
            timeout = 30 if any(x in camera.url for x in ["118.93", "121.75"]) else 20
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            self.logger.warning(f"✗ {camera.name} connection test timed out")
            return False
        except Exception as e:
            self.logger.warning(f"✗ {camera.name} connection test error: {e}")
            return False

    def camera_monitor_thread(self, camera: Camera):
        """Monitor individual camera"""
        self.logger.info(f"Starting monitor thread for {camera.name}")
        
        # Show initial placeholder
        if not self.show_placeholder_image(camera):
            self.logger.warning(f"Could not show placeholder for {camera.name}")
        
        while self.running:
            current_time = time.time()
            
            # Check if we need to test/retry this camera
            if camera.status in ["placeholder", "failed"] and (current_time - camera.last_test) >= self.display_config.camera_retry_interval:
                camera.last_test = current_time
                camera.status = "testing"
                
                self.logger.info(f"Testing {camera.name}: {camera.url}")
                
                # Test connection
                if self.test_camera_connection(camera):
                    # Connection successful, start player
                    if self.start_camera_player(camera):
                        camera.retry_count = 0
                        self.logger.info(f"🎥 {camera.name} is now LIVE!")
                    else:
                        camera.status = "failed"
                        camera.retry_count += 1
                        self.show_placeholder_image(camera)
                else:
                    camera.status = "failed"
                    camera.retry_count += 1
                    self.logger.warning(f"✗ {camera.name} connection failed (attempt {camera.retry_count})")
                    self.show_placeholder_image(camera)
            
            # Monitor running camera
            elif camera.status == "connected":
                if camera.player_process and camera.player_process.poll() is not None:
                    # Camera process died, mark for retry
                    self.logger.warning(f"Camera {camera.name} player died, marking for retry")
                    camera.status = "failed"
                    camera.player_process = None
                    self.show_placeholder_image(camera)
                elif (current_time - camera.last_test) >= 120:  # Test every 2 minutes
                    camera.last_test = current_time
                    if not self.test_camera_connection(camera):
                        self.logger.warning(f"Camera {camera.name} connection lost, restarting")
                        self.stop_camera_player(camera)
                        camera.status = "failed"
                        self.show_placeholder_image(camera)
            
            time.sleep(10)  # Check every 10 seconds

    def start_all_camera_monitors(self):
        """Start monitoring threads for all cameras"""
        for camera in self.cameras:
            if camera.enabled:
                thread = threading.Thread(
                    target=self.camera_monitor_thread, 
                    args=(camera,), 
                    daemon=True,
                    name=f"monitor-{camera.name}"
                )
                thread.start()
                self.camera_threads[camera.window_id] = thread
                self.logger.info(f"Started monitor thread for {camera.name}")

    def status_monitor_thread(self):
        """Monitor and log status of all cameras"""
        while self.running:
            status_counts = {"placeholder": 0, "testing": 0, "connected": 0, "failed": 0}
            
            for camera in self.cameras:
                if camera.enabled:
                    status_counts[camera.status] += 1
            
            self.logger.info(f"Camera Status: Connected={status_counts['connected']}, "
                           f"Failed={status_counts['failed']}, "
                           f"Testing={status_counts['testing']}, "
                           f"Placeholder={status_counts['placeholder']}")
            
            time.sleep(60)

    def stop_all_cameras(self):
        """Stop all camera processes"""
        for camera in self.cameras:
            self.stop_camera_player(camera)
        
        # Kill any remaining processes
        try:
            subprocess.run(['pkill', '-f', 'mpv'], capture_output=True)
            subprocess.run(['pkill', '-f', 'feh'], capture_output=True)
            subprocess.run(['pkill', '-f', 'xterm.*placeholder'], capture_output=True)
        except:
            pass

    def run(self) -> bool:
        """Main run loop"""
        if not self.load_config():
            return False
        
        if not self.setup_x11_environment():
            return False
        
        # Clear screen
        if not self.clear_screen():
            self.logger.warning("Could not clear screen, continuing anyway...")
        
        self.running = True
        
        # Start camera monitoring threads
        self.start_all_camera_monitors()
        
        # Start status monitoring
        status_thread = threading.Thread(target=self.status_monitor_thread, daemon=True)
        status_thread.start()
        
        self.logger.info("SmartPyCam started - X11 windowed approach")
        self.logger.info("Each camera gets its own positioned window")
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
        finally:
            self.running = False
            self.stop_all_cameras()
            
        return True

def signal_handler(signum, frame):
    global app
    if 'app' in globals():
        app.running = False
    sys.exit(0)

def main():
    global app
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SmartPyCam()
    app.logger.info("Starting SmartPyCam - Multi-Camera RTSP Display System...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
