    def _build_vlc_command(self) -> List[str]:
        """Build VLC command with precise windowed positioning"""
        cmd = [
            "cvlc",  # VLC without interface
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
            # Force X11 video output for windowed positioning
            "--vout", "x11",
            "--video-x", str(self.camera.x),
            "--video-y", str(self.camera.y),
            "--width", str(self.camera.width),
            "--height", str(self.camera.height),
            "--no-video-deco",  # No window decorations
            "--no-embedded-video",
            "--video-on-top",  # Keep video windows on top
            "--no-video-title",  # No title bar
            "--loop",  # Loop on connection loss
            self.camera.url
        ]
        return cmd