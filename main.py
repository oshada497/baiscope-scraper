from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import zipfile
import io
import json
from urllib.parse import urljoin, urlparse
import random
import requests
import threading
import signal
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def normalize_filename(filename):
    """Normalize filename for matching"""
    if not filename:
        return ""
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
    name = name.lower()
    name = re.sub(r'\.[^.]+$', '', name)
    name = re.sub(r'[^a-z0-9\u0D80-\u0DFF]', '', name)
    return name


class CloudflareD1:
    """D1 Database interface"""
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
                CREATE TABLE IF NOT EXISTS processed_urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE NOT NULL,
                    site TEXT,
                    success INTEGER DEFAULT 0,
                    title TEXT,
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                    site TEXT,
                    category TEXT,
                    message_id INTEGER,
                    uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.execute("CREATE INDEX IF NOT EXISTS idx_normalized_filename ON telegram_files(normalized_filename)")
            self.execute("CREATE INDEX IF NOT EXISTS idx_site ON processed_urls(site)")
            
            logger.info("✓ D1 tables initialized")
        except Exception as e:
            logger.error(f"D1 init error: {e}")
    
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
                logger.error(f"D1 error: {data.get('errors')}")
                return None
        except Exception as e:
            logger.error(f"D1 execute error: {e}")
            return None
    
    def add_processed_url(self, url, site, success=False, title=""):
        return self.execute(
            "INSERT OR REPLACE INTO processed_urls (url, site, success, title, processed_at) VALUES (?, ?, ?, ?, datetime('now'))",
            [url, site, 1 if success else 0, title[:200] if title else ""]
        )
    
    def is_url_processed(self, url):
        result = self.execute("SELECT 1 FROM processed_urls WHERE url = ?", [url])
        if result and len(result) > 0:
            return len(result[0].get("results", [])) > 0
        return False
    
    def get_all_processed_urls(self, site=None):
        if site:
            result = self.execute("SELECT url FROM processed_urls WHERE site = ?", [site])
        else:
            result = self.execute("SELECT url FROM processed_urls")
        if result and len(result) > 0:
            return set(row.get("url", "") for row in result[0].get("results", []))
        return set()
    
    def file_exists_by_normalized_name(self, normalized_filename):
        result = self.execute("SELECT 1 FROM telegram_files WHERE normalized_filename = ?", [normalized_filename])
        if result and len(result) > 0:
            return len(result[0].get("results", [])) > 0
        return False
    
    def get_all_normalized_filenames(self):
        result = self.execute("SELECT normalized_filename FROM telegram_files WHERE normalized_filename IS NOT NULL")
        if result and len(result) > 0:
            return set(row.get("normalized_filename", "") for row in result[0].get("results", []) if row.get("normalized_filename"))
        return set()
    
    def save_telegram_file(self, file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, site, category, message_id):
        return self.execute(
            """INSERT OR REPLACE INTO telegram_files 
               (file_id, file_unique_id, filename, normalized_filename, file_size, title, source_url, site, category, message_id, uploaded_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            [file_id, file_unique_id, filename, normalized_filename, file_size, title[:200] if title else "", 
             source_url[:500] if source_url else "", site, category or "", message_id]
        )


class TelegramUploader:
    """Telegram bot uploader with rate limiting"""
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
            time.sleep(extra_delay)
    
    def send_message(self, message, retries=3):
        if not self.enabled:
            return False
        for attempt in range(retries):
            self._wait_for_rate_limit()
            try:
                url = f"{self.base_url}/sendMessage"
                data = {'chat_id': self.chat_id, 'text': message, 'parse_mode': 'HTML'}
                response = requests.post(url, data=data, timeout=30)
                self.last_request_time = time.time()
                
                if response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    self.consecutive_429s += 1
                    logger.warning(f"Rate limited! Retry after {retry_after}s")
                    time.sleep(retry_after + 1)
                    continue
                    
                if response.status_code == 200:
                    self.consecutive_429s = max(0, self.consecutive_429s - 1)
                    return True
            except Exception as e:
                logger.warning(f"Telegram send failed: {e}")
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
                mime_type = 'application/x-subrip' if filename.lower().endswith('.srt') else 'application/zip'
                files = {'document': (filename, io.BytesIO(file_content), mime_type)}
                data = {'chat_id': self.chat_id}
                if caption:
                    data['caption'] = caption[:1024]
                    data['parse_mode'] = 'HTML'
                
                response = requests.post(url, data=data, files=files, timeout=60)
                self.last_request_time = time.time()
                
                if response.status_code == 429:
                    retry_after = response.json().get('parameters', {}).get('retry_after', 30)
                    self.consecutive_429s += 1
                    time.sleep(retry_after + 2)
                    continue
                    
                if response.status_code == 200:
                    self.consecutive_429s = max(0, self.consecutive_429s - 1)
                    result = response.json().get('result', {})
                    document = result.get('document', {})
                    return {
                        'file_id': document.get('file_id', ''),
                        'file_unique_id': document.get('file_unique_id', ''),
                        'file_size': document.get('file_size', 0),
                        'message_id': result.get('message_id', 0),
                        'filename': filename
                    }
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
            except Exception as e:
                logger.error(f"Upload failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None


class BaseSiteScraper(ABC):
    """Base class for site scrapers"""
    def __init__(self, base_url, site_name):
        self.base_url = base_url
        self.site_name = site_name
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
        self.consecutive_403s = 0
        self.max_consecutive_403s = 10
    
    def get_page(self, url, retries=6):
        for attempt in range(retries):
            try:
                browser = random.choice(self.browser_versions)
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                }
                response = curl_requests.get(url, impersonate=browser, timeout=45, headers=headers)
                response.raise_for_status()
                self.consecutive_403s = 0
                time.sleep(random.uniform(0.5, 1.5))
                return response
            except Exception as e:
                if '403' in str(e):
                    self.consecutive_403s += 1
                    backoff = 10 * (2 ** attempt) + random.uniform(5, 15)
                    backoff = min(backoff, 120)
                    logger.warning(f"403 Blocked! Backing off {backoff:.1f}s")
                    time.sleep(backoff)
                else:
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < retries - 1:
                        time.sleep(random.uniform(5, 10))
        return None
    
    @abstractmethod
    def get_categories(self):
        """Return list of category URLs"""
        pass
    
    @abstractmethod
    def get_subtitle_urls_from_page(self, category, page):
        """Extract subtitle URLs from a page"""
        pass
    
    @abstractmethod
    def find_download_link(self, soup):
        """Find download link in subtitle page"""
        pass


class BaiscopeScraper(BaseSiteScraper):
    def __init__(self):
        super().__init__('https://www.baiscope.lk', 'baiscope')
    
    def get_categories(self):
        return [
            "/category/sinhala-subtitles/movies/",
            "/category/sinhala-subtitles/",
            "/category/action/",
            "/category/comedy/",
            "/category/drama/",
        ]
    
    def get_subtitle_urls_from_page(self, category, page):
        url = f"{self.base_url}{category}" if page == 1 else f"{self.base_url}{category}page/{page}/"
        response = self.get_page(url)
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'sinhala-subtitle' in href.lower() and '/category/' not in href:
                full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                if 'baiscope.lk' in full_url:
                    urls.append(full_url)
        return urls
    
    def find_download_link(self, soup):
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(ext in href.lower() for ext in ['.zip', '.srt', '.rar']):
                return href
        return None


class ZoomScraper(BaseSiteScraper):
    def __init__(self):
        super().__init__('https://zoom.lk', 'zoom')
    
    def get_categories(self):
        return [
            "/category/films/",
            "/category/films/english/",
            "/category/films/telugu/",
            "/category/films/tamil/",
            "/category/films/hindi/",
            "/category/films/korean/",
        ]
    
    def get_subtitle_urls_from_page(self, category, page):
        url = f"{self.base_url}{category}" if page == 1 else f"{self.base_url}{category}page/{page}/"
        response = self.get_page(url)
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'subtitle' in href.lower() and 'zoom.lk' in href and '/category/' not in href:
                full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                urls.append(full_url)
        return urls
    
    def find_download_link(self, soup):
        # Zoom.lk typically uses direct links or MediaFire
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(domain in href for domain in ['mediafire.com', 'drive.google.com']) or any(ext in href.lower() for ext in ['.zip', '.srt']):
                return href
        return None


class SubzScraper(BaseSiteScraper):
    def __init__(self):
        super().__init__('https://subzlk.com', 'subz')
    
    def get_categories(self):
        return [
            "/",  # Homepage has recent posts
            "/page/",  # Pagination
        ]
    
    def get_subtitle_urls_from_page(self, category, page):
        if category == "/":
            url = f"{self.base_url}/" if page == 1 else f"{self.base_url}/page/{page}/"
        else:
            url = f"{self.base_url}/page/{page}/"
        
        response = self.get_page(url)
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'subzlk.com' in href and 'sinhala' in href.lower() and '/page/' not in href:
                urls.append(href)
        return urls
    
    def find_download_link(self, soup):
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True).lower()
            if 'download' in text or any(ext in href.lower() for ext in ['.zip', '.srt']):
                return href
        return None


class MultiSiteScraper:
    """Main scraper that coordinates all sites"""
    def __init__(self, telegram_token, telegram_chat_id, 
                 cf_account_id=None, cf_api_token=None, d1_database_id=None):
        self.d1 = CloudflareD1(cf_account_id, cf_api_token, d1_database_id)
        self.telegram = TelegramUploader(telegram_token, telegram_chat_id)
        
        # Initialize site scrapers
        self.sites = {
            'baiscope': BaiscopeScraper(),
            'zoom': ZoomScraper(),
            'subz': SubzScraper(),
        }
        
        self.processed_urls = self._load_processed_urls()
        self.existing_filenames = self.d1.get_all_normalized_filenames() if self.d1.enabled else set()
        self.lock = threading.Lock()
        self.num_workers = 3
        
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        logger.warning("Shutdown signal received!")
        self.telegram.send_message("⏸️ Scraper paused - will resume on restart")
        os._exit(0)
    
    def _load_processed_urls(self):
        if self.d1.enabled:
            return self.d1.get_all_processed_urls()
        return set()
    
    def download_and_process_subtitle(self, site_scraper, subtitle_url):
        site_name = site_scraper.site_name
        logger.info(f"[{site_name}] Processing: {subtitle_url}")
        
        response = site_scraper.get_page(subtitle_url)
        if not response:
            return False, ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        movie_title = soup.find('h1')
        title_text = movie_title.get_text(strip=True) if movie_title else 'Unknown'
        
        download_link = site_scraper.find_download_link(soup)
        if not download_link:
            logger.warning(f"[{site_name}] No download link found")
            return False, title_text
        
        download_url = urljoin(site_scraper.base_url, download_link)
        logger.info(f"[{site_name}] Downloading from: {download_url[:80]}")
        
        try:
            file_response = site_scraper.get_page(download_url)
            if not file_response:
                return False, title_text
            
            file_content = file_response.content
            is_zip = file_content[:4] == b'PK\x03\x04'
            
            clean_title = ''.join(c for c in title_text if c.isalnum() or c in (' ', '-', '_', '.'))
            clean_title = clean_title.strip()[:80]
            ext = '.zip' if is_zip else '.srt'
            final_filename = f"[{site_name.upper()}] {clean_title}{ext}"
            
            normalized = normalize_filename(final_filename)
            
            with self.lock:
                if normalized in self.existing_filenames:
                    logger.info(f"SKIPPING (duplicate): {final_filename}")
                    return True, title_text
            
            caption = f"<b>{title_text[:200]}</b>\n\n🌐 {site_name.upper()}\n🔗 {subtitle_url[:100]}"
            file_info = self.telegram.send_document(file_content, final_filename, caption)
            
            if file_info and self.d1.enabled:
                self.d1.save_telegram_file(
                    file_id=file_info['file_id'],
                    file_unique_id=file_info.get('file_unique_id', ''),
                    filename=final_filename,
                    normalized_filename=normalized,
                    file_size=file_info.get('file_size', 0),
                    title=title_text,
                    source_url=subtitle_url,
                    site=site_name,
                    category="",
                    message_id=file_info.get('message_id', 0)
                )
                with self.lock:
                    self.existing_filenames.add(normalized)
                logger.info(f"✓ [{site_name}] Uploaded: {final_filename}")
                return True, title_text
            
            return False, title_text
        except Exception as e:
            logger.error(f"[{site_name}] Error: {e}")
            return False, title_text
    
    def scrape_site(self, site_name, max_pages=30):
        """Scrape a single site"""
        if site_name not in self.sites:
            logger.error(f"Unknown site: {site_name}")
            return 0
        
        site_scraper = self.sites[site_name]
        logger.info(f"\n{'='*50}\nScraping {site_name.upper()}\n{'='*50}")
        
        categories = site_scraper.get_categories()
        total_success = 0
        
        for category in categories:
            page = 1
            consecutive_empty = 0
            
            while page <= max_pages and consecutive_empty < 3:
                subtitle_urls = site_scraper.get_subtitle_urls_from_page(category, page)
                
                if subtitle_urls is None:
                    consecutive_empty += 1
                    page += 1
                    continue
                
                new_urls = [url for url in subtitle_urls if url not in self.processed_urls]
                
                if len(new_urls) == 0:
                    consecutive_empty += 1
                    page += 1
                    continue
                
                logger.info(f"[{site_name}] Page {page}: Processing {len(new_urls)} subtitles")
                
                # Process with parallel workers
                with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                    futures = {executor.submit(self._process_single_url, site_scraper, url): url for url in new_urls}
                    for future in as_completed(futures):
                        try:
                            if future.result():
                                total_success += 1
                        except Exception as e:
                            logger.error(f"Worker error: {e}")
                
                consecutive_empty = 0
                page += 1
                time.sleep(random.uniform(2, 4))
        
        logger.info(f"[{site_name}] Complete: {total_success} successful")
        return total_success
    
    def _process_single_url(self, site_scraper, url):
        if url in self.processed_urls:
            return False
        
        try:
            result, title = self.download_and_process_subtitle(site_scraper, url)
            
            with self.lock:
                self.processed_urls.add(url)
                if self.d1.enabled:
                    self.d1.add_processed_url(url, site_scraper.site_name, result, title)
            
            time.sleep(random.uniform(0.2, 0.5))
            return result
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return False
    
    def scrape_all_sites(self, sites_to_scrape=None, max_pages=30):
        """Scrape all or specified sites"""
        if sites_to_scrape is None:
            sites_to_scrape = list(self.sites.keys())
        
        self.telegram.send_message(
            f"<b>🚀 Multi-Site Scraper Started</b>\n"
            f"Sites: {', '.join(sites_to_scrape)}\n"
            f"Previously processed: {len(self.processed_urls)}"
        )
        
        total = 0
        for site_name in sites_to_scrape:
            count = self.scrape_site(site_name, max_pages=max_pages)
            total += count
        
        self.telegram.send_message(
            f"<b>✅ Scraping Complete!</b>\n"
            f"Total uploaded: {total}\n"
            f"Total processed: {len(self.processed_urls)}"
        )
        
        logger.info(f"All sites complete! Total: {total}")
        return total


if __name__ == '__main__':
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    # Sites to scrape - set via env var or default to all
    SITES = os.environ.get('SCRAPE_SITES', 'baiscope,zoom,subz').split(',')
    MAX_PAGES = int(os.environ.get('MAX_PAGES', '30'))
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        exit(1)
    
    scraper = MultiSiteScraper(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        cf_account_id=CF_ACCOUNT_ID,
        cf_api_token=CF_API_TOKEN,
        d1_database_id=D1_DATABASE_ID
    )
    
    scraper.scrape_all_sites(sites_to_scrape=SITES, max_pages=MAX_PAGES)
