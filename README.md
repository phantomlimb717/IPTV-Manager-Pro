# IPTV Manager Pro

A desktop application for managing and checking the status of IPTV account credentials, built with Python and PySide6. 

![Application Screenshot](https://i.imgur.com/UfFyNok.png)

## Features

- **Add, Edit, and Delete Entries:** Easily manage your list of IPTV accounts.
- **Support for Multiple Account Types:**
    - **Xtream Codes API:** The original supported type, using server URL, username, and password.
    - **Stalker Portal:** Add accounts using Portal URL and MAC Address. Status checking will verify MAC activation and expiry.
- **Batch Import (Xtream Codes API):** Import multiple Xtream Codes API accounts at once from M3U `get.php` style URLs, either from a single URL or from a text file.
- **Status Checking:** Check account status (including expiry date, active/max connections for Xtream Codes API) for both Xtream Codes and Stalker Portal type accounts.
- **Categorization:** Organize your entries into custom categories.
- **Advanced Filtering:** Quickly search the list by any field and filter by category.
- **Export Links (Xtream Codes API):** Copy individual M3U links or export links for selected Xtream Codes API entries to a text file for use in other IPTV players. (Note: M3U link generation/export for Stalker Portals is not currently supported in this manner).

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
    *   `Import URL` and `Import File` are primarily for Xtream Codes API `get.php` links.
4.  Select accounts and use the `Check Selected` or `Check All Visible` buttons to refresh their status from the provider's API (*note*: `Check All Visible` will take a while if you have many playlists).

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
