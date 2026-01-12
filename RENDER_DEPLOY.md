# 🚀 Subz.lk Dedicated Scraper - Deployment Guide

This repository is dedicated to 24/7 monitoring and scraping of **Subz.lk** subtitles.

## 1. Quick Start (Web Service)

1.  Create a **New Web Service** on Render.
2.  Connect this GitHub repository.
3.  **Runtime**: `Python 3`
4.  **Build Command**: `pip install -r requirements.txt`
5.  **Start Command**: `gunicorn app:app --timeout 600`
6.  **Add Environment Variables**:
    *   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
    *   `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `D1_DATABASE_ID`

## 2. Status & Control

| Endpoint | Action |
| :--- | :--- |
| `/status` | Check current scraping stats and D1 records. |
| `/trigger`| Manually check for new subtitles immediately. |
| `/scrape/subz` | Start a full background crawl of all history. |
| `/debug` | View internal thread and memory state. |

## 3. Operations

- **Automatic Monitoring**: The service checks for new subtitles every 15 minutes.
- **Background Persistence**: All progress is stored in Cloudflare D1. Even if the server restarts, it remembers what was processed.
- **Worker Isolation**: The project uses a single-worker Gunicorn config to ensure stats are consistent.
