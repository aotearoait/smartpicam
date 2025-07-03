#!/usr/bin/env python3
"""
SmartPiCam - Modern RTSP Camera Display System for Raspberry Pi 5
A replacement for displaycameras that uses VLC instead of deprecated omxplayer

Repository: https://github.com/aotearoait/smartpicam
Author: smartpicam contributors
License: MIT
"""

import os
import sys
import time
import json
import logging
import subprocess
import threading
import signal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
import configparser
from enum import Enum

class StreamState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"
    RESTARTING = "restarting"

@dataclass
class CameraConfig:
    """Configuration for a single camera stream"""
    name: str
    url: str
    window_id: int
    x: int = 0
    y: int = 0
    width: int = 640
    height: int = 480
    enabled: bool = True
    
    def __post_init__(self):
        # Validate camera name for compatibility
        if not self.name.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f"Camera name '{self.name}' contains invalid characters")

@dataclass
class DisplayConfig:
    """Global display configuration"""
    screen_width: int = 1920
    screen_height: int = 1080
    grid_cols: int = 2
    grid_rows: int = 2
    enable_rotation: bool = False
    rotation_interval: int = 30
    network_timeout: int = 30
    restart_retries: int = 3
    log_level: str = "INFO"
    
class StreamManager:
    """Manages individual VLC stream processes"""
    
    def __init__(self, camera: CameraConfig, display_config: DisplayConfig):
        self.camera = camera
        self.display_config = display_config
        self.process: Optional[subprocess.Popen] = None
        self.state = StreamState.STOPPED
        self.restart_count = 0
        self.last_restart = 0
        self.logger = logging.getLogger(f"stream.{camera.name}")
        
    def _build_vlc_command(self) -> List[str]:
        """Build VLC command with Pi 5 optimized settings"""
        cmd = [
            "cvlc",  # VLC without interface - no sudo needed when service runs as pi
            "--intf", "dummy",  # No interface
            "--no-audio",  # Disable audio for camera feeds
            "--network-caching", str(self.display_config.network_timeout * 1000),
            "--rtsp-tcp",  # Force TCP for RTSP (more reliable)
            "--live-caching", "1000",  # Low latency caching
            "--clock-jitter", "0",
            "--clock-synchro", "0",
            "--no-osd",  # No on-screen display
            "--no-video-title-show",
            "--no-snapshot-preview",
            "--verbose", "1",
            "--fullscreen",  # Use fullscreen for simplicity
            "--no-video-deco",  # No window decorations
            "--loop",  # Loop on connection loss
            self.camera.url
        ]
        return cmd
    
    def start(self) -> bool:
        """Start the VLC stream process"""
        if self.state == StreamState.RUNNING:
            self.logger.warning("Stream already running")
            return True
            
        self.state = StreamState.STARTING
        self.logger.info(f"Starting stream for {self.camera.name}")
        
        try:
            cmd = self._build_vlc_command()
            self.logger.debug(f"VLC command: {' '.join(cmd)}")
            
            # Start VLC process with proper error handling
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # Create new process group
                env=dict(os.environ, DISPLAY=":0", XDG_RUNTIME_DIR="/run/user/1000")
            )
            
            # Give VLC time to initialize
            time.sleep(3)
            
            # Check if process started successfully
            if self.process.poll() is None:
                self.state = StreamState.RUNNING
                self.restart_count = 0
                self.logger.info(f"Stream started successfully for {self.camera.name}")
                return True
            else:
                # Process died immediately
                stderr = self.process.stderr.read().decode() if self.process.stderr else "No error output"
                self.logger.error(f"VLC process died immediately: {stderr}")
                self.state = StreamState.FAILED
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start stream: {e}")
            self.state = StreamState.FAILED
            return False
    
    def stop(self):
        """Stop the VLC stream process"""
        if self.process and self.process.poll() is None:
            self.logger.info(f"Stopping stream for {self.camera.name}")
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.logger.warning("Force killing VLC process")
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                    
            except Exception as e:
                self.logger.error(f"Error stopping stream: {e}")
                
        self.process = None
        self.state = StreamState.STOPPED
        
    def is_healthy(self) -> bool:
        """Check if the stream is running and healthy"""
        if not self.process:
            return False
            
        # Check if process is still running
        if self.process.poll() is not None:
            # Process has died
            stderr = self.process.stderr.read().decode() if self.process.stderr else "No error output"
            self.logger.warning(f"Stream process died: {stderr}")
            self.state = StreamState.FAILED
            return False
            
        return self.state == StreamState.RUNNING
    
    def restart(self) -> bool:
        """Restart the stream with backoff"""
        current_time = time.time()
        
        # Implement restart backoff
        if current_time - self.last_restart < 10:  # Don't restart too frequently
            self.logger.warning("Restart attempted too soon, backing off")
            return False
            
        if self.restart_count >= self.display_config.restart_retries:
            self.logger.error(f"Max restart attempts ({self.display_config.restart_retries}) reached")
            return False
            
        self.logger.info(f"Restarting stream (attempt {self.restart_count + 1})")
        self.state = StreamState.RESTARTING
        self.restart_count += 1
        self.last_restart = current_time
        
        self.stop()
        time.sleep(2)  # Brief pause before restart
        return self.start()

class SmartPiCam:
    """Main application class managing all camera streams"""
    
    def __init__(self, config_path: str = "/etc/smartpicam"):
        self.config_path = Path(config_path)
        self.display_config = DisplayConfig()
        self.cameras: Dict[str, CameraConfig] = {}
        self.stream_managers: Dict[str, StreamManager] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # Setup logging
        self._setup_logging()
        self.logger = logging.getLogger("smartpicam")
        
        # Load configuration
        self._load_configuration()
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _setup_logging(self):
        """Configure logging system"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=getattr(logging, self.display_config.log_level),
            format=log_format,
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('/var/log/smartpicam.log') if os.access('/var/log', os.W_OK) 
                else logging.FileHandler('/tmp/smartpicam.log')
            ]
        )
        
    def _load_configuration(self):
        """Load configuration from files"""
        # Try to load existing displaycameras config for migration
        legacy_config = self.config_path / "displaycameras.conf"
        if legacy_config.exists():
            self._migrate_legacy_config(legacy_config)
        else:
            self._load_modern_config()
            
    def _migrate_legacy_config(self, config_file: Path):
        """Migrate from legacy displaycameras configuration"""
        self.logger.info("Migrating legacy displaycameras configuration")
        
        config = configparser.ConfigParser()
        config.read(config_file)
        
        # Load display settings
        if 'DEFAULT' in config:
            section = config['DEFAULT']
            self.display_config.network_timeout = int(section.get('feedsleep', 30))
            self.display_config.restart_retries = int(section.get('retry', 3))
            
        # Load layout configuration
        layout_file = self.config_path / "layout.conf.default"
        if layout_file.exists():
            self._parse_legacy_layout(layout_file)
            
    def _parse_legacy_layout(self, layout_file: Path):
        """Parse legacy layout configuration"""
        with open(layout_file, 'r') as f:
            content = f.read()
            
        # Extract camera definitions (simplified parser)
        # This would need to be more robust for production
        lines = content.split('\n')
        camera_count = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith('camera') and '=' in line:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    camera_name = parts[0].strip()
                    camera_url = parts[1].strip().strip('"')
                    
                    # Calculate grid position
                    col = camera_count % self.display_config.grid_cols
                    row = camera_count // self.display_config.grid_cols
                    
                    width = self.display_config.screen_width // self.display_config.grid_cols
                    height = self.display_config.screen_height // self.display_config.grid_rows
                    
                    x = col * width
                    y = row * height
                    
                    self.cameras[camera_name] = CameraConfig(
                        name=camera_name,
                        url=camera_url,
                        window_id=camera_count,
                        x=x, y=y, width=width, height=height
                    )
                    camera_count += 1
                    
    def _load_modern_config(self):
        """Load modern JSON configuration"""
        config_file = self.config_path / "smartpicam.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
                
            # Load display config
            if 'display' in data:
                for key, value in data['display'].items():
                    if hasattr(self.display_config, key):
                        setattr(self.display_config, key, value)
                        
            # Load cameras
            if 'cameras' in data:
                for cam_data in data['cameras']:
                    camera = CameraConfig(**cam_data)
                    self.cameras[camera.name] = camera
                    
    def _calculate_grid_layout(self):
        """Calculate optimal grid layout for cameras"""
        if not self.cameras:
            return
            
        enabled_cameras = [cam for cam in self.cameras.values() if cam.enabled]
        if not enabled_cameras:
            return
            
        # Auto-calculate grid if needed
        num_cameras = len(enabled_cameras)
        if self.display_config.grid_cols * self.display_config.grid_rows < num_cameras:
            # Recalculate grid to fit all cameras
            cols = int(num_cameras ** 0.5) + (1 if num_cameras ** 0.5 != int(num_cameras ** 0.5) else 0)
            rows = (num_cameras + cols - 1) // cols
            self.display_config.grid_cols = cols
            self.display_config.grid_rows = rows
            
        # Calculate window dimensions
        window_width = self.display_config.screen_width // self.display_config.grid_cols
        window_height = self.display_config.screen_height // self.display_config.grid_rows
        
        # Update camera positions
        for i, camera in enumerate(enabled_cameras):
            col = i % self.display_config.grid_cols
            row = i // self.display_config.grid_cols
            
            camera.x = col * window_width
            camera.y = row * window_height
            camera.width = window_width
            camera.height = window_height
            camera.window_id = i
            
    def start(self):
        """Start all camera streams"""
        self.logger.info("Starting SmartPiCam...")
        
        if not self.cameras:
            self.logger.error("No cameras configured!")
            return False
            
        # Calculate layout
        self._calculate_grid_layout()
        
        # Initialize stream managers
        for camera in self.cameras.values():
            if camera.enabled:
                manager = StreamManager(camera, self.display_config)
                self.stream_managers[camera.name] = manager
                
        # Start all streams
        success_count = 0
        for name, manager in self.stream_managers.items():
            if manager.start():
                success_count += 1
            else:
                self.logger.error(f"Failed to start stream: {name}")
                
        if success_count == 0:
            self.logger.error("No streams started successfully!")
            return False
            
        self.running = True
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_streams, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info(f"SmartPiCam started with {success_count}/{len(self.stream_managers)} streams")
        return True
        
    def _monitor_streams(self):
        """Monitor stream health and restart failed streams"""
        while self.running:
            try:
                for name, manager in self.stream_managers.items():
                    if not manager.is_healthy():
                        self.logger.warning(f"Stream {name} is unhealthy, attempting restart")
                        manager.restart()
                        
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in stream monitor: {e}")
                time.sleep(5)
                
    def stop(self):
        """Stop all streams and cleanup"""
        self.logger.info("Stopping SmartPiCam...")
        self.running = False
        
        # Stop all stream managers
        for manager in self.stream_managers.values():
            manager.stop()
            
        # Wait for monitor thread
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
            
        self.logger.info("SmartPiCam stopped")
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        sys.exit(0)
        
    def get_status(self) -> Dict:
        """Get current system status"""
        status = {
            "running": self.running,
            "total_cameras": len(self.cameras),
            "active_streams": len([m for m in self.stream_managers.values() if m.state == StreamState.RUNNING]),
            "failed_streams": len([m for m in self.stream_managers.values() if m.state == StreamState.FAILED]),
            "display_config": asdict(self.display_config),
            "streams": {}
        }
        
        for name, manager in self.stream_managers.items():
            status["streams"][name] = {
                "state": manager.state.value,
                "restart_count": manager.restart_count,
                "camera": asdict(manager.camera)
            }
            
        return status

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="SmartPiCam - Modern RTSP Camera Display System")
    parser.add_argument("--config", default="/etc/smartpicam", help="Configuration directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("command", choices=["start", "stop", "status", "restart"], help="Command to execute")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        
    app = SmartPiCam(args.config)
    
    if args.command == "start":
        if app.start():
            try:
                # Keep running until interrupted
                while app.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        app.stop()
        
    elif args.command == "status":
        status = app.get_status()
        print(json.dumps(status, indent=2))
        
    elif args.command == "stop":
        # This would typically connect to running instance
        print("Stop command not implemented in standalone mode")
        
    elif args.command == "restart":
        app.stop()
        time.sleep(2)
        app.start()

if __name__ == "__main__":
    main()
