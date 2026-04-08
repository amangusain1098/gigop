# GigOptimizer Fiverr Market Capture

This Chrome extension reads the Fiverr page you already have open in your browser and sends the visible results to `GigOptimizer Pro`.

## What it does

- Captures visible Fiverr search-card data from the current tab
- Sends it to `https://animha.co.in/api/extension/import`
- Lets the backend compare your own gig against the imported page-one competitors

## Setup

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select this folder
5. Open the extension popup and fill in:
   - `API base URL`
   - `Extension API token`
   - `My Fiverr gig URL`
   - optional `Keyword override`

## Required backend env

Set these in the app environment before using the extension:

- `EXTENSION_ENABLED=true`
- `EXTENSION_API_TOKEN=<long-random-secret>`
- `EXTENSION_MAX_GIGS_PER_IMPORT=25`
- `EXTENSION_IMPORT_TTL_SECONDS=900`

## Notes

- This does not automate Fiverr login
- It uses the visible page the user already opened in Chrome
- The backend still validates and normalizes all imported data before analysis
