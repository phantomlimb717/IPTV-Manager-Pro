#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import sqlite3
import json
import logging
import time
import re # Added for MAC address validation
from typing import Optional # Added for type hinting
# import html # Not currently used
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

# --- Dependency Check & Imports ---
try:
    import zoneinfo
except ImportError:
    print("Error: 'zoneinfo' module required (Python 3.9+). Please upgrade Python or install 'backports.zoneinfo'.", file=sys.stderr)
    sys.exit(1)

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("\nError: Required library 'requests' not found. Please install it: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTableView, QPushButton, QDialog, QLineEdit, QComboBox,
        QFormLayout, QMessageBox, QDialogButtonBox, QLabel,
        QListWidget, QListWidgetItem, QInputDialog, QMenu,
        QAbstractItemView, QHeaderView, QStatusBar, QProgressBar,
        QFileDialog, QTreeWidget, QTreeWidgetItem
    )
    from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QAction, QIcon, QKeySequence, QGuiApplication
    from PySide6.QtCore import (
        Qt, Slot, Signal, QObject, QThread, QModelIndex, QSortFilterProxyModel,
        QDateTime, QTimer
    )
except ImportError:
    print("\nError: Required library 'PySide6' not found. Please install it: pip install PySide6", file=sys.stderr)
    sys.exit(1)

from companion_utils import MediaPlayerManager

# --- Resource Path Helper for PyInstaller ---
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# --- Configuration ---
APP_NAME = "IPTV Manager Pro"
APP_VERSION = "0.3" # Incremented version for new features
DATABASE_NAME = 'iptv_store.db'
LOG_FILE = 'iptv_manager_log.txt'
USER_AGENT = f'{APP_NAME}/{APP_VERSION} (okhttp/3.12.1)'
API_TIMEOUT = (5, 10) # (connect, read) seconds
REQUEST_DELAY_BETWEEN_CHECKS = 0.2
SETTINGS_FILE = "settings.json"

REPORT_DISPLAY_TIMEZONE = "America/Los_Angeles" # Example
try:
    DISPLAY_TZ = zoneinfo.ZoneInfo(REPORT_DISPLAY_TIMEZONE)
except zoneinfo.ZoneInfoNotFoundError:
    DISPLAY_TZ = timezone.utc

# --- Setup Logging ---
logging.basicConfig(
    level=logging.DEBUG, # Keep DEBUG for now
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    filename=LOG_FILE,
    filemode='w'
)
console_handler = logging.StreamHandler(sys.stderr)
console_handler.setLevel(logging.WARNING)
formatter = logging.Formatter('%(levelname)s: %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger('').addHandler(console_handler)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# =============================================================================
# DATABASE UTILITIES
# =============================================================================
def get_db_connection():
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    logging.info(f"Initializing database: {DATABASE_NAME}")
    conn = None
    try:
        if not os.path.exists(DATABASE_NAME):
            logging.info(f"Database not found. Creating '{DATABASE_NAME}'...")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'Uncategorized',
                server_base_url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                last_checked_at TEXT,
                api_status TEXT,
                api_message TEXT,
                expiry_date_ts INTEGER,
                is_trial INTEGER,
                active_connections INTEGER,
                max_connections INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                raw_user_info TEXT,
                raw_server_info TEXT,
                account_type TEXT DEFAULT 'xc',
                mac_address TEXT,
                portal_url TEXT
            )
        ''')
        # Add new columns if they don't exist (for existing databases)
        try:
            cursor.execute("SELECT account_type FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'account_type' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN account_type TEXT DEFAULT 'xc'")
        try:
            cursor.execute("SELECT mac_address FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'mac_address' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN mac_address TEXT")
        try:
            cursor.execute("SELECT portal_url FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'portal_url' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN portal_url TEXT")

        # Add columns for category counts
        try:
            cursor.execute("SELECT live_streams_count FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'live_streams_count' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN live_streams_count INTEGER")
        try:
            cursor.execute("SELECT movies_count FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'movies_count' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN movies_count INTEGER")
        try:
            cursor.execute("SELECT series_count FROM entries LIMIT 1")
        except sqlite3.OperationalError:
            logging.info("Adding 'series_count' column to entries table.")
            cursor.execute("ALTER TABLE entries ADD COLUMN series_count INTEGER")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            )
        ''')
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES ('Uncategorized')")
        conn.commit()
        logging.info("Database initialized/verified successfully.")
        return True
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")
        print(f"CRITICAL: Database initialization error: {e}", file=sys.stderr)
        return False
    finally:
        if conn: conn.close()

def add_entry(name, category, server_url, username, password, account_type='xc', mac_address=None, portal_url=None):
    conn = get_db_connection()
    try:
        cursor = conn.execute('''
            INSERT INTO entries (name, category, server_base_url, username, password, account_type, mac_address, portal_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (name, category, server_url, username, password, account_type, mac_address, portal_url))
        conn.commit()
        entry_id = cursor.lastrowid
        logging.info(f"Added entry: {name} (ID: {entry_id}, Type: {account_type})")
        return entry_id
    finally: conn.close()

def update_entry(entry_id, name, category, server_url, username, password, account_type='xc', mac_address=None, portal_url=None):
    conn = get_db_connection()
    try:
        conn.execute('''
            UPDATE entries
            SET name = ?, category = ?, server_base_url = ?, username = ?, password = ?,
                account_type = ?, mac_address = ?, portal_url = ?
            WHERE id = ?
        ''', (name, category, server_url, username, password, account_type, mac_address, portal_url, entry_id))
        conn.commit()
        logging.info(f"Updated entry ID: {entry_id} (Type: {account_type})")
    finally: conn.close()

def update_entry_category(entry_id, category):
    conn = get_db_connection()
    try:
        conn.execute("UPDATE entries SET category = ? WHERE id = ?", (category, entry_id))
        conn.commit()
        logging.info(f"Updated category for entry ID: {entry_id} to {category}")
    finally:
        conn.close()

def delete_entry(entry_id):
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.commit()
        logging.info(f"Deleted entry ID: {entry_id}")
    finally: conn.close()

def get_all_entries(category_filter=None):
    conn = get_db_connection()
    try:
        query = "SELECT * FROM entries"
        params = []
        if category_filter and category_filter != "All Categories":
            query += " WHERE category = ?"
            params.append(category_filter)
        query += " ORDER BY name COLLATE NOCASE ASC"
        entries = conn.execute(query, params).fetchall()
        return entries
    finally: conn.close()

def get_entry_by_id(entry_id):
    conn = get_db_connection()
    try:
        entry = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return entry
    finally: conn.close()

def update_entry_status(entry_id, status_data):
    conn = get_db_connection()
    try:
        current_time_iso = datetime.now(timezone.utc).isoformat()
        conn.execute('''
            UPDATE entries
            SET last_checked_at = ?, api_status = ?, api_message = ?,
                expiry_date_ts = ?, is_trial = ?, active_connections = ?,
                max_connections = ?, raw_user_info = ?, raw_server_info = ?,
                live_streams_count = ?, movies_count = ?, series_count = ?
            WHERE id = ?
        ''', (
            current_time_iso, status_data.get('api_status'), status_data.get('api_message'),
            status_data.get('expiry_date_ts'), status_data.get('is_trial'),
            status_data.get('active_connections'), status_data.get('max_connections'),
            status_data.get('raw_user_info'), status_data.get('raw_server_info'),
            status_data.get('live_streams_count'), status_data.get('movies_count'),
            status_data.get('series_count'), entry_id
        ))
        conn.commit()
        logging.info(f"Updated status for entry ID: {entry_id} to {status_data.get('api_status')}")
    except Exception as e: logging.error(f"Failed to update status for entry ID {entry_id}: {e}")
    finally: conn.close()

def get_all_categories():
    conn = get_db_connection()
    try:
        categories = conn.execute("SELECT name FROM categories ORDER BY name COLLATE NOCASE ASC").fetchall()
        return [cat['name'] for cat in categories]
    finally: conn.close()

def add_category(name):
    conn = get_db_connection()
    try:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
        conn.commit()
        logging.info(f"Added category: {name}")
    except sqlite3.IntegrityError: logging.warning(f"Category '{name}' already exists.")
    finally: conn.close()

def rename_category(old_name, new_name):
    conn = get_db_connection()
    try:
        existing = conn.execute("SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND LOWER(name) != LOWER(?)", (new_name, old_name)).fetchone()
        if existing:
            raise sqlite3.IntegrityError(f"Category '{new_name}' already exists.")
        conn.execute("UPDATE categories SET name = ? WHERE name = ?", (new_name, old_name))
        conn.execute("UPDATE entries SET category = ? WHERE category = ?", (new_name, old_name))
        conn.commit()
        logging.info(f"Renamed category '{old_name}' to '{new_name}'.")
    finally: conn.close()

def delete_category_and_reassign_entries(name):
    conn = get_db_connection()
    try:
        if name.lower() == "uncategorized": return False
        conn.execute("UPDATE entries SET category = 'Uncategorized' WHERE category = ?", (name,))
        conn.execute("DELETE FROM categories WHERE name = ?", (name,))
        conn.commit()
        logging.info(f"Deleted category '{name}' and reassigned entries.")
        return True
    except Exception as e:
        logging.error(f"Error deleting category {name}: {e}")
        return False
    finally: conn.close()

# =============================================================================
# URL PARSING UTILITY
# =============================================================================
def parse_get_php_url(url_string):
    details = {'error': None, 'server_base_url': None, 'username': None, 'password': ""}
    try:
        parsed_url = urlparse(url_string)
        query_params = parse_qs(parsed_url.query)
        scheme = parsed_url.scheme; hostname = parsed_url.hostname; port = parsed_url.port
        username = query_params.get('username', [None])[0]
        password_list = query_params.get('password', [""]); password = password_list[0] if password_list else ""
        if not all([scheme, hostname, username is not None]):
            details['error'] = "Invalid URL: Missing scheme, host, or username parameter."
            logging.warning(f"URL Parse Error: {details['error']} for URL: {url_string}")
            return details
        server_base_url = f"{scheme}://{hostname}"
        if port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443)):
            server_base_url += f":{port}"
        details['server_base_url'] = server_base_url; details['username'] = username; details['password'] = password
        logging.info(f"Parsed URL: {server_base_url}, User: {username}")
        return details
    except Exception as e:
        logging.error(f"Critical failure to parse URL '{url_string}': {e}")
        details['error'] = f"Critical parsing error: {e}"; return details

# =============================================================================
# API UTILITIES
# =============================================================================
API_HEADERS = {'User-Agent': USER_AGENT}
def get_safe_api_value(data_dict, key, default=None):
    if not isinstance(data_dict, dict): return default
    value = data_dict.get(key); return default if value == "" else value

def format_timestamp_display(unix_timestamp_utc):
    if unix_timestamp_utc is None or not isinstance(unix_timestamp_utc, (int, float)) or unix_timestamp_utc <= 0: return "N/A"
    try:
        dt_utc = datetime.fromtimestamp(int(unix_timestamp_utc), tz=timezone.utc); dt_local = dt_utc.astimezone(DISPLAY_TZ)
        return dt_local.strftime('%Y-%m-%d %H:%M %Z')
    except: return "Invalid"

def format_trial_status_display(is_trial):
    if is_trial is None: return "N/A"
    return "Yes" if str(is_trial) == '1' else "No"

def get_stream_counts(server_base_url, username, password, session):
    counts = {'live': None, 'movie': None, 'series': None}
    action_map = {'live': 'get_live_streams', 'movie': 'get_vod_streams', 'series': 'get_series'}
    for cat_type, action in action_map.items():
        api_url = f"{server_base_url.rstrip('/')}/player_api.php?username={username}&password={password}&action={action}"
        try:
            response = session.get(api_url, timeout=API_TIMEOUT, headers=API_HEADERS)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                counts[cat_type] = len(data)
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            logging.warning(f"Could not fetch {cat_type} streams: {e}")
    return counts

def check_account_status_detailed_api(server_base_url, username, password, session):
    processed_data = {
        'success': False, 'api_status': None, 'api_message': "Check init error",
        'expiry_date_ts': None, 'is_trial': None, 'active_connections': None,
        'max_connections': None, 'raw_user_info': None, 'raw_server_info': None,
        'live_streams_count': None, 'movies_count': None, 'series_count': None
    }
    # Session should be initialized before this is called in a loop.
    if not all([server_base_url, username is not None, session]):
        processed_data['api_message'] = "Internal Error: Missing parameters for API call"
        return processed_data

    try:
        parsed_base = urlparse(server_base_url)
        if not parsed_base.scheme or not parsed_base.netloc:
            raise ValueError("Invalid server_base_url format")
        api_url = f"{server_base_url.rstrip('/')}/player_api.php?username={username}&password={password}&action=get_user_info"
    except Exception as url_e:
        processed_data['api_message'] = f"Invalid Server URL: {url_e}"
        return processed_data

    logging.info(f"API Check: {parsed_base.scheme}://{parsed_base.netloc}/... (User: {username})")
    response_text = None
    try:
        response = session.get(api_url, timeout=API_TIMEOUT, headers=API_HEADERS)
        response_text = response.text
        response.raise_for_status()
        data = response.json()

        processed_data['raw_user_info'] = json.dumps(data.get('user_info')) if data.get('user_info') is not None else None
        processed_data['raw_server_info'] = json.dumps(data.get('server_info')) if data.get('server_info') is not None else None
        user_info = data.get('user_info', {})

        if not isinstance(user_info, dict):
            processed_data['api_message'] = "Invalid 'user_info' format"
            processed_data['success'] = False
            return processed_data

        auth_status = get_safe_api_value(user_info, 'auth')
        if auth_status == 0 or str(auth_status) == '0':
            processed_data['api_message'] = "Authentication Failed (auth: 0)"
            processed_data['api_status'] = "Auth Failed"
            processed_data['success'] = False
            return processed_data

        current_api_msg = ""
        if 'status' not in user_info:
            if not user_info:
                current_api_msg = "'user_info' object empty and missing 'status'"
            else:
                current_api_msg = "'user_info' missing 'status' field"
            processed_data['api_status'] = 'Unknown'

        processed_data['success'] = True
        api_status_val = get_safe_api_value(user_info, 'status')
        if api_status_val is not None:
             processed_data['api_status'] = api_status_val

        user_info_message = get_safe_api_value(user_info, 'message', '')
        if user_info_message:
             processed_data['api_message'] = f"{current_api_msg} {user_info_message}".strip() if current_api_msg else user_info_message
        elif current_api_msg:
             processed_data['api_message'] = current_api_msg
        else:
             processed_data['api_message'] = ''

        exp_date_raw = get_safe_api_value(user_info, 'exp_date')
        if exp_date_raw is not None:
            try:
                exp_ts = int(exp_date_raw)
                processed_data['expiry_date_ts'] = exp_ts if exp_ts > 0 else None
            except (ValueError, TypeError):
                logging.warning(f"API Check {username}: Invalid exp_date format '{exp_date_raw}'")
                pass

        is_trial_raw = get_safe_api_value(user_info, 'is_trial')
        if is_trial_raw is not None:
            try:
                processed_data['is_trial'] = int(is_trial_raw)
            except (ValueError, TypeError):
                logging.warning(f"API Check {username}: Invalid is_trial format '{is_trial_raw}'")
                pass

        active_c_raw = get_safe_api_value(user_info, 'active_cons')
        if active_c_raw is not None:
            try:
                processed_data['active_connections'] = int(active_c_raw)
            except (ValueError, TypeError):
                logging.warning(f"API Check {username}: Invalid active_cons format '{active_c_raw}'")
                pass

        max_c_raw = get_safe_api_value(user_info, 'max_connections')
        if max_c_raw is not None:
            try:
                processed_data['max_connections'] = int(max_c_raw)
            except (ValueError, TypeError):
                logging.warning(f"API Check {username}: Invalid max_connections format '{max_c_raw}'")
                pass

        if processed_data['success'] and processed_data['api_status'] in [None, 'Unknown'] and not processed_data['api_message']:
            processed_data['api_message'] = "Valid connection but key data missing from API."

        if processed_data['success']:
            stream_counts = get_stream_counts(server_base_url, username, password, session)
            processed_data['live_streams_count'] = stream_counts.get('live')
            processed_data['movies_count'] = stream_counts.get('movie')
            processed_data['series_count'] = stream_counts.get('series')

        return processed_data

    except requests.exceptions.Timeout:
        processed_data['api_message'] = f"Request Timeout ({API_TIMEOUT}s)"
    except requests.exceptions.HTTPError as e:
        processed_data['api_message'] = f"HTTP Error {e.response.status_code}"
        if response_text and ('raw_user_info' not in processed_data or not processed_data['raw_user_info']):
             processed_data['raw_user_info'] = json.dumps({"error_context_response": response_text[:500]})
    except requests.exceptions.RequestException as e:
        processed_data['api_message'] = f"Connection Error: {type(e).__name__}"
    except json.JSONDecodeError:
        processed_data['api_message'] = "Invalid JSON response"
        if response_text and ('raw_user_info' not in processed_data or not processed_data['raw_user_info']):
             processed_data['raw_user_info'] = json.dumps({"non_json_response": response_text[:500]})
    except Exception as e:
        processed_data['api_message'] = f"Unexpected API Error: {type(e).__name__}"
        logging.exception(f"Unexpected error during API check for {username}.")

    processed_data['success'] = False
    return processed_data

# --- Stalker Portal API Functions ---
STALKER_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
STALKER_COMMON_HEADERS = {
    'User-Agent': STALKER_USER_AGENT,
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest',
}

def _get_stalker_token(session: requests.Session, portal_url: str, mac_address: str) -> Optional[str]:
    """Performs handshake and retrieves token for Stalker Portal."""
    handshake_url = f"{portal_url.rstrip('/')}/portal.php?action=handshake&type=stb&token=&JsHttpRequest=1-xml"
    headers = {**STALKER_COMMON_HEADERS, 'Authorization': f"MAC {mac_address}"}
    # Stalker portals often expect the MAC as a cookie as well.
    # maclist.py seems to use the MAC with colons directly.
    session.cookies.update({"mac": mac_address})
    session.headers.update({'Referer': f"{portal_url.rstrip('/')}/c/"})

    logging.info(f"Stalker: Attempting handshake with {portal_url} for MAC {mac_address} (Cookie MAC: {mac_address})")
    try:
        response = session.get(handshake_url, headers=headers, timeout=API_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        token = data.get("js", {}).get("token")
        if token:
            logging.info(f"Stalker: Handshake successful, token received for MAC {mac_address}")
            return token
        else:
            logging.warning(f"Stalker: Handshake response did not contain token for MAC {mac_address}. Response: {response.text[:200]}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Stalker: Handshake request exception for MAC {mac_address} to {portal_url}: {e}")
    except json.JSONDecodeError as e:
        logging.error(f"Stalker: Handshake JSON decode error for MAC {mac_address} to {portal_url}: {e}. Response: {response.text[:200] if 'response' in locals() else 'N/A'}")
    except KeyError as e:
        logging.error(f"Stalker: Handshake Key error (likely missing 'js' or 'token') for MAC {mac_address}: {e}. Response: {response.text[:200] if 'response' in locals() else 'N/A'}")
    return None

def check_stalker_portal_status(portal_url: str, mac_address: str, session: requests.Session):
    processed_data = {
        'success': False, 'api_status': "Error", 'api_message': "Check init error (Stalker)",
        'expiry_date_ts': None, 'is_trial': None, 'active_connections': None, # Stalker might not provide these
        'max_connections': None, 'raw_user_info': None, 'raw_server_info': None # server_info not typical for Stalker
    }

    if not all([portal_url, mac_address, session]):
        processed_data['api_message'] = "Internal Error: Missing parameters for Stalker API call"
        return processed_data

    # Ensure MAC address is in the common format for headers/cookies if needed
    formatted_mac = mac_address.upper() # For Authorization header
    # cookie_mac = mac_address.replace(":", "").lower() # Example for cookie, if portal expects it specifically

    token = _get_stalker_token(session, portal_url, formatted_mac)

    if not token:
        processed_data['api_message'] = "Stalker Handshake Failed: Could not get token."
        # Log already done in _get_stalker_token
        return processed_data

    account_info_url = f"{portal_url.rstrip('/')}/portal.php?type=account_info&action=get_main_info&JsHttpRequest=1-xml"
    headers = {**STALKER_COMMON_HEADERS, 'Authorization': f"Bearer {token}"}
    # Referer is typically set on the session already by _get_stalker_token

    logging.info(f"Stalker: Getting account info from {portal_url} for MAC {formatted_mac}")
    response_text = None
    try:
        response = session.get(account_info_url, headers=headers, timeout=API_TIMEOUT)
        response_text = response.text
        response.raise_for_status()
        data = response.json()
        user_info = data.get("js", {})

        processed_data['raw_user_info'] = json.dumps(user_info)

        if not isinstance(user_info, dict):
            processed_data['api_message'] = "Invalid 'user_info' format (Stalker)"
            processed_data['success'] = False
            return processed_data

        # Stalker portals use various fields for status and expiry.
        # Common ones include 'status', 'exp_date' (unix timestamp or string), or sometimes in 'data' sub-object.
        # The `maclist.py` example used `phone` for expiry, which is unusual. Let's be flexible.

        # Infer status:
        # A common pattern is status=1 means active, status=0 or 2 might mean inactive/expired.
        # If 'status' field exists and is 0 or 2, it's likely not active.
        # If 'exp_date' is in the past, it's expired.

        api_status_val = user_info.get('status')
        if api_status_val is not None:
            api_status_str = str(api_status_val).lower()
            if api_status_str == '1':
                processed_data['api_status'] = "Active"
            elif api_status_str == '0' or api_status_str == '2':
                 processed_data['api_status'] = "Inactive/Disabled" # More specific than just "Expired"
            else:
                processed_data['api_status'] = f"Status: {api_status_val}"
        else:
            # If no explicit status, we'll rely on expiry date or assume active if expiry is future/valid.
            processed_data['api_status'] = "Info Retrieved" # Placeholder, will be updated by expiry logic

        # Expiry Date Handling:
        # Stalker portals can have 'exp_date' as a unix timestamp or a string 'YYYY-MM-DD HH:MM:SS' or 'DD.MM.YYYY'.
        # The example `maclist.py` used 'phone' for expiry.
        exp_date_raw = user_info.get('exp_date') # Primary target
        if exp_date_raw is None:
            exp_date_raw = user_info.get('expire_date') # Secondary common target

        source_of_date = "exp_date/expire_date"

        if exp_date_raw is None and 'phone' in user_info: # Check 'phone' only if others failed
            exp_date_raw = user_info.get('phone')
            source_of_date = "phone"
            logging.info(f"Stalker: Trying to parse expiry from 'phone' field for MAC {formatted_mac}: '{exp_date_raw}'")


        if exp_date_raw is not None:
            try:
                # Attempt to parse as Unix timestamp first
                exp_ts = int(float(exp_date_raw))
                if exp_ts > 0:
                    processed_data['expiry_date_ts'] = exp_ts
                    logging.info(f"Stalker: Parsed expiry for MAC {formatted_mac} as UNIX timestamp: {exp_ts} from '{source_of_date}' field.")
            except (ValueError, TypeError):
                # Attempt to parse as string date
                if isinstance(exp_date_raw, str):
                    dt_obj = None
                    parsed_format_msg = ""
                    try:
                        # Try "Month Day, Year, HH:MM am/pm" format (e.g., "August 17, 2025, 12:00 am")
                        dt_obj = datetime.strptime(exp_date_raw, '%B %d, %Y, %I:%M %p')
                        parsed_format_msg = "%B %d, %Y, %I:%M %p"
                    except ValueError:
                        try:
                            # Try "YYYY-MM-DD HH:MM:SS"
                            dt_obj = datetime.strptime(exp_date_raw, '%Y-%m-%d %H:%M:%S')
                            parsed_format_msg = "%Y-%m-%d %H:%M:%S"
                        except ValueError:
                            try:
                                # Try "DD.MM.YYYY"
                                dt_obj = datetime.strptime(exp_date_raw, '%d.%m.%Y')
                                parsed_format_msg = "%d.%m.%Y"
                            except ValueError:
                                # Add more formats if needed
                                pass # dt_obj remains None

                    if dt_obj:
                        # Assume parsed naive datetime is in UTC as server times often are.
                        # If it were local, timezone conversion would be needed if TZ known.
                        processed_data['expiry_date_ts'] = int(dt_obj.replace(tzinfo=timezone.utc).timestamp())
                        logging.info(f"Stalker: Parsed expiry for MAC {formatted_mac} from string '{exp_date_raw}' (format '{parsed_format_msg}') to TS: {processed_data['expiry_date_ts']} from '{source_of_date}' field.")
                        if source_of_date == "phone" and (not processed_data['api_message'] or processed_data['api_message'] == "Check init error (Stalker)"):
                             processed_data['api_message'] = f"Expiry from 'phone': {exp_date_raw}"

                    else:
                        logging.warning(f"Stalker: Unparseable string exp_date '{exp_date_raw}' for MAC {formatted_mac} from '{source_of_date}'.")
                        if not processed_data['api_message'] or processed_data['api_message'] == "Check init error (Stalker)" or "format unknown" not in processed_data['api_message'] :
                             processed_data['api_message'] = f"Expiry date format unknown: {str(exp_date_raw)[:30]}"
                else:
                    logging.warning(f"Stalker: Invalid (non-string, non-numeric) exp_date format '{exp_date_raw}' for MAC {formatted_mac} from '{source_of_date}'.")

        # Update status based on expiry
        if processed_data['expiry_date_ts'] is not None:
            if processed_data['expiry_date_ts'] < datetime.now(timezone.utc).timestamp():
                processed_data['api_status'] = "Expired"
            elif processed_data['api_status'] == "Info Retrieved": # Only if not explicitly inactive
                 processed_data['api_status'] = "Active"
        elif processed_data['api_status'] == "Info Retrieved": # No expiry, no explicit status
            processed_data['api_status'] = "Unknown" # Or "Active (No Expiry)"

        # Stalker portals usually don't provide trial, active_cons, max_cons in get_main_info
        # These will remain None unless specific portals are found to provide them.
        # is_trial, active_connections, max_connections remain as their defaults (None)

        processed_data['success'] = True
        if not processed_data.get('api_message') or processed_data['api_message'] == "Check init error (Stalker)":
            processed_data['api_message'] = user_info.get('message', "Status successfully retrieved.") # Some portals might have a message field
        if not processed_data['api_message'] and processed_data['success']:
             processed_data['api_message'] = "OK"


        return processed_data

    except requests.exceptions.Timeout:
        processed_data['api_message'] = f"Request Timeout ({API_TIMEOUT}s) (Stalker)"
        logging.warning(f"Stalker: Timeout for MAC {formatted_mac} at {portal_url}")
    except requests.exceptions.HTTPError as e:
        processed_data['api_message'] = f"HTTP Error {e.response.status_code} (Stalker)"
        if response_text: processed_data['raw_user_info'] = json.dumps({"error_context_response": response_text[:500]})
        logging.warning(f"Stalker: HTTP Error {e.response.status_code} for MAC {formatted_mac} at {portal_url}. Response: {response_text[:200] if response_text else 'N/A'}")
    except requests.exceptions.RequestException as e:
        processed_data['api_message'] = f"Connection Error (Stalker): {type(e).__name__}"
        logging.warning(f"Stalker: Connection Error for MAC {formatted_mac} at {portal_url}: {e}")
    except json.JSONDecodeError:
        processed_data['api_message'] = "Invalid JSON response (Stalker)"
        if response_text: processed_data['raw_user_info'] = json.dumps({"non_json_response": response_text[:500]})
        logging.warning(f"Stalker: JSON Decode Error for MAC {formatted_mac} at {portal_url}. Response: {response_text[:200] if response_text else 'N/A'}")
    except Exception as e:
        processed_data['api_message'] = f"Unexpected API Error (Stalker): {type(e).__name__}"
        logging.exception(f"Stalker: Unexpected error during API check for MAC {formatted_mac} at {portal_url}.")

    processed_data['success'] = False
    return processed_data


# =============================================================================
# DIALOGS
# =============================================================================
class EntryDialog(QDialog):
    def __init__(self, entry_id=None, parent=None):
        super().__init__(parent); self.entry_id = entry_id; self.is_edit_mode = entry_id is not None
        self.setWindowTitle(f"{'Edit' if self.is_edit_mode else 'Add'} IPTV Entry"); self.setMinimumWidth(450); self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self); form_layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.populate_categories()

        self.account_type_combo = QComboBox()
        self.account_type_combo.addItems(["Xtream Codes API", "Stalker Portal"])
        self.account_type_combo.currentTextChanged.connect(self.toggle_input_fields)

        # XC API Fields
        self.server_url_label = QLabel("Server URL (e.g., http://domain:port):")
        self.server_url_edit = QLineEdit()
        self.username_label = QLabel("Username:")
        self.username_edit = QLineEdit()
        self.password_label = QLabel("Password:")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        # Stalker Portal Fields
        self.portal_url_label = QLabel("Portal URL (e.g., http://domain:port/c/):")
        self.portal_url_edit = QLineEdit()
        self.mac_address_label = QLabel("MAC Address (XX:XX:XX:XX:XX:XX):")
        self.mac_address_edit = QLineEdit()

        form_layout.addRow("Display Name:", self.name_edit)
        form_layout.addRow("Category:", self.category_combo)
        form_layout.addRow("Account Type:", self.account_type_combo)

        # Add XC fields (will be shown/hidden)
        form_layout.addRow(self.server_url_label, self.server_url_edit)
        form_layout.addRow(self.username_label, self.username_edit)
        form_layout.addRow(self.password_label, self.password_edit)

        # Add Stalker fields (will be shown/hidden)
        form_layout.addRow(self.portal_url_label, self.portal_url_edit)
        form_layout.addRow(self.mac_address_label, self.mac_address_edit)

        layout.addLayout(form_layout)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept_dialog)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        if self.is_edit_mode:
            self.load_entry_data()
        else:
            self.toggle_input_fields(self.account_type_combo.currentText()) # Initial field visibility

        self.name_edit.setFocus()

    def toggle_input_fields(self, account_type_text):
        is_stalker = account_type_text == "Stalker Portal"

        # XC Fields
        self.server_url_label.setVisible(not is_stalker)
        self.server_url_edit.setVisible(not is_stalker)
        self.username_label.setVisible(not is_stalker)
        self.username_edit.setVisible(not is_stalker)
        self.password_label.setVisible(not is_stalker)
        self.password_edit.setVisible(not is_stalker)

        # Stalker Fields
        self.portal_url_label.setVisible(is_stalker)
        self.portal_url_edit.setVisible(is_stalker)
        self.mac_address_label.setVisible(is_stalker)
        self.mac_address_edit.setVisible(is_stalker)

    def populate_categories(self):
        self.category_combo.clear();
        try: cats = get_all_categories(); self.category_combo.addItems(cats if cats else ["Uncategorized"])
        except Exception as e: logging.error(f"Failed to populate categories: {e}"); self.category_combo.addItem("Uncategorized")

    def load_entry_data(self):
        try:
            entry = get_entry_by_id(self.entry_id)
            if entry:
                self.name_edit.setText(entry['name'])
                # entry is an sqlite3.Row object.
                current_account_type = entry['account_type'] if entry['account_type'] is not None else 'xc'
                type_display_name = "Stalker Portal" if current_account_type == 'stalker' else "Xtream Codes API"
                self.account_type_combo.setCurrentText(type_display_name)
                self.toggle_input_fields(type_display_name) # Ensure fields are visible before setting text

                if current_account_type == 'stalker':
                    self.portal_url_edit.setText(entry['portal_url'] or "")
                    self.mac_address_edit.setText(entry['mac_address'] or "")
                    # Clear XC fields if they had data from a previous type
                    self.server_url_edit.setText("")
                    self.username_edit.setText("")
                    self.password_edit.setText("")
                else: # 'xc' or default
                    self.server_url_edit.setText(entry['server_base_url'])
                    self.username_edit.setText(entry['username'])
                    self.password_edit.setText(entry['password'])
                    # Clear Stalker fields
                    self.portal_url_edit.setText("")
                    self.mac_address_edit.setText("")

                idx = self.category_combo.findText(entry['category'])
                if idx != -1: self.category_combo.setCurrentIndex(idx)
                else: self.category_combo.addItem(entry['category']); self.category_combo.setCurrentText(entry['category'])
            else: QMessageBox.warning(self, "Error", "Could not load entry data."); self.reject()
        except Exception as e: logging.error(f"Error loading entry ID {self.entry_id}: {e}"); QMessageBox.critical(self, "Load Error", f"Failed to load: {e}"); self.reject()

    def get_data(self):
        data = {
            "name": self.name_edit.text().strip(),
            "category": self.category_combo.currentText(),
            "account_type_text": self.account_type_combo.currentText()
        }
        if data["account_type_text"] == "Stalker Portal":
            data["account_type"] = "stalker"
            data["portal_url"] = self.portal_url_edit.text().strip()
            data["mac_address"] = self.mac_address_edit.text().strip().upper()
            # For Stalker, server_base_url might be derived from portal_url or set to portal_url itself
            # Let's use portal_url for server_base_url for now, can be refined.
            # Username/password are not used for Stalker in this context
            parsed_portal = urlparse(data["portal_url"])
            data["server_url"] = f"{parsed_portal.scheme}://{parsed_portal.netloc}" if parsed_portal.scheme and parsed_portal.netloc else data["portal_url"]
            data["username"] = "" # Not applicable
            data["password"] = "" # Not applicable
        else: # Xtream Codes API
            data["account_type"] = "xc"
            data["server_url"] = self.server_url_edit.text().strip()
            data["username"] = self.username_edit.text().strip()
            data["password"] = self.password_edit.text()
            data["portal_url"] = None
            data["mac_address"] = None
        return data

    @Slot()
    def accept_dialog(self):
        data = self.get_data()

        # Common validation
        if not data['name']:
            QMessageBox.warning(self, "Input Error", "Display Name must be filled.")
            return

        if data['account_type'] == 'xc':
            if not all([data['server_url'], data['username'] is not None]): # Password can be empty
                QMessageBox.warning(self, "Input Error", "For Xtream Codes API, Name, Server URL, and Username must be filled.")
                return
            if not (data['server_url'].startswith("http://") or data['server_url'].startswith("https://")):
                QMessageBox.warning(self, "Input Error", "Server URL must start with http:// or https://.")
                return
        elif data['account_type'] == 'stalker':
            if not all([data['portal_url'], data['mac_address']]):
                QMessageBox.warning(self, "Input Error", "For Stalker Portal, Portal URL and MAC Address must be filled.")
                return
            if not (data['portal_url'].startswith("http://") or data['portal_url'].startswith("https://")):
                QMessageBox.warning(self, "Input Error", "Portal URL must start with http:// or https://.")
                return

            mac_pattern = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
            if not mac_pattern.match(data['mac_address']):
                 QMessageBox.warning(self, "Input Error", "MAC Address must be in the format XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX.")
                 return

        try:
            if self.is_edit_mode:
                update_entry(self.entry_id, data['name'], data['category'],
                             data['server_url'], data['username'], data['password'],
                             data['account_type'], data['mac_address'], data['portal_url'])
            else:
                add_entry(data['name'], data['category'],
                          data['server_url'], data['username'], data['password'],
                          data['account_type'], data['mac_address'], data['portal_url'])
            self.accept()
        except Exception as e: logging.error(f"Error saving entry: {e}"); QMessageBox.critical(self, "Database Error", f"Could not save: {e}")

class ManageCategoriesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Manage Categories"); self.setMinimumWidth(350); self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self); self.category_list_widget = QListWidget(); self.category_list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.category_list_widget); button_layout = QHBoxLayout()
        self.add_button = QPushButton("Add"); self.rename_button = QPushButton("Rename"); self.delete_button = QPushButton("Delete")
        button_layout.addWidget(self.add_button); button_layout.addWidget(self.rename_button); button_layout.addWidget(self.delete_button); layout.addLayout(button_layout)
        self.close_button = QPushButton("Close"); layout.addWidget(self.close_button, alignment=Qt.AlignRight)
        self.add_button.clicked.connect(self.add_category_action); self.rename_button.clicked.connect(self.rename_category_action)
        self.delete_button.clicked.connect(self.delete_category_action); self.close_button.clicked.connect(self.accept)
        self.refresh_categories_list(); self.category_list_widget.itemSelectionChanged.connect(self.update_button_states); self.update_button_states()
    def refresh_categories_list(self):
        self.category_list_widget.clear()
        try:
            for cat_name in get_all_categories():
                item = QListWidgetItem(cat_name)
                if cat_name.lower() == "uncategorized": item.setFlags(item.flags() & ~(Qt.ItemIsSelectable | Qt.ItemIsEditable)); item.setForeground(QColor("gray"))
                self.category_list_widget.addItem(item)
        except Exception as e: logging.error(f"Failed to refresh categories in dialog: {e}")
        self.update_button_states()
    def update_button_states(self):
        sel = self.category_list_widget.currentItem(); is_sel = sel is not None; is_uncat = is_sel and sel.text().lower() == "uncategorized"
        self.rename_button.setEnabled(is_sel and not is_uncat); self.delete_button.setEnabled(is_sel and not is_uncat)

    @Slot()
    def add_category_action(self): # CORRECTED METHOD
        new_name, ok = QInputDialog.getText(self, "Add Category", "Enter new category name:")
        if ok and new_name.strip():
            try:
                add_category(new_name.strip())
                self.refresh_categories_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not add category: {e}")
        elif ok and not new_name.strip():
            QMessageBox.warning(self, "Input Error", "Category name cannot be empty.")

    @Slot()
    def rename_category_action(self):
        sel = self.category_list_widget.currentItem()
        if not sel or sel.text().lower() == "uncategorized": return
        old_name = sel.text(); new_name, ok = QInputDialog.getText(self, "Rename Category", f"New name for '{old_name}':", text=old_name)
        if ok and new_name.strip() and new_name.strip().lower() != old_name.lower():
            try: rename_category(old_name, new_name.strip()); self.refresh_categories_list();
            except sqlite3.IntegrityError as e: QMessageBox.warning(self, "Rename Error", str(e))
            except Exception as e: QMessageBox.critical(self, "Error", f"Could not rename: {e}")
        elif ok and not new_name.strip(): QMessageBox.warning(self, "Input Error", "Name cannot be empty.")
    @Slot()
    def delete_category_action(self):
        sel = self.category_list_widget.currentItem();
        if not sel or sel.text().lower() == "uncategorized": return
        name_del = sel.text(); reply = QMessageBox.question(self, "Confirm Delete", f"Delete category '{name_del}'?\nEntries will move to 'Uncategorized'.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if delete_category_and_reassign_entries(name_del): self.refresh_categories_list()
            else: QMessageBox.warning(self, "Delete Error", f"Could not delete '{name_del}'.")

class ImportUrlDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Import Entry from URL"); self.setMinimumWidth(500); self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self); form_layout = QFormLayout(); self.url_edit = QLineEdit(); self.url_edit.setPlaceholderText("http://server:port/get.php?username=...")
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("Optional: Auto-generated if blank"); self.category_combo = QComboBox(); self.populate_categories()
        form_layout.addRow("M3U Get Link URL:", self.url_edit); form_layout.addRow("Display Name (Optional):", self.name_edit); form_layout.addRow("Category:", self.category_combo)
        layout.addLayout(form_layout); self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept_dialog); self.button_box.rejected.connect(self.reject); layout.addWidget(self.button_box); self.url_edit.setFocus()

    def populate_categories(self):
        self.category_combo.clear()
        try:
            cats = get_all_categories(); self.category_combo.addItems(cats if cats else ["Uncategorized"]); uncat_idx = self.category_combo.findText("Uncategorized")
            if uncat_idx != -1: self.category_combo.setCurrentIndex(uncat_idx)
        except Exception as e: logging.error(f"ImportUrlDialog: Failed to populate categories: {e}"); self.category_combo.addItem("Uncategorized")

    def get_data(self): return {"url": self.url_edit.text().strip(), "name": self.name_edit.text().strip(), "category": self.category_combo.currentText()}

    @Slot()
    def accept_dialog(self):
        data = self.get_data()
        if not data['url']:
            QMessageBox.warning(self, "Input Error", "M3U Get Link URL must be provided.")
            return

        parsed = parse_get_php_url(data['url'])
        if not parsed or parsed.get('error'):
            err_msg = parsed.get('error', "Unknown error during parsing") if parsed else "Failed to parse URL (parser returned None)"
            QMessageBox.critical(self, "URL Parse Error", f"Could not parse URL: {err_msg}")
            return

        display_name = data['name']
        if not display_name:
            try:
                host = urlparse(parsed['server_base_url']).hostname or "host"
                display_name = f"{host}_{parsed['username']}"
            except Exception as e:
                logging.warning(
                    f"Error auto-generating display name for URL '{data['url']}': {e}. "
                    f"Details - Parsed server: '{parsed.get('server_base_url', 'N/A')}', "
                    f"Parsed user: '{parsed.get('username', 'N/A')}'. Using fallback name."
                )
                username_for_fallback = str(parsed.get('username', ''))
                display_name = f"Imported_{username_for_fallback}"

        try:
            add_entry(display_name, data['category'], parsed['server_base_url'], parsed['username'], parsed['password'])
            QMessageBox.information(self, "Success", f"Entry '{display_name}' imported.")
            self.accept()
        except Exception as e:
            logging.error(f"Error adding imported entry: {e}")
            QMessageBox.critical(self, "Database Error", f"Could not save imported entry: {e}")

class BatchImportOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setWindowTitle("Batch Import Options"); self.setWindowModality(Qt.WindowModal)
        layout = QVBoxLayout(self); form_layout = QFormLayout(); self.category_combo = QComboBox(); self.populate_categories()
        form_layout.addRow("Assign to Category:", self.category_combo); layout.addLayout(form_layout); self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept); self.button_box.rejected.connect(self.reject); layout.addWidget(self.button_box)
    def populate_categories(self):
        self.category_combo.clear()
        try:
            cats = get_all_categories(); self.category_combo.addItems(cats if cats else ["Uncategorized"]); uncat_idx = self.category_combo.findText("Uncategorized")
            if uncat_idx != -1: self.category_combo.setCurrentIndex(uncat_idx)
        except Exception as e: logging.error(f"BatchImportOptionsDialog: Failed to populate categories: {e}"); self.category_combo.addItem("Uncategorized")
    def get_selected_category(self): return self.category_combo.currentText()

class BulkEditCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Bulk Edit Category")
        self.setMinimumWidth(350)
        self.setWindowModality(Qt.WindowModal)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.category_combo = QComboBox()
        self.populate_categories()

        form_layout.addRow("Assign to Category:", self.category_combo)
        layout.addLayout(form_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def populate_categories(self):
        self.category_combo.clear()
        try:
            cats = get_all_categories()
            self.category_combo.addItems(cats if cats else ["Uncategorized"])
            uncat_idx = self.category_combo.findText("Uncategorized")
            if uncat_idx != -1:
                self.category_combo.setCurrentIndex(uncat_idx)
        except Exception as e:
            logging.error(f"BulkEditCategoryDialog: Failed to populate categories: {e}")
            self.category_combo.addItem("Uncategorized")

    def get_selected_category(self):
        return self.category_combo.currentText()


class CategoryLoaderWorker(QObject):
    data_ready = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, entry_data):
        super().__init__()
        self.entry_data = entry_data
        self._session = None

    @Slot()
    def run(self):
        category_data = {'live': [], 'movie': [], 'series': []}
        try:
            self._session = requests.Session()
            # Note: Xtream Codes API uses 'get_vod_categories' for movies.
            action_map = {'live': 'get_live_categories', 'movie': 'get_vod_categories', 'series': 'get_series_categories'}

            server_url = self.entry_data['server_base_url']
            username = self.entry_data['username']
            password = self.entry_data['password']

            for cat_type, action in action_map.items():
                try:
                    api_url = f"{server_url.rstrip('/')}/player_api.php?username={username}&password={password}&action={action}"
                    response = self._session.get(api_url, timeout=API_TIMEOUT, headers=API_HEADERS)
                    response.raise_for_status()
                    data = response.json()
                    if isinstance(data, list):
                        category_data[cat_type] = data
                except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
                    logging.warning(f"Could not fetch categories for type '{cat_type}': {e}")

            self.data_ready.emit(category_data)

        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred while loading categories: {e}")
        finally:
            if self._session:
                self._session.close()
            self.finished.emit()

class StreamLoaderWorker(QObject):
    data_ready = Signal(list)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, entry_data, category_id, stream_type):
        super().__init__()
        self.entry_data = entry_data
        self.category_id = category_id
        self.stream_type = stream_type # 'live', 'movie', or 'series'
        self._session = None

    @Slot()
    def run(self):
        try:
            self._session = requests.Session()
            action_map = {
                'live': 'get_live_streams',
                'movie': 'get_vod_streams',
                'series': 'get_series'
            }
            action = action_map.get(self.stream_type)
            if not action:
                raise ValueError(f"Invalid stream type: {self.stream_type}")

            server_url = self.entry_data['server_base_url']
            username = self.entry_data['username']
            password = self.entry_data['password']

            api_url = f"{server_url.rstrip('/')}/player_api.php?username={username}&password={password}&action={action}"
            if self.category_id != '*':
                api_url += f"&category_id={self.category_id}"
            response = self._session.get(api_url, timeout=API_TIMEOUT, headers=API_HEADERS)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                self.data_ready.emit(data)
            else:
                self.error_occurred.emit(f"Unexpected data returned for streams: {str(data)[:200]}")

        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Network Error fetching streams: {e}")
        except json.JSONDecodeError:
            self.error_occurred.emit("API returned invalid JSON for streams.")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred loading streams: {e}")
        finally:
            if self._session:
                self._session.close()
            self.finished.emit()

class SeriesInfoWorker(QObject):
    data_ready = Signal(dict)
    error_occurred = Signal(str)
    finished = Signal()

    def __init__(self, entry_data, series_id):
        super().__init__()
        self.entry_data = entry_data
        self.series_id = series_id
        self._session = None

    @Slot()
    def run(self):
        try:
            self._session = requests.Session()
            server_url = self.entry_data['server_base_url']
            username = self.entry_data['username']
            password = self.entry_data['password']

            api_url = f"{server_url.rstrip('/')}/player_api.php?username={username}&password={password}&action=get_series_info&series_id={self.series_id}"
            response = self._session.get(api_url, timeout=API_TIMEOUT, headers=API_HEADERS)
            response.raise_for_status()
            data = response.json()
            self.data_ready.emit(data)

        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Network Error: {e}")
        except json.JSONDecodeError:
            self.error_occurred.emit("API returned invalid JSON for series info.")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred: {e}")
        finally:
            if self._session:
                self._session.close()
            self.finished.emit()

class PlaylistBrowserDialog(QDialog):
    def __init__(self, entry_data, parent=None):
        super().__init__(parent)
        self.entry_data = entry_data
        self.media_player_manager = MediaPlayerManager()
        self.category_data = {} # Renamed from playlist_data
        self.category_worker_thread = None
        self.stream_worker_thread = None
        self.series_info_thread = None
        self.original_window_title = f"Playlist for {self.entry_data['name']}"

        self.setWindowTitle(self.original_window_title)
        self.setMinimumSize(800, 600)
        self.setWindowModality(Qt.WindowModal)

        # UI Elements
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.stream_table = QTableView()
        self.search_bar = QLineEdit()
        self.play_button = QPushButton("Play Selected")
        self.status_label = QLabel("Loading categories...")

        # Models for the table
        self.stream_model = QStandardItemModel(0, 2) # Name, Stream ID (hidden)
        self.stream_model.setHorizontalHeaderLabels(["Name", "Stream ID"])
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.stream_model)
        self.proxy_model.setFilterKeyColumn(0)
        self.stream_table.setModel(self.proxy_model)
        self.stream_table.setSortingEnabled(True)
        self.stream_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.stream_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.stream_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.stream_table.setColumnHidden(1, True)


        self.setup_ui()
        self.setup_connections()
        self.load_playlist_data()

    def setup_ui(self):
        self.main_layout = QHBoxLayout(self)

        self.left_widget = QWidget()
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.addWidget(QLabel("Categories"))
        left_layout.addWidget(self.category_tree)

        right_layout = QVBoxLayout()
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        search_layout.addWidget(self.search_bar)
        right_layout.addLayout(search_layout)
        right_layout.addWidget(self.stream_table)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.play_button)
        right_layout.addLayout(bottom_layout)

        self.main_layout.addWidget(self.left_widget, 1)
        self.main_layout.addLayout(right_layout, 3)

    def setup_connections(self):
        self.search_bar.textChanged.connect(self.proxy_model.setFilterRegularExpression)
        self.category_tree.itemClicked.connect(self.on_category_clicked)
        self.play_button.clicked.connect(self.on_play_clicked)
        self.stream_table.doubleClicked.connect(self.on_play_clicked)

    def load_playlist_data(self):
        # This is now for loading categories
        self.category_worker = CategoryLoaderWorker(self.entry_data)
        self.category_worker_thread = QThread()
        self.category_worker.moveToThread(self.category_worker_thread)
        self.category_worker_thread.started.connect(self.category_worker.run)
        self.category_worker.data_ready.connect(self.on_categories_ready)
        self.category_worker.error_occurred.connect(self.on_load_error)
        self.category_worker.finished.connect(self.category_worker_thread.quit)
        self.category_worker.finished.connect(self.category_worker.deleteLater)
        self.category_worker_thread.finished.connect(self.category_worker_thread.deleteLater)
        self.category_worker_thread.start()

    @Slot(dict)
    def on_categories_ready(self, data):
        self.category_data = data
        self.category_tree.clear()

        type_map = {'live': "Live TV", 'movie': "Movies", 'series': "Series"}

        for cat_type, categories in self.category_data.items():
            if categories:
                top_level_item = QTreeWidgetItem([type_map[cat_type]])
                self.category_tree.addTopLevelItem(top_level_item)

                # Add "All" sub-category
                all_child_item = QTreeWidgetItem(["All"])
                all_child_item.setData(0, Qt.UserRole, {'type': cat_type, 'id': '*'})
                top_level_item.addChild(all_child_item)

                for category in categories:
                    child_item = QTreeWidgetItem([category['category_name']])
                    child_item.setData(0, Qt.UserRole, {'type': cat_type, 'id': category['category_id']})
                    top_level_item.addChild(child_item)

        self.category_tree.expandAll()
        self.status_label.setText("Ready. Select a category.")
        self.category_worker_thread.quit()

    @Slot(str)
    def on_load_error(self, error_message):
        QMessageBox.critical(self, "Error Loading Playlist", error_message)
        self.status_label.setText(f"Error: {error_message}")
        if self.category_worker_thread and self.category_worker_thread.isRunning():
            self.category_worker_thread.quit()
        if self.stream_worker_thread and self.stream_worker_thread.isRunning():
            self.stream_worker_thread.quit()
        if self.series_info_thread and self.series_info_thread.isRunning():
            self.series_info_thread.quit()

    @Slot(QTreeWidgetItem, int)
    def on_category_clicked(self, item, column):
        if self.windowTitle() != self.original_window_title:
            self.setWindowTitle(self.original_window_title)

        category_info = item.data(0, Qt.UserRole)
        cat_id = None
        stream_type = None

        if category_info: # It's a sub-category item
            cat_id = category_info.get('id', '*') # Use '*' for 'All'
            stream_type = category_info.get('type')
        elif not item.parent(): # It's a top-level item
            top_level_text = item.text(0)
            if top_level_text == "Live TV":
                stream_type = 'live'
            elif top_level_text == "Movies":
                stream_type = 'movie'
            elif top_level_text == "Series":
                stream_type = 'series'
            cat_id = '*' # Signal to load all streams

        if not stream_type:
            return

        self.status_label.setText(f"Loading {item.text(0)}...")
        self.stream_model.removeRows(0, self.stream_model.rowCount())

        # Start the stream loader worker
        self.stream_worker = StreamLoaderWorker(self.entry_data, cat_id, stream_type)
        self.stream_worker_thread = QThread()
        self.stream_worker.moveToThread(self.stream_worker_thread)
        self.stream_worker_thread.started.connect(self.stream_worker.run)
        self.stream_worker.data_ready.connect(self.on_streams_ready)
        self.stream_worker.error_occurred.connect(self.on_load_error)
        self.stream_worker.finished.connect(self.stream_worker_thread.quit)
        self.stream_worker.finished.connect(self.stream_worker.deleteLater)
        self.stream_worker_thread.finished.connect(self.stream_worker_thread.deleteLater)
        self.stream_worker_thread.start()

    @Slot(list)
    def on_streams_ready(self, streams):
        self.stream_model.removeRows(0, self.stream_model.rowCount())
        for stream in streams:
            name = stream.get('name', 'No Name')
            stream_id = str(stream.get('stream_id'))

            # For VOD, name might be None, but title might exist
            if not name and 'title' in stream:
                name = stream.get('title')

            name_item = QStandardItem(name)
            id_item = QStandardItem(stream_id)
            self.stream_model.appendRow([name_item, id_item])

        self.status_label.setText(f"Loaded {len(streams)} items.")
        self.stream_worker_thread.quit()

    def on_play_clicked(self):
        selected_indexes = self.stream_table.selectionModel().selectedRows()
        if not selected_indexes:
            return

        source_index = self.proxy_model.mapToSource(selected_indexes[0])
        stream_id = self.stream_model.item(source_index.row(), 1).text()

        # Check if we are in an episode view by checking the window title,
        # which is changed when series info is loaded.
        if self.windowTitle() != self.original_window_title:
            self.play_episode(stream_id)
            return

        # If not in episode view, determine type from category tree
        current_item = self.category_tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "No Category Selected", "Please select a category from the list before playing.")
            return

        # Determine the top-level category (Live TV, Movies, Series)
        parent = current_item.parent()
        if parent:
            top_level_category_name = parent.text(0)
        else:
            top_level_category_name = current_item.text(0)

        if top_level_category_name == 'Series':
            self.fetch_series_episodes(stream_id)
        elif top_level_category_name == 'Movies':
            self.play_vod_or_live(stream_id, 'Movies') # Pass 'Movies' to play_vod_or_live
        elif top_level_category_name == 'Live TV':
            self.play_vod_or_live(stream_id, 'Live TV') # Pass 'Live TV' for play_vod_or_live
        else:
            QMessageBox.warning(self, "Error", f"Could not determine stream type for category '{top_level_category_name}'.")

    def play_vod_or_live(self, stream_id, category):
        server = self.entry_data['server_base_url']
        username = self.entry_data['username']
        password = self.entry_data['password']
        stream_type = 'movie' if category == 'Movies' else 'live'
        extension = ".mp4" if category == 'Movies' else ".ts"
        stream_url = f"{server}/{stream_type}/{username}/{password}/{stream_id}{extension}"
        self.media_player_manager.play_stream(stream_url, self, referer_url=server)

    def play_episode(self, stream_id):
        server = self.entry_data['server_base_url']
        username = self.entry_data['username']
        password = self.entry_data['password']
        stream_url = f"{server}/series/{username}/{password}/{stream_id}.mp4"
        self.media_player_manager.play_stream(stream_url, self, referer_url=server)

    def fetch_series_episodes(self, series_id):
        self.status_label.setText(f"Fetching episodes for series ID: {series_id}...")
        self.series_worker = SeriesInfoWorker(self.entry_data, series_id)
        self.series_info_thread = QThread()
        self.series_worker.moveToThread(self.series_info_thread)
        self.series_info_thread.started.connect(self.series_worker.run)
        self.series_worker.data_ready.connect(self.on_series_info_ready)
        self.series_worker.error_occurred.connect(self.on_load_error)
        self.series_worker.finished.connect(self.series_info_thread.quit)
        self.series_worker.finished.connect(self.series_worker.deleteLater)
        self.series_info_thread.finished.connect(self.series_info_thread.deleteLater)
        self.series_info_thread.start()

    @Slot(dict)
    def on_series_info_ready(self, data):
        self.stream_model.removeRows(0, self.stream_model.rowCount())
        series_name = data.get('info', {}).get('name', 'Series')
        self.setWindowTitle(f"Episodes for: {series_name}")

        episodes = data.get('episodes', {})
        # Assuming episodes is a dict of seasons
        for season_num, season_episodes in episodes.items():
            for episode in season_episodes:
                title = episode.get('title', 'No Title')
                episode_id = str(episode.get('id'))
                # You might want to add season/episode number to title
                display_title = f"S{episode.get('season')} E{episode.get('episode_num')} - {title}"
                name_item = QStandardItem(display_title)
                id_item = QStandardItem(episode_id)
                self.stream_model.appendRow([name_item, id_item])

        # self.category_list.hide() # QTreeWidget is used now
        # self.back_button.show() # Back button is removed
        self.status_label.setText(f"Loaded {self.stream_model.rowCount()} episodes.")
        self.series_info_thread.quit()

    def closeEvent(self, event):
        if self.category_worker_thread and self.category_worker_thread.isRunning():
            self.category_worker_thread.quit()
            self.category_worker_thread.wait()
        if self.stream_worker_thread and self.stream_worker_thread.isRunning():
            self.stream_worker_thread.quit()
            self.stream_worker_thread.wait()
        if self.series_info_thread and self.series_info_thread.isRunning():
            self.series_info_thread.quit()
            self.series_info_thread.wait()
        super().closeEvent(event)


# =============================================================================
# API CHECKER WORKER
# =============================================================================
class ApiCheckerWorker(QObject):
    result_ready = Signal(int, dict)
    status_message_updated = Signal(str)
    progress_updated = Signal(int, int)
    batch_finished = Signal()
    session_initialized_signal = Signal() # Signal that session is ready

    def __init__(self):
        super().__init__()
        self._session = None
        self._is_running = True

    @Slot()
    def initialize_session(self):
        if not self._session:
            try:
                logging.info("API Worker: Initializing session with retries...")
                self._session = requests.Session()
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS"]
                )
                adapter = HTTPAdapter(max_retries=retry_strategy)
                self._session.mount("http://", adapter)
                self._session.mount("https://", adapter)
                logging.info("API Worker: Session initialized.")
                self.session_initialized_signal.emit()
            except Exception as e:
                logging.error(f"API Worker: Failed to initialize session: {e}")
                self.status_message_updated.emit("Error: Could not initialize network session.")
                self._is_running = False

    @Slot()
    def stop_processing(self):
        self._is_running = False
        logging.info("API Worker: Stop requested.")

    def run_checks(self, entry_ids_to_check):
        # Session initialization is now typically called before run_checks
        # or we wait for session_initialized_signal if initialize_session is called by thread.started
        if not self._session:
            # This case should ideally be handled by waiting for session_initialized_signal
            # if initialize_session() is called asynchronously.
            # For now, if called directly, ensure session is initialized.
            self.initialize_session()
            if not self._session: # If initialization failed
                self.batch_finished.emit() # End the batch if session is not up
                return

        self._is_running = True
        total = len(entry_ids_to_check)
        processed_count = 0
        logging.info(f"Worker checking {total} entries.")
        # Emit initial progress immediately AFTER session is confirmed to be ready.
        # If initialize_session is called by thread.started, this emit should be after session_initialized_signal is received.
        # For this direct call structure, it's okay here if initialize_session() is blocking and successful.
        self.progress_updated.emit(0, total)

        for i, entry_id in enumerate(entry_ids_to_check):
            if not self._is_running:
                self.progress_updated.emit(processed_count, total) # Emit final processed count
                self.status_message_updated.emit(f"API checking cancelled after {processed_count}/{total}.")
                logging.info("API check cancelled by flag.")
                break

            # This message is good.
            # self.status_message_updated.emit(f"Checking {i+1}/{total} (ID: {entry_id})...")
            try:
                entry_data = get_entry_by_id(entry_id)
                if not entry_data:
                    logging.warning(f"Worker: Entry ID {entry_id} not found.")
                    self.result_ready.emit(entry_id, {'success': False, 'api_message': "Entry not found in DB"})
                    processed_count += 1
                    self.progress_updated.emit(processed_count, total)
                    continue

                # entry_data is an sqlite3.Row object.
                account_type = entry_data['account_type'] if entry_data['account_type'] is not None else 'xc'
                api_result = None

                if account_type == 'stalker':
                    logging.info(f"Worker: Checking Stalker Portal entry ID {entry_id} (MAC: {entry_data['mac_address']})")
                    api_result = check_stalker_portal_status(
                        entry_data['portal_url'], # Use the specific portal_url field
                        entry_data['mac_address'],
                        self._session
                    )
                else: # 'xc' or other unknown types default to XC API check
                    if account_type != 'xc':
                        logging.warning(f"Worker: Unknown account type '{account_type}' for entry ID {entry_id}. Defaulting to XC API check.")
                    logging.info(f"Worker: Checking XC API entry ID {entry_id} (User: {entry_data['username']})")
                    api_result = check_account_status_detailed_api(
                        entry_data['server_base_url'],
                        entry_data['username'],
                        entry_data['password'],
                        self._session
                    )

                self.result_ready.emit(entry_id, api_result)
                processed_count += 1
                if REQUEST_DELAY_BETWEEN_CHECKS > 0:
                    # This sleep helps the main thread process UI updates for the progress bar
                    time.sleep(REQUEST_DELAY_BETWEEN_CHECKS)
            except Exception as e:
                logging.error(f"Worker: Error checking ID {entry_id}: {e}")
                self.result_ready.emit(entry_id, {'success': False, 'api_message': f"Worker Error: {e.__class__.__name__}"})
                processed_count += 1
            finally:
                # Update progress after each item attempt
                self.progress_updated.emit(processed_count, total)
                logging.debug(f"Worker progress: {processed_count}/{total}")


        if self._is_running:
            self.status_message_updated.emit(f"Finished checking {processed_count}/{total} entries.")

        self.batch_finished.emit()

    def cleanup_session(self):
        if self._session:
            self._session.close()
            self._session = None
            logging.info("API Worker: Session closed.")


# =============================================================================
# CUSTOM PROXY MODEL FOR FILTERING
# =============================================================================
COL_ID, COL_NAME, COL_CATEGORY, COL_STATUS, COL_CHANNELS, COL_MOVIES, COL_SERIES, COL_EXPIRY, COL_TRIAL, \
COL_ACTIVE_CONN, COL_MAX_CONN, COL_LAST_CHECKED, COL_SERVER, COL_USER, COL_MSG = range(15)

class EntryFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""
        self._exclude_na = False
        self._na_strings = {"N/A", "INVALID", "NOT CHECKED", "NEVER"}

    def set_search_text(self, text):
        self._search_text = text.lower()
        self.invalidateFilter()

    def set_exclude_na(self, exclude):
        self._exclude_na = exclude
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        search_match = True
        if self._search_text:
            search_match = False
            search_columns = [COL_NAME, COL_CATEGORY, COL_STATUS, COL_SERVER, COL_USER, COL_MSG]
            for col in search_columns:
                idx = self.sourceModel().index(source_row, col, source_parent)
                data = self.sourceModel().data(idx)
                if data and self._search_text in str(data).lower():
                    search_match = True
                    break
        if not search_match:
            return False

        if self._exclude_na:
            na_check_columns = [COL_EXPIRY, COL_TRIAL, COL_ACTIVE_CONN, COL_MAX_CONN, COL_LAST_CHECKED, COL_STATUS]
            for col in na_check_columns:
                idx = self.sourceModel().index(source_row, col, source_parent)
                data_str = str(self.sourceModel().data(idx)).upper()
                if data_str in self._na_strings:
                    return False
        return True

# =============================================================================
# MAIN APPLICATION WINDOW
# =============================================================================
COLUMN_HEADERS = ["ID", "Name", "Category", "API Status", "Channels", "Movies", "Series", "Expires", "Trial?", "Active", "Max", "Last Checked", "Server", "User / MAC", "Message"]

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setGeometry(100, 100, 1280, 720)
        self.current_category_filter = "All Categories"
        self.api_worker = None
        self.api_thread = None
        self._is_checking_api = False
        self.setup_ui()
        self.load_entries_to_table()
        self.update_category_filter_combo()
        self.update_action_button_states()
        self.load_settings() # Load settings on startup
        # *** MODIFIED LINE ***
        # Use the resource_path helper to find the icon, both in development and in the PyInstaller bundle.
        self.setWindowIcon(QIcon(resource_path("icon.icns" if sys.platform == "darwin" else "icon.ico")))

    def setup_ui(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        import_url_action = QAction("Import from &URL...", self)
        import_url_action.triggered.connect(self.import_from_url_action)
        file_menu.addAction(import_url_action)
        import_file_action = QAction("Import from &File...", self)
        import_file_action.triggered.connect(self.import_from_file_action)
        file_menu.addAction(import_file_action)
        file_menu.addSeparator()
        export_clipboard_action = QAction("Copy Link for Current Entry", self)
        export_clipboard_action.triggered.connect(self.export_current_to_clipboard)
        file_menu.addAction(export_clipboard_action)
        export_txt_action = QAction("Export Links for Selected Entries...", self)
        export_txt_action.triggered.connect(self.export_selected_to_txt)
        file_menu.addAction(export_txt_action)
        file_menu.addSeparator()

        # Theme selection
        theme_menu = file_menu.addMenu("&Theme")
        self.light_theme_action = QAction("Light Mode", self, checkable=True)
        self.light_theme_action.triggered.connect(lambda: self.set_theme("light"))
        theme_menu.addAction(self.light_theme_action)
        self.dark_theme_action = QAction("Dark Mode", self, checkable=True)
        self.dark_theme_action.triggered.connect(lambda: self.set_theme("dark"))
        theme_menu.addAction(self.dark_theme_action)
        file_menu.addSeparator()

        exit_action = QAction("&Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)

        top_controls_layout = QHBoxLayout()
        self.add_button = QPushButton("Add Entry")
        self.edit_button = QPushButton("Edit Selected")
        self.delete_button = QPushButton("Delete Selected")
        self.delete_duplicates_button = QPushButton("Delete Duplicates")
        self.bulk_edit_button = QPushButton("Bulk Edit")
        self.import_url_button = QPushButton("Import URL")
        self.import_file_button = QPushButton("Import File")

        top_controls_layout.addWidget(self.add_button)
        top_controls_layout.addWidget(self.edit_button)
        top_controls_layout.addWidget(self.delete_button)
        top_controls_layout.addWidget(self.delete_duplicates_button)
        top_controls_layout.addWidget(self.bulk_edit_button)
        top_controls_layout.addSpacing(10)
        top_controls_layout.addWidget(self.import_url_button)
        top_controls_layout.addWidget(self.import_file_button)
        top_controls_layout.addStretch()
        main_layout.addLayout(top_controls_layout)

        export_buttons_layout = QHBoxLayout()
        self.export_clipboard_button = QPushButton("Copy Link (Current)")
        export_buttons_layout.addWidget(self.export_clipboard_button)
        self.export_txt_button = QPushButton("Export Links (Selected)")
        export_buttons_layout.addWidget(self.export_txt_button)
        export_buttons_layout.addStretch()
        top_controls_layout.addSpacing(20)
        top_controls_layout.addWidget(self.export_clipboard_button)
        top_controls_layout.addWidget(self.export_txt_button)

        secondary_controls_layout = QHBoxLayout()
        self.check_selected_button = QPushButton("Check Selected")
        self.check_all_button = QPushButton("Check All Visible")
        self.manage_categories_button = QPushButton("Categories...")
        secondary_controls_layout.addWidget(self.check_selected_button)
        secondary_controls_layout.addWidget(self.check_all_button)
        secondary_controls_layout.addStretch()
        secondary_controls_layout.addWidget(self.manage_categories_button)
        main_layout.addLayout(secondary_controls_layout)

        filter_controls_layout = QHBoxLayout()
        filter_controls_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to search...")
        filter_controls_layout.addWidget(self.search_edit)
        filter_controls_layout.addSpacing(10)
        filter_controls_layout.addWidget(QLabel("Category:"))
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.setMinimumWidth(150)
        filter_controls_layout.addWidget(self.category_filter_combo)
        self.exclude_na_button = QPushButton("Exclude N/A")
        self.exclude_na_button.setCheckable(True)
        filter_controls_layout.addWidget(self.exclude_na_button)
        filter_controls_layout.addStretch()
        main_layout.addLayout(filter_controls_layout)

        self.table_view = QTableView()
        self.table_model = QStandardItemModel(0, len(COLUMN_HEADERS))
        self.table_model.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.proxy_model = EntryFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.table_view.setModel(self.proxy_model)

        self.table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.setSortingEnabled(True)
        self.table_view.sortByColumn(COL_NAME, Qt.AscendingOrder)
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(COL_ID, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Interactive)
        self.table_view.setColumnWidth(COL_NAME, 200)
        header.setSectionResizeMode(COL_CATEGORY, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_CHANNELS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_MOVIES, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_SERIES, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_EXPIRY, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_TRIAL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_ACTIVE_CONN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_MAX_CONN, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_LAST_CHECKED, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_SERVER, QHeaderView.Interactive)
        self.table_view.setColumnWidth(COL_SERVER, 150)
        header.setSectionResizeMode(COL_USER, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_MSG, QHeaderView.Stretch)
        main_layout.addWidget(self.table_view)
        self.setCentralWidget(main_widget)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.add_button.clicked.connect(self.add_entry_action)
        self.edit_button.clicked.connect(self.edit_entry_action)
        self.delete_button.clicked.connect(self.delete_entry_action)
        self.delete_duplicates_button.clicked.connect(self.delete_duplicates_action)
        self.bulk_edit_button.clicked.connect(self.bulk_edit_category_action)
        self.import_url_button.clicked.connect(self.import_from_url_action)
        self.import_file_button.clicked.connect(self.import_from_file_action)
        self.manage_categories_button.clicked.connect(self.manage_categories_action)
        self.check_selected_button.clicked.connect(self.check_selected_entries_action)
        self.check_all_button.clicked.connect(self.check_all_entries_action)
        self.export_clipboard_button.clicked.connect(self.export_current_to_clipboard)
        self.export_txt_button.clicked.connect(self.export_selected_to_txt)

        self.table_view.doubleClicked.connect(self.edit_entry_action)
        self.category_filter_combo.currentTextChanged.connect(self.category_filter_changed)
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        self.exclude_na_button.toggled.connect(self.on_exclude_na_toggled)

        self.table_view.selectionModel().selectionChanged.connect(self.update_action_button_states)
        self.table_view.selectionModel().currentChanged.connect(self.update_action_button_states)

    def update_category_filter_combo(self):
        cur_sel = self.category_filter_combo.currentText(); self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.clear(); self.category_filter_combo.addItem("All Categories")
        try: self.category_filter_combo.addItems(get_all_categories())
        except Exception as e: logging.error(f"Failed to populate category filter: {e}")
        idx = self.category_filter_combo.findText(cur_sel); self.category_filter_combo.setCurrentIndex(idx if idx != -1 else 0)
        self.category_filter_combo.blockSignals(False)

    @Slot(str)
    def category_filter_changed(self, cat_name):
        self.current_category_filter = cat_name;
        self.load_entries_to_table()

    @Slot(str)
    def on_search_text_changed(self, text):
        self.proxy_model.set_search_text(text)

    @Slot(bool)
    def on_exclude_na_toggled(self, checked):
        self.proxy_model.set_exclude_na(checked)

    def load_entries_to_table(self):
        self.table_model.removeRows(0, self.table_model.rowCount())
        try:
            for row_data in get_all_entries(category_filter=self.current_category_filter): self.table_model.appendRow(self.create_row_items(row_data))
        except Exception as e: logging.error(f"Error loading entries: {e}"); QMessageBox.critical(self, "Load Error", f"Could not load: {e}")
        self.proxy_model.invalidateFilter()

    def create_row_items(self, entry_data):
        items = []; id_item = QStandardItem(str(entry_data['id'])); id_item.setData(entry_data['id'], Qt.UserRole); items.append(id_item)
        items.append(QStandardItem(entry_data['name'])); items.append(QStandardItem(entry_data['category']))
        status_val = entry_data['api_status'] if entry_data['api_status'] is not None else "Not Checked"
        status_item = QStandardItem(status_val); self.apply_status_coloring(status_item, status_val); items.append(status_item)
        items.append(QStandardItem(str(entry_data['live_streams_count']) if entry_data['live_streams_count'] is not None else "N/A"))
        items.append(QStandardItem(str(entry_data['movies_count']) if entry_data['movies_count'] is not None else "N/A"))
        items.append(QStandardItem(str(entry_data['series_count']) if entry_data['series_count'] is not None else "N/A"))
        items.append(QStandardItem(format_timestamp_display(entry_data['expiry_date_ts'])))
        items.append(QStandardItem(format_trial_status_display(entry_data['is_trial'])))
        active_c = entry_data['active_connections']; items.append(QStandardItem(str(active_c) if active_c is not None else "N/A"))
        max_c = entry_data['max_connections']; items.append(QStandardItem(str(max_c) if max_c is not None else "N/A"))
        last_chk_raw = entry_data['last_checked_at']; last_chk_disp = "Never"
        if last_chk_raw:
            try:
                dt_utc = QDateTime.fromString(last_chk_raw.split('.')[0], Qt.ISODate).toUTC()
                if not dt_utc.isValid() : dt_utc = QDateTime.fromString(last_chk_raw, Qt.ISODateWithMs).toUTC()
                dt_local = dt_utc.toLocalTime(); last_chk_disp = dt_local.toString("yyyy-MM-dd hh:mm")
            except Exception as e: logging.warning(f"Error parsing last_checked_at '{last_chk_raw}': {e}")
        items.append(QStandardItem(last_chk_disp))

        # entry_data is an sqlite3.Row object. Access columns using dictionary-style access.
        # The 'account_type' column should exist due to migrations, defaulting to 'xc'.
        account_type = entry_data['account_type'] if entry_data['account_type'] is not None else 'xc'

        if account_type == 'stalker':
            items.append(QStandardItem(entry_data['portal_url'] or 'N/A')) # Server column
            items.append(QStandardItem(entry_data['mac_address'] or 'N/A')) # Username column, now User/MAC
        else: # XC or if somehow account_type is None and defaulted to 'xc'
            items.append(QStandardItem(entry_data['server_base_url'] or 'N/A'))
            items.append(QStandardItem(entry_data['username'] or 'N/A'))

        api_msg = entry_data['api_message'] if entry_data['api_message'] is not None else ""
        items.append(QStandardItem(api_msg))
        return items

    def apply_status_coloring(self, item, status_text):
        s_lower = str(status_text).lower()
        # Default color will be the current text color from the stylesheet
        # This ensures that if no specific rule matches, it uses the theme's default text color.
        default_text_color = QGuiApplication.palette().text().color() # Get theme's default text color
        color = default_text_color

        if self.dark_theme_action.isChecked(): # Dark Theme Colors
            if "active" in s_lower: color = QColor("white") # Changed to white for Dark Mode
            elif "expired" in s_lower: color = QColor("#FF9800") # Orange
            elif "banned" in s_lower or "disabled" in s_lower: color = QColor("#F44336") # Red
            elif "auth failed" in s_lower: color = QColor("#B71C1C") # Darker Red
            elif "error" in s_lower or "failed" in s_lower and "auth failed" not in s_lower : color = QColor("#E91E63") # Pink
            # For "Not Checked" or other statuses in dark mode, let it use the default_text_color (usually light grey/white)
            # else: color = QColor("#BDBDBD") # Explicit Grey, or rely on default_text_color
        else: # Light Theme Colors
            if "active" in s_lower: color = QColor("darkGreen") # Kept as darkGreen for Light Mode
            elif "expired" in s_lower: color = QColor("orange")
            elif "banned" in s_lower or "disabled" in s_lower: color = QColor("red")
            elif "auth failed" in s_lower: color = QColor(139,0,0) # DarkRed
            elif "error" in s_lower or "failed" in s_lower and "auth failed" not in s_lower : color = QColor("magenta")
            else: color = QColor("gray") # Grey for "Not Checked" or other statuses in light mode

        item.setForeground(color)

    @Slot()
    def update_action_button_states(self):
        selection_model = self.table_view.selectionModel()
        has_selection = selection_model.hasSelection()
        selected_row_count = len(selection_model.selectedRows(0))

        can_interact = not self._is_checking_api

        self.edit_button.setEnabled(selected_row_count == 1 and can_interact)
        self.delete_button.setEnabled(has_selection and can_interact)
        self.bulk_edit_button.setEnabled(has_selection and can_interact)
        self.check_selected_button.setEnabled(has_selection and can_interact)
        self.export_txt_button.setEnabled(has_selection and can_interact)

        self.check_all_button.setEnabled(self.proxy_model.rowCount() > 0 and can_interact)

        current_proxy_index = self.table_view.currentIndex()
        is_valid_current_item = current_proxy_index.isValid() and current_proxy_index.row() >= 0
        self.export_clipboard_button.setEnabled(is_valid_current_item and can_interact)

        self.add_button.setEnabled(can_interact)
        self.import_url_button.setEnabled(can_interact)
        self.import_file_button.setEnabled(can_interact)
        self.manage_categories_button.setEnabled(can_interact)

        self.category_filter_combo.setEnabled(can_interact)
        self.search_edit.setEnabled(can_interact)
        self.exclude_na_button.setEnabled(can_interact)


    @Slot()
    def add_entry_action(self):
        diag = EntryDialog(parent=self)
        if diag.exec(): self.load_entries_to_table(); self.update_category_filter_combo()

    @Slot()
    def edit_entry_action(self):
        current_proxy_index = self.table_view.currentIndex()
        if not current_proxy_index.isValid():
            sel_proxied = self.table_view.selectionModel().selectedRows(COL_ID)
            if not sel_proxied: return
            current_proxy_index = sel_proxied[0]

        src_idx = self.proxy_model.mapToSource(current_proxy_index)
        entry_id_item = self.table_model.itemFromIndex(src_idx.siblingAtColumn(COL_ID))
        if not entry_id_item: return
        entry_id = entry_id_item.data(Qt.UserRole)

        # Fetch full entry data to decide which dialog to open
        entry_data = get_entry_by_id(entry_id)
        if not entry_data:
            QMessageBox.warning(self, "Error", "Could not retrieve entry data.")
            return

        account_type = entry_data['account_type'] if entry_data['account_type'] is not None else 'xc'
        api_status = entry_data['api_status']

        # If it's an active XC account, open the playlist browser. Otherwise, open the edit dialog.
        if account_type == 'xc' and api_status and 'active' in api_status.lower():
            diag = PlaylistBrowserDialog(entry_data=entry_data, parent=self)
            diag.exec() # This dialog is for browsing, no refresh needed on close
        else:
            diag = EntryDialog(entry_id=entry_id, parent=self)
            if diag.exec(): self.refresh_row_by_id(entry_id); self.update_category_filter_combo()

    @Slot()
    def bulk_edit_category_action(self):
        selected_ids = self.get_selected_entry_ids()
        if not selected_ids:
            QMessageBox.information(self, "Bulk Edit", "No entries selected.")
            return

        dialog = BulkEditCategoryDialog(parent=self)
        if dialog.exec():
            new_category = dialog.get_selected_category()
            try:
                for entry_id in selected_ids:
                    update_entry_category(entry_id, new_category)
                self.load_entries_to_table()
                QMessageBox.information(self, "Success", f"{len(selected_ids)} entries have been moved to the '{new_category}' category.")
            except Exception as e:
                logging.error(f"Error bulk updating categories: {e}")
                QMessageBox.critical(self, "Database Error", f"Could not update categories: {e}")

    @Slot()
    def delete_entry_action(self):
        sel_proxied = self.table_view.selectionModel().selectedRows(COL_ID)
        if not sel_proxied: return
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete {len(sel_proxied)} selected entry(s)?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            ids_del = []
            for proxy_idx in sel_proxied:
                src_idx = self.proxy_model.mapToSource(proxy_idx)
                id_item = self.table_model.itemFromIndex(src_idx.siblingAtColumn(COL_ID))
                if id_item: ids_del.append(id_item.data(Qt.UserRole))

            for entry_id in ids_del:
                try: delete_entry(entry_id)
                except Exception as e: QMessageBox.warning(self, "Delete Error", f"Could not delete ID {entry_id}: {e}")
            self.load_entries_to_table()

    @Slot()
    def delete_duplicates_action(self):
        try:
            all_entries = get_all_entries()
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not retrieve entries to check for duplicates: {e}")
            return

        xtream_map = {}
        stalker_map = {}
        duplicates_to_delete = set()

        for entry in all_entries:
            entry_id = entry['id']
            account_type = entry['account_type'] if entry['account_type'] is not None else 'xc'

            if account_type == 'xc':
                key = (entry['server_base_url'], entry['username'], entry['password'])
                if key in xtream_map:
                    existing_id, existing_last_checked = xtream_map[key]
                    current_last_checked = entry['last_checked_at']

                    if existing_last_checked is None and current_last_checked is None:
                        # If both are None, keep the one with the lower ID
                        if entry_id > existing_id:
                            duplicates_to_delete.add(entry_id)
                        else:
                            duplicates_to_delete.add(existing_id)
                            xtream_map[key] = (entry_id, current_last_checked)
                    elif current_last_checked is None:
                        duplicates_to_delete.add(entry_id)
                    elif existing_last_checked is None:
                        duplicates_to_delete.add(existing_id)
                        xtream_map[key] = (entry_id, current_last_checked)
                    elif current_last_checked > existing_last_checked:
                        duplicates_to_delete.add(existing_id)
                        xtream_map[key] = (entry_id, current_last_checked)
                    else:
                        duplicates_to_delete.add(entry_id)
                else:
                    xtream_map[key] = (entry_id, entry['last_checked_at'])
            elif account_type == 'stalker':
                key = (entry['portal_url'], entry['mac_address'])
                if key in stalker_map:
                    existing_id, existing_last_checked = stalker_map[key]
                    current_last_checked = entry['last_checked_at']

                    if existing_last_checked is None and current_last_checked is None:
                        if entry_id > existing_id:
                            duplicates_to_delete.add(entry_id)
                        else:
                            duplicates_to_delete.add(existing_id)
                            stalker_map[key] = (entry_id, current_last_checked)
                    elif current_last_checked is None:
                        duplicates_to_delete.add(entry_id)
                    elif existing_last_checked is None:
                        duplicates_to_delete.add(existing_id)
                        stalker_map[key] = (entry_id, current_last_checked)
                    elif current_last_checked > existing_last_checked:
                        duplicates_to_delete.add(existing_id)
                        stalker_map[key] = (entry_id, current_last_checked)
                    else:
                        duplicates_to_delete.add(entry_id)
                else:
                    stalker_map[key] = (entry_id, entry['last_checked_at'])

        if not duplicates_to_delete:
            QMessageBox.information(self, "No Duplicates Found", "No duplicate entries were found.")
            return

        reply = QMessageBox.question(self, "Confirm Deletion",
                                     f"Found {len(duplicates_to_delete)} duplicate entries. Do you want to delete them?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            deleted_count = 0
            for entry_id in duplicates_to_delete:
                try:
                    delete_entry(entry_id)
                    deleted_count += 1
                except Exception as e:
                    logging.error(f"Could not delete duplicate entry with ID {entry_id}: {e}")

            QMessageBox.information(self, "Deletion Complete", f"Successfully deleted {deleted_count} duplicate entries.")
            self.load_entries_to_table()

    @Slot()
    def manage_categories_action(self):
        diag = ManageCategoriesDialog(parent=self)
        diag.exec()
        self.load_entries_to_table()
        self.update_category_filter_combo()

    @Slot()
    def import_from_url_action(self):
        dialog = ImportUrlDialog(parent=self)
        if dialog.exec():
            self.load_entries_to_table(); self.update_category_filter_combo()

    @Slot()
    def import_from_file_action(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Text File with URLs", "", "Text Files (*.txt);;All Files (*)")
        if not file_path: return
        options_dialog = BatchImportOptionsDialog(parent=self)
        if not options_dialog.exec(): return
        default_category = options_dialog.get_selected_category()
        imported_count = 0
        failed_count = 0

        current_stalker_portal_url_for_mac_list = None
        mac_pattern = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line_content = line.strip()
                    if not line_content or line_content.startswith('#'):
                        continue

                    is_stalker_credential_string = line_content.startswith("stalker_portal:")
                    is_xc_link = "get.php?" in line_content
                    # Check for MAC pattern first, as URLs can be short and might be misidentified by simple http check alone
                    is_potential_mac = mac_pattern.fullmatch(line_content) is not None # Use fullmatch for MAC

                    # A line is a potential portal URL if it starts with http/https, is NOT an XC link, AND NOT a stalker credential string
                    is_potential_portal_url = (line_content.startswith("http://") or line_content.startswith("https://")) \
                                               and not is_xc_link and not is_stalker_credential_string

                    if is_stalker_credential_string:
                        current_stalker_portal_url_for_mac_list = None # Reset context
                        try:
                            parts = line_content.split(',')
                            if len(parts) < 2: raise ValueError("Malformed stalker string, missing comma.")
                            portal_part_full = parts[0].strip()
                            mac_part_full = parts[1].strip()

                            if not portal_part_full.startswith("stalker_portal:") or not mac_part_full.startswith("mac:"):
                                raise ValueError("Malformed stalker string, missing prefixes.")

                            portal_url = portal_part_full.replace("stalker_portal:", "").strip()
                            mac_address = mac_part_full.replace("mac:", "").strip().upper()

                            if not (portal_url.startswith("http://") or portal_url.startswith("https://")):
                                logging.warning(f"Batch Import: Invalid Stalker portal URL in string on line {line_num}: {portal_url}"); failed_count += 1; continue
                            if not mac_pattern.fullmatch(mac_address): # Re-check MAC after parsing
                                logging.warning(f"Batch Import: Invalid Stalker MAC address in string on line {line_num}: {mac_address}"); failed_count += 1; continue

                            parsed_p_url = urlparse(portal_url)
                            host = parsed_p_url.hostname or "stalker_host"
                            display_name = f"{host}_{mac_address.replace(':', '')}_L{line_num}"
                            server_base_url = f"{parsed_p_url.scheme}://{parsed_p_url.netloc}" if parsed_p_url.scheme and parsed_p_url.netloc else portal_url
                            add_entry(display_name, default_category, server_base_url, "", "", account_type='stalker', mac_address=mac_address, portal_url=portal_url)
                            imported_count += 1
                            logging.info(f"Batch Import: Successfully imported Stalker credential string from line {line_num}")
                        except Exception as e_stalker_str:
                            logging.error(f"Batch Import: Error processing Stalker credential string on line {line_num} ('{line_content}'): {e_stalker_str}"); failed_count += 1

                    elif is_xc_link:
                        current_stalker_portal_url_for_mac_list = None # Reset context
                        parsed_info = parse_get_php_url(line_content)
                        if parsed_info and not parsed_info.get('error'):
                            try:
                                host = urlparse(parsed_info['server_base_url']).hostname or "host"
                                display_name = f"{host}_{parsed_info['username']}_L{line_num}"
                                add_entry(display_name, default_category, parsed_info['server_base_url'], parsed_info['username'], parsed_info['password'])
                                imported_count += 1
                            except Exception as db_e: logging.error(f"Batch Import: DB error for XC URL on line {line_num} ('{line_content}'): {db_e}"); failed_count += 1
                        else:
                            logging.warning(f"Batch Import: Failed to parse XC URL on line {line_num}: {line_content} - {parsed_info.get('error', 'Unknown') if parsed_info else 'None'}"); failed_count += 1

                    elif is_potential_portal_url: # Must be checked AFTER specific formats (XC, stalker_portal:)
                        parsed_val_url = urlparse(line_content)
                        if parsed_val_url.scheme and parsed_val_url.netloc: # Basic validation
                            current_stalker_portal_url_for_mac_list = line_content
                            logging.info(f"Batch Import: Set current Stalker portal URL for subsequent MACs to: {current_stalker_portal_url_for_mac_list} (from line {line_num})")
                        else:
                            logging.warning(f"Batch Import: Skipped potential URL (malformed or unsupported) on line {line_num}: {line_content}")
                            # current_stalker_portal_url_for_mac_list = None # Keep previous context or reset? Let's keep for now.
                            failed_count +=1

                    elif is_potential_mac and current_stalker_portal_url_for_mac_list:
                        mac_address = line_content.strip().upper() # Already validated by is_potential_mac basically
                        portal_url = current_stalker_portal_url_for_mac_list
                        try:
                            parsed_p_url = urlparse(portal_url)
                            host = parsed_p_url.hostname or "stalker_host"
                            display_name = f"{host}_{mac_address.replace(':', '')}_L{line_num}"
                            server_base_url = f"{parsed_p_url.scheme}://{parsed_p_url.netloc}" if parsed_p_url.scheme and parsed_p_url.netloc else portal_url
                            add_entry(display_name, default_category, server_base_url, "", "", account_type='stalker', mac_address=mac_address, portal_url=portal_url)
                            imported_count += 1
                            logging.info(f"Batch Import: Successfully imported Stalker MAC {mac_address} for portal {portal_url} from line {line_num}")
                        except Exception as e_mac_list:
                            logging.error(f"Batch Import: Error processing MAC {mac_address} for portal {portal_url} on line {line_num}: {e_mac_list}"); failed_count += 1

                    else:
                        if is_potential_mac and not current_stalker_portal_url_for_mac_list:
                            logging.warning(f"Batch Import: Skipped MAC address {line_content} on line {line_num} as no Stalker Portal URL was previously defined in a block.")
                        else:
                            logging.warning(f"Batch Import: Skipped unrecognized line {line_num}: {line_content[:100]}...")
                        failed_count += 1

            QMessageBox.information(self, "Batch Import Complete", f"Imported: {imported_count}\nFailed/Skipped: {failed_count}\nSee log for details.")
            if imported_count > 0: self.load_entries_to_table(); self.update_category_filter_combo()
        except IOError as e: logging.error(f"Error reading import file '{file_path}': {e}"); QMessageBox.critical(self, "File Error", f"Could not read file: {e}")
        except Exception as e_gen: logging.error(f"Unexpected error during batch import: {e_gen}"); QMessageBox.critical(self, "Import Error", f"Unexpected error: {e_gen}")

    def get_entry_data_for_export(self, proxy_index):
        if not proxy_index.isValid(): return None
        source_index = self.proxy_model.mapToSource(proxy_index)
        entry_id_item = self.table_model.itemFromIndex(source_index.siblingAtColumn(COL_ID))
        if not entry_id_item: return None

        entry_id = entry_id_item.data(Qt.UserRole)
        entry = get_entry_by_id(entry_id) # entry is an sqlite3.Row
        if entry:
            account_type = entry['account_type'] if entry['account_type'] is not None else 'xc'
            if account_type == 'stalker':
                portal_url = entry['portal_url'] or ""
                mac_address = entry['mac_address'] or ""
                return f"stalker_portal:{portal_url},mac:{mac_address}"
            else: # XC
                return f"{entry['server_base_url']}/get.php?username={entry['username']}&password={entry['password']}&type=m3u_plus&output=ts"
        return None

    @Slot()
    def export_current_to_clipboard(self):
        current_proxy_index = self.table_view.currentIndex()
        export_string = self.get_entry_data_for_export(current_proxy_index)
        if export_string:
            QGuiApplication.clipboard().setText(export_string)

            # Determine message based on what was copied
            source_index = self.proxy_model.mapToSource(current_proxy_index)
            entry_id_item = self.table_model.itemFromIndex(source_index.siblingAtColumn(COL_ID))
            message = "Data copied to clipboard."
            if entry_id_item:
                entry_id = entry_id_item.data(Qt.UserRole)
                db_entry = get_entry_by_id(entry_id)
                if db_entry:
                    account_type = db_entry['account_type'] if db_entry['account_type'] is not None else 'xc'
                    if account_type == 'stalker':
                        message = "Stalker credentials copied to clipboard."
                    else:
                        message = "XC API M3U link copied to clipboard."
            self.status_bar.showMessage(message, 3000)
        else:
            QMessageBox.warning(self, "Export Error", "Could not get data for the current entry to copy.")

    @Slot()
    def export_selected_to_txt(self):
        selected_proxy_indexes = self.table_view.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QMessageBox.information(self, "Export", "No entries selected.")
            return

        m3u_links = []
        for proxy_idx in selected_proxy_indexes:
            link = self.get_entry_data_for_export(proxy_idx)
            if link: m3u_links.append(link)

        if not m3u_links:
            QMessageBox.warning(self, "Export Error", "Could not get data for any selected entries.")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save Exported Links", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    for link in m3u_links: f.write(link + "\n")
                self.status_bar.showMessage(f"{len(m3u_links)} links exported to {os.path.basename(file_path)}.", 5000)
                QMessageBox.information(self, "Export Successful", f"{len(m3u_links)} M3U links exported to:\n{file_path}")
            except IOError as e:
                logging.error(f"Error writing export file '{file_path}': {e}")
                QMessageBox.critical(self, "File Error", f"Could not write to file: {e}")


    def get_selected_entry_ids(self):
        ids = []
        # A bit of logging to see how long this takes if it's an issue
        logging.debug("Getting selected entry IDs...")
        start_time = time.perf_counter()
        for proxy_idx in self.table_view.selectionModel().selectedRows(COL_ID): # Specify column for row indexes
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            id_item = self.table_model.itemFromIndex(src_idx) # Use src_idx directly if it's for COL_ID
            if id_item: ids.append(id_item.data(Qt.UserRole))
        end_time = time.perf_counter()
        logging.debug(f"Got {len(ids)} selected IDs in {end_time - start_time:.4f} seconds.")
        return ids

    def get_all_visible_entry_ids(self):
        ids = []
        logging.debug("Getting all visible entry IDs...")
        start_time = time.perf_counter()
        for row in range(self.proxy_model.rowCount()):
            proxy_idx = self.proxy_model.index(row, COL_ID)
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            id_item = self.table_model.itemFromIndex(src_idx)
            if id_item: ids.append(id_item.data(Qt.UserRole))
        end_time = time.perf_counter()
        logging.debug(f"Got {len(ids)} visible IDs in {end_time - start_time:.4f} seconds.")
        return ids

    @Slot()
    def check_selected_entries_action(self):
        ids = self.get_selected_entry_ids()
        if ids: self.start_api_checks(ids)

    @Slot()
    def check_all_entries_action(self):
        ids = self.get_all_visible_entry_ids()
        if ids: self.start_api_checks(ids)

    def start_api_checks(self, entry_ids):
        if self._is_checking_api:
            QMessageBox.warning(self, "Busy", "API check already in progress.")
            return

        self._is_checking_api = True
        num_entries = len(entry_ids)

        # --- UI Updates on Main Thread BEFORE starting thread ---
        self.progress_bar.setRange(0, num_entries)
        self.progress_bar.setValue(0) # Set to 0 before showing
        self.progress_bar.setFormat("%v / %m (%p%)")
        self.progress_bar.setVisible(True) # Make visible NOW
        self.status_bar.showMessage(f"Starting API checks for {num_entries} entries...")
        self.update_action_button_states() # Disable buttons
        QApplication.processEvents() # Try to force immediate UI update
        # --- End UI Updates on Main Thread ---

        logging.debug("Creating API thread and worker.")
        self.api_thread = QThread(self) # Pass parent to QThread for potential lifecycle mgt
        self.api_worker = ApiCheckerWorker()

        # Connect session_initialized_signal from worker
        # This ensures run_checks is called only after the session is ready in the worker's thread
        self.api_worker.session_initialized_signal.connect(
            lambda: self.api_worker.run_checks(list(entry_ids)) # Pass a copy
        )

        self.api_worker.moveToThread(self.api_thread)

        self.api_worker.result_ready.connect(self.handle_api_result)
        self.api_worker.status_message_updated.connect(self.status_bar.showMessage)
        self.api_worker.progress_updated.connect(self.update_progress_bar_values)
        self.api_worker.batch_finished.connect(self.on_api_worker_batch_finished)

        # The worker's run_checks will be triggered by session_initialized_signal
        # We now trigger initialize_session when the thread starts.
        self.api_thread.started.connect(self.api_worker.initialize_session)

        self.api_thread.finished.connect(self.api_worker.cleanup_session)
        self.api_thread.finished.connect(self.api_worker.deleteLater)
        self.api_thread.finished.connect(self.api_thread.deleteLater)
        self.api_thread.finished.connect(self._clear_thread_references)

        logging.debug("Starting API thread.")
        self.api_thread.start()
        logging.debug("start_api_checks method finished on main thread.")


    @Slot(int, int)
    def update_progress_bar_values(self, current_val, total_val):
        logging.debug(f"Main Thread: Received progress update: {current_val}/{total_val}")
        if self.progress_bar.maximum() != total_val:
            self.progress_bar.setMaximum(total_val)
        self.progress_bar.setValue(current_val)
        # No processEvents() here, let Qt handle it unless flickering persists badly.

    # set_buttons_enabled_during_check is removed as update_action_button_states handles it.

    @Slot(int, dict)
    def handle_api_result(self, entry_id, result_data):
        logging.debug(f"GUI received API result for ID {entry_id}: {result_data.get('api_status', 'N/A')}")
        try:
            update_entry_status(entry_id, result_data)
            self.refresh_row_by_id(entry_id)
        except Exception as e:
            logging.error(f"Error handling API result for ID {entry_id} in GUI: {e}")

    def refresh_row_by_id(self, entry_id):
        entry_data = get_entry_by_id(entry_id)
        if not entry_data: return

        new_row_items = self.create_row_items(entry_data)

        for row in range(self.table_model.rowCount()):
            source_id_item = self.table_model.item(row, COL_ID)
            if source_id_item and source_id_item.data(Qt.UserRole) == entry_id:
                for col, item_data in enumerate(new_row_items):
                    existing_item = self.table_model.item(row, col)
                    if existing_item:
                        existing_item.setText(item_data.text())
                        if col == COL_ID: existing_item.setData(item_data.data(Qt.UserRole), Qt.UserRole)
                        if col == COL_STATUS: self.apply_status_coloring(existing_item, item_data.text())
                    else:
                        self.table_model.setItem(row, col, item_data)
                self.proxy_model.invalidateFilter()
                return
        logging.warning(f"Could not find row for ID {entry_id} to refresh directly in source model, or it's filtered. Proxy will update.")
        self.proxy_model.invalidateFilter()

    @Slot()
    def _clear_thread_references(self):
        logging.info("QThread.finished received. Clearing Python references and re-enabling UI.")

        self.api_worker = None
        self.api_thread = None
        self._is_checking_api = False

        self.progress_bar.setVisible(False)
        self.update_action_button_states()
        self.status_bar.showMessage("API checks fully completed.", 5000)


    @Slot()
    def on_api_worker_batch_finished(self):
        # Worker's internal processing loop has finished.
        # Status bar would have been updated by the worker with "Finished checking X/Y entries."

        if self.api_worker:
            self.api_worker.stop_processing() # Ensure its _is_running flag is false

        if self.api_thread:
            logging.info("Worker batch finished. Requesting QThread to quit its event loop.")
            self.api_thread.quit()

        logging.info("API Worker batch processing finished. Waiting for QThread.finished for full cleanup and UI reset.")


    def closeEvent(self, event):
        self.save_settings()
        if self._is_checking_api and self.api_thread and self.api_thread.isRunning():
            logging.info("Attempting to stop API worker thread before closing...")
            self.api_worker.stop_processing()
            self.api_thread.quit()
            # Wait a bit for the thread to finish gracefully.
            if not self.api_thread.wait(1000): # Wait 1 sec
                logging.warning("API thread did not stop gracefully. Forcing termination.")
                self.api_thread.terminate() # Fallback if it doesn't quit
                self.api_thread.wait() # Wait for termination
        event.accept()
        logging.info(f"{APP_NAME} closing.")

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                    theme = settings.get("theme", "light") # Default to light theme
                    self.set_theme(theme)
            else:
                self.set_theme("light") # Default to light theme if no settings file
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
            self.set_theme("light") # Default to light theme on error

    def save_settings(self):
        try:
            settings = {
                "theme": "dark" if self.dark_theme_action.isChecked() else "light"
            }
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving settings: {e}")

    def set_theme(self, theme_name):
        # TODO: Implement actual theme switching logic
        if theme_name == "light":
            self.light_theme_action.setChecked(True)
            self.dark_theme_action.setChecked(False)
            QApplication.instance().setStyleSheet("""
                QWidget { background-color: #f0f0f0; color: #333; }
                QTableView { background-color: white; selection-background-color: #a6cfff; }
                QHeaderView::section { background-color: #e0e0e0; }
                QPushButton { background-color: #d0d0d0; border: 1px solid #b0b0b0; padding: 5px; }
                QPushButton:hover { background-color: #c0c0c0; }
                QLineEdit, QComboBox { background-color: white; border: 1px solid #ccc; padding: 3px; }
            """)
        elif theme_name == "dark":
            self.dark_theme_action.setChecked(True)
            self.light_theme_action.setChecked(False)
            QApplication.instance().setStyleSheet("""
                QWidget { background-color: #2e2e2e; color: #f0f0f0; }
                QTableView { background-color: #3e3e3e; selection-background-color: #5a5a5a; }
                QHeaderView::section { background-color: #4e4e4e; }
                QPushButton { background-color: #5e5e5e; border: 1px solid #7e7e7e; padding: 5px; }
                QPushButton:hover { background-color: #6e6e6e; }
                QLineEdit, QComboBox { background-color: #4e4e4e; border: 1px solid #6e6e6e; padding: 3px; }
                QMenu { background-color: #3e3e3e; color: #f0f0f0; }
                QMenu::item:selected { background-color: #5a5a5a; }
                QStatusBar { background-color: #2e2e2e; }
            """)
        self.save_settings()
        self.refresh_table_coloring_on_theme_change() # Add this call

    def refresh_table_coloring_on_theme_change(self):
        """Refreshes the coloring of status items in the table after a theme change."""
        if not hasattr(self, 'table_model') or self.table_model is None:
            return

        logging.debug("Refreshing table item coloring due to theme change.")
        for row in range(self.table_model.rowCount()):
            # Assuming COL_STATUS is the correct column index for the API status
            status_item = self.table_model.item(row, COL_STATUS)
            if status_item:
                status_text = status_item.text()
                self.apply_status_coloring(status_item, status_text)
        # If using a proxy model, you might need to trigger an update for the view,
        # but changing item properties directly often reflects. If not, further signals might be needed.


# =============================================================================
# APPLICATION ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    logging.info("Application starting with DEBUG level logging.")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    if not initialize_database():
        QMessageBox.critical(None, "Startup Error", f"Failed to initialize the database ({DATABASE_NAME}).\nSee log: {LOG_FILE}\nApplication will exit.")
        sys.exit(1)

    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())
