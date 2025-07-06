#!/usr/bin/env python3
"""
VLC Grid Display Test for SmartPiCam
Alternative to FFmpeg for multi-camera display on Pi 5
"""

import json
import logging
import subprocess
import time
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

class VLCGridDisplay:
    def __init__(self, config_path: str = "config/smartpicam_improved.json"):
        self.config_path = config_path
        self.cameras: List[Camera] = []
        self.display_config: DisplayConfig = None
        self.vlc_processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.setup_logging()
        
    def setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("vlc_grid_test")
        self.logger.info("VLC Grid Display Test v1.0")
        
    def load_config(self) -> bool:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            display_data = config_data.get("display", {})
            self.display_config = DisplayConfig(**display_data)
            
            cameras_data = config_data.get("cameras", [])
            enabled_cameras = [Camera(**cam_data) for cam_data in cameras_data if cam_data.get("enabled", True)]
            
            if not enabled_cameras:
                self.logger.error("No enabled cameras found in configuration")
                return False
                
            self.cameras = enabled_cameras
            self.logger.info(f"Loaded {len(self.cameras)} cameras for VLC grid test")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return False

    def check_vlc_capabilities(self) -> Dict[str, bool]:
        """Check VLC capabilities on Pi 5"""
        capabilities = {
            'vlc_available': False,
            'hw_accel_available': False,
            'v4l2_support': False
        }
        
        try:
            # Check if VLC is installed
            result = subprocess.run(['vlc', '--version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                capabilities['vlc_available'] = True
                self.logger.info("✓ VLC is available")
                
                # Check for hardware acceleration modules
                result = subprocess.run(['vlc', '--list'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    output = result.stdout.lower()
                    if 'v4l2' in output:
                        capabilities['v4l2_support'] = True
                        self.logger.info("✓ V4L2 support detected")
                    if 'mmal' in output or 'drm' in output:
                        capabilities['hw_accel_available'] = True
                        self.logger.info("✓ Hardware acceleration available")
            else:
                self.logger.error("VLC not available")
                
        except Exception as e:
            self.logger.error(f"Error checking VLC capabilities: {e}")
            
        return capabilities

    def test_single_stream_vlc(self, camera: Camera) -> bool:
        """Test single camera stream with VLC"""
        self.logger.info(f"Testing {camera.name} with VLC...")
        
        # VLC command optimized for Pi 5 and RTSP streams
        cmd = [
            'vlc',
            '--intf', 'dummy',  # No interface
            '--extraintf', 'logger',  # Enable logging
            '--verbose', '1',  # Minimal verbosity
            '--no-audio',  # Disable audio
            '--rtsp-tcp',  # Force TCP for RTSP
            '--network-caching', '1000',  # 1 second cache
            '--rtsp-caching', '1000',
            '--file-caching', '1000',
            '--live-caching', '1000',
            '--sout-transcode-hurry-up',  # Speed up transcoding
            '--sout-transcode-threads', '2',  # Use 2 threads for Pi 5
            '--play-and-exit',  # Exit after playing
            '--run-time', '5',  # Test for 5 seconds
            camera.url
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            success = result.returncode == 0
            
            if success:
                self.logger.info(f"✓ {camera.name} VLC test passed")
            else:
                self.logger.warning(f"✗ {camera.name} VLC test failed")
                if result.stderr:
                    self.logger.debug(f"VLC error: {result.stderr[:200]}")
                    
            return success
            
        except subprocess.TimeoutExpired:
            self.logger.warning(f"⏱️ {camera.name} VLC test timeout")
            return False
        except Exception as e:
            self.logger.error(f"VLC test error for {camera.name}: {e}")
            return False

    def create_vlc_grid_config(self) -> str:
        """Create VLC mosaic configuration"""
        config_lines = []
        
        # Basic setup
        config_lines.extend([
            "# VLC Grid Configuration for SmartPiCam",
            "interface=dummy",
            "extraintf=logger",
            "verbose=1",
            "no-audio",
            "rtsp-tcp",
            "network-caching=1000",
            "rtsp-caching=1000"
        ])
        
        # Mosaic setup
        config_lines.extend([
            "# Mosaic configuration",
            f"mosaic-width={self.display_config.screen_width}",
            f"mosaic-height={self.display_config.screen_height}",
            f"mosaic-rows={self.display_config.grid_rows}",
            f"mosaic-cols={self.display_config.grid_cols}",
            "mosaic-position=1",
            "mosaic-order=1,2,3,4"
        ])
        
        config_content = "\n".join(config_lines)
        
        # Write to temporary config file
        config_file = "/tmp/vlc_grid.conf"
        with open(config_file, 'w') as f:
            f.write(config_content)
            
        return config_file

    def start_vlc_grid(self) -> bool:
        """Start VLC grid display"""
        self.logger.info("Starting VLC grid display...")
        
        # Create VLC config
        config_file = self.create_vlc_grid_config()
        
        # Build VLC command for mosaic
        cmd = [
            'vlc',
            '--config', config_file,
            '--intf', 'dummy',
            '--fullscreen',
            '--no-osd',
            '--no-audio',
            '--rtsp-tcp'
        ]
        
        # Add mosaic configuration
        mosaic_options = []
        for i, camera in enumerate(self.cameras):
            input_id = i + 1
            mosaic_options.extend([
                f'--mosaic-id={input_id}',
                f'--mosaic-position={input_id}',
                f'--mosaic-width={camera.width}',
                f'--mosaic-height={camera.height}'
            ])
        
        cmd.extend(mosaic_options)
        
        # Add input streams
        for camera in self.cameras:
            cmd.append(camera.url)
        
        try:
            self.logger.info(f"VLC command: {' '.join(cmd[:10])}...")
            
            vlc_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy()
            )
            
            # Wait and check if it started
            time.sleep(3)
            
            if vlc_process.poll() is None:
                self.logger.info("✓ VLC grid display started")
                self.vlc_processes['grid'] = vlc_process
                return True
            else:
                stdout, stderr = vlc_process.communicate()
                self.logger.error("VLC grid failed to start")
                if stderr:
                    self.logger.error(f"VLC error: {stderr.decode()[:300]}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start VLC grid: {e}")
            return False

    def start_individual_vlc_windows(self) -> bool:
        """Start individual VLC windows for each camera (alternative approach)"""
        self.logger.info("Starting individual VLC windows...")
        
        for i, camera in enumerate(self.cameras):
            cmd = [
                'vlc',
                '--intf', 'dummy',
                '--no-audio',
                '--rtsp-tcp',
                '--network-caching', '500',  # Lower caching for live streams
                '--rtsp-caching', '500',
                '--video-x', str(camera.x),
                '--video-y', str(camera.y),
                '--width', str(camera.width),
                '--height', str(camera.height),
                '--no-video-deco',  # No window decoration
                '--no-embedded-video',
                camera.url
            ]
            
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.vlc_processes[camera.name] = process
                self.logger.info(f"✓ Started VLC window for {camera.name}")
                time.sleep(1)  # Small delay between starting windows
                
            except Exception as e:
                self.logger.error(f"Failed to start VLC for {camera.name}: {e}")
                
        return len(self.vlc_processes) > 0

    def stop_vlc_processes(self):
        """Stop all VLC processes"""
        for name, process in self.vlc_processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
                self.logger.info(f"✓ Stopped VLC process: {name}")
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                self.logger.info(f"⚡ Killed VLC process: {name}")
            except Exception as e:
                self.logger.warning(f"Error stopping {name}: {e}")
        
        self.vlc_processes.clear()

    def run_test(self):
        """Run VLC grid test"""
        if not self.load_config():
            return False
        
        # Check VLC capabilities
        capabilities = self.check_vlc_capabilities()
        if not capabilities['vlc_available']:
            self.logger.error("VLC is not available - install with: sudo apt install vlc")
            return False
        
        # Test individual camera streams
        self.logger.info("Testing individual camera streams...")
        working_cameras = []
        for camera in self.cameras:
            if self.test_single_stream_vlc(camera):
                working_cameras.append(camera)
        
        if not working_cameras:
            self.logger.error("No cameras are working with VLC")
            return False
        
        self.logger.info(f"Working cameras: {[cam.name for cam in working_cameras]}")
        
        # Try grid approach first
        self.logger.info("Attempting VLC mosaic grid...")
        if self.start_vlc_grid():
            self.logger.info("✓ VLC grid is running. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("Stopping VLC grid...")
                self.stop_vlc_processes()
        else:
            # Fallback to individual windows
            self.logger.info("Grid failed, trying individual windows...")
            if self.start_individual_vlc_windows():
                self.logger.info("✓ Individual VLC windows running. Press Ctrl+C to stop.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    self.logger.info("Stopping VLC windows...")
                    self.stop_vlc_processes()
            else:
                self.logger.error("Both VLC approaches failed")
                return False
        
        return True

def main():
    """Main function"""
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config/smartpicam_improved.json"
    
    display = VLCGridDisplay(config_path)
    
    try:
        success = display.run_test()
        sys.exit(0 if success else 1)
    except Exception as e:
        display.logger.error(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
