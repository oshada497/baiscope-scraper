# Subtitle Scraper Bot

## Overview

This is a Python-based web scraper that monitors subtitle websites (primarily biscope.lk) for new Sinhala subtitle files and sends notifications via Telegram. The bot tracks processed files in a SQLite database to avoid duplicate notifications.

**Core functionality:**
- Scrapes subtitle websites for new subtitle files (.srt, .zip, .rar, .7z)
- Detects and filters video files vs subtitle files
- Stores processed file URLs in SQLite to prevent duplicate processing
- Sends Telegram notifications when new subtitles are found

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Structure
- **Single-file Python application**: Main logic resides in `main.py` with database operations separated into `database.py`
- **Synchronous processing**: Uses standard requests library for HTTP calls and sequential processing

### Web Scraping
- **BeautifulSoup4** for HTML parsing
- **Requests** library for HTTP operations
- User-agent spoofing to avoid bot detection
- File type detection based on URL extensions

### Data Storage
- **SQLite database** (`subtitles.db`) for persistence
- Single table `processed_subtitles` tracking:
  - File URL (unique identifier)
  - Title, source, file type
  - Processing timestamp
- Database initialized on application startup

### Notification System
- **Telegram Bot API** via pyTelegramBotAPI library
- Environment variables for configuration:
  - `TELEGRAM_TOKEN`: Bot authentication token
  - `TELEGRAM_CHAT_ID`: Target chat for notifications
- Graceful handling when Telegram credentials are not configured

### File Organization
- Downloads stored in `downloads/` directory
- Supports subtitle formats: .srt, .zip, .rar, .7z
- Filters out video files: .mp4, .mkv, .avi, .mov, .webm, .flv, .m3u8, .ts

## External Dependencies

### Third-Party Services
- **Telegram Bot API**: For sending notifications about new subtitles
- **biscope.lk**: Primary source website for Sinhala subtitles

### Python Packages
- `beautifulsoup4`: HTML parsing and web scraping
- `requests`: HTTP client for web requests
- `pytelegrambotapi`: Telegram Bot API wrapper

### Database
- **SQLite**: Local file-based database, no external database service required

### Environment Variables Required
- `TELEGRAM_TOKEN`: Telegram bot token from BotFather
- `TELEGRAM_CHAT_ID`: Chat ID where notifications should be sent