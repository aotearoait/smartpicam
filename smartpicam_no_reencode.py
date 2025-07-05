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
    def __init__(self, config_path: str = "config/smartpicam_improved.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.working_cameras: List[Camera] = []
        self.failed_cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.ffmpeg_process: Optional[subprocess.Popen] = None
        self.camera_processes: Dict[str, subprocess.Popen] = {}  # Camera name -> process
        self.camera_modes: Dict[str, str] = {}  # Camera name -> 'copy' or 'encode'
        self.running = False
        self.cursor_hidden = False
        self.camera_status_changed = threading.Event()
        self.placeholder_available = False
        self.base_udp_port = 5000
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("smartpicam_no_reencode")
        self.logger.info("SmartPiCam No Re-encode v2.2 - Fixed Camera Display Issue")
        
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
                    self.placeholder_available = True
                    self.logger.info(f"✓ Placeholder image found: {self.display_config.placeholder_image}")
                else:
                    self.placeholder_available = False
                    self.logger.info(f"ℹ Placeholder image not found: {self.display_config.placeholder_image}")
                    self.logger.info("Will use solid color placeholders instead")
            
            if self.display_config.enable_camera_retry:
                self.logger.info(f"Auto-recovery enabled: checking failed cameras every {self.display_config.camera_retry_interval}s")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False

    def _create_placeholder_for_camera(self, camera: Camera, reason: str = "loading") -> str:
        """Create a placeholder input for a camera"""
        if self.display_config.show_placeholders and self.placeholder_available:
            # Use actual placeholder image with loop to make it continuous
            return f"-loop 1 -i {self.display_config.placeholder_image}"
        else:
            # Use solid color placeholder
            color = self.display_config.placeholder_bg_color
            return f"-f lavfi -i color=c={color}:s={camera.width}x{camera.height}:r=25"
    
    def _show_initial_placeholders(self) -> bool:
        """Show placeholders for all cameras immediately while testing streams"""
        self.logger.info("Showing initial placeholders for all camera positions...")
        
        # Simple command to show placeholders quickly
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        
        # Add placeholder inputs for all cameras
        for camera in self.cameras:
            placeholder_input = self._create_placeholder_for_camera(camera, "loading")
            cmd.extend(placeholder_input.split())
        
        # Build filter chain
        filter_parts = []
        
        # Scale each placeholder to its camera size
        for i, camera in enumerate(self.cameras):
            scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}[v{i}]"
            filter_parts.append(scale_filter)
        
        # Create black background
        filter_parts.append(f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}[bg]")
        
        # Overlay each placeholder at its position
        overlay_chain = "[bg]"
        for i, camera in enumerate(self.cameras):
            if i == len(self.cameras) - 1:
                # Last overlay
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y},format=rgb565le[out]"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}[bg{i}]"
                overlay_chain = f"[bg{i}]"
            filter_parts.append(overlay)
        
        filter_string = ";".join(filter_parts)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-map", "[out]",
            "-f", "fbdev", "/dev/fb0",
            "-pix_fmt", "rgb565le",
            "-t", "2"  # Show for 2 seconds
        ])
        
        try:
            env = os.environ.copy()
            env.pop('DISPLAY', None)
            
            result = subprocess.run(cmd, capture_output=True, timeout=5, env=env)
            if result.returncode == 0:
                self.logger.info("✓ Initial placeholders displayed")
                return True
            else:
                self.logger.warning(f"Could not show initial placeholders: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                return False
        except subprocess.TimeoutExpired:
            self.logger.warning("Initial placeholder display timed out")
            return False
        except Exception as e:
            self.logger.warning(f"Error showing initial placeholders: {e}")
            return False

    def is_h264(self, rtsp_url: str) -> bool:
        """Check if RTSP stream uses H.264 codec using ffprobe"""
        try:
            cmd = [
                "ffprobe", "-v", "error", 
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                "-timeout", "5000000",  # 5 second timeout
                rtsp_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            
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
                "-timeout", "10000000",  # 10 second timeout
                "-i", camera.url,
                "-c", "copy",  # No re-encoding!
                "-f", "mpegts",
                f"udp://127.0.0.1:{udp_port}"
            ]
            self.camera_modes[camera.name] = "copy"
            self.logger.info(f"🚀 {camera.name} using COPY mode (no re-encoding) on port {udp_port}")
        else:
            # Use software encoder for non-H.264 streams (more compatible)
            cmd = [
                "ffmpeg", "-y",
                "-rtsp_transport", "tcp",
                "-timeout", "10000000",  # 10 second timeout
                "-i", camera.url,
                "-c:v", "libx264",  # Software encoder (fallback)
                "-preset", "ultrafast",  # Fastest encoding
                "-b:v", "800k",
                "-r", "10",
                "-f", "mpegts",
                f"udp://127.0.0.1:{udp_port}"
            ]
            self.camera_modes[camera.name] = "encode"
            self.logger.info(f"🚀 {camera.name} using SOFTWARE ENCODE mode on port {udp_port}")
        
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

    def _test_single_camera(self, camera: Camera) -> bool:
        """Test a single camera stream"""
        test_cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-timeout", "8000000",  # 8 second timeout
            "-rtsp_transport", "tcp",
            "-i", camera.url,
            "-t", "1",
            "-f", "null", "-"
        ]
        
        try:
            result = subprocess.run(test_cmd, capture_output=True, timeout=12, text=True)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False
    
    def _test_camera_streams_parallel(self) -> bool:
        """Test camera streams in parallel and separate working from failed"""
        self.logger.info("Testing camera streams...")
        
        def test_camera(camera):
            success = self._test_single_camera(camera)
            if success:
                self.logger.info(f"✓ {camera.name} stream OK")
            else:
                self.logger.warning(f"✗ {camera.name} stream failed")
            return camera, success
        
        working_cameras = []
        failed_cameras = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(self.cameras), 5)) as executor:
            future_to_camera = {executor.submit(test_camera, camera): camera 
                               for camera in self.cameras}
            
            for future in concurrent.futures.as_completed(future_to_camera, timeout=50):
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
        
        self.working_cameras = working_cameras
        self.failed_cameras = failed_cameras
        
        self.logger.info(f"Stream test complete: {len(working_cameras)}/{len(self.cameras)} cameras working")
        
        if failed_cameras:
            failed_names = [cam.name for cam in failed_cameras]
            self.logger.info(f"Will show placeholders for: {', '.join(failed_names)}")
        
        return len(self.cameras) > 0

    def start_working_camera_streams(self):
        """Start UDP streams for working cameras"""
        if not self.working_cameras:
            self.logger.warning("No working cameras to start UDP streams for")
            return
            
        self.logger.info("Starting UDP streams for working cameras...")
        
        for i, camera in enumerate(self.cameras):
            if camera in self.working_cameras:
                udp_port = self.base_udp_port + i
                process = self.start_camera_stream(camera, udp_port)
                if process:
                    self.camera_processes[camera.name] = process
                    self.logger.info(f"✓ {camera.name} UDP stream active on port {udp_port}")
                else:
                    self.logger.warning(f"⚠️ Failed to start UDP stream for {camera.name}")
                    # Move to failed list
                    if camera in self.working_cameras:
                        self.working_cameras.remove(camera)
                    if camera not in self.failed_cameras:
                        self.failed_cameras.append(camera)

    def _build_ffmpeg_grid_command(self) -> List[str]:
        """Build FFmpeg command for grid layout with placeholders for failed cameras"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y", "-loglevel", "info"]
        
        # Add timeout and thread settings to prevent hangs
        cmd.extend(["-thread_queue_size", "1024"])
        
        # Build input list with both working cameras (UDP) and placeholders
        input_sources = []
        
        for i, camera in enumerate(self.cameras):
            # Check if this camera has an active UDP process
            has_active_udp = camera.name in self.camera_processes and self.camera_processes[camera.name].poll() is None
            
            if camera in self.working_cameras and has_active_udp:
                # Working camera - use UDP input
                udp_port = self.base_udp_port + i
                cmd.extend([
                    "-timeout", "30000000",  # 30 second timeout for UDP
                    "-i", f"udp://127.0.0.1:{udp_port}?timeout=5000000"
                ])
                input_sources.append(("camera", camera, udp_port))
                self.logger.info(f"Input {len(input_sources)-1}: UDP camera {camera.name} on port {udp_port}")
            else:
                # Failed camera - use placeholder
                reason = "timeout" if camera in self.failed_cameras else "offline"
                placeholder_input = self._create_placeholder_for_camera(camera, reason)
                cmd.extend(placeholder_input.split())
                input_sources.append(("placeholder", camera, None))
                self.logger.info(f"Input {len(input_sources)-1}: Placeholder for {camera.name} ({reason})")
        
        # Build filter complex
        filter_parts = []
        
        # Scale each input to its target size
        for i, (source_type, camera, port) in enumerate(input_sources):
            if source_type == "camera":
                # For UDP camera inputs, add buffering
                scale_filter = f"[{i}:v]fps=25,scale={camera.width}:{camera.height}[v{i}]"
            else:
                # For placeholder inputs
                scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}[v{i}]"
            filter_parts.append(scale_filter)
        
        # Create black background
        filter_parts.append(f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}[bg]")
        
        # Overlay each camera at its position
        overlay_chain = "[bg]"
        for i, (source_type, camera, port) in enumerate(input_sources):
            if i == len(input_sources) - 1:
                # Last overlay
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y},format=rgb565le[out]"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}[bg{i}]"
                overlay_chain = f"[bg{i}]"
            filter_parts.append(overlay)
        
        # Join all filters
        filter_string = ";".join(filter_parts)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-map", "[out]",
            "-f", "fbdev", "/dev/fb0",
            "-pix_fmt", "rgb565le"
        ])
        
        return cmd

    def start_display(self) -> bool:
        """Start the FFmpeg grid display with placeholders"""
        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            self.logger.warning("Display already running")
            return True
        
        self._hide_cursor()
        
        # Show initial placeholders immediately
        self._show_initial_placeholders()
        
        # Test streams and identify working/failed cameras
        if not self._test_camera_streams_parallel():
            self.logger.error("No cameras configured")
            return False
        
        # Start UDP streams for working cameras
        self.start_working_camera_streams()
        
        # Wait for UDP streams to establish
        if self.camera_processes:
            self.logger.info("Waiting for UDP streams to establish...")
            time.sleep(5)  # Give more time for UDP streams
            
            # Verify UDP streams are still running
            active_streams = []
            for camera_name, process in list(self.camera_processes.items()):
                if process.poll() is None:
                    active_streams.append(camera_name)
                else:
                    self.logger.warning(f"UDP stream for {camera_name} died, moving to failed")
                    # Find camera and move to failed
                    camera = next((c for c in self.cameras if c.name == camera_name), None)
                    if camera and camera in self.working_cameras:
                        self.working_cameras.remove(camera)
                        self.failed_cameras.append(camera)
                    del self.camera_processes[camera_name]
            
            self.logger.info(f"Active UDP streams: {active_streams}")
        else:
            self.logger.warning("No UDP streams started - all cameras failed")
            
        cmd = self._build_ffmpeg_grid_command()
        if not cmd:
            self.logger.error("Failed to build FFmpeg command")
            return False
        
        self.logger.info("Starting FFmpeg grid display with working cameras...")
        self.logger.info(f"FFmpeg command: {' '.join(cmd[:20])}...")  # Log first part of command
        
        try:
            env = os.environ.copy()
            env.pop('DISPLAY', None)
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN),
                env=env
            )
            
            # Wait and check if it started
            time.sleep(3)
            
            if self.ffmpeg_process.poll() is None:
                self.logger.info("FFmpeg grid display started successfully")
                self._log_camera_layout()
                return True
            else:
                stdout, stderr = self.ffmpeg_process.communicate()
                self.logger.error(f"FFmpeg failed to start:")
                if stderr:
                    self.logger.error(f"STDERR: {stderr.decode()}")
                if stdout:
                    self.logger.error(f"STDOUT: {stdout.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start FFmpeg: {e}")
            return False
    
    def _log_camera_layout(self):
        """Log the camera layout"""
        self.logger.info("📺 Camera layout:")
        for camera in self.cameras:
            if camera in self.working_cameras and camera.name in self.camera_processes:
                mode = self.camera_modes.get(camera.name, "unknown")
                status = f"WORKING ({mode.upper()})"
            else:
                status = "PLACEHOLDER"
            self.logger.info(f"  {camera.name}: ({camera.x},{camera.y}) {camera.width}x{camera.height} [{status}]")
    
    def _retry_failed_cameras(self):
        """Periodically test failed cameras and bring them back online"""
        while self.running and self.display_config.enable_camera_retry:
            time.sleep(self.display_config.camera_retry_interval)
            
            if not self.running or not self.failed_cameras:
                continue
            
            self.logger.info(f"Retrying failed cameras: {[cam.name for cam in self.failed_cameras]}")
            
            recovered_cameras = []
            still_failed = []
            
            for camera in self.failed_cameras:
                if self._test_single_camera(camera):
                    self.logger.info(f"🔄 {camera.name} recovered - bringing back online")
                    recovered_cameras.append(camera)
                else:
                    still_failed.append(camera)
            
            if recovered_cameras:
                # Start UDP streams for recovered cameras
                for camera in recovered_cameras:
                    camera_index = self.cameras.index(camera)
                    udp_port = self.base_udp_port + camera_index
                    process = self.start_camera_stream(camera, udp_port)
                    if process:
                        self.camera_processes[camera.name] = process
                        self.working_cameras.append(camera)
                    else:
                        still_failed.append(camera)
                        continue
                
                self.failed_cameras = still_failed
                self.camera_status_changed.set()
                
                recovered_names = [cam.name for cam in recovered_cameras if cam.name in self.camera_processes]
                if recovered_names:
                    self.logger.info(f"✅ Cameras recovered: {', '.join(recovered_names)}")

    def stop_display(self):
        """Stop all FFmpeg processes"""
        # Stop display process
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.ffmpeg_process.kill()
                self.ffmpeg_process.wait()
            finally:
                self.ffmpeg_process = None
        
        # Stop all camera UDP processes
        for camera_name, process in self.camera_processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            except Exception as e:
                self.logger.warning(f"Error stopping {camera_name}: {e}")
        
        self.camera_processes.clear()
        self.camera_modes.clear()
        
        self._show_cursor()
        self.logger.info("✅ All processes stopped")
                
    def is_healthy(self) -> bool:
        """Check if display is running properly"""
        return self.ffmpeg_process is not None and self.ffmpeg_process.poll() is None
        
    def monitor_display(self):
        """Monitor and restart display if it fails or cameras recover"""
        restart_count = 0
        
        while self.running:
            display_failed = not self.is_healthy()
            camera_status_changed = self.camera_status_changed.is_set()
            
            if display_failed or camera_status_changed:
                if camera_status_changed:
                    self.logger.info("Camera status changed - restarting display to include recovered cameras")
                    self.camera_status_changed.clear()
                    restart_count = 0
                elif display_failed:
                    if restart_count >= self.display_config.restart_retries:
                        self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
                        break
                    
                    restart_count += 1
                    self.logger.warning(f"Display unhealthy, restarting ({restart_count}/{self.display_config.restart_retries})")
                    
                    # Log any error output
                    if self.ffmpeg_process:
                        try:
                            stdout, stderr = self.ffmpeg_process.communicate(timeout=1)
                            if stderr:
                                self.logger.error(f"FFmpeg error: {stderr.decode()}")
                        except:
                            pass
                
                self.stop_display()
                time.sleep(3)
                
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
        
        # Start camera retry thread if enabled
        if self.display_config.enable_camera_retry:
            retry_thread = threading.Thread(target=self._retry_failed_cameras, daemon=True)
            retry_thread.start()
            self.logger.info("Camera auto-recovery thread started")
        
        try:
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
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = SmartPiCamNoReencode()
    app.logger.info("Starting SmartPiCam No Re-encode for ultra-low latency...")
    
    success = app.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
