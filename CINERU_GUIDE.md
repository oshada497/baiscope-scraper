# Cineru.lk Scraper - Cloudflare Bypass Guide

## How It Works

### Cloudflare Protection Bypass

Cineru.lk uses Cloudflare protection which blocks:
- Simple HTTP requests (curl, requests library)
- curl_cffi (browser impersonation)

**Solution: CloudScraper**

The `cloudscraper` library automatically:
1. Detects Cloudflare challenge pages
2. Solves JavaScript challenges
3. Handles browser fingerprinting
4. Maintains session cookies

```python
import cloudscraper

# Create scraper session
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'mobile': False
    }
)

# Use like normal requests
response = scraper.get('https://cineru.lk')
```

## Running the Scraper

### Local Test

```bash
cd C:\Users\oshada\.gemini\antigravity\scratch\baiscope-scraper
pip install cloudscraper
python cineru_scraper.py
```

### Deploy to Render

1. **Update requirements.txt** (already done)
   - Added `cloudscraper>=1.2.71`

2. **Choose deployment method:**

   **Option A: Standalone App**
   - Create separate Render service for cineru scraper
   - Start command: `python cineru_scraper.py`
   
   **Option B: Add to existing app**
   - Add cineru endpoint to `new_app.py`

### Option B: Add to Existing App (Recommended)

Update `new_app.py`:

```python
from cineru_scraper import CineruScraper

cineru_scraper = None

@app.route('/scrape/cineru')
def scrape_cineru():
    global worker_thread, is_running
    
    if is_running:
        return jsonify({'error': 'Scraper already running'}), 400
    
    def run_cineru():
        global is_running, cineru_scraper
        try:
            is_running = True
            cineru_scraper = CineruScraper()
            cineru_scraper.initialize()
            cineru_scraper.scrape_all()
        except Exception as e:
            logger.error(f"Cineru scraper error: {e}", exc_info=True)
        finally:
            is_running = False
    
    worker_thread = threading.Thread(target=run_cineru, daemon=True)
    worker_thread.start()
    
    return jsonify({'message': 'Cineru scraper started'})
```

## API Endpoints

After adding to app:

```
GET /scrape         # Scrape subz.lk
GET /scrape/cineru  # Scrape cineru.lk
GET /status         # Current status
```

## Database Tables

The scraper uses separate tables:

- `subtitles` - Subz.lk data
- `cineru_subtitles` - Cineru.lk data

This keeps data from different sources separate.

## Expected Behavior

```
=== STARTING CINERU.LK SCRAPE ===
Discovering categories...
Found 3 category pages: ['https://cineru.lk/category/movies', ...]

Crawling https://cineru.lk/category/movies...
Page 1: Found 48 links (48 new)
Page 2: Found 52 links (52 new)
...

=== DISCOVERY COMPLETE ===
Total new URLs: 847

Processing 847 cineru.lk subtitles...
✓ Uploaded: Spider-Man No Way Home 2021.zip
✓ Uploaded: The Batman 2022.zip
...
```

## Cloudflare Bypass Alternatives

If `cloudscraper` fails:

### Option 1: FlareSolverr (Proxy Service)
```bash
# Run FlareSolverr in Docker
docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest

# Then use in Python
import requests
response = requests.post('http://localhost:8191/v1', json={
    'cmd': 'request.get',
    'url': 'https://cineru.lk',
    'maxTimeout': 60000
})
```

### Option 2: Playwright (Full Browser)
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('https://cineru.lk')
    content = page.content()
```

## Troubleshooting

### "403 Forbidden" error
- Cloudflare is blocking the request
- Try increasing delays between requests
- Use rotating user agents

### "Challenge loop" error  
- Cloudflare updated their protection
- Update cloudscraper: `pip install --upgrade cloudscraper`
- Try FlareSolverr alternative

### Rate limiting
- Reduce worker threads (default: 2)
- Increase sleep time between requests
- Current: 2-4 seconds between subtitles

## Performance

- **Speed**: Slower than subz.lk (Cloudflare overhead)
- **Rate**: ~15-25 subtitles/hour
- **Safety**: Built-in delays prevent Cloudflare bans

## Next Steps

1. Test locally first
2. Deploy to Render
3. Trigger: `curl your-app.onrender.com/scrape/cineru`
4. Monitor progress via Telegram
