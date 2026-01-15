# FlareSolverr Deployment Guide

Cineru.lk's Cloudflare protection is too strong for basic `cloudscraper`. You need **FlareSolverr** - a service that uses a real browser.

## Option 1: Deploy FlareSolverr on Render (Free)

### Step 1: Create New Render Service

1. Go to Render Dashboard
2. Click **New** → **Web Service**
3. Connect to Docker image:
   - **Image URL**: `ghcr.io/flaresolverr/flaresolverr:latest`
4. Configure:
   - **Name**: `flaresolverr`
   - **Region**: Same as your scraper
   - **Instance Type**: Free
5. Environment Variables:
   - `LOG_LEVEL` = `info`
6. Click **Create Web Service**

### Step 2: Get FlareSolverr URL

After deployment, you'll get a URL like:
```
https://flaresolverr-XXXX.onrender.com
```

### Step 3: Add Environment Variable to Scraper

In your **baiscope-scraper** service:

1. Settings → Environment
2. Add new variable:
   - **Key**: `FLARESOLVERR_URL`
   - **Value**: `https://flaresolverr-XXXX.onrender.com/v1`

### Step 4: Update Code

Replace `cineru_scraper.py` with `cineru_scraper_v2.py`:

```bash
cd C:\Users\oshada\.gemini\antigravity\scratch\baiscope-scraper
git rm cineru_scraper.py
git mv cineru_scraper_v2.py cineru_scraper.py
git add cineru_scraper.py
git commit -m "Switch to FlareSolverr for cineru bypass"
git push origin main
```

Or update `new_app.py` to use `CineruScraperV2`.

---

## Option 2: Run FlareSolverr Locally (Testing)

```bash
docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest
```

Then set:
```
FLARESOLVERR_URL=http://localhost:8191/v1
```

---

## Option 3: Simple Alternative - Skip Cineru for Now

Since cineru.lk has very strong Cloudflare protection that requires a full browser, you have options:

### A. Focus on Subz.lk Only
- Subz.lk works perfectly (no Cloudflare)
- Continue using `/scrape` endpoint
- Skip cineru until better solution

### B. Manual Cineru Download
- Manually download cineru.lk subtitles
- Upload them to Telegram yourself
- Not scalable but works

---

## Recommended Next Steps

**Easiest**: Skip cineru.lk for now, focus on subz.lk which works great.

**Best**: Deploy FlareSolverr on Render (takes 5 minutes, completely free).

**Alternative**: Try different subtitle site that doesn't have Cloudflare.

---

## Why FlareSolverr Works

```
Regular Request → Cloudflare blocks (403)
CloudScraper → Cloudflare blocks (403)
FlareSolverr → Uses real Chrome browser → Passes checks ✅
```

FlareSolverr runs an actual Chrome browser that:
- Executes JavaScript
- Solves CAPTCHA challenges  
- Passes browser fingerprint checks
- Returns clean HTML to your scraper

---

Want me to help you:
1. Deploy FlareSolverr on Render?
2. Skip cineru and focus on subz.lk?
3. Find alternative subtitle sites without Cloudflare?
