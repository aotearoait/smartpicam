    def _build_ffmpeg_grid_command(self) -> List[str]:
        """Build FFmpeg command for grid layout with Pi 5 optimizations"""
        if not self.cameras:
            return []
        
        cmd = ["ffmpeg", "-y", "-loglevel", "info"]
        
        # Pi 5 specific optimizations - NO hardware acceleration for grid display
        cmd.extend([
            "-thread_queue_size", "1024",
            "-fflags", "nobuffer+discardcorrupt",  # Handle corrupted packets
            "-flags", "low_delay", 
            "-analyzeduration", "5000000",   # 5 seconds analysis (was 0)
            "-probesize", "5000000"          # 5MB probe size (was 32)
        ])
        
        # Build input list with both working cameras (UDP) and placeholders
        input_sources = []
        
        for i, camera in enumerate(self.cameras):
            # Check if this camera has an active UDP process
            has_active_udp = camera.name in self.camera_processes and self.camera_processes[camera.name].poll() is None
            
            if camera in self.working_cameras and has_active_udp:
                # Working camera - use UDP input with Pi 5 optimizations
                udp_port = self.base_udp_port + i
                cmd.extend([
                    "-timeout", "30000000",  # 30 second timeout for UDP
                    "-rtsp_transport", "tcp",  # Force TCP even for UDP inputs
                    "-i", f"udp://127.0.0.1:{udp_port}?timeout=10000000&buffer_size=1048576"
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
        
        # Build filter complex with error resilience
        filter_parts = []
        
        # Scale each input to its target size with error handling
        for i, (source_type, camera, port) in enumerate(input_sources):
            if source_type == "camera":
                # For UDP camera inputs, add buffering and error resilience
                scale_filter = f"[{i}:v]fps=fps=25:round=near,scale={camera.width}:{camera.height}:flags=fast_bilinear[v{i}]"
            else:
                # For placeholder inputs
                scale_filter = f"[{i}:v]scale={camera.width}:{camera.height}:flags=fast_bilinear[v{i}]"
            filter_parts.append(scale_filter)
        
        # Create black background
        filter_parts.append(f"color=black:{self.display_config.screen_width}x{self.display_config.screen_height}:rate=25[bg]")
        
        # Overlay each camera at its position
        overlay_chain = "[bg]"
        for i, (source_type, camera, port) in enumerate(input_sources):
            if i == len(input_sources) - 1:
                # Last overlay - output directly to framebuffer format
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}:shortest=1,format=rgb565le[out]"
            else:
                overlay = f"{overlay_chain}[v{i}]overlay={camera.x}:{camera.y}:shortest=1[bg{i}]"
                overlay_chain = f"[bg{i}]"
            filter_parts.append(overlay)
        
        # Join all filters
        filter_string = ";".join(filter_parts)
        
        cmd.extend([
            "-filter_complex", filter_string,
            "-map", "[out]",
            "-f", "fbdev", "/dev/fb0",
            "-pix_fmt", "rgb565le",
            "-r", "25"  # Force 25fps output
        ])
        
        return cmd