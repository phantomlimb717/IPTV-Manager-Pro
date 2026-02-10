# companion_utils.py

import os
import platform
import subprocess
import shutil
import logging
import json

from PySide6.QtWidgets import QMessageBox

class MediaPlayerManager:
    """
    Manages media player selection, configuration, and execution across platforms.
    """
    PLAYER_CONFIG = {
        "mpv": {
            "base_args": [
                "--no-config",
                "--ytdl=no",
                "--fs",
                "--keep-open=no",
            ],
            "windows": ["--ao=wasapi"],
            "darwin": [],
            "linux": [],
        },
        "ffplay": {
            "base_args": [
                "-fs",
                "-noborder",
                "-autoexit",
            ],
            "windows": [],
            "darwin": [],
            "linux": [],
        },
        "ffprobe": {
            "base_args": [
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
            ],
             "windows": [],
            "darwin": [],
            "linux": [],
        }
    }

    def __init__(self):
        self.current_os = platform.system().lower()

    def get_player_executable(self, player_type):
        """Gets the appropriate executable name for the current platform."""
        if self.current_os == "windows":
            return f"{player_type}.exe"
        else:
            return player_type

    def check_player_availability(self, player_type):
        """Checks if a media player is available on the system."""
        executable = self.get_player_executable(player_type)
        return shutil.which(executable) is not None

    def get_player_command(self, stream_url, player_type, referer_url=None, cookies=None, user_agent=None):
        """Generate the appropriate command line for playing a stream."""
        executable = self.get_player_executable(player_type)
        if not user_agent:
            user_agent = "VLC/3.0.18"

        config = self.PLAYER_CONFIG.get(player_type, {})
        command = [executable] + config.get("base_args", [])

        platform_args = config.get(self.current_os, [])
        if platform_args:
            command.extend(platform_args)

        if player_type == "mpv":
            headers = [f"User-Agent: {user_agent}"]
            if referer_url:
                headers.append(f"Referer: {referer_url}")
            if cookies:
                headers.append(f"Cookie: {cookies}")
            command.append(f"--http-header-fields={','.join(headers)}")
        elif player_type in ["ffplay", "ffprobe"]:
            headers = f"User-Agent: {user_agent}\r\n"
            if referer_url:
                headers += f"Referer: {referer_url}\r\n"
            if cookies:
                headers += f"Cookie: {cookies}\r\n"
            command.extend(["-headers", headers])

        command.append(stream_url)
        return command

    def get_stream_info(self, stream_url, referer_url=None, cookies=None, user_agent=None):
        """
        Uses ffprobe to get codec and format information for a stream.
        """
        if not self.check_player_availability("ffprobe"):
            logging.warning("ffprobe is not available, cannot get stream info.")
            return None

        command = self.get_player_command(stream_url, "ffprobe", referer_url, cookies, user_agent)

        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=15)
            return json.loads(result.stdout)
        except FileNotFoundError:
            logging.error("ffprobe executable not found, though check passed. This is unexpected.")
            return None
        except subprocess.TimeoutExpired:
            logging.error(f"ffprobe timed out analyzing stream: {stream_url}")
            return None
        except subprocess.CalledProcessError as e:
            logging.error(f"ffprobe failed with exit code {e.returncode} for stream: {stream_url}")
            logging.error(f"ffprobe stderr: {e.stderr}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode JSON from ffprobe output: {e}")
            return None
        except Exception as e:
            logging.error(f"An unexpected error occurred while running ffprobe: {e}")
            return None

    def play_stream(self, stream_url, parent_widget=None, referer_url=None, cookies=None, user_agent=None):
        """
        Analyzes and plays a stream URL using the best available media player.
        """
        # 1. Analyze the stream
        logging.info(f"Attempting to play stream: {stream_url}")
        stream_info = self.get_stream_info(stream_url, referer_url, cookies, user_agent)

        if stream_info:
            logging.info(f"Stream analysis successful for: {stream_url}")
            # Log format information
            if 'format' in stream_info:
                format_info = stream_info['format']
                logging.info(f"  Format: {format_info.get('format_long_name', 'N/A')}")
            # Log codec information for each stream
            if 'streams' in stream_info:
                for stream in stream_info['streams']:
                    codec_type = stream.get('codec_type', 'unknown')
                    codec_name = stream.get('codec_long_name', 'N/A')
                    logging.info(f"  - {codec_type.capitalize()} stream: {codec_name}")
        else:
            logging.warning(f"Could not analyze stream, proceeding with playback attempt: {stream_url}")

        # 2. Select player and play
        player_to_use = None
        if self.check_player_availability("mpv"):
            player_to_use = "mpv"
        elif self.check_player_availability("ffplay"):
            player_to_use = "ffplay"
        else:
            self._show_player_not_found_error(parent_widget)
            return False

        command = self.get_player_command(stream_url, player_to_use, referer_url, cookies, user_agent)

        try:
            subprocess.Popen(command)
            logging.info(f"Launched {player_to_use} with command: {' '.join(command)}")
            return True
        except FileNotFoundError:
            self._show_player_not_found_error(parent_widget)
            return False
        except Exception as e:
            self._show_playback_error(str(e), parent_widget)
            return False

    def _show_player_not_found_error(self, parent_widget):
        """Show error message when no supported player is found."""
        error_msg = "No compatible media player found (FFplay or MPV).\\n\\n"
        error_msg += "Please ensure either FFplay (part of FFmpeg) or MPV is installed and available in your system's PATH."
        QMessageBox.critical(parent_widget, "Media Player Error", error_msg)

    def _show_playback_error(self, error_message, parent_widget):
        """Show generic playback error."""
        QMessageBox.critical(
            parent_widget,
            "Playback Error",
            f"An error occurred while trying to play the stream:\\n\\n{error_message}"
        )
