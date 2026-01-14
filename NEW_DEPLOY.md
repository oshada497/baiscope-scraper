# Deploy Fresh Subz.lk Scraper to Render

## New Files Created

- `new_scraper.py` - Main scraper logic (clean implementation)
- `d1_database.py` - Simple D1 database handler
- `telegram_bot.py` - Telegram upload handler  
- `new_app.py` - Flask web server

## How It Works

1. **Crawls ALL pages** in `/category/movies/` and `/category/tv-shows/` until 404
2. **Discovers** all subtitle URLs first
3. **Processes** each subtitle one-by-one (downloads + uploads to Telegram)
4. **Prevents duplicates** using normalized filenames
5. **Stores** in clean D1 database (no old baiscope data)

## Deployment Steps

### 1. Update Render Configuration

Change your `render.yaml` or web service start command to use the new app:

**Option A: Update Start Command in Render Dashboard:**
```bash
gunicorn new_app:app
```

**Option B: Or create new render.yaml:**
```yaml
services:
  - type: web
    name: subz-scraper
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn new_app:app
    envVars:
      - key: TELEGRAM_BOT_TOKEN
        sync: false
      - key: TELEGRAM_CHAT_ID
        sync: false
      - key:CF_ACCOUNT_ID
        sync: false
      - key: CF_API_TOKEN
        sync: false
      - key: D1_DATABASE_ID
        sync: false
```

### 2. Commit and Push

```bash
git add new_scraper.py d1_database.py telegram_bot.py new_app.py
git commit -m "New clean implementation for subz.lk scraper"
git push origin main
```

### 3. Trigger Scrape

After deployment:
```bash
curl https://your-app.onrender.com/scrape
```

## API Endpoints

- `GET /` - Health check
- `GET /status` - Current scraper status
- `GET /scrape` - Start full scrape

## Database Schema

Simple clean table:
```sql
CREATE TABLE subtitles (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    title TEXT,
    filename TEXT,
    normalized_filename TEXT,
    file_id TEXT,
    file_size INTEGER,
    created_at TEXT
)
```

**No migrations, no old data!**

## Expected Behavior

1. First run creates empty database table
2. Crawls all pages (movies + TV shows)
3. Finds ALL subtitle URLs
4. Processes each one
5. Uploads to Telegram with captions
6. Subsequent runs only process NEW subtitles

## Differences from Old Code

| Old | New |
|-----|-----|
| Complex migration logic | Fresh database |
| Mixed baiscope + subz data | Only subz.lk |
| Stopped at duplicate pages | Crawls until 404 |
| Multiple source tracking | Single purpose |
| Complex state management | Simple URL & filename sets |
