#!/usr/bin/env python3
"""
SmartCamDisplay - Production Multi-Camera RTSP Display System
A reliable Python implementation for Ubuntu/Intel NUC systems
Uses X11 windowed approach with individual MPV processes for each camera

Production Features:
- Individual positioned camera windows with exact scaling
- Automatic placeholder display with transparency removal
- Robust camera monitoring and reconnection
- Clean desktop with no overlays or cursor issues
- Production logging and error handling
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

__version__ = "1.0.1"
__author__ = "SmartCamDisplay Project"

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

class SmartCamDisplay:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.running = False
        self.camera_threads: Dict[int, threading.Thread] = {}
        self.setup_logging()
        
    def setup_logging(self):
        """Configure production logging"""
        try:
            # Create log directory if it doesn't exist
            os.makedirs('/var/log', exist_ok=True)
            
            # Configure both file and console logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler('/var/log/smartcamdisplay.log'),
                    logging.StreamHandler()
                ]
            )
        except PermissionError:
            # Fallback to user directory if can't write to /var/log
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(os.path.expanduser('~/smartcamdisplay.log')),
                    logging.StreamHandler()
                ]
            )
        
        self.logger = logging.getLogger("smartcamdisplay")
        self.logger.info(f"SmartCamDisplay v{__version__} - Production Multi-Camera Display System")
        
    def setup_x11_environment(self) -> bool:
        """Setup X11 environment and verify access"""
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
            self.install_dependencies()
            
            return True
            
        except Exception as e:
            self.logger.error(f"X11 setup failed: {e}")
            return False
    
    def install_dependencies(self):
        """Install required system packages"""
        required_packages = ['mpv', 'feh', 'imagemagick']
        missing_packages = []
        
        for package in ['mpv', 'feh', 'convert']:
            try:
                subprocess.run(['which', package], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                if package == 'convert':
                    missing_packages.append('imagemagick')
                else:
                    missing_packages.append(package)
        
        if missing_packages:
            self.logger.info(f"Installing required packages: {', '.join(missing_packages)}")
            try:
                subprocess.run(['sudo', 'apt', 'update'], capture_output=True, timeout=60)
                subprocess.run(['sudo', 'apt', 'install', '-y'] + missing_packages, 
                              capture_output=True, timeout=300)
                self.logger.info("✓ Dependencies installed successfully")
            except Exception as e:
                self.logger.warning(f"Could not install dependencies: {e}")
        
    def load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            if not os.path.exists(self.config_path):
                self.logger.error(f"Configuration file not found: {self.config_path}")
                return False
                
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            display_data = config_data.get("display", {})
            self.display_config = DisplayConfig(**display_data)
            
            # Set logging level from config
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

    def cleanup_desktop(self) -> bool:
        """Clean up desktop and prepare for camera display"""
        try:
            self.logger.info("Cleaning up desktop environment...")
            
            # Kill unclutter (causes X overlay)
            subprocess.run(['pkill', '-f', 'unclutter'], capture_output=True)
            
            # Kill other potential overlay processes
            overlay_processes = ['conky', 'cairo-dock', 'plank', 'tint2', 'panel']
            for process in overlay_processes:
                subprocess.run(['pkill', '-f', process], capture_output=True)
            
            # Clear screen to black
            result = subprocess.run(['xsetroot', '-solid', 'black'], 
                                  capture_output=True, timeout=10)
            if result.returncode == 0:
                self.logger.info("✓ Desktop cleaned and screen cleared")
                return True
            else:
                self.logger.warning("Screen clear may have failed")
                return False
            
        except Exception as e:
            self.logger.error(f"Failed to clean desktop: {e}")
            return False

    def show_placeholder_image(self, camera: Camera) -> bool:
        """Show placeholder image for camera with transparency removal"""
        try:
            placeholder_path = os.path.expanduser("~/smartpicam/camera_offline.png")
            
            if os.path.exists(placeholder_path):
                return self.show_placeholder_with_feh(camera, placeholder_path)
            else:
                self.logger.warning(f"Placeholder image not found: {placeholder_path}")
                return self.show_colored_placeholder(camera)
                
        except Exception as e:
            self.logger.warning(f"Failed to show placeholder for {camera.name}: {e}")
            return self.show_colored_placeholder(camera)
    
    def show_placeholder_with_feh(self, camera: Camera, image_path: str) -> bool:
        """Show placeholder image using feh with transparency removal"""
        try:
            # Kill any existing placeholder for this camera
            if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
                try:
                    camera.placeholder_process.terminate()
                    camera.placeholder_process.wait(timeout=3)
                except:
                    pass
            
            # Create a temporary image with solid black background to remove transparency
            temp_image = f"/tmp/placeholder_{camera.name}_{camera.window_id}.png"
            
            # Use ImageMagick to flatten the image against a black background
            cmd_convert = [
                'convert', image_path, 
                '-background', 'black', 
                '-flatten',
                '-resize', f'{camera.width}x{camera.height}!',  # Force exact size
                temp_image
            ]
            
            result = subprocess.run(cmd_convert, capture_output=True, timeout=10)
            if result.returncode != 0:
                self.logger.warning(f"ImageMagick convert failed for {camera.name}, using fallback")
                return self.show_colored_placeholder(camera)
            
            # Use feh to display the processed image
            cmd = [
                'feh', '--borderless', 
                '--geometry', f'{camera.width}x{camera.height}+{camera.x}+{camera.y}',
                temp_image
            ]
            
            camera.placeholder_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            
            time.sleep(1)
            
            # Schedule cleanup of temp file
            def cleanup_temp_file():
                time.sleep(5)
                try:
                    os.remove(temp_image)
                except:
                    pass
            
            threading.Thread(target=cleanup_temp_file, daemon=True).start()
            
            # Check if process is still running
            if camera.placeholder_process.poll() is None:
                self.logger.info(f"✓ Showed placeholder image for {camera.name}")
                return True
            else:
                self.logger.warning(f"✗ Placeholder image failed for {camera.name}")
                return self.show_colored_placeholder(camera)
                
        except Exception as e:
            self.logger.warning(f"Placeholder image failed for {camera.name}: {e}")
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
        """Start MPV player for camera with exact scaling and no overlays"""
        if camera.player_process and camera.player_process.poll() is None:
            return True  # Already running
            
        self.logger.info(f"Starting camera player for {camera.name}")
        
        # Kill placeholder first
        if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
            try:
                camera.placeholder_process.terminate()
                camera.placeholder_process.wait(timeout=3)
            except:
                pass
            camera.placeholder_process = None
        
        # MPV command with comprehensive no-overlay configuration
        cmd = [
            'mpv', 
            '--no-audio',                                        # No audio
            '--no-input-terminal',                               # No terminal input
            '--no-input-default-bindings',                       # Disable ALL input bindings
            '--no-input-vo-keyboard',                            # Disable video output keyboard input
            '--no-osc',                                          # No on-screen controls
            '--no-osd-bar',                                      # No OSD bar
            '--osd-level=0',                                     # Completely disable OSD
            '--cursor-autohide=always',                          # Always hide cursor
            '--cursor-autohide-fs-only=no',                      # Hide cursor in windowed mode too
            '--no-border',                                       # No window border
            '--ontop',                                           # Keep on top
            '--geometry={}x{}+{}+{}'.format(camera.width, camera.height, camera.x, camera.y),
            '--autofit-larger={}x{}'.format(camera.width, camera.height),
            '--autofit-smaller={}x{}'.format(camera.width, camera.height),
            '--title={}'.format(camera.name),                   # Window title
            '--keep-open=yes',                                   # Keep window open on stream end
            '--loop-file=yes',                                   # Loop on stream end
            '--cache=yes',                                       # Enable caching
            '--rtsp-transport=tcp',                              # Force TCP for RTSP
            '--network-timeout=30',                              # Network timeout
            '--hwdec=auto',                                      # Try hardware decoding
            '--video-aspect-override=-1',                        # Ignore source aspect ratio
            '--video-unscaled=no',                               # Allow scaling
            '--keepaspect=no',                                   # Don't keep aspect ratio - STRETCH TO FIT
            '--panscan=0.0',                                     # No panscan
            '--video-zoom=0',                                    # No zoom
            '--video-align-x=0',                                 # Center horizontally
            '--video-align-y=0',                                 # Center vertically
            '--no-window-dragging',                              # Disable window dragging
            '--no-fs',                                           # Not fullscreen
            '--input-conf=/dev/null',                            # No input configuration
            '--no-input-cursor',                                 # Disable cursor input
            camera.url
        ]
        
        try:
            camera.player_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
            )
            
            # Give it time to start and stabilize
            time.sleep(5)
            
            if camera.player_process.poll() is None:
                camera.status = "connected"
                self.logger.info(f"✓ {camera.name} camera player started successfully")
                return True
            else:
                _, stderr = camera.player_process.communicate()
                self.logger.error(f"✗ {camera.name} player failed: {stderr.decode() if stderr else 'Unknown error'}")
                camera.status = "failed"
                camera.player_process = None
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start camera player for {camera.name}: {e}")
            camera.status = "failed"
            camera.player_process = None
            return False

    def stop_camera_player(self, camera: Camera):
        """Stop camera player and cleanup"""
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
                self.logger.info(f"Stopped camera player for {camera.name}")
        
        # Stop placeholder too
        if hasattr(camera, 'placeholder_process') and camera.placeholder_process:
            try:
                camera.placeholder_process.terminate()
                camera.placeholder_process.wait(timeout=3)
            except:
                pass
            camera.placeholder_process = None

    def test_camera_connection(self, camera: Camera) -> bool:
        """Test camera connection using FFmpeg"""
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
        """Monitor individual camera with automatic recovery"""
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
                
                self.logger.info(f"Testing connection to {camera.name}")
                
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
                elif (current_time - camera.last_test) >= 120:  # Health check every 2 minutes
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
            
            time.sleep(60)  # Status update every minute

    def stop_all_cameras(self):
        """Stop all camera processes and cleanup"""
        self.logger.info("Stopping all camera processes...")
        
        for camera in self.cameras:
            self.stop_camera_player(camera)
        
        # Kill any remaining processes
        try:
            subprocess.run(['pkill', '-f', 'mpv'], capture_output=True)
            subprocess.run(['pkill', '-f', 'feh'], capture_output=True)
            subprocess.run(['pkill', '-f', 'xterm.*placeholder'], capture_output=True)
        except:
            pass
        
        self.logger.info("All camera processes stopped")

    def run(self) -> bool:
        """Main application loop"""
        self.logger.info("Starting SmartCamDisplay...")
        
        # Load configuration
        if not self.load_config():
            self.logger.error("Failed to load configuration, exiting")
            return False
        
        # Setup X11 environment
        if not self.setup_x11_environment():
            self.logger.error("Failed to setup X11 environment, exiting")
            return False
        
        # Clean up desktop and prepare display
        if not self.cleanup_desktop():
            self.logger.warning("Desktop cleanup failed, continuing anyway...")
        
        self.running = True
        
        # Start camera monitoring threads
        self.start_all_camera_monitors()
        
        # Start status monitoring
        status_thread = threading.Thread(target=self.status_monitor_thread, daemon=True)
        status_thread.start()
        
        self.logger.info("SmartCamDisplay is running - all cameras monitoring started")
        self.logger.info(f"Displaying {len(self.cameras)} cameras on {self.display_config.screen_width}x{self.display_config.screen_height} screen")
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
        finally:
            self.running = False
            self.stop_all_cameras()
            
        self.logger.info("SmartCamDisplay shutdown complete")
        return True

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global app
    if 'app' in globals():
        app.running = False
    sys.exit(0)

def main():
    """Main entry point"""
    global app
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create and run application
    app = SmartCamDisplay()
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
