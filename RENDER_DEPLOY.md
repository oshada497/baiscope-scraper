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
    *   **Start Command**: `gunicorn app:app --timeout 600`
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
The web service is great for *monitoring new files*, but for the **first run** to scrape thousands of existing movies, you should run the dedicated script.

### Method A: Using Render Shell (Easiest)
1.  Wait for the Web Service to be "Live".
2.  Go to the **Shell** tab in your Render service dashboard.
3.  Run this command:
    ```bash
    python scrape_subz_full.py
    ```
4.  You will see the logs immediately in the terminal. It will crawl all categories and then process them. This is the **fastest** way.

### Method B: Using Cron Job (Alternative)
If you don't want a web server and just want the script to run repeatedly (e.g. every hour):
1.  Create a **Cron Job** instead of a Web Service.
2.  **Schedule**: `0 * * * *` (Runs every hour)
3.  **Command**: `python scrape_subz_full.py`
4.  This will run the full check every hour and exit when done.

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
