#!/usr/bin/env python3
"""
FFmpeg Pi 5 Compatibility Test
Diagnose and fix hardware acceleration issues on Raspberry Pi 5
"""

import subprocess
import logging
import sys
import time
import os
from typing import Dict, List, Tuple

class FFmpegPi5Tester:
    def __init__(self):
        self.setup_logging()
        
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("ffmpeg_pi5_test")
        
    def check_pi_version(self) -> str:
        """Check Raspberry Pi version"""
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
            self.logger.info(f"Hardware: {model}")
            return model
        except Exception as e:
            self.logger.warning(f"Could not detect Pi model: {e}")
            return "Unknown"
    
    def check_memory_split(self) -> Dict[str, int]:
        """Check GPU memory split"""
        memory_info = {}
        try:
            # Check GPU memory
            result = subprocess.run(['vcgencmd', 'get_mem', 'gpu'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                gpu_mem = int(result.stdout.strip().split('=')[1][:-1])
                memory_info['gpu'] = gpu_mem
                
            # Check ARM memory  
            result = subprocess.run(['vcgencmd', 'get_mem', 'arm'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                arm_mem = int(result.stdout.strip().split('=')[1][:-1])
                memory_info['arm'] = arm_mem
                
            self.logger.info(f"Memory split - GPU: {memory_info.get('gpu', 'unknown')}MB, "
                           f"ARM: {memory_info.get('arm', 'unknown')}MB")
                           
        except Exception as e:
            self.logger.warning(f"Could not check memory split: {e}")
            
        return memory_info
    
    def check_v4l2_devices(self) -> List[str]:
        """Check available V4L2 devices"""
        devices = []
        try:
            for device_num in range(10):  # Check /dev/video0 to /dev/video9
                device_path = f"/dev/video{device_num}"
                if os.path.exists(device_path):
                    devices.append(device_path)
                    
            self.logger.info(f"V4L2 devices found: {devices}")
            
            # Check device capabilities
            for device in devices:
                try:
                    result = subprocess.run(['v4l2-ctl', '--device', device, '--list-formats'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        self.logger.info(f"{device} formats: {result.stdout.strip()}")
                except:
                    pass
                    
        except Exception as e:
            self.logger.warning(f"Error checking V4L2 devices: {e}")
            
        return devices
    
    def test_ffmpeg_capabilities(self) -> Dict[str, bool]:
        """Test FFmpeg hardware acceleration capabilities"""
        capabilities = {
            'ffmpeg_available': False,
            'h264_v4l2m2m_encoder': False,
            'h264_v4l2m2m_decoder': False,
            'drm_hwaccel': False,
            'v4l2_hwaccel': False
        }
        
        try:
            # Check FFmpeg availability
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                capabilities['ffmpeg_available'] = True
                self.logger.info("✓ FFmpeg is available")
                
                # Check for hardware acceleration support
                result = subprocess.run(['ffmpeg', '-hwaccels'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    hwaccels = result.stdout.lower()
                    if 'drm' in hwaccels:
                        capabilities['drm_hwaccel'] = True
                        self.logger.info("✓ DRM hardware acceleration available")
                    if 'v4l2m2m' in hwaccels:
                        capabilities['v4l2_hwaccel'] = True
                        self.logger.info("✓ V4L2M2M hardware acceleration available")
                        
                # Check for hardware codecs
                result = subprocess.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    encoders = result.stdout.lower()
                    if 'h264_v4l2m2m' in encoders:
                        capabilities['h264_v4l2m2m_encoder'] = True
                        self.logger.info("✓ H.264 V4L2M2M encoder available")
                        
                result = subprocess.run(['ffmpeg', '-decoders'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    decoders = result.stdout.lower()
                    if 'h264_v4l2m2m' in decoders:
                        capabilities['h264_v4l2m2m_decoder'] = True
                        self.logger.info("✓ H.264 V4L2M2M decoder available")
                        
        except Exception as e:
            self.logger.error(f"Error testing FFmpeg capabilities: {e}")
            
        return capabilities
    
    def test_rtsp_stream_compatibility(self, rtsp_url: str) -> Dict[str, any]:
        """Test RTSP stream with different FFmpeg configurations"""
        test_results = {
            'basic_test': False,
            'hw_decode_test': False,
            'sw_decode_test': True,
            'stream_info': {},
            'errors': []
        }
        
        self.logger.info(f"Testing RTSP stream: {rtsp_url}")
        
        # Test 1: Basic stream info with increased probe parameters
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-analyzeduration', '10000000',  # 10 seconds
                '-probesize', '10000000',        # 10MB
                '-timeout', '10000000',          # 10 seconds
                '-rtsp_transport', 'tcp',
                '-show_entries', 'stream=codec_name,width,height,r_frame_rate',
                '-of', 'json',
                rtsp_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                import json
                stream_info = json.loads(result.stdout)
                test_results['stream_info'] = stream_info
                test_results['basic_test'] = True
                self.logger.info("✓ Basic stream analysis passed")
                
                # Log stream details
                for stream in stream_info.get('streams', []):
                    if stream.get('codec_type') == 'video':
                        self.logger.info(f"Stream: {stream.get('codec_name')} "
                                       f"{stream.get('width')}x{stream.get('height')} "
                                       f"@ {stream.get('r_frame_rate')}")
            else:
                test_results['errors'].append(f"Stream analysis failed: {result.stderr}")
                self.logger.error(f"✗ Stream analysis failed: {result.stderr}")
                
        except Exception as e:
            test_results['errors'].append(f"Stream analysis error: {e}")
            self.logger.error(f"Stream analysis error: {e}")
        
        # Test 2: Hardware decode test (if basic test passed)
        if test_results['basic_test']:
            try:
                cmd = [
                    'ffmpeg', '-y', '-v', 'error',
                    '-hwaccel', 'v4l2m2m',
                    '-analyzeduration', '10000000',
                    '-probesize', '10000000',
                    '-timeout', '10000000',
                    '-rtsp_transport', 'tcp',
                    '-i', rtsp_url,
                    '-t', '3',  # Test for 3 seconds
                    '-f', 'null', '-'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    test_results['hw_decode_test'] = True
                    self.logger.info("✓ Hardware decode test passed")
                else:
                    test_results['errors'].append(f"Hardware decode failed: {result.stderr}")
                    self.logger.warning(f"⚠️ Hardware decode failed: {result.stderr}")
                    
            except Exception as e:
                test_results['errors'].append(f"Hardware decode error: {e}")
                self.logger.warning(f"Hardware decode error: {e}")
        
        # Test 3: Software decode test
        if test_results['basic_test']:
            try:
                cmd = [
                    'ffmpeg', '-y', '-v', 'error',
                    '-analyzeduration', '10000000',
                    '-probesize', '10000000', 
                    '-timeout', '10000000',
                    '-rtsp_transport', 'tcp',
                    '-i', rtsp_url,
                    '-t', '3',  # Test for 3 seconds
                    '-f', 'null', '-'
                ]
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    test_results['sw_decode_test'] = True
                    self.logger.info("✓ Software decode test passed")
                else:
                    test_results['sw_decode_test'] = False
                    test_results['errors'].append(f"Software decode failed: {result.stderr}")
                    self.logger.error(f"✗ Software decode failed: {result.stderr}")
                    
            except Exception as e:
                test_results['sw_decode_test'] = False
                test_results['errors'].append(f"Software decode error: {e}")
                self.logger.error(f"Software decode error: {e}")
        
        return test_results
    
    def generate_optimized_ffplay_command(self, rtsp_url: str, 
                                        hw_capable: bool = False) -> List[str]:
        """Generate optimized ffplay command for Pi 5"""
        
        cmd = ['ffplay']
        
        # Basic optimizations for Pi 5
        cmd.extend([
            '-loglevel', 'info',           # Better logging
            '-analyzeduration', '10000000', # 10 seconds analysis
            '-probesize', '10000000',       # 10MB probe size
            '-timeout', '30000000',         # 30 second timeout
            '-rtsp_transport', 'tcp',       # Force TCP
            '-sync', 'video',               # Sync to video
            '-framedrop',                   # Allow frame dropping
            '-fflags', 'nobuffer',          # No buffering
            '-flags', 'low_delay'           # Low delay
        ])
        
        # Hardware acceleration if available
        if hw_capable:
            cmd.extend(['-hwaccel', 'auto'])
        
        # Audio handling (disable to avoid SDL errors)
        cmd.extend(['-an'])  # No audio
        
        # Add the RTSP URL
        cmd.append(rtsp_url)
        
        return cmd
    
    def test_optimized_playback(self, rtsp_url: str, hw_capable: bool = False) -> bool:
        """Test optimized playback"""
        self.logger.info(f"Testing optimized playback for {rtsp_url}")
        
        cmd = self.generate_optimized_ffplay_command(rtsp_url, hw_capable)
        self.logger.info(f"Command: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Let it run for 10 seconds
            time.sleep(10)
            
            # Check if still running
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
                self.logger.info("✓ Optimized playback test successful")
                return True
            else:
                stdout, stderr = process.communicate()
                self.logger.error(f"✗ Playback failed: {stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Playback test error: {e}")
            return False
    
    def run_comprehensive_test(self, rtsp_url: str = None):
        """Run comprehensive Pi 5 compatibility test"""
        self.logger.info("=== FFmpeg Pi 5 Compatibility Test ===")
        
        # System checks
        pi_model = self.check_pi_version()
        memory_info = self.check_memory_split()
        v4l2_devices = self.check_v4l2_devices()
        ffmpeg_caps = self.test_ffmpeg_capabilities()
        
        # Recommendations based on findings
        self.logger.info("\n=== RECOMMENDATIONS ===")
        
        if memory_info.get('gpu', 0) < 128:
            self.logger.warning("⚠️ GPU memory is low. Consider increasing with: "
                              "sudo raspi-config -> Advanced Options -> Memory Split -> 256")
        
        if not v4l2_devices:
            self.logger.warning("⚠️ No V4L2 devices found. Hardware acceleration may not work.")
        
        if not ffmpeg_caps.get('h264_v4l2m2m_decoder'):
            self.logger.warning("⚠️ H.264 hardware decoder not available. "
                              "Install latest FFmpeg or use software decoding.")
        
        # Test RTSP stream if provided
        if rtsp_url:
            self.logger.info(f"\n=== TESTING RTSP STREAM: {rtsp_url} ===")
            stream_results = self.test_rtsp_stream_compatibility(rtsp_url)
            
            if stream_results['basic_test']:
                hw_capable = stream_results['hw_decode_test']
                self.logger.info(f"\n=== OPTIMIZED PLAYBACK TEST ===")
                self.test_optimized_playback(rtsp_url, hw_capable)
                
                # Generate final recommendation
                self.logger.info(f"\n=== FINAL RECOMMENDATION ===")
                if hw_capable:
                    self.logger.info("✓ Use hardware acceleration for best performance")
                    cmd = self.generate_optimized_ffplay_command(rtsp_url, True)
                else:
                    self.logger.info("⚠️ Use software decoding (hardware acceleration failed)")
                    cmd = self.generate_optimized_ffplay_command(rtsp_url, False)
                
                self.logger.info(f"Recommended command:")
                self.logger.info(f"  {' '.join(cmd)}")
        
        # Generate Pi 5 specific fixes
        self.logger.info(f"\n=== PI 5 SPECIFIC FIXES ===")
        self.logger.info("1. Increase probe/analysis duration for RTSP streams:")
        self.logger.info("   -analyzeduration 10000000 -probesize 10000000")
        self.logger.info("2. Use TCP transport for RTSP:")
        self.logger.info("   -rtsp_transport tcp")
        self.logger.info("3. Disable audio to avoid SDL errors:")
        self.logger.info("   -an")
        self.logger.info("4. Enable frame dropping for live streams:")
        self.logger.info("   -framedrop")
        self.logger.info("5. Consider using VLC as alternative to FFmpeg")

def main():
    """Main function"""
    tester = FFmpegPi5Tester()
    
    # Get RTSP URL from command line or use default test URL
    rtsp_url = None
    if len(sys.argv) > 1:
        rtsp_url = sys.argv[1]
    else:
        # Ask user for RTSP URL
        try:
            rtsp_url = input("Enter RTSP URL to test (or press Enter to skip): ").strip()
            if not rtsp_url:
                rtsp_url = None
        except KeyboardInterrupt:
            print("\nTest cancelled.")
            sys.exit(1)
    
    tester.run_comprehensive_test(rtsp_url)

if __name__ == "__main__":
    main()
