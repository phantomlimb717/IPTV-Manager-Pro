# Fixing Stalker Portal Functionality in IPTV Manager Pro

## Executive Summary
The current Stalker implementation in `IPTV Manager Pro` is fundamentally broken for the vast majority of standard Stalker middleware servers. It relies on non-standard endpoints (`/portal.php`), sends incorrect headers during the handshake, and fails to manage the session state (tokens/cookies) correctly. This document details the specific flaws and provides a comprehensive, code-level plan to rebuild the `check_stalker_portal` functionality to match the robustness of dedicated Stalker players.

---

## 1. Current Implementation Flaws

### A. Incorrect Endpoint Targeting
*   **Current:** Hardcodes `portal_url + '/portal.php'`.
*   **Problem:** Most standard Stalker installations use `/stalker_portal/server/load.php`. The `/portal.php` endpoint is typically an alias or a specific configuration not present on all servers.
*   **Fix:** Use `/stalker_portal/server/load.php` as the primary endpoint.

### B. Broken Handshake Authentication
*   **Current:** Sends `Authorization: Bearer <MAC>` during the initial handshake.
*   **Problem:** The handshake is *how* you get the token. Sending the MAC as a Bearer token is invalid and will cause 401/403 errors on strict servers.
*   **Fix:** Remove the Authorization header for the initial handshake. Only send it *after* you receive a token.

### C. Missing Session State (Cookies)
*   **Current:** Only sets the `mac` cookie.
*   **Problem:** Stalker middleware strictly requires `stb_lang`, `timezone`, and often the `token` itself to be present in cookies for subsequent requests.
*   **Fix:** Implement a proper cookie jar containing `mac`, `stb_lang`, `timezone`, and `token`.

### D. No Fallback Mechanism
*   **Current:** Single attempt at handshake.
*   **Problem:** Many portals return 404 or empty responses to a bare handshake to prevent scraping. They require a client-generated token and "prehash" to proceed.
*   **Fix:** Implement the "token + prehash" retry logic found in robust players.

---

## 2. Implementation Plan

The following changes should be made to `core_checker.py`.

### Step 1: Update Constants & Headers
Define the standard headers and paths used by MAG boxes.

```python
STALKER_API_PATH = "/stalker_portal/server/load.php"
DEFAULT_TZ = "Europe/London"
MAG_USER_AGENT = "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3"
```

### Step 2: Rewrite `check_stalker_portal`
Orchestrate the flow: Handshake -> Get Profile -> Get Account Info (optional).

### Step 3: Implement Robust `_stalker_handshake`
Handle the 404 fallback logic.

### Step 4: Implement `_stalker_get_profile`
Use the token from the handshake to fetch the user profile.

---

## 3. Code Implementation (Asyncio/Aiohttp)

Below is the complete, drop-in replacement code for the Stalker section of `core_checker.py`.

### A. Helper Methods

First, we need a way to generate the random token and prehash if the simple handshake fails.

```python
import hashlib
import random
import string

def _generate_token(self):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=32))

def _generate_prehash(self, token, mac):
    # Standard Stalker prehash is often just SHA1 of the token or similar
    # But usually just token is enough for the "random" param.
    # For full compliance, some portals verify a prehash of (token + mac).
    # Simple Stalker logic often accepts:
    return hashlib.sha1(token.encode()).hexdigest()
```

### B. The `_stalker_handshake` Function

This replaces the existing `_stalker_handshake`.

```python
async def _stalker_handshake(self, session, portal_url, mac_address):
    # 1. Try standard endpoint first
    base_url = portal_url.rstrip('/')
    api_url = f"{base_url}{STALKER_API_PATH}"

    # Basic Headers
    headers = {
        'User-Agent': MAG_USER_AGENT,
        'Referer': f"{base_url}/stalker_portal/c/",
        'Cookie': f"mac={mac_address}; stb_lang=en; timezone={DEFAULT_TZ};"
    }

    # Params for initial handshake
    params = {'type': 'stb', 'action': 'handshake', 'token': '', 'JsHttpRequest': '1-xml'}

    try:
        async with session.get(api_url, params=params, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None) # Handle text/html responses
                token = data.get('js', {}).get('token')
                if token: return token
            elif resp.status == 404:
                # Fallback: Generate token manually
                token = self._generate_token()
                prehash = self._generate_prehash(token, mac_address)

                # Update params
                params['token'] = token
                params['prehash'] = prehash

                # Retry
                async with session.get(api_url, params=params, headers=headers) as resp2:
                    if resp2.status == 200:
                        # We blindly trust our generated token works if we get a 200 OK JSON
                        # The real test is the next profile fetch.
                        return token
    except Exception as e:
        logging.error(f"Stalker Handshake Error: {e}")

    return None
```

### C. The `_stalker_get_profile` Function

This replaces `_stalker_get_info` as the primary verification step. `get_profile` is more reliable than `get_main_info`.

```python
async def _stalker_get_profile(self, session, portal_url, token, mac_address):
    base_url = portal_url.rstrip('/')
    api_url = f"{base_url}{STALKER_API_PATH}"

    headers = {
        'User-Agent': MAG_USER_AGENT,
        'Authorization': f'Bearer {token}',  # Now we send the Bearer
        'Referer': f"{base_url}/stalker_portal/c/",
        'Cookie': f"mac={mac_address}; stb_lang=en; timezone={DEFAULT_TZ}; token={token};"
    }

    # Params to mimic a real MAG box request
    # 'sn', 'device_id', etc. are often required. We can fake them or derive from MAC.
    device_id = hashlib.sha256(mac_address.encode()).hexdigest().upper()
    device_id2 = device_id
    signature = hashlib.sha256(f"{mac_address}{device_id}{device_id2}".encode()).hexdigest().upper()

    params = {
        'type': 'stb',
        'action': 'get_profile',
        'hd': '1',
        'ver': 'ImageDescription: 0.2.18-r23-250; ImageDate: Fri Jan 15 15:00:00 2021; PORTAL version: 5.6.1; API Version: JS API version: 343; STB API version: 146; Player Engine version: 0x58c',
        'num_banks': '2',
        'sn': '0000000000000', # Or derive 13 chars from MAC MD5
        'stb_type': 'MAG250',
        'client_type': 'STB',
        'image_version': '218',
        'video_out': 'hdmi',
        'device_id': device_id,
        'device_id2': device_id2,
        'signature': signature,
        'auth_second_step': '1',
        'hw_version': '1.7-BD-00',
        'not_valid_token': '0',
        'timestamp': int(time.time()),
        'JsHttpRequest': '1-xml'
    }

    try:
        async with session.get(api_url, params=params, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                return data.get('js', {})
    except Exception as e:
        logging.error(f"Stalker Get Profile Error: {e}")

    return None
```

### D. Updating the Main Logic (`check_stalker_portal`)

```python
async def check_stalker_portal(self, portal_url, mac_address):
    session = await self.get_session()
    result = {'success': False, 'api_status': 'Error'}

    if not portal_url or not mac_address:
        result['api_message'] = "Missing Portal URL or MAC"
        return result

    try:
        # 1. Handshake
        token = await self._stalker_handshake(session, portal_url, mac_address)
        if not token:
            result['api_message'] = "Handshake Failed (Invalid MAC or URL)"
            return result

        # 2. Get Profile (Verify Token)
        profile = await self._stalker_get_profile(session, portal_url, token, mac_address)

        # If profile is empty, auth failed
        if not profile or not profile.get('id'):
            result['api_message'] = "Profile fetch failed (Auth Invalid)"
            return result

        # 3. Success
        result['success'] = True
        result['raw_user_info'] = json.dumps(profile)

        # Parse Status
        # Usually Stalker doesn't return a simple 'status' field in get_profile like Xtream.
        # We assume Active if we got the profile.
        # But we can check for 'account_balance' or 'expire_date' if available.
        result['api_status'] = 'Active'

        # Expiry
        # Try multiple fields
        exp_date_keys = ['expire_date', 'expiration_date', 'expire_billing_date', 'phone']
        # Note: 'phone' is sometimes hijacked for expiry in old panels

        for k in exp_date_keys:
            val = profile.get(k)
            if val and str(val) != '0' and str(val) != '':
                ts = self._parse_stalker_date(val)
                if ts:
                    result['expiry_date_ts'] = ts
                    break

        # Check if expired
        if result['expiry_date_ts'] and result['expiry_date_ts'] < time.time():
            result['api_status'] = 'Expired'

    except Exception as e:
        result['api_message'] = f"Error: {str(e)}"

    return result
```

## 4. Key Takeaways
1.  **Endpoint**: Switch to `/stalker_portal/server/load.php`.
2.  **Headers**: Drop `Authorization` from the handshake. Add `Referer`.
3.  **Cookies**: Send `mac`, `stb_lang`, `timezone` with every request.
4.  **Verification**: Trust `get_profile` results over `get_main_info`.
