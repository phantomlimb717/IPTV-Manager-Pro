# Stalker & MAC Portal Playback Features: Deep Technical Analysis

This document provides a comprehensive technical breakdown of the `MAC-Portal IPTV Player` codebase (`STALKER PLAYER.py`, `stalker.py`, `Epg.py`). It details the implementation strategies, API interactions, threading models, and data structures used to achieve the application's feature set.

---

## 1. MAC & Stalker IPTV Support

The application implements a dual-mode playback engine that detects the portal type based on the input URL structure.

### 1.1 Portal Detection Logic
Located in `STALKER PLAYER.py` -> `MainWindow.get_playlist()`:
```python
if "/stalker_portal/" in hostname_input:
    # Stalker portal logic: Instantiates StalkerPortal class
    self.portal = StalkerPortal(portal_url=self.base_url, mac=self.mac_address, ...)
else:
    # Generic MAC logic: Uses generic RequestThread
    self.token = get_token(self.session, self.base_url, self.mac_address)
```

### 1.2 Stalker Authentication (`stalker.py`)
The `StalkerPortal` class manages the complex handshake required by Stalker middleware.

#### Handshake Protocol (`handshake()`)
1.  **Initial Request**:
    ```python
    initial_url = f"{self.portal_url}/stalker_portal/server/load.php?type=stb&action=handshake&token=&JsHttpRequest=1-xml"
    ```
2.  **404 Handling & Token Generation**:
    If the initial request fails with `404`, the client generates its own token and prehash (SHA1) to retry:
    ```python
    token = self.generate_token()  # Random 32-char string
    prehash = hashlib.sha1(token.encode()).hexdigest()
    retry_url = f"...&action=handshake&token={token}&prehash={prehash}..."
    ```
3.  **Session Initialization**:
    On success, it extracts `js.token` and `js.random` from the JSON response to use in subsequent `Authorization: Bearer <token>` headers.

#### Profile & Device Signature (`get_profile()`)
The server validates the client as a legitimate STB using a cryptographic signature:
```python
def generate_signature(self) -> str:
    # serial = md5(mac)[:13].upper()
    # device_id = sha256(mac).upper()
    data = f"{self.mac}{self.serial}{self.device_id1}{self.device_id2}"
    return hashlib.sha256(data.encode()).hexdigest().upper()
```
This signature is sent in the `get_profile` request headers along with metrics and hardware version info (`ver`, `stb_type="MAG250"`).

---

## 2. Live Channel Streaming

### 2.1 Channel Retrieval (`stalker.py`)
Channels are fetched via the `fetch_all_pages` method, which handles pagination concurrently.

-   **Endpoint**: `.../load.php?type=itv&action=get_ordered_list&genre={genre_id}&p={page}`
-   **Concurrency**: Uses `concurrent.futures.ThreadPoolExecutor` to fetch all pages in parallel.
    ```python
    with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
        future_to_page = {
            executor.submit(self.make_request_with_retries, ..., p=p): p
            for p in range(1, total_pages + 1)
        }
    ```

### 2.2 Stream Link Generation (`get_stream_link()`)
When a channel is selected, the application requests a temporary playback URL.

1.  **Request**:
    `action=create_link`, `type=itv`, `cmd={channel_cmd}` (e.g., `ffmpeg http://...`).
2.  **Response Parsing**:
    The server returns a JSON with `cmd` or `url`. The code specifically handles `ffmpeg` prefixes commonly sent by Stalker portals:
    ```python
    if re.match(r'(?i)^ffmpeg\s*(.*)', stream_url):
        stream_url = re.sub(r'(?i)^ffmpeg\s*', '', stream_url).strip()
    ```
3.  **Absolute URL Construction**:
    If the returned URL is relative (e.g., `http://server/stream`), it is used directly. If it's a path, it's appended to `stream_base_url`.

---

## 3. VOD & Series Playback

The application distinguishes between single-file movies (VOD) and multi-file series using keyword heuristics on category names and metadata flags.

### 3.1 Category Separation (`stalker.py`)
-   **VOD**: Excludes categories containing "tv", "series", "show".
-   **Series**: Includes *only* categories containing those keywords.

### 3.2 Hierarchical Data Fetching
-   **Series Level**: `get_series_in_category` fetches items where `is_series="1"`.
-   **Season Level**: `get_seasons(movie_id)` calls `get_ordered_list` with `movie_id={id}` and `season_id=0`. It filters results for `is_season=1`.
-   **Episode Level**: `get_episodes(movie_id, season_id)` calls `get_ordered_list` with specific `season_id`.

### 3.3 Episode Stream Resolution
Accessing an episode stream is a two-step process in Stalker middleware:
1.  **Fetch Episode Data**: `get_ordered_list` with `episode_id` to get the internal `stream_id` (often different from the visible ID).
2.  **Create Link**:
    ```python
    params = {
        "action": "create_link",
        "type": "vod",
        "cmd": f"/media/file_{stream_id}.mpg",  # Specific Stalker format
        ...
    }
    ```

---

## 4. Live EPG (Electronic Program Guide)

### 4.1 Architecture (`Epg.py`)
The `EpgManager` runs as a separate `QThread` to prevent UI blocking. It uses a producer-consumer pattern with a `queue.Queue` for incoming requests.

-   **Endpoints**: Tries `/stalker_portal/server/load.php` first, falls back to `/stalker_portal/load.php`.
-   **Actions**:
    1.  `get_short_epg` (Primary): Fast, returns limited data.
    2.  `get_epg_info` (Fallback): Slower, returns detailed data.

### 4.2 Prefetching Strategy (`STALKER PLAYER.py`)
To avoid flooding the server, the UI uses a **batched prefetcher**:
```python
def _prefetch_live_epg_for_current_list(...):
    t = QTimer(self)
    t.setInterval(10) # 10ms interval between batches
    def _tick():
        batch = queue[:25] # Process 25 channels at a time
        for item in batch:
            self.epg.request(ch) # Enqueue in EpgManager
```
This ensures the UI remains responsive even when scrolling through hundreds of channels.

---

## 5. Movie & TV Show Tooltips

### 5.1 Tooltip Generation (`STALKER PLAYER.py`)
The `_format_movie_tooltip` function constructs a rich HTML tooltip.

-   **HTML Structure**: Uses a `<table>` layout for consistent alignment of poster vs. text.
-   **CSS**:
    ```html
    <div style="max-width:520px; font-size:12px; line-height:1.25;">
    ```
-   **Poster Caching**:
    To prevent re-downloading images on every hover, `_poster_local_file` saves images to a temp directory using a SHA1 hash of the URL as the filename:
    ```python
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    cache_path = os.path.join(tempfile.gettempdir(), "maciptv_posters", f"{h}{ext}")
    ```

---

## 6. Info Tab

The Info tab aggregates data from multiple Stalker API endpoints to display account status.

-   **Profile Data** (`get_profile`): `mac_address`, `fname` (Full Name), `expire_date`.
-   **Account Info** (`get_main_info`): `phone`, `parent_password`.
-   **Storage Info**: Parses the `storages` JSON object to calculate `max_online` connections allowed.

---

## 7. Theme Refresh (Cyan Look)

The application applies a custom QSS (Qt Style Sheet) on top of `qdarkstyle`.

### 7.1 Implementation
Located in `apply_dark_theme()`:
1.  **Load Base**: `qdarkstyle.load_stylesheet(qt_api='pyqt5')`
2.  **String Replacement**:
    ```python
    qss = qss.replace('#2a82da', '#00dfff')  # Blue -> Cyan Highlight
    qss.replace('#3daee9', '#9befff')      # Lighter Cyan
    ```
3.  **Custom Widgets**:
    Specific overrides for `QProgressBar` (cyan chunks), `QToolTip` (dark background, cyan border), and `QPushButton`.

---

## 8. Playlist Management & Threading

### 8.1 Threading Model
The application strictly separates UI and Network operations.

-   **Main Thread (UI)**: Handles user input, signals, and drawing.
-   **RequestThread / StalkerRequestThread (Worker)**:
    -   Inherits from `QThread`.
    -   Emits signals (`request_complete`, `update_progress`) to pass data back to the UI.
    -   **Parallelism**: Inside the worker thread, `concurrent.futures.ThreadPoolExecutor` is used to fetch categories or pages in parallel (e.g., fetching "Live", "Movies", and "Series" categories simultaneously).

### 8.2 Progress Tracking
Progress is calculated based on the number of completed tasks (pages/categories) vs. total expected tasks.
```python
completed_categories += 1
progress_percent = int((completed_categories / total_categories) * 100)
self.update_progress.emit(progress_percent)
```

---

## 9. Multi-Player Support

The application acts as a launcher for external media players, ensuring wide codec support (HEVC, AC3, etc.) that `QMediaPlayer` might lack.

### 9.1 Launch Logic (`launch_media_player`)
1.  **Prefix Stripping**: Removes `ffmpeg ` or `ffrt3 ` prefixes from the URL.
2.  **User-Agent Injection**:
    VLC is launched with a specific User-Agent to mimic a browser or STB, reducing the chance of server-side blocking:
    ```python
    vlc_command = [
        media_player_path,
        stream_url,
        ":http-user-agent=Lavf53.32.100"  # Mimics FFmpeg/Lavf
    ]
    subprocess.Popen(vlc_command)
    ```

---

## 10. Cross-Compatibility

-   **File Systems**: Uses `os.path.join` and `tempfile.gettempdir()` to handle path separators (`\` vs `/`) correctly on Windows and Linux/macOS.
-   **PyQt Abstraction**: The code primarily uses `PyQt5`, which abstracts the underlying windowing system (Win32, Cocoa, X11).
-   **Networking**: `requests.Session` handles keep-alive and connection pooling transparently across platforms.
