# Baiscope Subtitle Scraper

## Overview
A Python scraper that downloads Sinhala subtitles from baiscope.lk and uploads them directly to Telegram. Uses Cloudflare D1 database for storing discovered URLs, Telegram file IDs, and resume capability. Deployed on Render.

## Current Status
- Deployed on Render at: https://baiscope-scraper.onrender.com
- Uses curl_cffi for Cloudflare bypass (browser impersonation)
- Stores subtitles directly to Telegram channel
- Uses Cloudflare D1 for URL tracking, file metadata, and resume capability

## Features
- **Telegram Storage** - Uploads SRT files directly to Telegram channel
- **D1 Database** - Stores discovered URLs, processed URLs, and Telegram file metadata
- **Telegram File IDs** - Stores file_id, file_unique_id, filename, size for later use
- **Resume Capability** - Continues from where it left off after restart
- **Duplicate Skipping** - Automatically skips already processed URLs
- **Page-by-Page Processing** - Fetches page → downloads all SRTs → uploads to Telegram → next page
- **Better 403 Handling** - Exponential backoff up to 2 minutes, extended breaks after 10+ consecutive 403s
- **Telegram Rate Limiting** - Respects API limits, automatic cooldown on 429 errors
- **Graceful Shutdown** - Saves state when receiving SIGTERM/SIGINT signals

## Files
- `main.py` - Main scraper with BaiscopeScraperTelegram class
- `app.py` - Flask wrapper for Render web service
- `requirements.txt` - Python dependencies
- `render.yaml` - Render deployment config

## Environment Variables (on Render)
### Required:
- `TELEGRAM_BOT_TOKEN` - Telegram bot token for uploading subtitles
- `TELEGRAM_CHAT_ID` - Telegram channel ID (default: -1003442794989)

### For D1 Database (optional but recommended):
- `CF_ACCOUNT_ID` - Cloudflare account ID
- `CF_API_TOKEN` - Cloudflare API token with D1 permissions
- `D1_DATABASE_ID` - D1 database UUID

### Optional:
- `BATCH_SIZE` - Processing batch size (default: 50)

## D1 Database Tables
```sql
discovered_urls (id, url, category, page, discovered_at)
processed_urls (id, url, success, title, processed_at)
scraper_state (id, current_category, current_page, last_updated)
telegram_files (id, file_id, file_unique_id, filename, file_size, title, source_url, category, message_id, uploaded_at)
```

## GitHub
- Repository: github.com/oshada497/baiscope-scraper
- Push changes: `git add -A && git commit -m "message" && git push`

## Notes
- Replit is used for code editing and pushing to GitHub only
- Scraper runs on Render, not on Replit
- Some 403 errors are expected due to Cloudflare - scraper handles them with backoff
- Telegram file IDs stored in D1 can be used to forward/resend files without re-uploading
