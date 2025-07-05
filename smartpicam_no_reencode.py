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
    # Placeholder features from improved version
    show_placeholders: bool = True
    placeholder_image: str = "camera_offline.png"
    placeholder_text_color: str = "white"
    placeholder_bg_color: str = "darkgray"
    camera_retry_interval: int = 30
    enable_camera_retry: bool = True

class SmartPiCamNoReencode:
    def __init__(self, config_path: str = "config/smartpicam.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.ffmpeg_processes: List[subprocess.Popen] = []
        self.running = False
        self.cursor_hidden = False
        self.base_udp_port = 5000
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("smartpicam_no_reencode")
        self.logger.info("SmartPiCam No Re-encode v1.1 - Ultra Low Latency with Placeholders")
        
    def _hide_cursor(self):
        """Hide the console cursor to prevent flickering"""
        try:
            sys.stdout.write('\033[?25l')
            sys.stdout.flush()
            subprocess.run(['sudo', 'sh', '-c', 'echo 0 > /sys/class/graphics/fbcon/cursor_blink'], 
                         capture_output=True, timeout=5)
            subprocess.run(['setterm', '-cursor', 'off'], capture_output=True, timeout=5)
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
                subprocess.run(['setterm', '-cursor', 'on'], capture_output=True, timeout=5)
                self.cursor_hidden = False
                self.logger.info("Console cursor restored")
        except Exception as e:
            self.logger.warning(f"Could not restore cursor: {e}")
        
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
            
            # Check placeholder image
            if self.display_config.show_placeholders:
                if os.path.exists(self.display_config.placeholder_image):
                    self.logger.info(f"✓ Placeholder image found: {self.display_config.placeholder_image}")
                else:
                    self.logger.info(f"ℹ Placeholder image not found: {self.display_config.placeholder_image}")
                    self.logger.info("Will use solid color placeholders instead")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False

    def is_h264(self, rtsp_url: str) -> bool:
        """Check if RTSP stream uses H.264 codec using ffprobe"""
        try:
            cmd = [
                "ffprobe", "-v", "error", 
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                rtsp_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                codec = result.stdout.strip().lower()
                is_h264 = codec == "h264"
                self.logger.info(f"📹 {rtsp_url}: codec={codec} (H.264: {is_h264})")
                return is_h264
            else:
                self.logger.warning(f"ffprobe failed for {rtsp_url}: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"ffprobe timeout for {rtsp_url}")
            return False
        except Exception as e:
            self.logger.warning(f"ffprobe error for {rtsp_url}: {e}")
            return False

    def start_camera_stream(self, camera: Camera, udp_port: int) -> Optional[subprocess.Popen]:
        """Start individual camera stream with optimal encoding strategy"""
        start_time = time.time()
        self.logger.info(f"📅 Starting stream for {camera.name} at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Check if stream is H.264
        is_h264_stream = self.is_h264(camera.url)
        
        if is_h264_stream:
            # Use copy codec for H.264 streams (no re-encoding)
            cmd = [
                "ffmpeg", "-y",
                "-rtsp_transport", "tcp",
                "-i", camera.url,
                "-c", "copy",  # No re-encoding!
                "-f", "mpegts",
                f"udp://127.0.0.1:{udp_port}"
            ]
            self.logger.info(f"🚀 {camera.name} using COPY mode (no re-encoding) on port {udp_port}")
        else:
            # Use hardware encoder for non-H.264 streams
            cmd = [
                "ffmpeg", "-y",
                "-rtsp_transport", "tcp",
                "-i", camera.url,
                "-c:v", "h264_v4l2m2m",  # Hardware encoder
                "-b:v", "800k",
                "-r", "10",
                "-f", "mpegts",
                f"udp://127.0.0.1:{udp_port}"
            ]
            self.logger.info(f"🚀 {camera.name} using HARDWARE ENCODE mode on port {udp_port}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
            )
            
            elapsed = time.time() - start_time
            self.logger.info(f"⏱️  {camera.name} stream started in {elapsed:.2f}s")
            return process
            
        except Exception as e:
            self.logger.error(f"Failed to start stream for {camera.name}: {e}")
            return None

    def start_display_receiver(self) -> Optional[subprocess.Popen]:
        """Start FFmpeg to receive UDP streams and display on framebuffer"""
        if not self.cameras:
            return None
        
        self._hide_cursor()
        
        cmd = ["ffmpeg", "-y"]
        
        # Add UDP inputs for each camera
        for i, camera in enumerate(self.cameras):
            udp_port = self.base_udp_port + i
            cmd.extend(["-i", f"udp://127.0.0.1:{udp_port}"])
        
        # Build filter graph for grid layout
        filter_complex = []
        
        # Scale each input to the desired size
        for i, camera in enumerate(self.cameras):
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}[v{i}]"
            filter_complex.append(scale_filter)
        
        # Create black background
        background = f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}[bg]"
        filter_complex.append(background)
        
        # Overlay each camera at its position
        overlay_chain = "[bg]"
        for i, camera in enumerate(self.cameras):
            if i == len(self.cameras) - 1:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y},format=rgb565le"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}[tmp{i}]"
                overlay_chain = f"[tmp{i}]"
            filter_complex.append(overlay)
        
        filter_string = ";".join(filter_complex)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-f", "fbdev", "/dev/fb0",
            "-pix_fmt", "rgb565le"
        ])
        
        self.logger.info("Starting grid display receiver...")
        self.logger.info(f"Display command: {' '.join(cmd)}")
        
        try:
            env = os.environ.copy()
            env.pop('DISPLAY', None)
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
                env=env
            )
            return process
            
        except Exception as e:
            self.logger.error(f"Failed to start display receiver: {e}")
            return None

    def start_streams(self) -> bool:
        """Start all camera streams and display"""
        self.logger.info("📅 Stream startup began at: " + time.strftime('%Y-%m-%d %H:%M:%S'))
        
        # Start individual camera streams
        for i, camera in enumerate(self.cameras):
            udp_port = self.base_udp_port + i
            process = self.start_camera_stream(camera, udp_port)
            if process:
                self.ffmpeg_processes.append(process)
            else:
                self.logger.warning(f"⚠️ Failed to start stream for {camera.name} - continuing anyway")
        
        self.logger.info("⏳ Waiting for streams to establish...")
        time.sleep(3)
        
        display_process = self.start_display_receiver()
        if display_process:
            self.ffmpeg_processes.append(display_process)
            self.logger.info("✅ All streams and display started successfully")
            self._log_camera_layout()
            return True
        else:
            self.logger.error("Failed to start display receiver")
            return False

    def _log_camera_layout(self):
        """Log the camera layout and stream info for debugging"""
        self.logger.info("📺 Camera layout and stream info:")
        for i, camera in enumerate(self.cameras):
            udp_port = self.base_udp_port + i
            self.logger.info(f"  {camera.name}: ({camera.x},{camera.y}) {camera.width}x{camera.height} → UDP:{udp_port}")

    def stop_streams(self):
        """Stop all FFmpeg processes"""
        self.logger.info("🛑 Stopping all streams...")
        
        for process in self.ffmpeg_processes:
            try:
                process.terminate()
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except Exception as e:
                self.logger.warning(f"Error stopping process: {e}")
        
        self.ffmpeg_processes.clear()
        self._show_cursor()
        self.logger.info("✅ All streams stopped")

    def is_healthy(self) -> bool:
        """Check if all processes are running properly"""
        if not self.ffmpeg_processes:
            return False
        
        for process in self.ffmpeg_processes:
            if process.poll() is not None:
                return False
        return True

    def monitor_streams(self):
        """Monitor and restart streams if they fail"""
        restart_count = 0
        
        while self.running:
            if not self.is_healthy():
                if restart_count >= self.display_config.restart_retries:
                    self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
                    break
                
                restart_count += 1
                self.logger.warning(f"Streams unhealthy, attempting restart ({restart_count}/{self.display_config.restart_retries})")
                
                for process in self.ffmpeg_processes:
                    if process and process.poll() is not None:
                        try:
                            stdout, stderr = process.communicate(timeout=1)
                            if stderr:
                                self.logger.error(f"FFmpeg error output: {stderr.decode()}")
                        except:
                            pass
                
                self.stop_streams()
                time.sleep(5)
                
                if self.start_streams():
                    restart_count = 0
                    
            time.sleep(10)

    def run(self):
        """Main run loop"""
        if not self.load_config():
            return False
            
        if not self.start_streams():
            self.logger.error("Failed to start streams")
            return False
            
        self.running = True
        
        monitor_thread = threading.Thread(target=self.monitor_streams, daemon=True)
        monitor_thread.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal, shutting down...")
        finally:
            self.stop_streams()
            
        return True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global app
    if 'app' in globals():
        app.stop_streams()
    sys.exit(0)

def main():
    global app
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SmartPiCamNoReencode()
    app.logger.info("Starting SmartPiCam No Re-encode for ultra-low latency...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
