# Quick Deploy Guide: Render.com

## Step 1: Create Cloudflare API Token (5 minutes)

**You need a NEW token with D1 permissions** (your current one doesn't have D1 Edit access)

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Click **"Create Token"**
3. Click **"Get started"** next to "Create Custom Token"
4. Fill in:
   - **Token name**: `D1 Scraper Token`
   - **Permissions**: Click "Add more"
     - Select: **Account** → **D1** → **Edit**
     - Select: **Account** → **Account Settings** → **Read**
   - **Account Resources**: Include → Your account
5. Click **"Continue to summary"**
6. Click **"Create Token"**
7. **COPY THE TOKEN** - you'll need it in Step 3

## Step 2: Create Web Service on Render

1. Go to: https://dashboard.render.com/
2. Log in with your GitHub account
3. Click **"New +"** (top right)
4. Select **"Web Service"**

## Step 3: Connect GitHub Repository

1. **Find your repository**:
   - If you see `oshada497/baiscope-scraper` in the list → Click **"Connect"**
   - If not → Click **"Configure account"** → Grant Render access to the repo

2. **Configure the service**:

   **Service name**: `baiscope-subz-scraper` (or any name you like)
   
   **Runtime**: Select **Python 3**
   
   **Region**: Choose closest to you (or leave default)
   
   **Branch**: `main`
   
   **Build Command**: 
   ```
   pip install -r requirements.txt
   ```
   
   **Start Command**: 
   ```
   gunicorn app:app --timeout 600 --workers 1
   ```
   
   **Instance Type**: 
   - **Free** (for testing) - service will sleep after 15 min
   - **Starter** ($7/month) - recommended for 24/7 operation

## Step 4: Add Environment Variables

Scroll down to **"Environment Variables"** section. Click **"Add Environment Variable"** for each:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your channel/group chat ID |
| `CF_ACCOUNT_ID` | `573f9a28fb2a48c7c065c9fe6223429b` |
| `CF_API_TOKEN` | **Your NEW token from Step 1** |
| `D1_DATABASE_ID` | `2318c943-7efd-4dd5-97c1-36039621be59` |

**How to get Telegram credentials:**
- **Bot Token**: Message @BotFather on Telegram → `/newbot` → follow steps
- **Chat ID**: 
  - Add bot to your channel
  - Send a message in the channel
  - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
  - Look for `"chat":{"id":-1234567890}` ← that's your chat ID

## Step 5: Deploy!

1. Click **"Create Web Service"** (bottom of page)
2. Render will:
   - Clone your repo
   - Install dependencies
   - Start the app
   - This takes 2-3 minutes

3. **Wait for "Live"** status (green dot)

## Step 6: Initial Setup (One-time only)

Once deployed, your service URL will be: `https://baiscope-subz-scraper.onrender.com`

**Run full scrape of subz.lk ONCE** to populate database:

Open in browser:
```
https://baiscope-subz-scraper.onrender.com/scrape/subz
```

You'll see:
```json
{
  "message": "Full scrape of subz.lk started",
  "note": "This will take several hours. Check /status for progress"
}
```

**This runs in background**. The scraper will:
- Download ALL subtitles from subz.lk
- Upload to Telegram
- Store in D1 database
- Takes 2-6 hours depending on content

## Step 7: Monitor Progress

**Check status**:
```
https://baiscope-subz-scraper.onrender.com/status
```

**View logs**:
1. Go to Render dashboard
2. Click your service
3. Click **"Logs"** tab
4. See real-time progress

## Step 8: Automatic Monitoring (Starts Automatically!)

After deployment, the scraper **automatically**:
- Runs every 15 minutes
- Checks baiscope.lk for new subtitles
- Checks subz.lk for new subtitles
- Downloads and uploads to Telegram
- No action needed from you!

**You can manually trigger anytime**:
```
https://baiscope-subz-scraper.onrender.com/trigger
```

## Troubleshooting

### "Service is not live" or keeps restarting
- Check **Logs** tab for errors
- Verify all environment variables are correct
- Make sure API token has D1 Edit permission

### "No new subtitles found"
- Normal if there are no new posts
- Check Telegram to verify old subtitles were uploaded

### Free tier service sleeping
- Free tier sleeps after 15 min inactivity
- Upgrade to Starter ($7/mo) for 24/7 operation
- OR: Set up UptimeRobot to ping your service every 14 min

### Telegram rate limits
- App handles this automatically with backoff
- Just wait, it will resume

## API Endpoints Reference

Once deployed, you have these endpoints:

- **`/`** - Health check, service info
- **`/status`** - View scraper status and statistics
- **`/trigger`** - Manually trigger monitoring cycle
- **`/scrape/subz`** - Full scrape of subz.lk (use once)

## Success Checklist

- ✅ Cloudflare API token created with D1 Edit permission
- ✅ Render service created and deployed
- ✅ All environment variables added
- ✅ Service shows "Live" status (green)
- ✅ Visited `/scrape/subz` once for initial population
- ✅ Checked `/status` to see it's running
- ✅ Logs show monitoring cycles every 15 minutes
- ✅ Subtitles appearing in Telegram channel

## Costs

- **Render Free**: $0 (service sleeps, needs pinger)
- **Render Starter**: $7/month (recommended, 24/7 uptime)
- **Cloudflare D1**: Free (up to 5M reads/day)
- **Telegram**: Free

**Recommended total: $7/month for reliable 24/7 operation**

---

## Quick Commands Summary

```bash
# Check status
curl https://your-app.onrender.com/status

# Manual trigger
curl https://your-app.onrender.com/trigger

# Start full scrape (once)
curl https://your-app.onrender.com/scrape/subz
```

Replace `your-app` with your actual Render app name.

---

**Need help?** Check the detailed guide: [RENDER_DEPLOY.md](./RENDER_DEPLOY.md)
