#!/usr/bin/env python3

import json
import logging
import subprocess
import time
import signal
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
import threading

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

class CameraStream:
    def __init__(self, camera: Camera, display_config: DisplayConfig):
        self.camera = camera
        self.display_config = display_config
        self.process: Optional[subprocess.Popen] = None
        self.restart_count = 0
        self.logger = logging.getLogger(f"stream.{camera.name}")
        
    def _detect_display_mode(self) -> str:
        """Detect if we're running on Pi OS Lite (framebuffer) or Desktop (X11)"""
        # Check if X11 is available
        try:
            result = subprocess.run(['xdpyinfo'], capture_output=True, timeout=2, 
                                  env={'DISPLAY': ':0'})
            if result.returncode == 0:
                return "x11"
        except:
            pass
            
        # Check if we're on a tty (console)
        if os.path.exists('/dev/fb0'):
            return "framebuffer"
            
        return "framebuffer"  # Default for Pi OS Lite
        
    def _build_vlc_command(self) -> List[str]:
        """Build VLC command based on display environment"""
        display_mode = self._detect_display_mode()
        self.logger.info(f"Using display mode: {display_mode}")
        
        base_cmd = [
            "cvlc",  # VLC without interface
            "--intf", "dummy",  # No interface
            "--no-audio",  # Disable audio completely
            "--network-caching", str(self.display_config.network_timeout * 1000),
            "--rtsp-tcp",  # Force TCP for RTSP (more reliable)
            "--live-caching", "300",  # Lower latency caching
            "--clock-jitter", "0",
            "--clock-synchro", "0",
            "--no-osd",  # No on-screen display
            "--no-video-title-show",
            "--no-snapshot-preview",
            "--verbose", "0",  # Reduced verbosity
            # Hardware acceleration fallback
            "--avcodec-hw", "none",  # Disable hardware decoding if problematic
            "--loop",  # Loop on connection loss
        ]
        
        if display_mode == "x11":
            # X11 mode (Pi OS Desktop)
            base_cmd.extend([
                "--vout", "xcb_x11",
                "--x11-display", ":0",
                "--video-x", str(self.camera.x),
                "--video-y", str(self.camera.y),
                "--width", str(self.camera.width),
                "--height", str(self.camera.height),
                "--no-video-deco",
                "--no-embedded-video",
                "--video-on-top",
                "--no-video-title",
                "--qt-start-minimized",
                "--no-qt-privacy-ask",
            ])
        else:
            # Framebuffer mode (Pi OS Lite)
            base_cmd.extend([
                "--vout", "fb",  # Use framebuffer
                "--fbdev", "/dev/fb0",  # Framebuffer device
                "--no-video-deco",
                "--fullscreen",  # Important for framebuffer
            ])
        
        base_cmd.append(self.camera.url)
        return base_cmd

    def start(self) -> bool:
        """Start the camera stream"""
        if self.process and self.process.poll() is None:
            self.logger.warning("Stream already running")
            return True
            
        self.logger.info(f"Starting stream for {self.camera.name} at position ({self.camera.x},{self.camera.y}) size {self.camera.width}x{self.camera.height}")
        
        try:
            cmd = self._build_vlc_command()
            
            # Set up environment
            env = os.environ.copy()
            if self._detect_display_mode() == "framebuffer":
                # For framebuffer mode, don't set DISPLAY
                env.pop('DISPLAY', None)
            else:
                # For X11 mode
                env['DISPLAY'] = ':0'
                env['XAUTHORITY'] = '/home/pi/.Xauthority'
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
                env=env
            )
            
            # Give VLC time to initialize
            time.sleep(3)
            
            if self.process.poll() is None:
                self.logger.info(f"Stream started successfully for {self.camera.name}")
                self.restart_count = 0
                return True
            else:
                stderr_output = self.process.stderr.read().decode() if self.process.stderr else "No error output"
                self.logger.error(f"VLC process died immediately: {stderr_output}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start stream: {e}")
            return False

    def stop(self):
        """Stop the camera stream"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            finally:
                self.process = None
                
    def is_healthy(self) -> bool:
        """Check if stream is running properly"""
        return self.process is not None and self.process.poll() is None
        
    def restart(self) -> bool:
        """Restart the stream if it has failed"""
        if self.restart_count >= self.display_config.restart_retries:
            self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
            return False
            
        self.restart_count += 1
        self.logger.info(f"Restarting stream (attempt {self.restart_count})")
        
        self.stop()
        time.sleep(2)  # Brief pause before restart
        return self.start()

class SmartPiCam:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.streams: List[CameraStream] = []
        self.running = False
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("smartpicam")
        
        # Detect environment
        if os.path.exists('/usr/bin/startx'):
            self.logger.info("Detected Pi OS Desktop environment")
        else:
            self.logger.info("Detected Pi OS Lite environment - using framebuffer")
        
    def load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            # Parse display config
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
                
            # Create streams
            self.streams = [CameraStream(camera, self.display_config) for camera in enabled_cameras]
            
            self.logger.info(f"Loaded configuration with {len(self.streams)} enabled cameras")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False
            
    def start_all_streams(self) -> bool:
        """Start all camera streams"""
        success_count = 0
        for stream in self.streams:
            if stream.start():
                success_count += 1
            else:
                self.logger.warning(f"Failed to start stream for {stream.camera.name}")
                
        total_streams = len(self.streams)
        self.logger.info(f"SmartPiCam started with {success_count}/{total_streams} streams")
        return success_count > 0
        
    def monitor_streams(self):
        """Monitor and restart failed streams"""
        while self.running:
            for stream in self.streams:
                if not stream.is_healthy():
                    self.logger.warning(f"Stream {stream.camera.name} is unhealthy, attempting restart")
                    if not stream.restart():
                        self.logger.error(f"Failed to restart stream {stream.camera.name}")
                        
            time.sleep(10)  # Check every 10 seconds
            
    def stop_all_streams(self):
        """Stop all camera streams"""
        self.running = False
        for stream in self.streams:
            stream.stop()
            
    def run(self):
        """Main run loop"""
        if not self.load_config():
            return False
            
        if not self.start_all_streams():
            self.logger.error("Failed to start any streams")
            return False
            
        self.running = True
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_streams, daemon=True)
        monitor_thread.start()
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
        finally:
            self.stop_all_streams()
            
        return True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global app
    if 'app' in globals():
        app.stop_all_streams()
    sys.exit(0)

def main():
    global app
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SmartPiCam()
    app.logger.info("Starting SmartPiCam...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
