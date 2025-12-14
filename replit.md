# Baiscope Subtitle Scraper

## Overview
A Python scraper that downloads 20,000+ Sinhala subtitles from baiscope.lk and uploads them to Cloudflare R2 storage. Deployed on Render as a free web service.

## Current Status
- Deployed on Render at: https://baiscope-scraper.onrender.com
- Uses curl_cffi for Cloudflare bypass (browser impersonation)
- Crawls all categories to find subtitles
- Some 403 errors are normal - Cloudflare blocks some requests randomly
- Telegram notifications every 1 minute

## Features
- Bypasses Cloudflare using curl_cffi browser impersonation
- Extracts SRT files from ZIP archives
- Uploads subtitles to Cloudflare R2 with metadata
- Crawls all categories (movies, anime, drama, horror, etc.)
- Telegram progress notifications

## Files
- `main.py` - Main scraper with BaiscopeScraperAdvanced class
- `app.py` - Flask wrapper for Render web service
- `requirements.txt` - Python dependencies
- `render.yaml` - Render deployment config
- `.github/workflows/scraper.yml` - GitHub Actions (alternative deployment)

## Environment Variables (on Render)
- `R2_ACCOUNT_ID` - Cloudflare account ID
- `R2_ACCESS_KEY` - R2 API access key
- `R2_SECRET_KEY` - R2 API secret key
- `R2_BUCKET_NAME` - Bucket name (default: baiscope-subtitles)
- `TELEGRAM_BOT_TOKEN` - Telegram bot token for notifications
- `TELEGRAM_CHAT_ID` - Telegram chat ID for notifications

## GitHub
- Repository: github.com/oshada497/baiscope-scraper
- Push changes: `git add -A && git commit -m "message" && git push`

## R2 Storage Structure
```
subtitles/{movie_title}/{srt_filename}
```

## Notes
- GitHub integration not connected via Replit - push manually
- Some 403 errors are expected due to Cloudflare - scraper continues anyway
- Free Render web service keeps scraper running
