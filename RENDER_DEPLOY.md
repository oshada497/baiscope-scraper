# 🚀 Render.com Deployment Guide

This guide will help you deploy the Subz.lk & Baiscope Scraper to Render.

## Option 1: Web Service (Recommended for 24/7 Monitoring)
This method runs the `app.py` server which:
1.  automatically checks for updates every 15 minutes.
2.  provides a web dashboard/API to check status.
3.  shows real-time logs of all scraping activity.

### Step 1: Push Code to GitHub
Ensure all your latest changes (including `scrape_subz_full.py` and `requirements.txt`) are pushed to your GitHub repository.

### Step 2: Create Web Service
1.  Log in to [Render Dashboard](https://dashboard.render.com/).
2.  Click **New +** -> **Web Service**.
3.  Connect your GitHub repository.
4.  Configure the service:
    *   **Name**: `subz-scraper-bot`
    *   **Runtime**: `Python 3`
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `gunicorn app:app --timeout 600 --access-logfile - --error-logfile -`
    *   **Instance Type**: `Starter` ($7/mo) is recommended for 24/7 uptime. Free tier will sleep after 15 minutes of inactivity.

### Step 3: Environment Variables
Go to the **Environment** tab and add these 5 keys:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | (Your Bot Token) |
| `TELEGRAM_CHAT_ID` | (Your Channel/Chat ID) |
| `CF_ACCOUNT_ID` | (Your Cloudflare Account ID) |
| `CF_API_TOKEN` | (Your Cloudflare API Token) |
| `D1_DATABASE_ID` | (Your D1 Database ID) |

### Step 4: Deploy
Click **Create Web Service**. Render will start the build.

---

## ⚡ How to Run the Initial Full Scrape
Since you are using the **Render Free Tier**, you do not have Shell access. 
However, I have built a special "Trigger URL" so you can start the full scrape directly from your browser.

### Step-by-Step Instructions
1.  Deploy the Web Service as described above.
2.  Wait for the service to be **Live**.
3.  Open your browser and visit this URL (replace with your actual Render URL):
    ```
    https://subz-scraper-bot.onrender.com/scrape/subz
    ```
4.  You will see a JSON response saying:
    ```json
    {
      "message": "Full scrape of subz.lk started",
      "note": "This will take several hours. Check /status for progress"
    }
    ```
5.  **That's it!** The scraper is now running in the background. 
    *   It will crawl all pages.
    *   It will save all new links to the database.
    *   It will start processing them.

### Important Note for Free Tier
On the Free Tier, Render might spin down your service if it's "inactive" for 15 minutes. 
*   **The Problem**: If the service sleeps, the background scrape might pause.
*   **The Fix**: Use a free uptime monitor (like UptimeRobot) to ping your main URL (`https://...onrender.com/`) every 10 minutes. This keeps it awake so the scraper can finish its job.

---

## 📜 Viewing Logs
Since we enabled detailed logging:
1.  Go to the **Logs** tab in Render.
2.  You will see real-time output like:
    ```text
    2026-01-12 18:30:05 - INFO - >>> STEP 1: CRAWLING <<<
    2026-01-12 18:30:10 - INFO - Page 1: Found 20 links, 5 new pending
    ...
    2026-01-12 18:45:00 - INFO - >>> STEP 2: PROCESSING QUEUE <<<
    2026-01-12 18:45:02 - INFO - Processing batch of 3 with 3 workers
    2026-01-12 18:45:05 - INFO - Uploaded to Telegram: Avengers_Endgame_Sinhala.srt
    ```

## ✅ Verification
Check your Telegram channel. You should see files appearing as the logs show "Uploaded".
