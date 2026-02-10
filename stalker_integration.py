import requests
import hashlib
import time
import json
import logging
import random
import string
from urllib.parse import urlparse, quote

# Constants matching those in core_checker.py for consistency
STALKER_API_PATH = "/stalker_portal/server/load.php"
DEFAULT_TZ = "Europe/London"
MAG_USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"

logger = logging.getLogger(__name__)

class StalkerPortal:
    """
    Synchronous Stalker Portal Client for IPTV Manager Pro.
    Used by Worker threads in the UI.
    """
    def __init__(self, portal_url, mac_address):
        self.mac_address = mac_address.upper()
        self.portal_url = self._normalize_url(portal_url)
        self.api_url = f"{self.portal_url}{STALKER_API_PATH}" # Default, but will be updated if handshake finds another

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': MAG_USER_AGENT,
            'Referer': f"{self.portal_url}/stalker_portal/c/"
        })

        # Initialize cookies
        self.session.cookies.update({
            'mac': self.mac_address,
            'stb_lang': 'en',
            'timezone': DEFAULT_TZ
        })

        self.token = None

        # Hardware identifiers
        self.serial = self._generate_serial(self.mac_address)
        self.device_id = hashlib.sha256(self.mac_address.encode()).hexdigest().upper()
        self.device_id2 = self.device_id
        self.signature = self._generate_signature()

    def _normalize_url(self, url):
        if not url: return ""
        url = url.strip()
        # Order matters: strip longer suffixes first
        suffixes = ['/stalker_portal/c/', '/stalker_portal/c', '/c/', '/c',
                    '/portal.php', '/stalker_portal/server/load.php', '/server/load.php']
        for suffix in suffixes:
            if url.endswith(suffix):
                url = url[:-len(suffix)]
                break

        # Also strip trailing /stalker_portal if present to avoid duplication
        # because handshake adds it back in the first endpoint option.
        if url.endswith('/stalker_portal'):
             url = url[:-len('/stalker_portal')]

        return url.rstrip('/')

    def _generate_serial(self, mac):
        return hashlib.md5(mac.encode()).hexdigest()[:13].upper()

    def _generate_signature(self):
        # Signature: sha256(mac + sn + device_id + device_id2)
        source = f"{self.mac_address}{self.serial}{self.device_id}{self.device_id2}"
        return hashlib.sha256(source.encode()).hexdigest().upper()

    def _generate_token(self):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=32))

    def _generate_prehash(self, token, mac):
        return hashlib.sha1(token.encode()).hexdigest()

    def handshake(self):
        """
        Performs the initial handshake to obtain a token.
        Implements fallback logic for strict portals and multiple endpoints.
        """
        endpoints = [
            "/stalker_portal/server/load.php",
            "/server/load.php",
            "/portal.php",
            "/c/portal.php"
        ]

        params = {'type': 'stb', 'action': 'handshake', 'token': '', 'JsHttpRequest': '1-xml'}

        for endpoint in endpoints:
            current_api_url = f"{self.portal_url}{endpoint}"
            try:
                # 1. Try standard handshake
                resp = self.session.get(current_api_url, params=params, timeout=10)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        token = data.get('js', {}).get('token')
                        if token:
                            self.token = token
                            self.session.cookies.update({'token': token})
                            self.api_url = current_api_url # Store working endpoint
                            return True
                    except json.JSONDecodeError:
                        pass

                # 2. Fallback: Generate token manually if 404 or no token returned
                if resp.status_code in [404, 403] or not self.token:
                    logger.info(f"Standard handshake failed for {endpoint}, trying fallback with generated token.")
                    token = self._generate_token()
                    prehash = self._generate_prehash(token, self.mac_address)

                    fallback_params = params.copy()
                    fallback_params['token'] = token
                    fallback_params['prehash'] = prehash

                    resp = self.session.get(current_api_url, params=fallback_params, timeout=10)
                    if resp.status_code == 200:
                        try:
                            # Verify valid JSON response
                            resp.json()
                            self.token = token
                            self.session.cookies.update({'token': token})
                            self.api_url = current_api_url # Store working endpoint
                            return True
                        except json.JSONDecodeError:
                            pass

            except Exception as e:
                logger.error(f"Handshake error for {endpoint}: {e}")
                continue

        return False

    def get_profile(self):
        """
        Authenticates and retrieves the user profile.
        Required before making other requests.
        """
        if not self.token:
            if not self.handshake():
                raise Exception("Handshake failed. Cannot get profile.")

        headers = {'Authorization': f'Bearer {self.token}'}

        params = {
            'type': 'stb',
            'action': 'get_profile',
            'hd': '1',
            'ver': 'ImageDescription: 0.2.18-r23-250; ImageDate: Fri Jan 15 15:00:00 2021; PORTAL version: 5.6.1; API Version: JS API version: 343; STB API version: 146; Player Engine version: 0x58c',
            'num_banks': '2',
            'sn': self.serial,
            'stb_type': 'MAG250',
            'client_type': 'STB',
            'image_version': '218',
            'video_out': 'hdmi',
            'device_id': self.device_id,
            'device_id2': self.device_id2,
            'signature': self.signature,
            'auth_second_step': '1',
            'hw_version': '1.7-BD-00',
            'not_valid_token': '0',
            'timestamp': int(time.time()),
            'JsHttpRequest': '1-xml'
        }

        try:
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            js_data = data.get('js', {})

            # Token rotation check
            if 'token' in js_data and js_data['token']:
                self.token = js_data['token']
                self.session.cookies.update({'token': self.token})

            if not js_data or 'id' not in js_data:
                 raise Exception("Authentication failed (Invalid Profile Data)")

            return js_data

        except Exception as e:
            logger.error(f"Get Profile error: {e}")
            raise

    def get_categories(self, type_val):
        """
        Fetches categories/genres.
        type_val: 'itv' (Live), 'vod' (Movies), 'series' (Series)
        """
        action = 'get_genres' if type_val == 'itv' else 'get_categories'
        params = {
            'type': type_val,
            'action': action,
            'JsHttpRequest': '1-xml'
        }

        headers = {'Authorization': f'Bearer {self.token}'}

        try:
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=10)
            data = resp.json()
            return data.get('js', [])
        except Exception as e:
            logger.error(f"Error fetching categories for {type_val}: {e}")
            return []

    def get_streams(self, type_val, category_id):
        """
        Fetches streams for a category.
        Handles pagination internally to get all items (or a large limit).
        """
        params = {
            'type': type_val,
            'action': 'get_ordered_list',
            'p': 1,
            'JsHttpRequest': '1-xml'
        }

        if type_val == 'itv':
            params['genre'] = category_id if category_id != '*' else 0
        else:
            params['category'] = category_id if category_id != '*' else 0

        headers = {'Authorization': f'Bearer {self.token}'}

        all_items = []
        try:
            # Fetch page 1
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=10)
            data = resp.json()
            js_data = data.get('js', {})
            items = js_data.get('data', [])
            total_items = int(js_data.get('total_items', 0))
            all_items.extend(items)

            # Simple pagination: Fetch up to 5 pages max to keep it responsive
            # or try to force limit if possible (Stalker rarely supports limit override)
            import math
            page_size = len(items)
            if page_size > 0 and total_items > page_size:
                total_pages = math.ceil(total_items / page_size)
                # Limit to 5 pages max for now to avoid freezing
                limit_pages = min(total_pages, 5)

                for p in range(2, limit_pages + 1):
                    params['p'] = p
                    try:
                        r = self.session.get(self.api_url, params=params, headers=headers, timeout=5)
                        p_data = r.json().get('js', {}).get('data', [])
                        all_items.extend(p_data)
                    except Exception:
                        break

            return all_items

        except Exception as e:
            logger.error(f"Error fetching streams for {type_val} cat {category_id}: {e}")
            return []

    def create_link(self, type_val, cmd):
        """
        Generates a temporary playback link.
        """
        params = {
            'type': type_val,
            'action': 'create_link',
            'cmd': cmd,
            'JsHttpRequest': '1-xml'
        }

        headers = {'Authorization': f'Bearer {self.token}'}

        try:
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=10)
            data = resp.json()
            link = data.get('js', {}).get('cmd')

            if link and link.startswith('ffmpeg '):
                link = link.replace('ffmpeg ', '').strip()

            return link
        except Exception as e:
            logger.error(f"Error creating link for {cmd}: {e}")
            raise

    def get_epg(self, channel_id, period=3600):
        """
        Fetches EPG for a specific channel.
        period: seconds to look ahead (default 1 hour)
        """
        params = {
            'type': 'itv',
            'action': 'get_epg_info',
            'period': period,
            'ch_id': channel_id,
            'JsHttpRequest': '1-xml'
        }
        headers = {'Authorization': f'Bearer {self.token}'}

        try:
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=5)
            data = resp.json()
            return data.get('js', {}).get('data', [])
        except Exception:
            return []

    def get_series_episodes(self, series_id):
        """
        Fetches episodes for a series. Handles seasons if present.
        """
        # First try fetching directly with movie_id (some portals return flat list)
        params = {
            'type': 'vod',
            'action': 'get_ordered_list',
            'movie_id': series_id,
            'season_id': 0,
            'JsHttpRequest': '1-xml'
        }
        headers = {'Authorization': f'Bearer {self.token}'}

        episodes = []
        try:
            resp = self.session.get(self.api_url, params=params, headers=headers, timeout=10)
            data = resp.json()
            items = data.get('js', {}).get('data', [])

            if not items:
                return []

            # Check if result is seasons or episodes
            # Heuristic: Check for 'cmd' (playable) vs just 'id'/'name'
            has_cmd = any('cmd' in x for x in items)

            if has_cmd:
                return items

            # Assume seasons, iterate and fetch
            for season in items:
                s_id = season.get('id')
                if not s_id: continue

                p2 = params.copy()
                p2['season_id'] = s_id
                try:
                    r2 = self.session.get(self.api_url, params=p2, headers=headers, timeout=5)
                    d2 = r2.json().get('js', {}).get('data', [])
                    for ep in d2:
                        ep['season_num'] = season.get('season_number', season.get('name')) # Try to get season num
                    episodes.extend(d2)
                except Exception:
                    pass
            return episodes
        except Exception as e:
            logger.error(f"Error fetching episodes for series {series_id}: {e}")
            return []
