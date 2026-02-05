# IPTV Manager Pro

A desktop application for managing and checking the status of IPTV account credentials, built with Python and PySide6. 

![Application Screenshot](https://i.imgur.com/UfFyNok.png)

## Features

- **Add, Edit, and Delete Entries:** Easily manage your list of IPTV accounts.
- **Support for Multiple Account Types:**
    - **Xtream Codes API:** The original supported type, using server URL, username, and password.
    - **Stalker Portal:** Add accounts using Portal URL and MAC Address. Status checking will verify MAC activation and expiry.
- **Batch Import:** Import multiple accounts from a text file. Supports:
    - Xtream Codes API `get.php` style URLs.
    - Stalker Portal credentials in the formats listed below.
- **Advanced Status Checking (Modernized):**
    - **High-Performance Async Engine:** Checks hundreds of accounts rapidly without freezing the UI.
    - **Two-Tier Verification:**
        1.  **API Check:** Verifies credentials against the server's API.
        2.  **Stream Check:** If the API is valid, it attempts to verify that a live stream is actually playable (via high-speed download test or FFmpeg fallback).
    - **Smart Backoff Strategy:** Accounts that fail checks are automatically "frozen" for increasing periods (1 min, 2 min, 4 min...) to prevent IP bans and waste resources. Frozen accounts are skipped during bulk checks.
- **Integrated Playlist Browser:** Double-click an active Xtream Codes account to browse and play Live, Movie, and Series content directly through an external media player (FFplay or MPV).
- **Categorization:** Organize your entries into custom categories.
- **Advanced Filtering:** Quickly search the list by any field and filter by category.
- **Export Data:**
    - **Copy to Clipboard:** Copies Xtream Codes M3U links or Stalker Portal credential strings (`stalker_portal:URL,mac:MAC_ADDRESS`).
    - **Export to File:** Exports a list of Xtream Codes M3U links and/or Stalker Portal credential strings for selected entries. This file can be used for backup or re-import.


## Download & Installation

You can download the latest pre-compiled application for Windows from the official **[Releases Page](https://github.com/phantomlimb717/IPTV-Manager-Pro/releases)**.

No installation is required. Simply download the `IPTV_Manager_Pro.exe` file and run it.

## Usage

1.  Download `IPTV_Manager_Pro.exe` (or the latest version) from the latest release.
2.  Run the executable file. The application is portable and will create its database (`iptv_store.db`) and log files in the same folder it is run from.
3.  Use the `Add Entry` or `Import URL` buttons to add your first account.
    *   When clicking `Add Entry`, you can now choose the "Account Type":
        *   **Xtream Codes API:** Enter Server URL, Username, and Password.
        *   **Stalker Portal:** Enter Portal URL (e.g., `http://portal.example.com:8080/c/`) and the MAC Address for the device (format: `XX:XX:XX:XX:XX:XX`).
    *   `Import URL` is for single Xtream Codes API `get.php` links.
    *   `Import File` can be used to batch import entries. Supported formats per line:
        *   **Xtream Codes API:** `http://server:port/get.php?username=USER&password=PASS...`
        *   **Stalker Portal (Self-contained):** `stalker_portal:PORTAL_URL,mac:MAC_ADDRESS`
        *   **Stalker Portal (URL followed by MACs):**
            ```
            http://your-stalker-portal.com:8080/c/  // This URL applies to MACs below
            00:1A:79:XX:XX:XA
            00:1A:79:XX:XX:XB
            // Another portal URL would reset the context for subsequent MACs
            http://another-portal.com
            00:1A:79:YY:YY:YA
            ```
4.  Select accounts and use the `Check Selected` or `Check All Visible` buttons to refresh their status.
    *   **Note on "Frozen" Accounts:** If an account repeatedly fails, you may see a status like "Skipped (Frozen until...)". This is normal and protects your IP address. To force a check, you can delete and re-add the entry, or simply wait for the timer to expire.
5.  **Browse & Play:** For an active Xtream Codes account, double-click the entry to open the new Playlist Browser. From there, you can browse and play all available Live, Movie, and Series content.
6.  Use "Copy Link (Current)" or "Export Links (Selected)" to get account data:
    *   For Xtream Codes API entries, this will be the M3U playable link.
    *   For Stalker Portal entries, this will be a credential string in the format `stalker_portal:URL,mac:MAC_ADDRESS` (useful for backup or re-importing into this tool or others that might support this format).

## License

This project is licensed under a custom "source-available" license: the **Apache License 2.0 with the Commons Clause and an Acceptable Use Policy**.

We believe in open development, but also in protecting the project from being used in a way that goes against its spirit. Here’s a simple breakdown of what that means for you:

### The Short Version (What You Need to Know)

This software is free to use for personal, community, and non-commercial purposes. You can download, modify, and share the code freely under the following main conditions:

*   ✅ **You CAN** use this software for free.
*   ✅ **You CAN** modify the source code for your own purposes.
*   ✅ **You CAN** share the software and your modifications with others (as long as you include the same license).

*   ❌ **You CANNOT** sell this software. This means you can't offer it as a paid product, a commercial service, or charge fees for support or hosting that relies substantially on this software's functionality.
*   ❌ **You CANNOT** use this software for any illegal activities. You are responsible for ensuring your use complies with all local and international laws.
*   ❌ **You CANNOT** use this software with content that you do not have the legal right to use.

### The Fine Print (Liability)

The software is provided "AS IS", without any warranties.

For the full legal terms and conditions, please see the [LICENSE](LICENSE) file in this repository.

---

## Acknowledgements

- A special thanks to **kidpoleon** for their work on the [iptv-companion](https://github.com/kidpoleon/iptv-companion) project. The new Playlist Browser feature in this application was directly inspired by their excellent design and implementation, reflecting a great spirit of open-source collaboration.
- The application icon was created by **[Icons8](https://icons8.com)** and sourced from **[Icon-Icons.com](https://icon-icons.com/icon/tv-television-screen/54127)**.
- This feature integration was developed with the assistance of the AI software engineer, **Jules**.

---
