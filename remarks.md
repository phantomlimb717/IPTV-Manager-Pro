# Remarks & Strategy for Updating IPTV-Manager-Pro

## Overview
You have a legacy repository (`IPTV-Manager-Pro`) that is described as "outdated and bloated" with inefficient credential checking. You now possess a high-quality `knowledge-base.md` derived from a modern, high-performance aggregator (`iptv-api`).

## Recommended Strategy

### 1. Context Transfer
**Action:** Copy `knowledge-base.md` into the root of `IPTV-Manager-Pro`.
**Why:** This file acts as a "Spec Sheet" or "Gold Standard" for the new agent. It contains the exact Python snippets (aiohttp, ffmpeg, regex) that you want to see implemented, saving the agent from having to reinvent the wheel or guess your requirements.

### 2. The "Strangler Fig" Pattern
Don't try to rewrite the entire application in one go. Instead, replace the core "Checker" engine first.

*   **Step 1: Audit.** Ask the agent to compare the existing checking logic in `IPTV-Manager-Pro` against the patterns in `knowledge-base.md`.
    *   *Prompt:* "Analyze the current `Checker` class. How does it compare to the 'Speed Testing & Validation Logic' in `knowledge-base.md`? List the inefficiencies (e.g., synchronous requests, lack of ffmpeg fallback)."
*   **Step 2: Modular Replacement.** Ask the agent to create a new module (e.g., `modern_checker.py`) that implements the `knowledge-base.md` logic (AsyncIO, FFmpeg, Player API).
*   **Step 3: Integration.** Wiring the new module into the old UI/Database.

### 3. Specific Improvements to Target
Based on our research, here are the specific upgrades to request:

*   **Async I/O:** Move from `requests` (synchronous) to `aiohttp` (as detailed in the KB). This is the single biggest factor for efficiency when checking large lists.
*   **Hybrid Verification:** Request the implementation of the "two-tier" check:
    1.  **API Check:** Use the `player_api.php` logic (from the KB Appendix) to check account validity *first*. (Fastest fail).
    2.  **Stream Check:** Only if the API is valid, use the `FFmpeg/Download` logic to verify the actual stream quality.
*   **Frozen/Backoff Logic:** Replace any simple "if fail, delete" logic with the "Exponential Backoff" strategy documented in the KB.

### 4. Sample Prompt for Next Session
When you start the new task with Jules, use a prompt like this:

> "I have added `knowledge-base.md` to this repository. It contains the standard logic I want to use for checking IPTV credentials and streams.
>
> Please analyze the existing credential checking logic in this repo. Then, create a plan to refactor it to match the high-performance patterns (AsyncIO, FFmpeg, Player API checking) defined in `knowledge-base.md`. I want to replace the old logic with this new, efficient approach."
