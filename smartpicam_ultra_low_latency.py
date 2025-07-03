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
    # Ultra low latency specific options
    ultra_low_latency: bool = True
    use_udp_transport: bool = True  # UDP is faster than TCP for live streams
    disable_placeholders: bool = True  # No placeholders for speed
    skip_stream_testing: bool = False  # Still test, but don't let failures block startup

class UltraLowLatencySmartPiCam:
    def __init__(self, config_path: str = "config/smartpicam_ultra_low_latency.json"):
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
        self.logger.info("SmartPiCam Ultra Low Latency v2.3 - Optimized for minimal delay")
        
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
            
            # Parse cameras - only enabled ones
            cameras_data = config_data.get("cameras", [])
            enabled_cameras = [Camera(**cam_data) for cam_data in cameras_data if cam_data.get("enabled", True)]
            
            if not enabled_cameras:
                self.logger.error("No enabled cameras found in configuration")
                return False
                
            self.cameras = enabled_cameras
            self.logger.info(f"Loaded configuration with {len(self.cameras)} enabled cameras")
            self.logger.info("Ultra low latency mode: Prioritizing speed over reliability")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False
    
    def _get_ultra_low_latency_params(self, camera: Camera) -> List[str]:
        """Get ultra-low latency parameters for each camera stream"""
        params = []
        
        # Critical low-latency flags - these are the key to reducing lag
        params.extend([
            "-fflags", "nobuffer",  # CRITICAL: No input buffering
            "-flags", "low_delay",  # Low delay mode
            "-avioflags", "direct", # Direct I/O, bypass OS caching
            "-probesize", "32",     # Minimal stream probing (32 bytes)
            "-analyzeduration", "0", # Skip stream analysis entirely
        ])
        
        # Transport protocol - UDP is faster than TCP for live streams
        if self.display_config.use_udp_transport:
            params.extend(["-rtsp_transport", "udp"])
        else:
            params.extend(["-rtsp_transport", "tcp"])
        
        # Buffer and delay settings
        params.extend([
            "-max_delay", "0",        # No delay tolerance
            "-reorder_queue_size", "0", # No reordering queue
            "-thread_queue_size", "1",  # Minimal thread queue
            "-threads", "1",          # Single thread per stream
        ])
        
        return params
    
    def _build_ultra_low_latency_ffmpeg_command(self) -> List[str]:
        """Build ultra-low latency FFmpeg command - no placeholders, minimal processing"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y"]
        
        # Global ultra-low latency settings
        cmd.extend([
            "-loglevel", "error",    # Minimal logging for performance
            "-nostdin",              # Don't read from stdin
            "-nostats",              # Don't show stats
        ])
        
        # Add input streams with ultra-low latency params
        for camera in self.cameras:
            low_latency_params = self._get_ultra_low_latency_params(camera)
            cmd.extend(low_latency_params)
            cmd.extend(["-i", camera.url])
        
        # Build minimal filter chain - NO fps limiting, NO complex processing
        filter_parts = []
        
        # Create background
        bg_filter = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}[bg]"
        filter_parts.append(bg_filter)
        
        # Process each camera with minimal filtering
        overlay_input = "[bg]"
        for i, camera in enumerate(self.cameras):
            # Simple scale only - NO fps filter (fps filter adds buffering!)
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}:flags=fast_bilinear[v{i}]"
            filter_parts.append(scale_filter)
            
            # Chain overlays
            if i == len(self.cameras) - 1:
                # Last overlay with framebuffer format
                overlay_filter = f"{overlay_input}[v{i}]overlay={camera.x}:{camera.y},format=rgb565le[out]"
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
    
    def _quick_test_cameras(self) -> List[Camera]:
        """Quick test cameras but don't block startup"""
        if self.display_config.skip_stream_testing:
            self.logger.info("Skipping stream testing for ultra-low latency startup")
            return self.cameras
        
        self.logger.info("Quick camera test (non-blocking)...")
        working_cameras = []
        
        for camera in self.cameras:
            # Very quick test - 2 second timeout
            test_cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-timeout", "2000000",  # 2 second timeout
                "-i", camera.url,
                "-t", "0.1",  # Just 0.1 second test
                "-f", "null", "-"
            ]
            
            try:
                result = subprocess.run(test_cmd, capture_output=True, timeout=3, text=True)
                if result.returncode == 0:
                    self.logger.info(f"✓ {camera.name}")
                    working_cameras.append(camera)
                else:
                    self.logger.warning(f"✗ {camera.name} - continuing anyway")
                    working_cameras.append(camera)  # Include anyway for ultra-low latency
            except:
                self.logger.warning(f"✗ {camera.name} timeout - continuing anyway")
                working_cameras.append(camera)  # Include anyway
        
        return working_cameras
    
    def start_display(self) -> bool:
        """Start the ultra-low latency FFmpeg display"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        # Hide cursor
        self._hide_cursor()
        
        # Quick camera test (but don't block on failures)
        self.cameras = self._quick_test_cameras()
        
        if not self.cameras:
            self.logger.error("No cameras to display")
            return False
            
        cmd = self._build_ultra_low_latency_ffmpeg_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting ultra-low latency FFmpeg display...")
        self.logger.info(f"Transport: {'UDP' if self.display_config.use_udp_transport else 'TCP'}")
        self.logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        
        try:
            # Ultra-minimal environment
            env = os.environ.copy()
            env.pop('DISPLAY', None)
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
                env=env
            )
            
            # Minimal startup wait
            time.sleep(2)
            
            if self.ffmpeg_process.poll() is None:
                self.logger.info("Ultra-low latency display started successfully")
                self._log_camera_layout()
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
    
    def _log_camera_layout(self):
        """Log the camera layout"""
        self.logger.info("Camera layout:")
        for camera in self.cameras:
            self.logger.info(f"  {camera.name}: ({camera.x},{camera.y}) {camera.width}x{camera.height}")
    
    def stop_display(self):
        """Stop the FFmpeg display"""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=5)
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
        """Simple monitor without complex recovery"""
        restart_count = 0
        
        while self.running:
            if not self.is_healthy():
                if restart_count >= self.display_config.restart_retries:
                    self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
                    break
                
                restart_count += 1
                self.logger.warning(f"Display failed, restarting ({restart_count}/{self.display_config.restart_retries})")
                
                self.stop_display()
                time.sleep(2)
                
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
        
        # Start simple monitoring thread
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
    
    app = UltraLowLatencySmartPiCam()
    app.logger.info("Starting Ultra Low Latency SmartPiCam...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
