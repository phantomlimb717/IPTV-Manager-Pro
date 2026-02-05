import asyncio
import aiohttp
import logging
import json
import time
import re
import subprocess
from urllib.parse import urlparse
from datetime import datetime, timezone

# Constants
USER_AGENT = 'IPTV Manager Pro/0.3 (okhttp/3.12.1)'
API_TIMEOUT = 10
DOWNLOAD_TIMEOUT = 10
FFMPEG_TIMEOUT = 20  # Increased to allow for longer analysis

class IPTVChecker:
    """
    Core checking logic for IPTV credentials.
    Implements a two-tier verification strategy:
    1. API Credential Check (Fast)
    2. Stream Connectivity Check (Slower, but verifies playback)
    """

    def __init__(self):
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': USER_AGENT},
                timeout=timeout,
                connector=aiohttp.TCPConnector(ssl=False) # Often needed for IPTV providers with bad certs
            )
        return self.session

    async def close_session(self):
        if self.session:
            if not self.session.closed:
                await self.session.close()
            self.session = None

    async def check_entry(self, entry_data):
        """
        Main entry point for checking an IPTV entry.
        :param entry_data: Dictionary containing entry details (url, username, password, type, etc.)
        :return: Dictionary with check results (status, message, expiry, etc.)
        """
        account_type = entry_data.get('account_type', 'xc')
        result = {
            'success': False,
            'api_status': 'Unknown',
            'api_message': 'Check failed',
            'expiry_date_ts': None,
            'is_trial': None,
            'active_connections': None,
            'max_connections': None,
            'live_streams_count': None,
            'movies_count': None,
            'series_count': None,
            'raw_user_info': None,
            'raw_server_info': None
        }

        try:
            # --- Tier 1: API/Credential Check ---
            if account_type == 'stalker':
                api_result = await self.check_stalker_portal(
                    entry_data.get('portal_url'),
                    entry_data.get('mac_address')
                )
            else:
                api_result = await self.check_xtream_api(
                    entry_data.get('server_base_url'),
                    entry_data.get('username'),
                    entry_data.get('password')
                )

            # Merge API results
            result.update(api_result)

            # --- Tier 2: Stream Verification (Only if API checks out Active) ---
            # If API is valid/active, we proceed to verify if streams actually work.
            # Some providers have valid APIs but dead streams.
            if result.get('success') and result.get('api_status') == 'Active':
                 # Only perform stream check for XC currently as Stalker stream extraction is complex
                 if account_type == 'xc':
                    stream_status = await self.verify_stream_connectivity(
                        entry_data.get('server_base_url'),
                        entry_data.get('username'),
                        entry_data.get('password')
                    )

                    if not stream_status['working']:
                        result['api_status'] = 'Active (Stream Error)'
                        result['api_message'] = f"API OK, but stream check failed: {stream_status['message']}"
                    else:
                        result['api_message'] = "Active & Verified" # Stronger confirmation

        except Exception as e:
            logging.error(f"Unexpected error checking entry: {e}")
            result['api_message'] = f"Internal Error: {str(e)}"

        return result

    async def check_xtream_api(self, server_url, username, password):
        session = await self.get_session()
        result = {'success': False, 'api_status': 'Error'}

        if not server_url or not username:
             result['api_message'] = "Missing URL or Username"
             return result

        try:
            api_url = f"{server_url.rstrip('/')}/player_api.php"
            params = {'username': username, 'password': password}

            async with session.get(api_url, params=params) as response:
                if response.status != 200:
                    result['api_message'] = f"HTTP {response.status}"
                    return result

                try:
                    data = await response.json()
                except json.JSONDecodeError:
                     # Some panels return empty body on failure or plain text
                     text = await response.text()
                     result['api_message'] = f"Invalid JSON response: {text[:50]}"
                     return result

                user_info = data.get('user_info', {})
                server_info = data.get('server_info', {})

                result['raw_user_info'] = json.dumps(user_info)
                result['raw_server_info'] = json.dumps(server_info)

                # Auth Check
                auth = user_info.get('auth', 0)
                if str(auth) == '0':
                    result['api_status'] = 'Auth Failed'
                    result['api_message'] = user_info.get('message', 'Authentication failed')
                    return result

                # Status Check
                result['success'] = True
                result['api_status'] = user_info.get('status', 'Active') # Default to Active if auth passed but status missing
                result['is_trial'] = user_info.get('is_trial')
                result['active_connections'] = user_info.get('active_cons')
                result['max_connections'] = user_info.get('max_connections')

                # Expiry
                exp_date = user_info.get('exp_date')
                if exp_date:
                    try:
                        result['expiry_date_ts'] = int(exp_date)
                    except (ValueError, TypeError):
                        pass

                # Get Counts (Parallel requests)
                # We can launch these concurrently for speed
                counts = await self.get_xtream_counts(server_url, username, password)
                result.update(counts)

        except aiohttp.ClientError as e:
            result['api_message'] = f"Network Error: {str(e)}"
        except Exception as e:
            result['api_message'] = f"Check Error: {str(e)}"

        return result

    async def get_xtream_counts(self, server_url, username, password):
        """Fetches Live, VOD, and Series counts concurrently."""
        session = await self.get_session()
        base_url = f"{server_url.rstrip('/')}/player_api.php"
        base_params = {'username': username, 'password': password}

        actions = {
            'live_streams_count': 'get_live_streams',
            'movies_count': 'get_vod_streams',
            'series_count': 'get_series'
        }

        tasks = []
        for key, action in actions.items():
            params = base_params.copy()
            params['action'] = action
            tasks.append(self._fetch_count(session, base_url, params, key))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        counts = {}
        for res in results:
            if isinstance(res, dict):
                counts.update(res)
        return counts

    async def _fetch_count(self, session, url, params, key):
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        return {key: len(data)}
        except Exception:
            pass # Fail silently for counts
        return {key: 0}

    async def verify_stream_connectivity(self, server_url, username, password):
        """
        Tier 2: Checks if a stream is actually playable.
        Fetches one live stream URL and attempts to download/probe it.
        """
        session = await self.get_session()
        try:
            # 1. Get a list of live streams (limit to getting just the first few bytes of the JSON ideally, but API doesn't support limit)
            # We already fetched counts, so we know if there are streams.
            # We'll try to fetch the live streams list. If it's huge, this might be slow,
            # but usually for a check we just need one valid ID.

            api_url = f"{server_url.rstrip('/')}/player_api.php"
            params = {'username': username, 'password': password, 'action': 'get_live_streams'}

            # TODO: Optimization - If we could just guess a stream ID or use a test channel.
            # For now, we fetch the list. To avoid massive downloads, we can rely on the fact that `check_xtream_api` worked.
            # But strictly, we want to test a stream.

            # Let's try to fetch just the FIRST few kb of the stream list to find ONE stream_id.
            # This avoids downloading a 50MB JSON file for a 20k channel list.

            stream_id = await self._get_first_stream_id(session, api_url, params)

            if not stream_id:
                return {'working': True, 'message': 'No streams to test'} # Treat as working if empty, or maybe 'Empty'

            # Construct stream URL
            # Format: http://server:port/username/password/stream_id.ts
            stream_url = f"{server_url.rstrip('/')}/{username}/{password}/{stream_id}.ts"

            # Create headers for stream checks (Referer and UA)
            headers = {
                'User-Agent': USER_AGENT,
                'Referer': f"{server_url.rstrip('/')}/"
            }

            # 2. Try Speed Test (Fastest)
            # Relaxed threshold: > 0.05 MB/s (approx 50KB/s) is enough to show life
            speed_mb = await self.check_download_speed(stream_url, headers=headers)
            if speed_mb > 0.05:
                return {'working': True, 'message': f'Speed: {speed_mb:.2f} MB/s'}

            # 3. Fallback to FFmpeg (If download failed, maybe it's a specific protocol issue or headers)
            ffmpeg_ok = await self.verify_ffmpeg(stream_url, headers=headers)
            if ffmpeg_ok:
                 return {'working': True, 'message': 'Verified with FFmpeg'}

            return {'working': False, 'message': 'Stream unreachable'}

        except Exception as e:
            return {'working': False, 'message': str(e)}

    async def _get_first_stream_id(self, session, url, params):
        """
        Optimized fetch to find the first stream_id without parsing the whole JSON.
        Uses regex on the incoming stream.
        """
        try:
            async with session.get(url, params=params) as response:
                if response.status != 200: return None

                # Stream the response and look for "stream_id": 12345
                # JSON format: [{"num":1,"name":"...","stream_id":12345,...}, ...]
                pattern = re.compile(rb'"stream_id"\s*:\s*"?(\d+)"?')

                chunk_size = 8192
                buffer = b""

                # Read up to 64KB max to find an ID
                for _ in range(8):
                    chunk = await response.content.read(chunk_size)
                    if not chunk: break
                    buffer += chunk
                    match = pattern.search(buffer)
                    if match:
                        return match.group(1).decode('utf-8')

        except Exception as e:
            logging.warning(f"Error finding stream ID: {e}")
        return None

    async def check_download_speed(self, url, duration=3, headers=None):
        """
        Attempts to download the stream for a short duration to calculate speed.
        Returns speed in MB/s.
        """
        session = await self.get_session()
        start_time = time.time()
        downloaded_bytes = 0

        try:
            # Pass headers if provided
            # Increased duration to allow for initial handshake
            async with session.get(url, timeout=DOWNLOAD_TIMEOUT, headers=headers) as response:
                if response.status != 200: return 0

                while True:
                    chunk = await response.content.read(1024 * 64) # 64KB chunks
                    if not chunk: break
                    downloaded_bytes += len(chunk)

                    if time.time() - start_time > duration:
                        break

                    # If we have enough data (e.g. 512KB), we can stop early
                    if downloaded_bytes > 512 * 1024:
                        break
        except Exception:
            # Even if it errors (e.g. timeout), if we got some bytes, it might be alive
            pass

        elapsed = time.time() - start_time
        if elapsed == 0: return 0

        mb_per_s = (downloaded_bytes / (1024 * 1024)) / elapsed
        return mb_per_s

    async def verify_ffmpeg(self, url, headers=None):
        """
        Uses FFmpeg to verify if the stream is readable.
        Refined to be robust against initial garbage and sync errors.
        """
        # Build headers string for FFmpeg (CRLF separated)
        cmd_args = ["ffmpeg"]

        # 1. Be generous with analysis time/size
        cmd_args.extend(["-analyzeduration", "20000000"]) # 20 seconds
        cmd_args.extend(["-probesize", "20000000"])      # 20 MB

        # 2. Ignore initial errors (decode errors, etc)
        cmd_args.extend(["-err_detect", "ignore_err"])

        # 3. Read for longer (5 seconds)
        cmd_args.extend(["-t", "5"])

        if headers:
            header_str = "".join([f"{k}: {v}\r\n" for k, v in headers.items()])
            cmd_args.extend(["-headers", header_str])

        cmd_args.extend(["-i", url, "-f", "null", "-"])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )

            _, stderr = await asyncio.wait_for(process.communicate(), timeout=FFMPEG_TIMEOUT)

            # Check for success (return code 0 or 1 usually means it tried)
            # Better check: look at stderr for "Duration" or bitrate or "Video:"
            output = stderr.decode('utf-8', errors='ignore')

            # Loose success criteria: if we found a Video or Audio stream, it's alive.
            if "Video:" in output or "Audio:" in output:
                return True

        except (asyncio.TimeoutError, Exception) as e:
            logging.debug(f"FFmpeg check failed: {e}")

        return False

    async def check_stalker_portal(self, portal_url, mac_address):
        """
        Checks a Stalker/MAG portal.
        """
        session = await self.get_session()
        result = {'success': False, 'api_status': 'Error'}

        if not portal_url or not mac_address:
            result['api_message'] = "Missing Portal URL or MAC"
            return result

        try:
            # 1. Handshake / Get Token
            token = await self._stalker_handshake(session, portal_url, mac_address)
            if not token:
                result['api_message'] = "Stalker Handshake Failed"
                return result

            # 2. Get Account Info
            info = await self._stalker_get_info(session, portal_url, token, mac_address)
            if not info:
                result['api_message'] = "Failed to retrieve account info"
                return result

            result['success'] = True
            result['raw_user_info'] = json.dumps(info)

            # Logic to determine status from info
            # Stalker portals vary wildly.
            status_val = str(info.get('status', ''))

            if status_val == '1': result['api_status'] = 'Active'
            elif status_val in ['0', '2']: result['api_status'] = 'Inactive'
            else: result['api_status'] = 'Online' # Fallback

            # Expiry
            exp_date_raw = info.get('exp_date') or info.get('expire_date') or info.get('phone')
            if exp_date_raw:
                result['expiry_date_ts'] = self._parse_stalker_date(exp_date_raw)

            if result['expiry_date_ts'] and result['expiry_date_ts'] < time.time():
                result['api_status'] = 'Expired'

        except Exception as e:
            result['api_message'] = f"Stalker Error: {str(e)}"

        return result

    async def _stalker_handshake(self, session, portal_url, mac_address):
        url = f"{portal_url.rstrip('/')}/portal.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'Authorization': f'Bearer {mac_address}',
            'Referer': f"{portal_url.rstrip('/')}/c/"
        }
        cookies = {'mac': mac_address}
        params = {'action': 'handshake', 'type': 'stb', 'token': '', 'JsHttpRequest': '1-xml'}

        try:
            async with session.get(url, params=params, headers=headers, cookies=cookies) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('js', {}).get('token')
        except Exception as e:
            logging.debug(f"Stalker handshake error: {e}")
        return None

    async def _stalker_get_info(self, session, portal_url, token, mac_address):
        url = f"{portal_url.rstrip('/')}/portal.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'Authorization': f'Bearer {token}',
            'Referer': f"{portal_url.rstrip('/')}/c/"
        }
        cookies = {'mac': mac_address}
        params = {'type': 'account_info', 'action': 'get_main_info', 'JsHttpRequest': '1-xml'}

        try:
            async with session.get(url, params=params, headers=headers, cookies=cookies) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('js', {})
        except Exception:
            pass
        return None

    def _parse_stalker_date(self, date_str):
        """Parses various Stalker date formats."""
        if not date_str: return None
        # Unix timestamp
        if str(date_str).isdigit():
            return int(date_str)

        formats = [
            '%B %d, %Y, %I:%M %p', # August 17, 2025, 12:00 am
            '%Y-%m-%d %H:%M:%S',
            '%d.%m.%Y'
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return int(dt.replace(tzinfo=timezone.utc).timestamp())
            except ValueError:
                continue
        return None
