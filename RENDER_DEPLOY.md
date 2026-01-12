# Deploying the Subz.lk Dedicated Scraper (v2)

The scraper has been completely rewritten for maximum stability, resume-capability, and performance on Render's Free Tier.

## 1. Environment Variables
Ensure these are set in your Render dashboard:
- `TELEGRAM_BOT_TOKEN`: Your BotFather token.
- `TELEGRAM_CHAT_ID`: Your target chat ID.
- `CF_ACCOUNT_ID`: Cloudflare Account ID.
- `CF_API_TOKEN`: Cloudflare API Token (D1 Edit permissions).
- `D1_DATABASE_ID`: The ID of your D1 database.

## 2. Startup Command
Set the **Start Command** to:
```bash
gunicorn app:app --config gunicorn.conf.py
```

## 3. How to Use
- **Manual Check**: Hit `https://your-app.onrender.com/trigger` for a quick homepage check.
- **Full History Scrape**: Hit `https://your-app.onrender.com/scrape/subz`.
  - **Resume Support**: If Render restarts the app, just hit this URL again. The bot will check D1 and pick up exactly where it left off (e.g., Category: Movies, Page: 50).
- **Status Monitoring**: Visit `https://your-app.onrender.com/status` to see current progress and database counts.

> [!TIP]
> Use a service like **cron-job.org** to ping `/trigger` every 15 minutes to keep the service awake and check for new subtitles automatically.
