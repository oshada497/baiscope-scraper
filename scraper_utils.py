"""
Shared utilities for subtitle scrapers - Cloudflare D1, Telegram, and helper functions
"""
from curl_cffi import requests as curl_requests
import os
import time
import logging
import io
import json
import requests
import threading
import re

logger = logging.getLogger(__name__)


def normalize_filename(filename):
    """
    Normalize filename for matching - strips watermarks like (@SinhalaSubtitles_Rezoth) 
    and other common patterns before normalizing for comparison.
    """
    if not filename:
        return ""
    name = filename
    
    # Remove common Telegram channel watermark patterns
    watermark_patterns = [
        r'\(@[^)]+\)\s*',           # (@SinhalaSubtitles_Rezoth) with optional space
        r'@SinhalaSubtitles[_\-]?Rezoth[_\-]?\s*',  # @SinhalaSubtitles_Rezoth or variations
        r'@[A-Za-z0-9_]+[_\-]\s*',  # Generic @username_ pattern at start
        r'\s*\(@[^)]+\)',           # (@watermark) at end
        r'^\s*@[A-Za-z0-9_]+\s+',   # @username at start with space
    ]
    
    for pattern in watermark_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Convert to lowercase
    name = name.lower()
    
    # Remove file extension
    name = re.sub(r'\.[^.]+$', '', name)
    
    # Remove all special characters except alphanumerics and Sinhala characters
    name = re.sub(r'[^a-z0-9\u0D80-\u0DFF]', '', name)
    
    return name


def extract_movie_info(filename):
    """
    Extract movie/show name, year, and episode info for fuzzy matching.
    Returns (base_name, year, season, episode) tuple.
    """
    if not filename:
        return ("", None, None, None)
    
    # First normalize the filename to remove watermarks
    name = filename
    watermark_patterns = [
        r'\(@[^)]+\)\s*',
        r'@SinhalaSubtitles[_\-]?Rezoth[_\-]?\s*',
        r'@[A-Za-z0-9_]+[_\-]\s*',
        r'\s*\(@[^)]+\)',
        r'^\s*@[A-Za-z0-9_]+\s+',
    ]
    for pattern in watermark_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Remove extension
    name = re.sub(r'\.[^.]+$', '', name)
    
    # Extract year (4 digits that look like a year)
    year_match = re.search(r'[\.\-_\s\(]?(19[89]\d|20[0-2]\d)[\.\-_\s\)]?', name)
    year = year_match.group(1) if year_match else None
    
    # Extract season and episode (S01E01 or similar patterns)
    episode_match = re.search(r'[Ss](\d{1,2})[Ee](\d{1,2})', name)
    season = episode_match.group(1) if episode_match else None
    episode = episode_match.group(2) if episode_match else None
    
    # Get the base name (before year or episode info)
    base_name = name.lower()
    # Remove year and episode info for base comparison
    base_name = re.sub(r'[\.\-_\s\(]?(19[89]\d|20[0-2]\d)[\.\-_\s\)]?.*', '', base_name)
    base_name = re.sub(r'[Ss]\d{1,2}[Ee]\d{1,2}.*', '', base_name)
    base_name = re.sub(r'[^a-z0-9\u0D80-\u0DFF]', '', base_name)
    
    return (base_name, year, season, episode)


class CloudflareD1:
    def __init__(self, account_id, api_token, database_id):
        self.account_id = account_id
        self.api_token = api_token
        self.database_id = database_id
        self.base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.enabled = bool(account_id and api_token and database_id)
        
        self.enabled = bool(account_id and api_token and database_id)
        logger.info(f"D1 initialized. Enabled: {self.enabled} (Acc: {bool(account_id)}, Token: {bool(api_token)}, DB: {bool(database_id)})")
        
        if self.enabled:
            self._init_tables()
    
    def _init_tables(self):
        try:
            self.execute("""
                CREATE TABLE IF NOT EXISTS discovered_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    category TEXT,
                    page INTEGER,
                    source TEXT DEFAULT 'subz',
                    status TEXT DEFAULT 'pending',
                    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS processed_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    success INTEGER DEFAULT 0,
                    title TEXT,
                    source TEXT DEFAULT 'subz',
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS scraper_state (
                    id INTEGER PRIMARY KEY,
                    current_category TEXT,
                    current_page INTEGER,
                    source TEXT DEFAULT 'subz',
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS telegram_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id TEXT UNIQUE NOT NULL,
                    file_unique_id TEXT,
                    filename TEXT,
                    normalized_filename TEXT,
                    file_size INTEGER,
                    title TEXT,
                    source_url TEXT,
                    category TEXT,
                    source TEXT DEFAULT 'subz',
                    message_id INTEGER,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Try to add columns if they don't exist (migrations)
            schema_updates = [
                "ALTER TABLE scraper_state ADD COLUMN source TEXT DEFAULT 'subz'"
            ]
            
            # Try to add columns if they don't exist (migrations)
            for sql in schema_updates:
                try:
                    self.execute(sql, log_error=False)
                except Exception:
                    # Column likely exists, ignore error to keep logs clean
                    pass
            
            # Create indexes
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_normalized_filename ON telegram_files(normalized_filename)",
                "CREATE INDEX IF NOT EXISTS idx_source ON telegram_files(source)",
                "CREATE INDEX IF NOT EXISTS idx_source_urls ON processed_urls(source)",
                "CREATE INDEX IF NOT EXISTS idx_pending_urls ON discovered_urls(status, source)"
            ]
            
            for sql in indexes:
                self.execute(sql, log_error=False)
            
            logger.info("D1 database tables initialized and migrated to dedicated 'subz' source")
        except Exception as e:
            logger.error(f"Failed to initialize D1 tables: {e}")
    
    def execute(self, sql, params=None, log_error=True):
        if not self.enabled:
            return None
            
        try:
            payload = {"sql": sql}
            if params:
                payload["params"] = params
            
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            data = response.json()
            
            if data.get("success"):
                return data.get("result", [])
            else:
                if log_error:
                    logger.error(f"D1 query error: {data.get('errors')}")
                return None
        except Exception as e:
            if log_error:
                logger.error(f"D1 execute error: {e}")
            return None
    
    def add_discovered_url(self, url, category="", page=0, source="subz"):
        return self.execute(
            "INSERT OR IGNORE INTO discovered_urls (url, category, page, source, status) VALUES (?, ?, ?, ?, 'pending')",
            [url, category, page, source]
        )
    
    def get_pending_urls(self, limit=10, source="subz"):
        """Get a list of pending URLs to process"""
        result = self.execute(
            "SELECT url, category FROM discovered_urls WHERE status = 'pending' AND source = ? LIMIT ?", 
            [source, limit]
        )
        if result and len(result) > 0:
            return [row for row in result[0].get("results", [])]
        return []
        
    def update_url_status(self, url, status):
        """Update status of a discovered URL (pending, processing, completed, failed)"""
        return self.execute(
            "UPDATE discovered_urls SET status = ? WHERE url = ?",
            [status, url]
        )

    def add_processed_url(self, url, success=False, title="", source="subz"):
        # Update both tables - mark as completed in discovered, add to processed
        self.update_url_status(url, 'completed' if success else 'failed')
        
        return self.execute(
            "INSERT OR REPLACE INTO processed_urls (url, success, title, source, processed_at) VALUES (?, ?, ?, ?, datetime('now'))",
            [url, 1 if success else 0, title[:200] if title else "", source]
        )
    
    def is_url_processed(self, url):
        result = self.execute("SELECT 1 FROM processed_urls WHERE url = ?", [url])
        if result and len(result) > 0:
            results = result[0].get("results", [])
            return len(results) > 0
        return False
    
    def get_all_processed_urls(self, source=None):
        if source:
            result = self.execute("SELECT url FROM processed_urls WHERE source = ?", [source])
        else:
            result = self.execute("SELECT url FROM processed_urls")
        if result and len(result) > 0:
            return set(row.get("url", "") for row in result[0].get("results", []))
        return set()
    
    def get_discovered_urls_count(self, source=None):
        if source:
            result = self.execute("SELECT COUNT(*) as count FROM discovered_urls WHERE source = ?", [source])
        else:
            result = self.execute("SELECT COUNT(*) as count FROM discovered_urls")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0
    
    def get_pending_count(self, source=None):
        if source:
            result = self.execute("SELECT COUNT(*) as count FROM discovered_urls WHERE status = 'pending' AND source = ?", [source])
        else:
            result = self.execute("SELECT COUNT(*) as count FROM discovered_urls WHERE status = 'pending'")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0

    def get_processed_urls_count(self, source=None):
        if source:
            result = self.execute("SELECT COUNT(*) as count FROM processed_urls WHERE source = ?", [source])
        else:
            result = self.execute("SELECT COUNT(*) as count FROM processed_urls")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0
    
    def save_state(self, category, page, source="subz"):
        return self.execute(
            "INSERT OR REPLACE INTO scraper_state (id, current_category, current_page, source, last_updated) VALUES (?, ?, ?, ?, datetime('now'))",
            [hash(source) % 1000000, category, page, source]  # Use hash of source as id
        )
    
    def get_state(self, source="subz"):
        result = self.execute("SELECT current_category, current_page FROM scraper_state WHERE source = ?", [source])
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("current_category", ""), results[0].get("current_page", 1)
        return None, None
    
    def file_exists_by_normalized_name(self, normalized_filename):
        result = self.execute(
            "SELECT 1 FROM telegram_files WHERE normalized_filename = ?",
            [normalized_filename]
        )
        if result and len(result) > 0:
            return len(result[0].get("results", [])) > 0
        return False
    
    def get_all_normalized_filenames(self, source=None):
        if source:
            result = self.execute("SELECT normalized_filename FROM telegram_files WHERE normalized_filename IS NOT NULL AND source = ?", [source])
        else:
            result = self.execute("SELECT normalized_filename FROM telegram_files WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get("normalized_filename", "") for row in result[0].get("results", []) if row.get("normalized_filename"))
        return set()
    
    def save_telegram_file_with_normalized(self, file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, category, message_id, source="subz"):
        return self.execute(
            """INSERT OR REPLACE INTO telegram_files 
               (file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, category, source, message_id, uploaded_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            [file_id, file_unique_id, filename, normalized_filename, file_size, title[:200] if title else "", 
             source_url[:500] if source_url else "", category or "", source, message_id]
        )


class TelegramUploader:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.enabled = bool(bot_token and chat_id)
        self.last_request_time = 0
        # Increased delays for safety and to prevent "Flood Wait" errors
        self.min_delay = 1.0 
        self.rate_limit_delay = 2.0
        self.consecutive_429s = 0
        
    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed)
        
        if self.consecutive_429s > 0:
            extra_delay = self.rate_limit_delay * (2 ** min(self.consecutive_429s, 5))
            logger.info(f"Rate limit cooldown: waiting {extra_delay:.1f}s")
            time.sleep(extra_delay)
    
    def send_message(self, message, retries=3):
        if not self.enabled:
            return False
            
        for attempt in range(retries):
            self._wait_for_rate_limit()
            try:
                url = f"{self.base_url}/sendMessage"
                data = {
                    'chat_id': self.chat_id,
                    'text': message,
                    'parse_mode': 'HTML'
                }
                response = requests.post(url, data=data, timeout=30)
                self.last_request_time = time.time()
                
                if response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    self.consecutive_429s += 1
                    logger.warning(f"Telegram rate limited! Retry after {retry_after}s (attempt {attempt + 1})")
                    time.sleep(retry_after + 1)
                    continue
                    
                if response.status_code == 200:
                    self.consecutive_429s = max(0, self.consecutive_429s - 1)
                    return True
                    
                logger.warning(f"Telegram message failed: {response.status_code} - {response.text}")
                
            except Exception as e:
                logger.warning(f"Failed to send Telegram message: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    
        return False
    
    def send_document(self, file_content, filename, caption=None, retries=5):
        if not self.enabled:
            return None
            
        for attempt in range(retries):
            self._wait_for_rate_limit()
            try:
                url = f"{self.base_url}/sendDocument"
                
                mime_type = 'application/x-subrip'
                if filename.lower().endswith('.zip'):
                    mime_type = 'application/zip'
                elif filename.lower().endswith('.rar'):
                    mime_type = 'application/x-rar-compressed'
                
                files = {
                    'document': (filename, io.BytesIO(file_content), mime_type)
                }
                data = {
                    'chat_id': self.chat_id
                }
                if caption:
                    data['caption'] = caption[:1024]
                    data['parse_mode'] = 'HTML'
                
                response = requests.post(url, data=data, files=files, timeout=60)
                self.last_request_time = time.time()
                
                if response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    self.consecutive_429s += 1
                    logger.warning(f"Telegram rate limited on upload! Retry after {retry_after}s (attempt {attempt + 1})")
                    time.sleep(retry_after + 2)
                    continue
                    
                if response.status_code == 200:
                    self.consecutive_429s = max(0, self.consecutive_429s - 1)
                    logger.info(f"Uploaded to Telegram: {filename}")
                    
                    result = response.json().get('result', {})
                    document = result.get('document', {})
                    return {
                        'file_id': document.get('file_id', ''),
                        'file_unique_id': document.get('file_unique_id', ''),
                        'file_size': document.get('file_size', 0),
                        'message_id': result.get('message_id', 0),
                        'filename': filename
                    }
                    
                logger.warning(f"Telegram upload failed: {response.status_code} - {response.text}")
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Telegram upload timeout for {filename} (attempt {attempt + 1})")
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Failed to upload to Telegram: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    
        return None


class ProgressTracker:
    def __init__(self, telegram_uploader, interval=120):
        self.notifier = telegram_uploader
        self.interval = interval
        self.total_found = 0
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.start_time = None
        self.running = False
        self.thread = None
        self.current_page = 0
        self.current_category = ""
        
    def start(self, total_found):
        self.total_found = total_found
        self.start_time = time.time()
        self.running = True
        self.thread = threading.Thread(target=self._notification_loop, daemon=True)
        self.thread.start()
        self.notifier.send_message(
            f"<b>Scraper Started</b>\n"
            f"Total subtitles to process: {total_found}"
        )
        
    def update(self, success=True):
        self.processed += 1
        if success:
            self.success += 1
        else:
            self.failed += 1
            
    def update_page(self, category, page):
        self.current_category = category
        self.current_page = page
            
    def stop(self):
        self.running = False
        elapsed = time.time() - self.start_time if self.start_time else 0
        hours, remainder = divmod(int(elapsed), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.notifier.send_message(
            f"<b>Scraping Complete!</b>\n"
            f"Processed: {self.processed}/{self.total_found}\n"
            f"Success: {self.success}\n"
            f"Failed: {self.failed}\n"
            f"Time: {hours}h {minutes}m {seconds}s"
        )
        
    def _notification_loop(self):
        while self.running:
            time.sleep(self.interval)
            if self.running and self.total_found > 0:
                elapsed = time.time() - self.start_time
                hours, remainder = divmod(int(elapsed), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                rate = self.processed / (elapsed / 60) if elapsed > 0 else 0
                remaining = self.total_found - self.processed
                eta_minutes = remaining / rate if rate > 0 else 0
                eta_hours, eta_mins = divmod(int(eta_minutes), 60)
                
                # Get pending count from D1 if possible, otherwise use local tracking
                self.notifier.send_message(
                    f"<b>Scraper Progress</b>\n"
                    f"Category: {self.current_category}\n"
                    f"Page: {self.current_page}\n"
                    f"Processed: {self.processed}/{self.total_found} ({(self.processed/self.total_found*100):.1f}%)\n"
                    f"Success: {self.success} | Failed: {self.failed}\n"
                    f"Rate: {rate:.1f}/min\n"
                    f"Elapsed: {hours}h {minutes}m\n"
                    f"ETA: ~{eta_hours}h {eta_mins}m"
                )
