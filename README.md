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
- **Status Checking:** Check account status (including expiry date, active/max connections for Xtream Codes API) for both Xtream Codes and Stalker Portal type accounts.
- **Categorization:** Organize your entries into custom categories.
- **Advanced Filtering:** Quickly search the list by any field and filter by category.
- **Export Data:**
    - **Copy to Clipboard:** Copies Xtream Codes M3U links or Stalker Portal credential strings (`stalker_portal:URL,mac:MAC_ADDRESS`).
    - **Export to File:** Exports a list of Xtream Codes M3U links and/or Stalker Portal credential strings for selected entries. This file can be used for backup or re-import.


## Download & Installation

You can download the latest pre-compiled application for Windows from the official **[Releases Page](https://github.com/phantomlimb717/IPTV-Manager-Pro/releases)**.

No installation is required. Simply download the `IPTV Manager v0.2.4.exe` file and run it.

## Usage

1.  Download `IPTV Manager v0.2.4.exe` (or the latest version) from the latest release.
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
4.  Select accounts and use the `Check Selected` or `Check All Visible` buttons to refresh their status from the provider's API (*note*: `Check All Visible` will take a while if you have many playlists).
5.  Use "Copy Link (Current)" or "Export Links (Selected)" to get account data:
    *   For Xtream Codes API entries, this will be the M3U playable link.
    *   For Stalker Portal entries, this will be a credential string in the format `stalker_portal:URL,mac:MAC_ADDRESS` (useful for backup or re-importing into this tool or others that might support this format).

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)**.

You are free to:

- **Share** — copy and redistribute the material in any medium or format.
- **Adapt** — remix, transform, and build upon the material.

Under the following terms:

- **Attribution** — You must give appropriate credit if you use this code.
- **Non-Commercial** — You may not use the material for commercial purposes.
- **Share-Alike** — If you remix, transform, or build upon the material, you must distribute your contributions under the same license as the original.

For the full license text, please see the [LICENSE](LICENSE) file included in this repository.

---

## Acknowledgments


- The application icon was created by **[Icons8](https://icons8.com)** and sourced from **[Icon-Icons.com](https://icon-icons.com/icon/tv-television-screen/54127)**.


---
