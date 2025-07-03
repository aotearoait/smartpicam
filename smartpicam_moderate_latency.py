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

class ModerateLowLatencySmartPiCam:
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
        self.logger.info("SmartPiCam Moderate Low Latency v2.4 - Balanced speed and reliability")
        
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
            self.logger.info("Moderate latency mode: Balanced speed and reliability")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False
    
    def _build_moderate_latency_ffmpeg_command(self) -> List[str]:
        """Build moderate latency FFmpeg command - same as original but with key optimizations"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y"]
        
        # Add input streams with moderate optimizations
        for camera in self.cameras:
            # Just a few key optimizations - not as aggressive as ultra-low latency
            cmd.extend([
                "-fflags", "+genpts+discardcorrupt",  # Handle corrupt streams better
                "-rtsp_transport", "tcp",             # Keep TCP for reliability
                "-max_delay", "1000000",              # 1 second max delay (vs 0 in ultra-low)
                "-threads", "2",                      # 2 threads instead of 1 
                "-i", camera.url
            ])
        
        # Build filter graph - exactly like original but without fps limiting
        filter_complex = []
        
        # Scale each input to the desired size (NO fps filter)
        for i, camera in enumerate(self.cameras):
            # Simple scaling without fps filter
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}[v{i}]"
            filter_complex.append(scale_filter)
        
        # Create black background
        background = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}[bg]"
        filter_complex.append(background)
        
        # Overlay each camera at its position - exactly like original
        overlay_chain = "[bg]"
        for i, camera in enumerate(self.cameras):
            if i == len(self.cameras) - 1:
                # Last overlay - add format conversion for framebuffer
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y},format=rgb565le"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}[tmp{i}]"
                overlay_chain = f"[tmp{i}]"
            filter_complex.append(overlay)
        
        # Join all filters
        filter_string = ";".join(filter_complex)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-f", "fbdev", "/dev/fb0",
            "-pix_fmt", "rgb565le"
        ])
        
        return cmd
    
    def _test_camera_streams(self) -> bool:
        """Quick test individual camera streams"""
        self.logger.info("Testing individual camera streams...")
        
        for camera in self.cameras:
            self.logger.info(f"Testing {camera.name}: {camera.url}")
            
            test_cmd = [
                "ffmpeg", "-y",
                "-rtsp_transport", "tcp",
                "-i", camera.url,
                "-t", "1",  # Test for 1 second
                "-f", "null", "-"
            ]
            
            try:
                result = subprocess.run(
                    test_cmd,
                    capture_output=True,
                    timeout=10,
                    text=True
                )
                
                if result.returncode == 0:
                    self.logger.info(f"✓ {camera.name} stream is accessible")
                else:
                    self.logger.warning(f"✗ {camera.name} stream test failed - continuing anyway")
                    
            except subprocess.TimeoutExpired:
                self.logger.warning(f"✗ {camera.name} stream test timed out - continuing anyway")
            except Exception as e:
                self.logger.warning(f"✗ {camera.name} stream test error: {e} - continuing anyway")
                
        return True  # Always continue
    
    def start_display(self) -> bool:
        """Start the moderate latency FFmpeg display"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        # Hide cursor before starting display
        self._hide_cursor()
        
        # Test streams first
        if not self._test_camera_streams():
            self.logger.error("Camera stream tests failed - not starting display")
            return False
            
        cmd = self._build_moderate_latency_ffmpeg_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting moderate latency FFmpeg display...")
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
                self.logger.info("Moderate latency display started successfully")
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
        
        # Restore cursor when stopping
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
    
    app = ModerateLowLatencySmartPiCam()
    app.logger.info("Starting Moderate Low Latency SmartPiCam...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
