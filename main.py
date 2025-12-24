from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import zipfile
import io
import json
from urllib.parse import urljoin
import random
import requests
import threading
import signal
import re
from concurrent.futures import ThreadPoolExecutor, as_completed


def normalize_filename(filename):
    """
    Normalize filename for matching - strips watermarks like (@SinhalaSubtitles_Rezoth) 
    and other common patterns before normalizing for comparison.
    """
    if not filename:
        return ""
    name = filename
    
    # Remove common Telegram channel watermark patterns
    # Patterns like: (@SinhalaSubtitles_Rezoth), @SinhalaSubtitles_Rezoth_, etc.
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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
                    discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS processed_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    success INTEGER DEFAULT 0,
                    title TEXT,
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("""
                CREATE TABLE IF NOT EXISTS scraper_state (
                    id INTEGER PRIMARY KEY,
                    current_category TEXT,
                    current_page INTEGER,
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
                    message_id INTEGER,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("ALTER TABLE telegram_files ADD COLUMN normalized_filename TEXT")
            
            self.execute("CREATE INDEX IF NOT EXISTS idx_normalized_filename ON telegram_files(normalized_filename)")
            
            logger.info("D1 database tables initialized")
        except Exception as e:
            logger.error(f"Failed to initialize D1 tables: {e}")
    
    def execute(self, sql, params=None):
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
                logger.error(f"D1 query error: {data.get('errors')}")
                return None
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None
    
    def add_discovered_url(self, url, category="", page=0):
        return self.execute(
            "INSERT OR IGNORE INTO discovered_urls (url, category, page) VALUES (?, ?, ?)",
            [url, category, page]
        )
    
    def add_processed_url(self, url, success=False, title=""):
        return self.execute(
            "INSERT OR REPLACE INTO processed_urls (url, success, title, processed_at) VALUES (?, ?, ?, datetime('now'))",
            [url, 1 if success else 0, title[:200] if title else ""]
        )
    
    def is_url_processed(self, url):
        result = self.execute("SELECT 1 FROM processed_urls WHERE url = ?", [url])
        if result and len(result) > 0:
            results = result[0].get("results", [])
            return len(results) > 0
        return False
    
    def get_all_processed_urls(self):
        result = self.execute("SELECT url FROM processed_urls")
        if result and len(result) > 0:
            return set(row.get("url", "") for row in result[0].get("results", []))
        return set()
    
    def get_discovered_urls_count(self):
        result = self.execute("SELECT COUNT(*) as count FROM discovered_urls")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0
    
    def get_processed_urls_count(self):
        result = self.execute("SELECT COUNT(*) as count FROM processed_urls")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0
    
    def save_state(self, category, page):
        return self.execute(
            "INSERT OR REPLACE INTO scraper_state (id, current_category, current_page, last_updated) VALUES (1, ?, ?, datetime('now'))",
            [category, page]
        )
    
    def get_state(self):
        result = self.execute("SELECT current_category, current_page FROM scraper_state WHERE id = 1")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("current_category", ""), results[0].get("current_page", 1)
        return None, None
    
    def save_telegram_file(self, file_id, file_unique_id, filename, file_size, title, source_url, category, message_id):
        return self.execute(
            """INSERT OR REPLACE INTO telegram_files 
               (file_id, file_unique_id, filename, file_size, title, source_url, category, message_id, uploaded_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            [file_id, file_unique_id, filename, file_size, title[:200] if title else "", 
             source_url[:500] if source_url else "", category or "", message_id]
        )
    
    def get_telegram_files_count(self):
        result = self.execute("SELECT COUNT(*) as count FROM telegram_files")
        if result and len(result) > 0:
            results = result[0].get("results", [])
            if results:
                return results[0].get("count", 0)
        return 0
    
    def get_telegram_file_by_title(self, title):
        result = self.execute("SELECT * FROM telegram_files WHERE title LIKE ?", [f"%{title}%"])
        if result and len(result) > 0:
            return result[0].get("results", [])
        return []
    
    def file_exists_by_normalized_name(self, normalized_filename):
        result = self.execute(
            "SELECT 1 FROM telegram_files WHERE normalized_filename = ?",
            [normalized_filename]
        )
        if result and len(result) > 0:
            return len(result[0].get("results", [])) > 0
        return False
    
    def get_all_normalized_filenames(self):
        result = self.execute("SELECT normalized_filename FROM telegram_files WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get("normalized_filename", "") for row in result[0].get("results", []) if row.get("normalized_filename"))
        return set()
    
    def save_telegram_file_with_normalized(self, file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, category, message_id):
        return self.execute(
            """INSERT OR REPLACE INTO telegram_files 
               (file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, category, message_id, uploaded_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            [file_id, file_unique_id, filename, normalized_filename, file_size, title[:200] if title else "", 
             source_url[:500] if source_url else "", category or "", message_id]
        )


class TelegramUploader:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.enabled = bool(bot_token and chat_id)
        self.last_request_time = 0
        self.min_delay = 0.1
        self.rate_limit_delay = 1.0
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
            f"<b>Baiscope Scraper Started</b>\n"
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


class BaiscopeScraperTelegram:
    def __init__(self, telegram_token, telegram_chat_id, 
                 cf_account_id=None, cf_api_token=None, d1_database_id=None,
                 batch_size=50):
        self.base_url = 'https://www.baiscope.lk'
        self.batch_size = batch_size
        self.state_dir = 'scraper_state'
        self.state_file = f'{self.state_dir}/progress.json'
        
        os.makedirs(self.state_dir, exist_ok=True)
        
        self.d1 = CloudflareD1(cf_account_id, cf_api_token, d1_database_id)
        
        self.telegram = TelegramUploader(telegram_token, telegram_chat_id)
        self.tracker = ProgressTracker(self.telegram, interval=120)
        
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
        
        self.processed_urls = self._load_processed_urls()
        self.existing_filenames = self._load_existing_filenames()
        self._setup_signal_handlers()
        
        self.consecutive_403s = 0
        self.max_consecutive_403s = 10
        self.current_category = ""
        self.lock = threading.Lock()
        self.num_workers = 3
    
    def _setup_signal_handlers(self):
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, saving state before exit...")
            self._save_state_local()
            self.telegram.send_message(
                f"<b>Scraper Interrupted</b>\n"
                f"Saved progress: {len(self.processed_urls)} URLs processed\n"
                f"Will resume from here on next run"
            )
            logger.info("State saved, exiting gracefully")
        
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
            logger.info("Signal handlers registered for graceful shutdown")
        except Exception as e:
            logger.warning(f"Could not register signal handlers: {e}")
    
    def _load_processed_urls(self):
        if self.d1.enabled:
            urls = self.d1.get_all_processed_urls()
            if urls:
                logger.info(f"Loaded {len(urls)} processed URLs from D1")
                return urls
        
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                processed = set(state.get('processed_urls', []))
                logger.info(f"Loaded state from file: {len(processed)} previously processed URLs")
                return processed
        except Exception as e:
            logger.warning(f"Error loading state: {e}")
        
        logger.info("No previous state found, starting fresh")
        return set()
    
    def _load_existing_filenames(self):
        if self.d1.enabled:
            filenames = self.d1.get_all_normalized_filenames()
            if filenames:
                logger.info(f"Loaded {len(filenames)} existing filenames from D1 for duplicate check")
                return filenames
        return set()
    
    def _save_state_local(self):
        try:
            state = {
                'processed_urls': list(self.processed_urls),
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'count': len(self.processed_urls)
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
            logger.info(f"Saved state locally: {len(self.processed_urls)} processed URLs")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _mark_url_processed(self, url, success=False, title=""):
        self.processed_urls.add(url)
        
        if self.d1.enabled:
            self.d1.add_processed_url(url, success, title)
    
    def _save_discovered_url(self, url, category="", page=0):
        if self.d1.enabled:
            self.d1.add_discovered_url(url, category, page)
    
    def _save_resume_state(self, category, page):
        if self.d1.enabled:
            self.d1.save_state(category, page)
        self._save_state_local()
    
    def _get_resume_state(self):
        if self.d1.enabled:
            category, page = self.d1.get_state()
            if category:
                return category, page
        return None, None
    
    def get_page(self, url, retries=6):
        for attempt in range(retries):
            try:
                browser = random.choice(self.browser_versions)
                logger.info(f"Fetching {url} (attempt {attempt + 1}, browser: {browser})")
                
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124"',
                    'sec-ch-ua-mobile': '?0',
                    'sec-ch-ua-platform': '"Windows"'
                }
                
                response = curl_requests.get(
                    url,
                    impersonate=browser,
                    timeout=45,
                    headers=headers
                )
                response.raise_for_status()
                
                self.consecutive_403s = 0
                time.sleep(random.uniform(0.5, 1.5))
                return response
                
            except Exception as e:
                error_str = str(e)
                is_403 = '403' in error_str
                
                if is_403:
                    self.consecutive_403s += 1
                    base_backoff = 10
                    backoff_time = base_backoff * (2 ** attempt) + random.uniform(5, 15)
                    backoff_time = min(backoff_time, 120)
                    
                    logger.warning(f"403 Blocked! Attempt {attempt + 1}/{retries} - "
                                   f"consecutive 403s: {self.consecutive_403s} - "
                                   f"backing off for {backoff_time:.1f}s")
                    
                    if self.consecutive_403s >= self.max_consecutive_403s:
                        logger.warning(f"Too many consecutive 403s ({self.consecutive_403s}), taking extended break...")
                        time.sleep(random.uniform(60, 120))
                        self.consecutive_403s = 0
                    else:
                        time.sleep(backoff_time)
                else:
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < retries - 1:
                        time.sleep(random.uniform(5, 10))
                
                if attempt == retries - 1:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
        return None
    

    
    def download_and_process_subtitle(self, subtitle_url):
        logger.info(f"Processing: {subtitle_url}")
        
        response = self.get_page(subtitle_url)
        if not response:
            return False, ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        movie_title = soup.find('h1')
        title_text = movie_title.get_text(strip=True) if movie_title else 'Unknown'
        
        download_link = None
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(ext in href.lower() for ext in ['.zip', '.srt', '.rar']):
                download_link = href
                logger.info(f"Found direct file link: {href[:80]}")
                break
        
        if not download_link:
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'download' in href.lower() and ('?' in href or '.php' in href):
                    download_link = href
                    logger.info(f"Found download manager link: {href[:80]}")
                    break
        
        if not download_link:
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True).lower()
                if 'baiscopedownloads.link' in href:
                    continue
                if any(keyword in text for keyword in ['download subtitle', 'get subtitle', '.srt', '.zip']):
                    download_link = href
                    logger.info(f"Found download button: {href[:80]}")
                    break
        
        if not download_link:
            logger.warning(f"No valid download link found on {subtitle_url}")
            return False, title_text
        
        download_url = urljoin(self.base_url, download_link)
        logger.info(f"Downloading from: {download_url}")
        
        try:
            file_response = self.get_page(download_url)
            if not file_response:
                return False, title_text
            
            file_content = file_response.content
            
            # Check if likely a zip file
            is_zip = False
            if file_content[:4] == b'PK\x03\x04':
                is_zip = True
            
            clean_title = ''.join(c for c in title_text if c.isalnum() or c in (' ', '-', '_', '.'))
            clean_title = clean_title.strip()[:80]
            
            # Prepare filename
            if is_zip:
                ext = '.zip'
            else:
                ext = '.srt'
                
            final_filename = f"{clean_title}{ext}"
            final_filename = final_filename.replace('/', '_').replace('\\', '_')
            
            normalized = normalize_filename(final_filename)
            
            with self.lock:
                if self.d1.enabled and normalized in self.existing_filenames:
                    logger.info(f"SKIPPING (already exists in Telegram): {final_filename}")
                    return True, title_text

            caption = f"<b>{title_text[:200]}</b>\n\nSource: {subtitle_url[:100]}"
            
            file_info = self.telegram.send_document(file_content, final_filename, caption)
            
            if file_info:
                if self.d1.enabled and file_info.get('file_id'):
                    self.d1.save_telegram_file_with_normalized(
                        file_id=file_info['file_id'],
                        file_unique_id=file_info.get('file_unique_id', ''),
                        filename=final_filename,
                        normalized_filename=normalized,
                        file_size=file_info.get('file_size', 0),
                        title=title_text,
                        source_url=subtitle_url,
                        category=self.current_category,
                        message_id=file_info.get('message_id', 0)
                    )
                    with self.lock:
                        self.existing_filenames.add(normalized)
                
                logger.info(f"Uploaded to Telegram: {final_filename}")
                return True, title_text
            
            return False, title_text
            
        except Exception as e:
            logger.error(f"Error processing subtitle: {e}")
            return False, title_text
    
    def get_subtitle_urls_from_page(self, category, page):
        if page == 1:
            url = f"{self.base_url}{category}"
        else:
            url = f"{self.base_url}{category}page/{page}/"
        
        logger.info(f"Fetching {category} page {page}")
        response = self.get_page(url)
        
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        subtitle_urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href and (('sinhala-subtitle' in href.lower() or 'subtitles' in href.lower()) and '/category/' not in href and '/tag/' not in href):
                full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                if 'baiscope.lk' in full_url and full_url != self.base_url + '/':
                    if full_url not in subtitle_urls:
                        subtitle_urls.append(full_url)
                        self._save_discovered_url(full_url, category, page)
        
        logger.info(f"Found {len(subtitle_urls)} subtitle links on {category} page {page}")
        return subtitle_urls
    
    def _process_single_url(self, url):
        """Process a single URL - used by parallel workers"""
        if url in self.processed_urls:
            logger.info(f"Skipping already processed: {url}")
            return False
        
        try:
            result, title = self.download_and_process_subtitle(url)
            
            with self.lock:
                self._mark_url_processed(url, result, title)
                if result:
                    self.tracker.update(success=True)
                else:
                    self.tracker.update(success=False)
            
            time.sleep(random.uniform(0.2, 0.5))
            return result
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            with self.lock:
                self._mark_url_processed(url, False, "")
                self.tracker.update(success=False)
            return False
    
    def process_page_subtitles(self, subtitle_urls):
        success_count = 0
        
        urls_to_process = [url for url in subtitle_urls if url not in self.processed_urls]
        
        if not urls_to_process:
            logger.info("No new URLs to process on this page")
            return 0
        
        logger.info(f"Processing {len(urls_to_process)} URLs with {self.num_workers} parallel workers")
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self._process_single_url, url): url for url in urls_to_process}
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    result = future.result()
                    if result:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Worker error for {url}: {e}")
        
        self._save_state_local()
        return success_count
    
    def scrape_all(self, limit=None):
        logger.info("Starting Baiscope.lk subtitle scraper - Telegram storage mode with D1 database")
        logger.info(f"Previously processed URLs: {len(self.processed_urls)}")
        
        if self.d1.enabled:
            logger.info(f"D1 Database enabled - discovered: {self.d1.get_discovered_urls_count()}, processed: {self.d1.get_processed_urls_count()}")
        
        categories = [
            "/category/sinhala-subtitles/movies/",
            "/category/sinhala-subtitles/",
            "/category/anime/",
            "/category/war/",
            "/category/crime/",
            "/category/action/",
            "/category/adventure/",
            "/category/comedy/",
            "/category/drama/",
            "/category/fantasy/",
            "/category/horror/",
            "/category/mystery/",
            "/category/romance/",
            "/category/sci-fi/",
            "/category/thriller/",
            "/category/animation/",
            "/category/biography/",
            "/category/family/",
            "/category/history/",
            "/category/music/",
            "/category/sport/",
            "/category/western/",
            "/category/documentary/",
            "/category/tv-series/",
            "/category/hindi-subtitles/",
            "/category/korean-subtitles/",
            "/category/tamil-subtitles/",
        ]
        
        resume_category, resume_page = self._get_resume_state()
        start_from_category = 0
        start_from_page = 1
        
        if resume_category:
            logger.info(f"Resuming from category: {resume_category}, page: {resume_page}")
            for i, cat in enumerate(categories):
                if cat == resume_category:
                    start_from_category = i
                    start_from_page = resume_page or 1
                    break
        
        self.telegram.send_message(
            f"<b>Baiscope Scraper Starting</b>\n"
            f"Mode: Telegram + D1 Database\n"
            f"Categories: {len(categories)}\n"
            f"Previously processed: {len(self.processed_urls)}\n"
            f"Resume from: {resume_category or 'Beginning'}"
        )
        
        total_success = 0
        total_processed = 0
        
        for cat_idx in range(start_from_category, len(categories)):
            category = categories[cat_idx]
            page = start_from_page if cat_idx == start_from_category else 1
            max_pages = 500
            consecutive_empty = 0
            
            logger.info(f"\n=== Processing category: {category} ===")
            self.current_category = category
            self.tracker.update_page(category, page)
            
            while page <= max_pages:
                self._save_resume_state(category, page)
                
                subtitle_urls = self.get_subtitle_urls_from_page(category, page)
                
                if subtitle_urls is None:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info(f"Too many failed pages, moving to next category")
                        break
                    page += 1
                    continue
                
                new_urls = [url for url in subtitle_urls if url not in self.processed_urls]
                
                if len(new_urls) == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info(f"No more new content in {category}")
                        break
                    page += 1
                    continue
                
                consecutive_empty = 0
                self.tracker.update_page(category, page)
                
                logger.info(f"Processing {len(new_urls)} new subtitles from page {page}")
                
                success = self.process_page_subtitles(new_urls)
                total_success += success
                total_processed += len(new_urls)
                
                logger.info(f"Page {page} complete: {success}/{len(new_urls)} successful")
                
                if limit and total_processed >= limit:
                    logger.info(f"Reached limit of {limit} subtitles")
                    break
                
                page += 1
                time.sleep(random.uniform(2.0, 4.0))
            
            if limit and total_processed >= limit:
                break
            
            time.sleep(random.uniform(3.0, 6.0))
        
        self._save_state_local()
        
        self.telegram.send_message(
            f"<b>Scraping Complete!</b>\n"
            f"Total processed: {total_processed}\n"
            f"Successfully uploaded: {total_success}\n"
            f"Total in database: {len(self.processed_urls)}"
        )
        
        logger.info(f"Scraping complete! Processed {total_processed}, success: {total_success}")
        return total_success


if __name__ == '__main__':
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN! Please set the environment variable.")
        exit(1)
    
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, D1_DATABASE_ID]):
        logger.warning("D1 database credentials not set - will use local file storage only")
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 50))
    
    scraper = BaiscopeScraperTelegram(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        cf_account_id=CF_ACCOUNT_ID,
        cf_api_token=CF_API_TOKEN,
        d1_database_id=D1_DATABASE_ID,
        batch_size=BATCH_SIZE
    )
    
    scraper.scrape_all()
