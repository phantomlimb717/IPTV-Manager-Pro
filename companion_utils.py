# companion_utils.py

import os
import platform
import subprocess
import shutil

# Note: IPTV-Manager-Pro uses PySide6. The original code was PyQt6.
# Most of the API is compatible.
from PySide6.QtWidgets import QMessageBox

class MediaPlayerManager:
    """
    Manages media player selection and execution across platforms.
    Adapted from iptv-companion-copy.
    """

    def __init__(self):
        # Simplified settings: default to ffplay, but try mpv if ffplay is not found.
        self.current_os = platform.system().lower()
        self.preferred_player = "ffplay" # Default to ffplay

    def get_player_executable(self, player_type=None):
        """Gets the appropriate executable name for the current platform."""
        if player_type is None:
            player_type = self.preferred_player

        if self.current_os == "windows":
            if player_type == "mpv":
                # Try both mpv.exe and mpvnet.exe on Windows
                for exe_name in ["mpvnet.exe", "mpv.exe"]:
                    if shutil.which(exe_name):
                        return exe_name
                return "mpv.exe"  # Default fallback
            else:
                return "ffplay.exe"
        else:
            # Linux, macOS, and other Unix-like systems
            if player_type == "mpv":
                return "mpv"
            else:
                return "ffplay"

    def check_player_availability(self, player_type):
        """Checks if a media player is available on the system."""
        executable = self.get_player_executable(player_type)
        return shutil.which(executable) is not None

    def get_player_command(self, stream_url, player_type, referer_url=None):
        """Generate the appropriate command line for playing a stream"""
        executable = self.get_player_executable(player_type)
        user_agent = "VLC/3.0.18"

        if player_type == "mpv":
            command = [
                executable,
                "--no-config",
                "--ytdl=no",
                "--fs",
                "--keep-open=no",
            ]
            headers = [f"User-Agent: {user_agent}"]
            if referer_url:
                headers.append(f"Referer: {referer_url}")

            command.append(f"--http-header-fields={','.join(headers)}")

            if self.current_os == "windows":
                command.append("--ao=wasapi")

            command.append(stream_url)
            return command
        else:  # ffplay
            headers = f"User-Agent: {user_agent}\r\n"
            if referer_url:
                headers += f"Referer: {referer_url}\r\n"
            return [executable, "-headers", headers, "-fs", "-noborder", "-autoexit", stream_url]

    def play_stream(self, stream_url, parent_widget=None, referer_url=None):
        """
        Play a stream URL using the best available media player.
        It first tries mpv, then falls back to ffplay.
        """
        player_to_use = None
        if self.check_player_availability("mpv"):
            player_to_use = "mpv"
        elif self.check_player_availability("ffplay"):
            player_to_use = "ffplay"
        else:
            self._show_player_not_found_error(parent_widget)
            return False

        command = self.get_player_command(stream_url, player_to_use, referer_url)

        try:
            # Using Popen to run in a non-blocking way
            subprocess.Popen(command)
            return True
        except FileNotFoundError:
            # This case should be rare since we check availability first
            self._show_player_not_found_error(parent_widget)
            return False
        except Exception as e:
            self._show_playback_error(str(e), parent_widget)
            return False

    def _show_player_not_found_error(self, parent_widget):
        """Show error message when no supported player is found"""
        error_msg = "No compatible media player found (FFplay or MPV).\\n\\n"
        error_msg += "Please ensure either FFplay (part of FFmpeg) or MPV is installed and available in your system's PATH.\\n\\n"

        if self.current_os == "windows":
            error_msg += "For FFmpeg on Windows:\\n"
            error_msg += "• Download from https://ffmpeg.org/download.html\\n"
            error_msg += "• Add the 'bin' directory to your system PATH\\n\\n"
            error_msg += "For MPV on Windows:\\n"
            error_msg += "• Download from https://mpv.io/installation/\\n"
        else:
            error_msg += "For FFmpeg on Linux/macOS:\\n"
            error_msg += "• Ubuntu/Debian: sudo apt install ffmpeg\\n"
            error_msg += "• macOS: brew install ffmpeg\\n\\n"
            error_msg += "For MPV on Linux/macOS:\\n"
            error_msg += "• Ubuntu/Debian: sudo apt install mpv\\n"
            error_msg += "• macOS: brew install mpv\\n"

        QMessageBox.critical(parent_widget, "Media Player Error", error_msg)

    def _show_playback_error(self, error_message, parent_widget):
        """Show generic playback error"""
        QMessageBox.critical(
            parent_widget,
            "Playback Error",
            f"An error occurred while trying to play the stream:\\n\\n{error_message}"
        )
