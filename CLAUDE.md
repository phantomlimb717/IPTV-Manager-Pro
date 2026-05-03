# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Development is on Windows. A `.venv` exists in the repo root.

```powershell
# Install deps
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Run the app
.\.venv\Scripts\python.exe IPTV_Manager_Pro.py

# Build the Windows exe (matches CI in .github/workflows/build.yml)
pyinstaller --onefile --windowed --icon=icon.ico --add-data "icon.ico;." IPTV_Manager_Pro.py
```

There is no test suite, no linter config, and no packaging metadata (no `pyproject.toml` / `setup.py`). CI only builds the PyInstaller artifact on push to `main` and on a 10-day cron.

The app is portable: `iptv_store.db`, `iptv_manager_log.txt` (opened with `filemode='w'` — wiped each run), and `settings.json` are created in the working directory at runtime.

## Architecture

PySide6 desktop app for managing/checking IPTV credentials. Two account types are first-class: **Xtream Codes API** (`account_type='xc'`) and **Stalker Portal** (`account_type='stalker'`, identified by portal URL + MAC). Most logic conditions on this discriminator — when adding features, both branches generally need handling.

### Module layout (flat, no package)

- **`IPTV_Manager_Pro.py`** (~2700 lines, monolithic) — UI, sqlite persistence, all `QDialog`s, the `MainWindow`, and a fleet of `QObject` worker classes that get moved onto `QThread`s for background work (category loading, stream loading, series info, playback, EPG, API checking). Worker→thread wiring is hand-rolled; when adding a worker, follow the existing pattern (worker emits `finished`/`error` signals, thread is `quit`/`wait`ed in slots).
- **`core_checker.py`** — `IPTVChecker` class, the **async** (`aiohttp`) credential-checker engine. Two-tier: API check, then optional stream playability check (download speed test, FFmpeg fallback). Implements the "frozen account" backoff (failures → exponential skip windows) referenced in the README. Called from `ApiCheckerWorker` in the main file via `asyncio.run` inside a QThread.
- **`stalker_integration.py`** — `StalkerPortal` class, **synchronous** (`requests`) Stalker client used by all Qt worker threads (handshake, profile, EPG, stream link resolution). The async checker in `core_checker.py` has its own parallel Stalker implementation; **the two must stay behaviorally consistent** (same handshake quirks, same URL normalization, same MAG user-agent). `MAG_USER_AGENT` is shared via re-export.
- **`epg_manager.py`** — `EpgManager(QThread)` with its own `StalkerPortal` session, drained from a queue. UI requests EPG via `request_epg(channel_id)`; results come back via the `epg_ready(channel_id, data)` signal.
- **`companion_utils.py`** — `resource_path` (PyInstaller `_MEIPASS` aware), `MediaPlayerManager` (locates/launches FFplay or MPV), and `ThemeManager` (singleton; loads QSS from `styles/` per `styles/themes.json`).

### Data model

SQLite, schema initialized in `initialize_database()` in the main file. The same `entries` table holds both account types — Xtream fields (`server_url`, `username`, `password`) and Stalker fields (`portal_url`, `mac_address`) coexist as nullable columns. `account_type` discriminates. Status fields (`expiry_date_ts`, `is_trial`, `active_connections`, etc.) are written by `update_entry_status` after a check.

### Concurrency model

- UI thread: Qt event loop only.
- Bulk credential checks: `ApiCheckerWorker` runs an `asyncio` loop on a `QThread`, fans out to `IPTVChecker` (aiohttp). Progress reported via Qt signals.
- All other background work (Stalker browsing, playback resolution, EPG): one `QObject` worker per task, `moveToThread` onto a fresh `QThread`. These use the **synchronous** `StalkerPortal`/`requests` — do not mix the async checker into UI worker paths.

### Theming

QSS is external in `styles/dark.qss` and `styles/light.qss`, indexed by `styles/themes.json`. `ThemeManager` is a singleton with a QSS cache; switch themes through it, do not call `setStyleSheet` directly on widgets.

### Stalker portal specifics

The codebase has substantial accumulated knowledge about Stalker portal quirks documented in:
- `stalker-knowledge-base.md`, `Stalker-Portal-Playback-Features.md`, `iptv-manager-pro-guide-for-stalker-playback.md`, `iptv-manager-pro-stalker-portal-fix-plan.md`

Read these before modifying Stalker handshake, token handling, URL normalization, or stream-link resolution — there are workarounds for specific portal variants that aren't obvious from the code alone.

## License note

The project uses Apache 2.0 + Commons Clause + an Acceptable Use Policy (see `LICENSE`). It is source-available, **not** OSI-open-source: no commercial sale/hosting. Worth flagging if a change has licensing implications.
