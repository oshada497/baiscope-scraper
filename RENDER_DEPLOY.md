# Deployment Guide for Render.com

## Quick Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

## Manual Deployment Steps

### 1. Push Code to GitHub

```bash
cd baiscope-scraper
git add .
git commit -m "Add subz.lk scraper support"
git push origin main
```

### 2. Create New Web Service on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +" → "Web Service"**
3. Connect your GitHub repository: `oshada497/baiscope-scraper`
4. Configure the service:

**Settings:**
- **Name**: `baiscope-subz-scraper`
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app --timeout 600 --workers 1`
- **Instance Type**: Free or Starter (recommended)

### 3. Set Environment Variables

Add these in Render's Environment section:

| Key | Value | Notes |
|-----|-------|-------|
| `TELEGRAM_BOT_TOKEN` | `your_bot_token` | Get from @BotFather |
| `TELEGRAM_CHAT_ID` | `your_chat_id` | Your channel/group ID |
| `CF_ACCOUNT_ID` | `your_account_id` | Optional: Cloudflare account |
| `CF_API_TOKEN` | `your_api_token` | Optional: Cloudflare API token |
| `D1_DATABASE_ID` | `your_database_id` | Optional: D1 database ID |

### 4. Deploy

Click **"Create Web Service"** and Render will automatically deploy.

## How It Works on Render

The Flask app (`app.py`) runs continuously and:

1. **Automatic Monitoring**: Checks both sites every 15 minutes
2. **REST API**: Provides endpoints for manual triggers and status
3. **Background Thread**: Runs monitoring without blocking web requests
4. **Health Checks**: Render pings `/` to keep service alive

## API Endpoints

Once deployed, your service will be available at `https://baiscope-subz-scraper.onrender.com`

### GET /
Health check - Returns service info

```bash
curl https://baiscope-subz-scraper.onrender.com/
```

### GET /status
View current scraper status and statistics

```bash
curl https://baiscope-subz-scraper.onrender.com/status
```

Response:
```json
{
  "monitoring_interval": "15 minutes",
  "scrapers": {
    "baiscope": {
      "status": "idle",
      "last_run": "2026-01-12 17:00:00",
      "processed": 1250,
      "success": 15,
      "d1_stats": {
        "discovered": 10542,
        "processed": 9856
      }
    },
    "subz": {
      "status": "idle",
      "last_run": "2026-01-12 17:00:00",
      "processed": 320,
      "success": 24,
      "d1_stats": {
        "discovered": 580,
        "processed": 320
      }
    }
  }
}
```

### GET /trigger
Manually trigger monitoring cycle (checks both sites immediately)

```bash
curl https://baiscope-subz-scraper.onrender.com/trigger
```

### GET /scrape/subz
Start full scrape of subz.lk (run once for initial setup)

```bash
curl https://baiscope-subz-scraper.onrender.com/scrape/subz
```

**Note**: This takes several hours. Use this ONCE when first deploying to populate the database with all existing subz.lk subtitles.

## Monitoring Schedule

The app automatically runs monitoring every **15 minutes**:

- **00:00, 00:15, 00:30, 00:45...** → Check both sites for new subtitles
- Processes only NEW content (skips duplicates via D1 database)
- Uploads to Telegram automatically
- Sends progress notifications

## Logs

View real-time logs in Render Dashboard:
1. Go to your service
2. Click **"Logs"** tab
3. See monitoring cycles, file uploads, and any errors

## Free Tier Limitations

Render free tier restarts services after 15 minutes of inactivity. To keep running:

1. **Use Starter plan** ($7/month) - recommended for 24/7 operation
2. **External pinger**: Use a service like UptimeRobot to ping your `/` endpoint every 14 minutes

## Troubleshooting

### Service Keeps Sleeping

**Problem**: Free tier services sleep after 15 min inactivity

**Solution**: 
- Upgrade to Starter plan, OR
- Set up UptimeRobot to ping your service every 14 minutes

### Monitoring Not Running

**Problem**: No new subtitles being processed

**Solution**:
- Check logs for errors
- Visit `/status` to see last run time
- Manually trigger with `/trigger` endpoint

### Database Errors

**Problem**: D1 connection failing

**Solution**:
- Verify CF credentials in environment variables
- Check D1 database is accessible
- Service will fallback to local storage if D1 unavailable

### Telegram Rate Limits

**Problem**: Too many requests to Telegram

**Solution**:
- App has built-in rate limiting
- Wait for backoff period (shown in logs)
- Reduce worker count if needed

## Alternative: Render Cron Jobs

If you don't need 24/7 web service, use Render Cron:

1. Change service type to **Cron Job**
2. Set schedule: `*/15 * * * *` (every 15 minutes)
3. Set command: `python monitor_both.py`

**Pros**: Free tier sufficient, runs only when needed
**Cons**: No web API, no real-time status

## Production Recommendations

For production use:

1. ✅ Use **Starter plan** ($7/mo) for reliability
2. ✅ Enable **Auto-Deploy** from main branch
3. ✅ Set up **Cloudflare D1** for proper duplicate tracking
4. ✅ Configure **Telegram notifications** for monitoring
5. ✅ Monitor logs regularly for errors
6. ✅ Run full scrape once: `curl /scrape/subz`

## Cost Estimate

- **Free**: Works but services sleep (requires pinger)
- **Starter ($7/mo)**: Recommended - 24/7 operation
- **Cloudflare D1**: Free tier (first 5M reads/day)
- **Telegram Bot**: Free

**Total**: $7/month for reliable 24/7 monitoring
