# Baiscope Subtitle Scraper

## Overview
A Python scraper that downloads 20,000+ Sinhala subtitles from baiscope.lk and uploads them to Cloudflare R2 storage.

## Features
- Bypasses Cloudflare protection using cloudscraper
- Extracts SRT files from ZIP archives
- Uploads subtitles to Cloudflare R2 with metadata
- Handles pagination and retry logic
- Configured for full scrape (no limits)

## Configuration
The scraper uses these environment secrets:
- `R2_ACCOUNT_ID` - Cloudflare account ID
- `R2_ACCESS_KEY` - R2 API access key
- `R2_SECRET_KEY` - R2 API secret key
- `R2_BUCKET_NAME` - R2 bucket name (default: baiscope-subtitles)

## Local Usage
Run the scraper directly:
```bash
python main.py
```

## Deploy to Render via GitHub

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "Baiscope subtitle scraper"
git remote add origin https://github.com/YOUR_USERNAME/baiscope-scraper.git
git push -u origin main
```

### Step 2: Deploy on Render
1. Go to https://render.com and sign in
2. Click "New" > "Blueprint"
3. Connect your GitHub repo
4. Render will detect `render.yaml` and configure automatically
5. Add your environment variables:
   - `R2_ACCOUNT_ID`
   - `R2_ACCESS_KEY`
   - `R2_SECRET_KEY`
   - `R2_BUCKET_NAME` (optional)
6. Click Deploy

### Alternative: Manual Worker Setup
1. Go to Render Dashboard > New > Background Worker
2. Connect your GitHub repo
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `python main.py`
5. Add environment variables
6. Deploy

## File Structure
- `main.py` - Main scraper with BaiscopeScraperAdvanced class
- `requirements.txt` - Python dependencies for Render
- `render.yaml` - Render deployment configuration

## R2 Storage Structure
Subtitles are stored as:
```
subtitles/{movie_title}/{srt_filename}
```

## Notes
- GitHub integration not connected via Replit - push manually using git commands
- Scraper handles up to 2000 pages (~20,000+ subtitles)
- Has built-in delays to be respectful to the source website
