# Stalker Knowledge Base

## Introduction
This document provides a detailed technical guide for developers on how to interface with Stalker middleware servers. It covers authentication, data retrieval, credential verification, and common API interactions used in the `IPTV-MAC-STALKER-PLAYER`.

## 1. Stalker Portal Protocol
Stalker middleware typically exposes a JSON-based API at `/stalker_portal/server/load.php`. Most requests use `GET` with query parameters.

### Common Parameters
-   `type`: The resource type (e.g., `stb`, `itv`, `vod`, `series`).
-   `action`: The operation to perform (e.g., `handshake`, `get_profile`, `get_genres`, `create_link`).
-   `JsHttpRequest`: Usually set to `1-xml`.
-   `mac`: The device's MAC address (e.g., `00:1A:79:XX:XX:XX`).
-   `token`: An authorization token obtained during handshake.

### Headers & Cookies
-   **User-Agent**: Must emulate a MAG set-top box (e.g., `Mozilla/5.0 (QtEmbedded; U; Linux; C) ... MAG200 ...`).
-   **Cookie**: Essential cookies are `mac`, `stb_lang`, `timezone`. Once authenticated, `token` is also required.
-   **Authorization**: Bearer token header is often required (`Authorization: Bearer <token>`).

---

## 2. Authentication Flow

### Step 1: Handshake
The initial step to establish a session and get a token.

**Endpoint:**
`GET /stalker_portal/server/load.php?type=stb&action=handshake&token=&JsHttpRequest=1-xml`

**Response:**
Returns a JSON object with a `token` and optionally a `random` seed.
```json
{
  "js": {
    "token": "Cbwd...",
    "random": "..."
  }
}
```

### Step 2: Get Profile
Fetches device settings and user account details. This confirms the handshake was successful.

**Endpoint:**
`GET /stalker_portal/server/load.php?type=stb&action=get_profile&...` (requires many parameters like `sn`, `device_id`, `device_id2`, `signature`, etc.)

**Key Data Returned:**
-   `id`: User ID.
-   `name`: User name.
-   `account_balance`: Current balance.
-   `expiration_date`: Subscription expiry.

### Step 3: Get Account Info
Fetches detailed account information like expiration date and max connections.

**Endpoint:**
`GET /stalker_portal/server/load.php?type=account_info&action=get_main_info`

---

## 3. Data Retrieval

### Fetching Categories
-   **Live TV:** `type=itv&action=get_genres`
-   **VOD (Movies):** `type=vod&action=get_categories`
-   **Series:** `type=series&action=get_categories`

### Fetching Content (Pagination)
-   **Channels:** `type=itv&action=get_ordered_list&genre=<category_id>&p=<page_number>`
-   **Movies:** `type=vod&action=get_ordered_list&category=<category_id>&p=<page_number>`
-   **Series:** `type=series&action=get_ordered_list&category=<category_id>&p=<page_number>`

**Pagination Note:** Stalker typically returns pagination metadata in the `js` object:
```json
{
  "js": {
    "total_items": "1234",
    "data": [ ... ]
  }
}
```
You calculate total pages as `ceil(total_items / len(data))`.

### Series: Season & Episode Structure
Unlike VOD, Series involve a deeper hierarchy.
1.  **Get Series:** `action=get_ordered_list&type=series` (returns items with `is_series=1`).
2.  **Get Seasons:** `action=get_ordered_list&type=vod&movie_id=<series_id>&season_id=0`.
    *   Look for items where `item_type="season"`.
3.  **Get Episodes:** `action=get_ordered_list&type=vod&movie_id=<series_id>&season_id=<season_id>`.
    *   Look for items where `item_type="episode"`.

### Fetching Stream Links
To play a stream, you must request a temporary link.

-   **Live TV:** `type=itv&action=create_link&cmd=<channel_cmd>`
-   **VOD:** `type=vod&action=create_link&cmd=<movie_cmd>`
-   **Series Episode:** `type=vod&action=create_link&cmd=<episode_cmd>&series=<episode_number>`

**Response:**
```json
{
  "js": {
    "cmd": "http://stream.server.com:8080/..."
  }
}
```
*Note: The returned `cmd` often contains the direct stream URL. Sometimes it is prefixed with `ffmpeg `.*

---

## 4. Credential Verification & Expiration

To verify if an account is active and check its expiration:

1.  **Check Token Validity:**
    -   Store the `token` timestamp.
    -   If `(current_time - token_timestamp) > 3600` (1 hour), refresh the token via `handshake()`.

2.  **Check Account Expiration:**
    -   Call `get_account_info()` or `get_profile()`.
    -   Look for fields like `expire_date`, `expiration_date`, or `expire_billing_date`.
    -   If the date is in the past or `0`, the account may be expired or trial ended.

---

## 5. Code Examples (Python)

### Handshake & Token Generation
```python
def handshake(self):
    url = f"{self.portal_url}/stalker_portal/server/load.php?type=stb&action=handshake&token=&JsHttpRequest=1-xml"
    headers = self.generate_headers(include_auth=False)
    response = self.session.get(url, headers=headers)
    data = response.json()
    self.token = data['js']['token']
```

### Checking Expiration
```python
def check_expiry(self):
    info = self.get_account_info()
    expire_date = info.get('expire_date')
    print(f"Account expires on: {expire_date}")
```

### Fetching Live Channels
```python
def get_channels(self, genre_id):
    url = f"{self.portal_url}/stalker_portal/server/load.php"
    params = {
        "type": "itv",
        "action": "get_ordered_list",
        "genre": genre_id,
        "JsHttpRequest": "1-xml",
        "p": 1
    }
    response = self.session.get(url, params=params, headers=self.generate_headers(include_auth=True))
    return response.json()['js']['data']
```

### Creating a Stream Link
```python
def get_stream_url(self, cmd):
    url = f"{self.portal_url}/stalker_portal/server/load.php"
    params = {
        "type": "itv",
        "action": "create_link",
        "cmd": cmd,
        "JsHttpRequest": "1-xml"
    }
    response = self.session.get(url, params=params, headers=self.generate_headers(include_auth=True))
    data = response.json()
    stream_url = data['js']['cmd']
    # Remove 'ffmpeg ' prefix if present
    if stream_url.startswith('ffmpeg '):
        stream_url = stream_url[7:]
    return stream_url
```

### Series Handling
```python
def get_episodes(self, series_id, season_id):
    # Retrieve episodes for a specific season
    url = f"{self.portal_url}/stalker_portal/server/load.php"
    params = {
        "type": "vod",
        "action": "get_ordered_list",
        "movie_id": series_id,
        "season_id": season_id,
        "episode_id": 0,
        "JsHttpRequest": "1-xml",
        "p": 1
    }
    response = self.session.get(url, params=params, headers=self.generate_headers(include_auth=True))
    return response.json()['js']['data']
```
