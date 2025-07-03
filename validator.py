#!/usr/bin/env python3
"""
SmartPiCam Configuration Validator and Testing Tool

This utility helps validate camera configurations, test stream connectivity,
and diagnose common issues with SmartPiCam setups.

Repository: https://github.com/aotearoait/smartpicam
"""

import os
import sys
import json
import time
import subprocess
import threading
import logging
import urllib.request
import urllib.parse
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path
import argparse

@dataclass
class ValidationResult:
    """Result of a validation test"""
    test_name: str
    success: bool
    message: str
    details: Optional[str] = None

class StreamTester:
    """Test RTSP stream connectivity and playback"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.logger = logging.getLogger("StreamTester")
        
    def test_stream_connectivity(self, url: str) -> ValidationResult:
        """Test if we can connect to the RTSP stream"""
        try:
            # Parse URL to extract components
            parsed = urllib.parse.urlparse(url)
            
            if parsed.scheme not in ['rtsp', 'http', 'https']:
                return ValidationResult(
                    "Stream Connectivity",
                    False,
                    f"Unsupported protocol: {parsed.scheme}",
                    "Only RTSP, HTTP, and HTTPS streams are supported"
                )
            
            # Test basic connectivity for RTSP
            if parsed.scheme == 'rtsp':
                return self._test_rtsp_connectivity(url)
            else:
                return self._test_http_connectivity(url)
                
        except Exception as e:
            return ValidationResult(
                "Stream Connectivity",
                False,
                f"Connection test failed: {str(e)}"
            )
    
    def _test_rtsp_connectivity(self, url: str) -> ValidationResult:
        """Test RTSP stream connectivity using ffprobe"""
        try:
            cmd = [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height,r_frame_rate",
                "-of", "json",
                "-rtsp_transport", "tcp",
                "-timeout", str(self.timeout * 1000000),  # ffprobe wants microseconds
                url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode == 0:
                # Parse stream info
                try:
                    data = json.loads(result.stdout)
                    if 'streams' in data and data['streams']:
                        stream = data['streams'][0]
                        codec = stream.get('codec_name', 'unknown')
                        width = stream.get('width', 'unknown')
                        height = stream.get('height', 'unknown')
                        fps = stream.get('r_frame_rate', 'unknown')
                        
                        details = f"Codec: {codec}, Resolution: {width}x{height}, FPS: {fps}"
                        return ValidationResult(
                            "Stream Connectivity",
                            True,
                            "Stream accessible and valid",
                            details
                        )
                except json.JSONDecodeError:
                    pass
                
                return ValidationResult(
                    "Stream Connectivity",
                    True,
                    "Stream accessible"
                )
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                return ValidationResult(
                    "Stream Connectivity",
                    False,
                    "Stream not accessible",
                    f"ffprobe error: {error_msg}"
                )
                
        except subprocess.TimeoutExpired:
            return ValidationResult(
                "Stream Connectivity",
                False,
                f"Connection timeout after {self.timeout} seconds"
            )
        except FileNotFoundError:
            return ValidationResult(
                "Stream Connectivity",
                False,
                "ffprobe not found",
                "Install ffmpeg package: sudo apt install ffmpeg"
            )
    
    def _test_http_connectivity(self, url: str) -> ValidationResult:
        """Test HTTP/HTTPS stream connectivity"""
        try:
            request = urllib.request.Request(url)
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get('Content-Type', '')
                content_length = response.headers.get('Content-Length', 'unknown')
                
                if 'video' in content_type or 'application/octet-stream' in content_type:
                    return ValidationResult(
                        "Stream Connectivity",
                        True,
                        "HTTP stream accessible",
                        f"Content-Type: {content_type}, Length: {content_length}"
                    )
                else:
                    return ValidationResult(
                        "Stream Connectivity",
                        False,
                        "Not a video stream",
                        f"Content-Type: {content_type}"
                    )
                    
        except urllib.error.URLError as e:
            return ValidationResult(
                "Stream Connectivity",
                False,
                f"HTTP connection failed: {str(e)}"
            )
    
    def test_vlc_playback(self, url: str, duration: int = 10) -> ValidationResult:
        """Test VLC playback capability"""
        try:
            cmd = [
                "timeout", str(duration),
                "cvlc",
                "--intf", "dummy",
                "--no-audio",
                "--vout", "dummy",  # No actual video output for test
                "--run-time", str(duration),
                "--verbose", "2",
                url
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration + 5
            )
            
            # VLC returns 124 when killed by timeout (success case)
            if result.returncode in [0, 124]:
                return ValidationResult(
                    "VLC Playback",
                    True,
                    f"VLC can play stream for {duration} seconds"
                )
            else:
                error_output = result.stderr if result.stderr else result.stdout
                return ValidationResult(
                    "VLC Playback",
                    False,
                    "VLC playback failed",
                    f"Exit code: {result.returncode}, Output: {error_output[:200]}..."
                )
                
        except subprocess.TimeoutExpired:
            return ValidationResult(
                "VLC Playback",
                False,
                "VLC test timeout"
            )
        except Exception as e:
            return ValidationResult(
                "VLC Playback",
                False,
                f"VLC test error: {str(e)}"
            )

def main():
    """Main validation and testing entry point"""
    parser = argparse.ArgumentParser(
        description="SmartPiCam Configuration Validator and Testing Tool"
    )
    parser.add_argument(
        "--config",
        default="/etc/smartpicam",
        help="Configuration directory path"
    )
    parser.add_argument(
        "--test-streams",
        action="store_true",
        help="Test stream connectivity for all configured cameras"
    )
    parser.add_argument(
        "--test-vlc",
        action="store_true",
        help="Test VLC playback for all configured cameras"
    )
    parser.add_argument(
        "--test-url",
        help="Test a specific stream URL"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for stream tests (seconds)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    all_results = []
    stream_tester = StreamTester(args.timeout)
    
    if args.test_url:
        print(f"🎥 Testing stream: {args.test_url}")
        connectivity_result = stream_tester.test_stream_connectivity(args.test_url)
        all_results.append(connectivity_result)
        
        if args.test_vlc and connectivity_result.success:
            vlc_result = stream_tester.test_vlc_playback(args.test_url, 10)
            all_results.append(vlc_result)
    
    else:
        # Load config and test configured cameras
        config_file = Path(args.config) / "smartpicam.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                
                cameras = config.get('cameras', [])
                enabled_cameras = [cam for cam in cameras if cam.get('enabled', True)]
                
                if enabled_cameras:
                    print(f"🎥 Testing {len(enabled_cameras)} enabled camera streams...")
                    
                    for camera in enabled_cameras:
                        name = camera.get('name', 'unknown')
                        url = camera.get('url', '')
                        
                        if not url:
                            continue
                        
                        print(f"  Testing {name}: {url}")
                        
                        if args.test_streams:
                            result = stream_tester.test_stream_connectivity(url)
                            result.test_name = f"Stream Test ({name})"
                            all_results.append(result)
                        
                        if args.test_vlc:
                            result = stream_tester.test_vlc_playback(url, 10)
                            result.test_name = f"VLC Test ({name})"
                            all_results.append(result)
                else:
                    print("❌ No enabled cameras found in configuration")
                    
            except Exception as e:
                print(f"❌ Error loading configuration: {e}")
        else:
            print("❌ No configuration file found")
    
    # Output results
    if args.json:
        # JSON output
        json_results = []
        for result in all_results:
            json_results.append({
                'test_name': result.test_name,
                'success': result.success,
                'message': result.message,
                'details': result.details
            })
        print(json.dumps(json_results, indent=2))
    else:
        # Human-readable output
        print("\n" + "="*60)
        print("📊 VALIDATION RESULTS")
        print("="*60)
        
        success_count = sum(1 for r in all_results if r.success)
        total_count = len(all_results)
        
        for result in all_results:
            status = "✅" if result.success else "❌"
            print(f"{status} {result.test_name}: {result.message}")
            if result.details and args.verbose:
                print(f"   ℹ️  {result.details}")
        
        print("="*60)
        print(f"📈 Overall: {success_count}/{total_count} tests passed")
        
        if success_count == total_count:
            print("🎉 All tests passed! SmartPiCam should work correctly.")
        else:
            failed_count = total_count - success_count
            print(f"⚠️  {failed_count} test(s) failed. Please address the issues above.")
            sys.exit(1)

if __name__ == "__main__":
    main()
