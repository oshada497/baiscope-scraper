# Deploying Baiscope Scraper (Zoom.lk + Subz.lk) to Render

This guide covers deploying the universal scraper to Render.com. The app now supports both `zoom.lk` and `subz.lk` in a single service without any V2Ray/VPN complexity.

## 1. Create Web Service
1.  Go to **Render Dashboard** > **New +** > **Web Service**.
2.  Connect your GitHub repository.
3.  **Name**: `baiscope-scraper` (or any name you like).
4.  **Region**: Any (e.g., Singapore, Frankfurt).
5.  **Branch**: `main`.
6.  **Runtime**: `Python 3`.

## 2. Build & Start Commands
*   **Build Command**:
    ```bash
    pip install -r requirements.txt
    ```
*   **Start Command**:
    ```bash
    gunicorn app:app
    ```

## 3. Environment Variables
Add the following variables under the **Environment** tab:

| Variable | Value Description |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_CHAT_ID` | Channel ID (e.g., `-100xxxx`) |
| `CF_ACCOUNT_ID` | Cloudflare Account ID |
| `CF_API_TOKEN` | Cloudflare API Token (Must have D1 Edit permissions) |
| `D1_DATABASE_ID` | Your D1 Database ID |
| `PYTHON_VERSION` | `3.11.0` (Recommended) |

## 4. How to Use
Once deployed, use these URLs:

### Status
*   **Check Status**: `https://your-app.onrender.com/status`
    *   Shows current job, running state, and database counts for both Zoom and Subz.

### Zoom.lk
*   **Deep Scrape (Full History)**: `https://your-app.onrender.com/scrape/zoom`
    *   Starts crawling from Page 1 of Movies and TV Series.
    *   Resumes automatically if interrupted (checks D1 state).
*   **Quick Check (Monitoring)**: `https://your-app.onrender.com/trigger/zoom`
    *   Checks only the first page for new items.

### Subz.lk
*   **Deep Scrape**: `https://your-app.onrender.com/scrape/subz`
*   **Quick Check**: `https://your-app.onrender.com/trigger/subz`

> [!TIP]
> Use **cron-job.org** to ping `/trigger/zoom` and `/trigger/subz` every 15-30 minutes to keep the service awake and fully automated.
