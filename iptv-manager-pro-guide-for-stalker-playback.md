# Stalker & MAC Portal Playback Guide for IPTV Manager Pro

This guide outlines a comprehensive plan to implement full **Stalker Portal support** (Live TV, VOD, Series, EPG) within the existing **IPTV Manager Pro** application, leveraging its current UI architecture and `MediaPlayerManager`.

## 1. Overview & Architecture Strategy

The goal is to seamlessly integrate Stalker functionality alongside the existing Xtream Codes (XC) API support. We will achieve this by:

1.  **Porting the Core Engine**: Adapting `StalkerPortal` (from `stalker.py`) into a new module `stalker_integration.py` compatible with **PySide6**.
2.  **Worker Abstraction**: Creating dedicated `QObject` worker classes (`StalkerCategoryWorker`, `StalkerStreamWorker`) that mimic the existing XC workers but use Stalker's API.
3.  **UI Extension**: Modifying `PlaylistBrowserDialog` to dynamically switch between XC and Stalker logic based on `entry_data['account_type']`.
4.  **Playback Logic**: Implementing the `create_link` flow required by Stalker middleware before passing the URL to `MediaPlayerManager`.
5.  **EPG Integration**: Porting the `EpgManager` for live channel program data.

---

## 2. Backend Integration: `stalker_integration.py`

Create a new file `stalker_integration.py` to house the `StalkerPortal` class. This class handles authentication, token management, and data fetching.

### Key Implementation Details
-   **Dependencies**: Uses `requests` and `PySide6.QtCore` (for signals).
-   **Token Management**: Implements `handshake()`, `get_profile()`, and automatic re-authentication on 401/404 errors.
-   **Concurrency**: Uses `ThreadPoolExecutor` internally for fetching paginated content (like channels/VOD lists) efficiently.

```python
# stalker_integration.py
import requests
import hashlib
import time
import json
import logging
import re
from urllib.parse import quote, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

class StalkerPortal(QObject):
    # Signals for progress updates (0-100)
    progress_updated = Signal(int)

    def __init__(self, portal_url, mac, serial=None, device_id=None):
        super().__init__()
        self.portal_url = portal_url.rstrip("/")
        self.mac = mac.upper()
        self.serial = serial or self._generate_serial(self.mac)
        self.device_id = device_id or self._generate_device_id(self.mac)
        self.device_id2 = self.device_id
        self.session = requests.Session()
        self.token = None
        self.token_timestamp = 0
        self.stream_base_url = self._derive_stream_base_url()

    def _generate_serial(self, mac):
        return hashlib.md5(mac.encode()).hexdigest()[:13].upper()

    def _generate_device_id(self, mac):
        return hashlib.sha256(mac.encode()).hexdigest().upper()

    def _derive_stream_base_url(self):
        # Fallback stream base if needed
        parsed = urlparse(self.portal_url)
        return f"{parsed.scheme}://{parsed.netloc}/vod4"

    def handshake(self):
        # ... (Implementation of handshake logic from original stalker.py)
        # Handle 404, generate token/prehash if needed
        pass

    def get_profile(self):
        # ... (Implementation of get_profile logic)
        pass

    def get_categories(self, category_type="itv"):
        # Maps to Stalker actions:
        # itv -> action=get_genres
        # vod -> action=get_categories (filtered for movies)
        # series -> action=get_categories (filtered for series)
        pass

    def get_streams(self, category_type, category_id):
        # Maps to Stalker actions:
        # itv -> action=get_ordered_list&genre={id}
        # vod/series -> action=get_ordered_list&category={id}
        pass

    def create_link(self, cmd, type="itv"):
        # Generates a temporary playback link
        # ... (Implementation of create_link logic)
        pass
```

---

## 3. Worker Integration in `IPTV_Manager_Pro.py`

Modify `IPTV_Manager_Pro.py` to include new worker classes for Stalker. These will interface between the UI thread and the `StalkerPortal` class.

### 3.1 `StalkerCategoryLoaderWorker`
Fetches Live, Movie, and Series categories in parallel using the `StalkerPortal` instance.

```python
class StalkerCategoryLoaderWorker(QObject):
    data_ready = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, entry_data):
        super().__init__()
        self.entry_data = entry_data

    def run(self):
        try:
            # Initialize portal
            portal = StalkerPortal(
                self.entry_data['portal_url'],
                self.entry_data['mac_address']
            )
            portal.handshake()
            portal.get_profile()

            # Fetch categories
            data = {
                'live': portal.get_categories("itv"),
                'movie': portal.get_categories("vod"),
                'series': portal.get_categories("series")
            }
            self.data_ready.emit(data)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()
```

### 3.2 `StalkerStreamLoaderWorker`
Fetches the content (channels, movies, or series) for a selected category.

```python
class StalkerStreamLoaderWorker(QObject):
    data_ready = Signal(list)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, entry_data, category_id, stream_type):
        super().__init__()
        self.entry_data = entry_data
        self.category_id = category_id
        self.stream_type = stream_type # 'live', 'movie', 'series'

    def run(self):
        try:
            portal = StalkerPortal(
                self.entry_data['portal_url'],
                self.entry_data['mac_address']
            )
            # Ensure session is valid
            portal.get_profile()

            # Map stream_type to Stalker equivalent
            stalker_type = "itv" if self.stream_type == 'live' else "vod" if self.stream_type == 'movie' else "series"

            # Fetch streams
            streams = portal.get_streams(stalker_type, self.category_id)
            self.data_ready.emit(streams)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()
```

---

## 4. UI Updates: `PlaylistBrowserDialog`

Modify `PlaylistBrowserDialog` to conditionally use either XC workers or Stalker workers based on the account type.

### 4.1 Update `load_playlist_data`
```python
    def load_playlist_data(self):
        account_type = self.entry_data.get('account_type', 'xc')

        if account_type == 'stalker':
            self.category_worker = StalkerCategoryLoaderWorker(self.entry_data)
        else:
            self.category_worker = CategoryLoaderWorker(self.entry_data)

        # ... (rest of the thread setup remains the same)
```

### 4.2 Update `on_category_clicked`
Similar logic for stream loading:
```python
    def on_category_clicked(self, item, column):
        # ... (existing setup)

        account_type = self.entry_data.get('account_type', 'xc')
        if account_type == 'stalker':
            self.stream_worker = StalkerStreamLoaderWorker(self.entry_data, cat_id, stream_type)
        else:
            self.stream_worker = StreamLoaderWorker(self.entry_data, cat_id, stream_type)

        # ... (rest of the thread setup)
```

---

## 5. Playback Logic Updates

Stalker portals require generating a temporary link via `create_link` before playback. The XC logic constructs the URL locally. We need to abstract this.

### 5.1 New `StalkerPlaybackWorker`
Create a worker to handle the synchronous network request to `create_link` without blocking the UI.

```python
class StalkerPlaybackWorker(QObject):
    link_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, entry_data, stream_id, stream_type, cmd=None):
        super().__init__()
        self.entry_data = entry_data
        self.stream_id = stream_id
        self.stream_type = stream_type
        self.cmd = cmd

    def run(self):
        try:
            portal = StalkerPortal(self.entry_data['portal_url'], self.entry_data['mac_address'])
            portal.get_profile()

            # Use 'cmd' if available (common in Live TV), else construct it for VOD
            command = self.cmd
            if not command and self.stream_type in ['movie', 'series']:
                command = f"/media/file_{self.stream_id}.mpg"

            real_url = portal.create_link(command, type="itv" if self.stream_type == 'live' else "vod")
            self.link_ready.emit(real_url)
        except Exception as e:
            self.error_occurred.emit(str(e))
```

### 5.2 Modify `play_vod_or_live` in `PlaylistBrowserDialog`
```python
    def play_vod_or_live(self, stream_id, category, container_extension=None):
        account_type = self.entry_data.get('account_type', 'xc')

        if account_type == 'stalker':
            # Need to fetch the real link first
            cmd = self.get_cmd_from_model(stream_id) # Helper to get stored cmd
            self.playback_worker = StalkerPlaybackWorker(self.entry_data, stream_id, 'live' if category=='Live TV' else 'movie', cmd)
            self.playback_thread = QThread()
            self.playback_worker.moveToThread(self.playback_thread)
            self.playback_worker.link_ready.connect(self.launch_player)
            self.playback_thread.started.connect(self.playback_worker.run)
            self.playback_thread.start()
        else:
            # Existing XC Logic
            # ...
            self.launch_player(stream_url)

    def launch_player(self, url):
        self.media_player_manager.play_stream(url, self)
```

---

## 6. EPG Integration (New Feature)

Port the `EpgManager` from `Epg.py` to `epg_manager.py`, adapting it for PySide6 signals.

### 6.1 `EpgManager` Structure
```python
# epg_manager.py
from PySide6.QtCore import QThread, Signal
import requests

class EpgManager(QThread):
    epg_ready = Signal(str, list) # channel_id, list of programs

    def __init__(self, portal_url, mac):
        super().__init__()
        self.portal = StalkerPortal(portal_url, mac)
        self.queue = []

    def request_epg(self, channel_id):
        self.queue.append(channel_id)

    def run(self):
        while True:
            if self.queue:
                ch_id = self.queue.pop(0)
                data = self.portal.get_epg(ch_id) # Implement get_epg in StalkerPortal
                self.epg_ready.emit(ch_id, data)
            self.msleep(100)
```

### 6.2 UI Integration
1.  Add a column "EPG" to `self.stream_model` in `PlaylistBrowserDialog`.
2.  Instantiate `EpgManager` in `PlaylistBrowserDialog`.
3.  Connect `epg_ready` signal to a slot that updates the model:
    ```python
    def update_epg_column(self, channel_id, programs):
        # Find row with channel_id
        # Update EPG cell with current program name
    ```
4.  Trigger `request_epg` when loading Live TV streams.

---

## 7. Database Updates

Ensure the `entries` table supports Stalker-specific fields. The current `IPTV-Manager-Pro` DB schema already has:
-   `mac_address`
-   `portal_url`
-   `account_type`

No further DB schema changes are strictly required, but ensuring `server_base_url` is correctly populated (derived from portal URL) is important for generic logic compatibility.

## 8. Summary of Changes

| Component | Status | Action Required |
| :--- | :--- | :--- |
| **Backend** | ⬜ | Create `stalker_integration.py` with `StalkerPortal` class. |
| **Workers** | ⬜ | Implement `StalkerCategoryLoaderWorker`, `StalkerStreamLoaderWorker`, `StalkerPlaybackWorker`. |
| **UI** | ⬜ | Update `PlaylistBrowserDialog` to switch logic based on account type. |
| **Playback** | ⬜ | Implement async link generation for Stalker streams. |
| **EPG** | ⬜ | Port `EpgManager` and add EPG column to playlist view. |
