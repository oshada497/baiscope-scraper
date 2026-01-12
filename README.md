# BiScope & Subz.lk Subtitle Scraper

Automated scraper system that monitors **baiscope.lk** and **subz.lk** for new Sinhala subtitles, downloads them, and uploads to Telegram with Cloudflare D1 database tracking for duplicate prevention.

## Features

- ✅ **Dual-site monitoring**: baiscope.lk and subz.lk
- ✅ **WordPress AJAX download support** for subz.lk
- ✅ **Cloudflare D1 database** tracking with source field
- ✅ **Telegram upload** with automatic duplicate detection
- ✅ **Parallel processing** with ThreadPoolExecutor (3 workers)
- ✅ **Normalized filename matching** to prevent duplicates
- ✅ **Progress tracking** with Telegram notifications
- ✅ **State management** for resuming interrupted scrapes

## Project Structure

```
baiscope-scraper/
├── scraper_utils.py          # Shared utilities (D1, Telegram, helpers)
├── main.py                    # BiScope scraper (original)
├── subz_scraper.py           # Subz.lk scraper module
├── monitor_both.py           # Unified monitoring script (recommended)
├── scrape_subz_full.py       # Full scrape for subz.lk initial population
└── README.md                 # This file
```

## Setup

### 1. Environment Variables

Set these environment variables before running:

```bash
# Required
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_ID="your_chat_id_here"

# Optional but recommended for duplicate tracking
export CF_ACCOUNT_ID="your_cloudflare_account_id"
export CF_API_TOKEN="your_cloudflare_api_token"
export D1_DATABASE_ID="your_d1_database_id"
```

### 2. Install Dependencies

```bash
pip install curl-cffi beautifulsoup4 requests flask gunicorn
```

## Quick Start: Render Deployment (Recommended)

**Deploy to Render.com for 24/7 automatic monitoring:**

1. Push this repo to GitHub
2. Create new Web Service on [Render](https://dashboard.render.com/)
3. Set environment variables (see Setup section)
4. Deploy - monitoring starts automatically every 15 minutes!
5. Visit `/scrape/subz` once to populate subz.lk database

**See [RENDER_DEPLOY.md](file:///C:/Users/oshada/.gemini/antigravity/scratch/baiscope-scraper/RENDER_DEPLOY.md) for detailed deployment guide.**

The deployed service provides:
- ✅ Automatic monitoring every 15 minutes
- ✅ REST API for manual triggers and status
- ✅ Telegram notifications
- ✅ No local machine needed!

## Usage

### Monitor Both Sites (Recommended)

Check both baiscope.lk and subz.lk for **new subtitles only**:

```bash
# Monitor both sites
python monitor_both.py

# Monitor only subz.lk
python monitor_both.py --site subz

# Monitor only baiscope.lk  
python monitor_both.py --site baiscope

# Test with limit
python monitor_both.py --limit 5
```

**Recommended**: Run this script every 10-15 minutes via cron

```cron
*/15 * * * * cd /path/to/baiscope-scraper && python monitor_both.py
```

### Full Scrape of Subz.lk (Initial Setup)

For first-time setup, scrape **all existing subtitles** from subz.lk:

```bash
# Full scrape of subz.lk (all categories, all pages)
python scrape_subz_full.py

# Test with limit
python scrape_subz_full.py --limit 50
```

**Note**: You only need to run this ONCE to populate the database with existing subtitles.

### BiScope Full Scrape

Continue using the original script for baiscope.lk full scrape:

```bash
python main.py
```

## How It Works

### 1. Monitoring Mode (`monitor_both.py`)

**For Subz.lk:**
- Checks homepage for recent updates
- Compares against D1 database processed URLs
- Downloads and uploads only NEW subtitles

**For Baiscope.lk:**
- Checks first 3 pages of main Sinhala category
- Processes only new URLs not in database
- Minimal overhead since most content already scraped

### 2. Full Scrape Mode (`scrape_subz_full.py`)

**For Subz.lk:**
- Processes ALL categories: Movies, TV Shows
- Paginates through all pages
- Skips duplicates using D1 database
- Uploads everything to Telegram

### 3. Duplicate Detection

The system prevents duplicates using **3 layers**:

1. **URL tracking**: Each processed URL stored in `processed_urls` table
2. **Normalized filename**: Removes watermarks and normalizes for comparison
3. **D1 database query**: Checks `telegram_files` table before upload

### 4. Source Tracking

All database tables include a `source` field:
- `baiscope` - from baiscope.lk
- `subz` - from subz.lk

This allows querying statistics per site and prevents cross-site duplicates.

## Database Schema

### Tables Created Automatically

```sql
-- Discovered URLs
CREATE TABLE discovered_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    category TEXT,
    page INTEGER,
    source TEXT DEFAULT 'baiscope',  -- NEW FIELD
    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Processed URLs
CREATE TABLE processed_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    success INTEGER DEFAULT 0,
    title TEXT,
    source TEXT DEFAULT 'baiscope',  -- NEW FIELD
    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Uploaded Telegram Files
CREATE TABLE telegram_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id TEXT UNIQUE NOT NULL,
    file_unique_id TEXT,
    filename TEXT,
    normalized_filename TEXT,
    file_size INTEGER,
    title TEXT,
    source_url TEXT,
    category TEXT,
    source TEXT DEFAULT 'baiscope',   -- NEW FIELD
    message_id INTEGER,
    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

## API Details

### Subz.lk Download Mechanism

Subz.lk uses WordPress AJAX for downloads:

```
https://subz.lk/wp-admin/admin-ajax.php?action=sub_download&sub_id={id}&nonce={nonce}
```

The scraper:
1. Fetches the subtitle detail page
2. Parses the download button for `sub_id` and `nonce`
3. Constructs the download URL
4. Downloads the file (ZIP/RAR/SRT)
5. Uploads to Telegram with metadata

## Monitoring & Notifications

The system sends Telegram notifications for:

- **Start**: When scraper starts (includes stats)
- **Progress**: Every 2 minutes during scraping (rate, ETA, success/failed)
- **Completion**: Final summary (total processed, success count)

## Troubleshooting

### "No download params found"

- The download button structure may have changed on subz.lk
- Check the HTML and update `_extract_download_params()` in `subz_scraper.py`

### "Rate limited by Telegram"

- The scraper auto-handles rate limits with exponential backoff
- If persistent, reduce `num_workers` in scraper initialization

### "D1 database errors"

- Verify Cloudflare credentials are correct
- Check D1 database exists and is accessible
- Scraper will fall back to local storage if D1 unavailable

### "Already exists in Telegram" log spam

- This is expected - it means duplicate detection is working
- The scraper skips files already uploaded

## Statistics Queries

Use Cloudflare D1 console or API:

```sql
-- Total files per source
SELECT source, COUNT(*) as total 
FROM telegram_files 
GROUP BY source;

-- Recent uploads from subz.lk
SELECT title, filename, uploaded_at 
FROM telegram_files 
WHERE source = 'subz' 
ORDER BY uploaded_at DESC 
LIMIT 20;

-- Processing success rate
SELECT source, 
       SUM(success) as successful, 
       COUNT(*) as total,
       ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_rate
FROM processed_urls 
GROUP BY source;
```

## Customization

### Adjust Worker Count

In `subz_scraper.py` or `main.py`:

```python
self.num_workers = 5  # Increase for faster processing (default: 3)
```

### Change Notification Interval

In scraper initialization:

```python
self.tracker = ProgressTracker(self.telegram, interval=300)  # 5 min notifications
```

### Add More Categories

In `subz_scraper.py`, edit `scrape_all_categories()`:

```python
categories = [
    "/category/movies/",
    "/category/tv-shows/",
    "/category/your-category/",  # Add here
]
```

## Performance

- **Baiscope.lk monitoring**: ~30 seconds (checks 3 pages)
- **Subz.lk monitoring**: ~1-2 minutes (homepage check)
- **Combined monitoring**: ~2-3 minutes total
- **Full scrape**: Several hours depending on content volume

## License

Use as needed for your scraping projects.
