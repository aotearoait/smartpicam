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

class SmartPiCam:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.running = False
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("smartpicam")
        self.logger.info("SmartPiCam v2.0 - FFmpeg Grid Display for Pi OS Lite")
        
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
                
            self.cameras = enabled_cameras
            self.logger.info(f"Loaded configuration with {len(self.cameras)} enabled cameras")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False
    
    def _build_ffmpeg_grid_command(self) -> List[str]:
        """Build FFmpeg command for grid layout using complex filters"""
        if not self.cameras:
            return []
        
        # Base command with compatible options for Pi FFmpeg
        cmd = ["ffmpeg", "-y", "-loglevel", "warning"]
        
        # Add input streams with Pi-compatible options
        for i, camera in enumerate(self.cameras):
            cmd.extend([
                "-i", camera.url,
                "-reconnect", "1",
                "-reconnect_streamed", "1", 
                "-reconnect_delay_max", "2",
                "-rtsp_transport", "tcp",
                "-timeout", "5000000"  # Use timeout instead of stimeout
            ])
        
        # Build filter graph for custom grid layout
        filter_complex = []
        
        # Scale each input to the desired size and add labels
        for i, camera in enumerate(self.cameras):
            # Add format conversion and scaling
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height},format=yuv420p[v{i}]"
            filter_complex.append(scale_filter)
        
        # Create background
        background = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}:rate=25:duration=3600[bg]"
        filter_complex.append(background)
        
        # Overlay each camera at its position
        overlay_chain = "[bg]"
        for i, camera in enumerate(self.cameras):
            if i == len(self.cameras) - 1:
                # Last overlay doesn't need output label
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}[tmp{i}]"
                overlay_chain = f"[tmp{i}]"
            filter_complex.append(overlay)
        
        # Join all filters
        filter_string = ";".join(filter_complex)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-f", "fbdev", "/dev/fb0",
            "-r", "25"  # Frame rate
        ])
        
        return cmd
    
    def _test_camera_streams(self) -> bool:
        """Test individual camera streams before starting grid"""
        self.logger.info("Testing individual camera streams...")
        
        for camera in self.cameras:
            self.logger.info(f"Testing {camera.name}: {camera.url}")
            
            test_cmd = [
                "ffmpeg", "-y",
                "-i", camera.url,
                "-rtsp_transport", "tcp",
                "-timeout", "5000000",
                "-t", "1",  # Test for 1 second
                "-f", "null", "-"
            ]
            
            try:
                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=15,
                    text=True
                )
                
                if result.returncode == 0:
                    self.logger.info(f"✓ {camera.name} stream is accessible")
                else:
                    self.logger.warning(f"✗ {camera.name} stream test failed: {result.stderr}")
                    # Don't fail completely - maybe stream is slow to start
                    self.logger.info(f"Continuing despite test failure for {camera.name}")
                    
            except subprocess.TimeoutExpired:
                self.logger.warning(f"✗ {camera.name} stream test timed out - continuing anyway")
            except Exception as e:
                self.logger.warning(f"✗ {camera.name} stream test error: {e} - continuing anyway")
                
        return True  # Always continue - let FFmpeg handle connection issues
    
    def start_display(self) -> bool:
        """Start the FFmpeg grid display"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        # Test streams first
        if not self._test_camera_streams():
            self.logger.error("Camera stream tests failed - not starting display")
            return False
            
        cmd = self._build_ffmpeg_grid_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting FFmpeg grid display...")
        self.logger.info(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            # Set environment for framebuffer access
            env = os.environ.copy()
            env.pop('DISPLAY', None)  # Remove X11 display for framebuffer mode
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
                env=env
            )
            
            # Give FFmpeg time to initialize
            time.sleep(5)
            
            if self.ffmpeg_process.poll() is None:
                self.logger.info("FFmpeg grid display started successfully")
                self._log_camera_layout()
                return True
            else:
                stdout, stderr = self.ffmpeg_process.communicate()
                self.logger.error(f"FFmpeg failed to start:")
                self.logger.error(f"STDOUT: {stdout.decode() if stdout else 'None'}")
                self.logger.error(f"STDERR: {stderr.decode() if stderr else 'None'}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start FFmpeg: {e}")
            return False
    
    def _log_camera_layout(self):
        """Log the camera layout for debugging"""
        self.logger.info("Camera layout:")
        for camera in self.cameras:
            self.logger.info(f"  {camera.name}: ({camera.x},{camera.y}) {camera.width}x{camera.height}")
    
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
                self.logger.warning(f"Display is unhealthy, attempting restart ({restart_count}/{self.display_config.restart_retries})")
                
                # Get error output before stopping
                if self.ffmpeg_process:
                    try:
                        stdout, stderr = self.ffmpeg_process.communicate(timeout=1)
                        if stderr:
                            self.logger.error(f"FFmpeg error output: {stderr.decode()}")
                    except:
                        pass
                
                self.stop_display()
                time.sleep(5)
                
                if self.start_display():
                    restart_count = 0  # Reset counter on successful restart
                    
            time.sleep(10)  # Check every 10 seconds
            
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
            # Keep main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
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
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SmartPiCam()
    app.logger.info("Starting SmartPiCam with FFmpeg grid display...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
