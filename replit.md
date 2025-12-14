# Baiscope Subtitle Scraper

## Overview
A Python scraper that downloads Sinhala subtitles from baiscope.lk and uploads them to Cloudflare R2 storage.

## Features
- Bypasses Cloudflare protection using cloudscraper
- Extracts SRT files from ZIP archives
- Uploads subtitles to Cloudflare R2 with metadata
- Handles pagination and retry logic

## Configuration
The scraper uses these environment secrets:
- `R2_ACCOUNT_ID` - Cloudflare account ID
- `R2_ACCESS_KEY` - R2 API access key
- `R2_SECRET_KEY` - R2 API secret key
- `R2_BUCKET_NAME` - R2 bucket name (default: baiscope-subtitles)

## Usage
Run the scraper via the workflow or directly:
```bash
python main.py
```

To scrape all subtitles instead of the test limit, edit `main.py` and change:
```python
scraper.scrape_all(limit=5)  # Change to scraper.scrape_all() for full scrape
```

## File Structure
- `main.py` - Main scraper with BaiscopeScraperAdvanced class

## R2 Storage Structure
Subtitles are stored as:
```
subtitles/{movie_title}/{srt_filename}
```
