"""
Subz.lk Dedicated Subtitle Scraper
Highly stable, resume-capable, and optimized for Render/D1 architecture.
"""
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import random
import re
import threading
import sys
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper_utils import CloudflareD1, TelegramUploader, ProgressTracker, normalize_filename

# Force logs to stdout for Render visibility
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class SubzLkScraper:
    def __init__(self, telegram_token, telegram_chat_id, 
                 cf_account_id=None, cf_api_token=None, d1_database_id=None):
        self.base_url = 'https://subz.lk'
        self.source = "subz"
        self.num_workers = 3
        self.batch_size = 50
        self.lock = threading.Lock()
        
        # Browser impersonation versions
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
        
        # D1 Setup
        self.cf_account_id = cf_account_id or os.getenv('CF_ACCOUNT_ID')
        self.cf_api_token = cf_api_token or os.getenv('CF_API_TOKEN')
        self.d1_database_id = d1_database_id or os.getenv('D1_DATABASE_ID')
        self.d1 = CloudflareD1(self.cf_account_id, self.cf_api_token, self.d1_database_id)
        
        # Telegram & Tracker
        self.telegram = TelegramUploader(telegram_token, telegram_chat_id)
        self.tracker = ProgressTracker(self.telegram, interval=120)
        
        # Runtime State
        self.stats = {'discovered': 0, 'processed': 0}
        self.initialization_status = "pending"
        self.processed_urls = set()
        self.existing_filenames = set()

    def initialize(self):
        """Perform all heavy D1 operations in one place (non-blocking for __init__)"""
        try:
            self.initialization_status = "initializing_d1_tables"
            if self.d1.enabled:
                self.d1._init_tables()
            
            self.initialization_status = "loading_d1_history"
            if self.d1.enabled:
                self.processed_urls = self.d1.get_all_processed_urls(source=self.source) or set()
                self.existing_filenames = self.d1.get_all_normalized_filenames(source=self.source) or set()
                self.stats['discovered'] = self.d1.get_discovered_urls_count(source=self.source)
                self.stats['processed'] = self.d1.get_processed_urls_count(source=self.source)
                
            logger.info(f"Subz.lk Initialized: {len(self.processed_urls)} items already processed.")
            self.initialization_status = "ready"
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.initialization_status = f"error: {str(e)[:50]}"
            return False

    def get_page(self, url, retries=6):
        """Fetch page with browser impersonation and retries"""
        for attempt in range(retries):
            try:
                response = curl_requests.get(
                    url, 
                    impersonate=random.choice(self.browser_versions),
                    timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0'} # Standard fallback
                )
                if response.status_code == 200:
                    return response
                if response.status_code == 404:
                    return None
            except Exception as e:
                logger.warning(f"Retry {attempt+1}/{retries} for {url}: {e}")
                time.sleep(random.uniform(2, 5))
        return None

    def crawl_only(self, limit_pages=None):
        """Discovery Phase: Crawl categories and save found URLs to D1"""
        logger.info(">>> STARTING DISCOVERY PHASE (Crawl Only) <<<")
        categories = ["/category/movies/", "/category/tv-shows/"]
        
        # Start tracker in "Discovery" mode
        self.tracker.start(0) 
        
        # Load resume state
        resume_cat, resume_page = self.d1.get_state(source=self.source) if self.d1.enabled else (None, None)
        start_tracking = False if resume_cat else True
        
        total_new = 0
        for category in categories:
            if not start_tracking:
                if category == resume_cat:
                    start_tracking = True
                    page = resume_page or 1
                else: continue # Skip done categories

            page = page if (start_tracking and category == resume_cat) else 1
            
            while True:
                if limit_pages and page > limit_pages: break
                
                self.tracker.update_page(category, page)
                cat_url = f"{self.base_url}{category}"
                fetch_url = cat_url if page == 1 else f"{cat_url.rstrip('/')}/page/{page}/"
                
                response = self.get_page(fetch_url)
                if not response: break # End of category
                
                soup = BeautifulSoup(response.text, 'html.parser')
                links = [a['href'] for a in soup.find_all('a', href=True) if 'sinhala-subtitle' in a['href'].lower()]
                links = list(set(links)) # Deduplicate from page
                
                new_on_page = 0
                for link in links:
                    if link not in self.processed_urls:
                        if self.d1.enabled:
                            self.d1.add_discovered_url(link, category, page, source=self.source)
                        new_on_page += 1
                        total_new += 1
                
                logger.info(f"Category {category} Page {page}: Found {len(links)} links ({new_on_page} NEW)")
                
                # Update tracker with newly discovered count
                self.tracker.total_found = self.d1.get_pending_count(source=self.source)
                
                # Persistence: Save state every page
                if self.d1.enabled:
                    self.d1.save_state(category, page, source=self.source)
                
                # Only break if page is truly empty (no links at all)
                if not links:
                    logger.info(f"Category {category}: Page {page} returned no links. End of category.")
                    break
                
                # For monitoring mode only (limit_pages set), stop if we hit 0 new items
                # During full scrape, we continue checking all pages even if they're duplicates
                if limit_pages and new_on_page == 0:
                    logger.info("Monitoring mode: No new items on this page, assuming up to date.")
                    break
                    
                page += 1
                time.sleep(random.uniform(0.5, 1.0)) # Faster discovery

        logger.info(f"Discovery complete. Total new URLs found: {total_new}")
        self.tracker.stop()
        return total_new


    def _process_one(self, url):
        """Download and upload a single subtitle"""
        try:
            # 0. Basic Validation
            if not url or 'subz.lk' not in url.lower():
                logger.warning(f"Skipping invalid/non-subz URL: {url}")
                self.d1.add_processed_url(url, False, "Invalid Source", source=self.source)
                return False

            # 1. Fetch detail page
            res = self.get_page(url)
            if not res:
                logger.warning(f"Link Failed (404 or Timeout): {url}")
                return False
            
            soup = BeautifulSoup(res.text, 'html.parser')
            title_node = soup.find('h2', class_='subz_title') or soup.find('h1')
            title = title_node.get_text(strip=True).replace(' Sinhala Subtitle', '') if title_node else "Unknown"
            
            # 2. Extract Download Params
            dl_btn = soup.find('a', class_='sub-download')
            if not dl_btn:
                logger.warning(f"No Download Button: {url} (Title: {title})")
                return False
            
            href = dl_btn.get('href', '')
            sub_id = re.search(r'sub_id=(\d+)', href)
            nonce = re.search(r'nonce=([^&]+)', href)
            
            if not sub_id or not nonce:
                logger.warning(f"Missing ID/Nonce in button: {url} (Title: {title})")
                return False
            
            # 3. Download File
            dl_url = f"{self.base_url}/wp-admin/admin-ajax.php?action=sub_download&sub_id={sub_id.group(1)}&nonce={nonce.group(1)}"
            file_res = self.get_page(dl_url)
            if not file_res:
                logger.warning(f"File Download Failed: {dl_url}")
                return False
            
            # 4. Handle Metadata & File naming
            clean_title = re.sub(r'[^\w\s-]', '', title).strip()[:100]
            ext = ".zip" if file_res.content[:4] == b'PK\x03\x04' else ".rar" if file_res.content[:4] == b'Rar!' else ".srt"
            filename = f"{clean_title}{ext}"
            norm_name = normalize_filename(filename)
            
            logger.info(f"Downloading: {title} -> {filename}")

            # 5. Duplicate check
            with self.lock:
                if norm_name in self.existing_filenames:
                    logger.info(f"Skipping Duplicate (Filename): {filename}")
                    self.d1.add_processed_url(url, True, title, source=self.source)
                    self.processed_urls.add(url)
                    return True

            # 6. Telegram Upload
            caption = f"<b>{title}</b>\n\nSource: Subz.lk\nLink: {url}"
            file_info = self.telegram.send_document(file_res.content, filename, caption)
            
            if file_info:
                if self.d1.enabled:
                    self.d1.save_telegram_file_with_normalized(
                        file_id=file_info['file_id'],
                        file_unique_id=file_info.get('file_unique_id', ''),
                        filename=filename,
                        normalized_filename=norm_name,
                        file_size=len(file_res.content),
                        title=title,
                        source_url=url,
                        category="",
                        message_id=file_info.get('message_id', 0),
                        source=self.source
                    )
                    self.d1.add_processed_url(url, True, title, source=self.source)
                    with self.lock:
                        self.processed_urls.add(url)
                        self.existing_filenames.add(norm_name)
                        self.stats['processed'] += 1
                logger.info(f"Successfully uploaded: {filename}")
                return True
            
            logger.warning(f"Telegram Upload Failed: {filename}")
            return False
        except Exception as e:
            logger.error(f"Critical error processing {url}: {e}", exc_info=True)
            return False


    def process_queue_mode(self, limit=None):
        """Step 2: Take pending URLs from D1 and process in parallel"""
        logger.info(">>> STARTING PROCESSING PHASE (Queue Worker) <<<")
        processed_count = 0
        
        while True:
            if limit and processed_count >= limit: break
            
            batch = self.d1.get_pending_urls(limit=self.batch_size, source=self.source)
            if not batch: break
            
            urls = [r['url'] for r in batch if r.get('url')]
            logger.info(f"Processing Batch: {len(urls)} items with {self.num_workers} workers")
            
            # Start tracker if not already running (e.g. if we jumped straight to processing)
            if not self.tracker.thread or not self.tracker.thread.is_alive():
                self.tracker.start(self.d1.get_pending_count(source=self.source))
                
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                futures = {executor.submit(self._process_one, u): u for u in urls}
                for future in as_completed(futures):
                    res = future.result()
                    self.tracker.update(success=res)
                    processed_count += 1
            
            # Force log flush for Render
            sys.stdout.flush()
            time.sleep(random.uniform(2, 5)) # Batch cooldown
            
        self.tracker.stop()
        return processed_count

    def scrape_all_categories(self, limit=None):
        """Unified Master Method - Full Historical Scrape"""
        logger.info(">>> STARTING FULL SCRAPE (Discovery + Processing) <<<")
        
        # 1. Discover everything - crawl ALL pages until 404 or empty
        new_discovered = self.crawl_only()  # No limit_pages parameter for full scrape
        
        # 2. Update stats and show pending queue size
        self.stats['discovered'] = self.d1.get_discovered_urls_count(source=self.source)
        pending = self.d1.get_pending_count(source=self.source)
        
        logger.info(f"Discovery phase complete. Newly discovered: {new_discovered}")
        logger.info(f"Total discovered URLs: {self.stats['discovered']}, Pending to process: {pending}")
        
        # 3. Process the queue
        return self.process_queue_mode(limit=limit)


    def monitor_new_subtitles(self):
        """Quick check of homepage for immediate updates"""
        logger.info("Monitoring homepage for new subtitles...")
        return self.crawl_only(limit_pages=1) # Just check first page of categories

if __name__ == "__main__":
    # Test block
    s = SubzLkScraper(os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID'))
    s.initialize()
    s.scrape_all_categories(limit=10)
