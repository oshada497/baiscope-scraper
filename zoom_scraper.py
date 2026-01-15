"""
Zoom.lk Dedicated Subtitle Scraper
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

# Force logs to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class ZoomLkScraper:
    def __init__(self, telegram_token, telegram_chat_id, 
                 cf_account_id=None, cf_api_token=None, d1_database_id=None):
        self.base_url = 'https://zoom.lk'
        self.source = "zoom"
        self.num_workers = 10 # Increased for speed
        self.batch_size = 50
        self.lock = threading.Lock()
        
        # Browser impersonation
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
        """Perform all heavy D1 operations"""
        try:
            self.initialization_status = "initializing_d1_tables"
            if self.d1.enabled:
                self.d1._init_tables()
            
            self.initialization_status = "loading_d1_history"
            if self.d1.enabled:
                self.processed_urls = self.d1.get_all_processed_urls(source=self.source) or set()
                # Also load excluded URLs (invalid/failed ones) to avoid re-looping
                # (Assuming get_all_processed_urls covers them if we save them there)
                
                self.existing_filenames = self.d1.get_all_normalized_filenames(source=self.source) or set()
                self.stats['discovered'] = self.d1.get_discovered_urls_count(source=self.source)
                self.stats['processed'] = self.d1.get_processed_urls_count(source=self.source)
                
            logger.info(f"Zoom.lk Initialized: {len(self.processed_urls)} items already processed.")
            self.initialization_status = "ready"
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.initialization_status = f"error: {str(e)[:50]}"
            return False

    def get_page(self, url, retries=6):
        """Fetch page with browser impersonation"""
        for attempt in range(retries):
            try:
                response = curl_requests.get(
                    url, 
                    impersonate=random.choice(self.browser_versions),
                    timeout=30,
                    headers={'User-Agent': 'Mozilla/5.0'}
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
        """Discovery Phase: Crawl categories"""
        logger.info(">>> STARTING DISCOVERY PHASE (Crawl Only) <<<")
        categories = ["/category/films/", "/category/tv-series/"]
        
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
                else: continue

            page = page if (start_tracking and category == resume_cat) else 1
            
            while True:
                if limit_pages and page > limit_pages: break
                
                self.tracker.update_page(category, page)
                cat_url = f"{self.base_url}{category}"
                fetch_url = cat_url if page == 1 else f"{cat_url.rstrip('/')}/page/{page}/"
                
                response = self.get_page(fetch_url)
                if not response: break # End of category
                
                soup = BeautifulSoup(response.text, 'html.parser')
                # Zoom.lk selector: h3.entry-title a (titles) or maybe a.td-image-wrap (thumbnails)
                # Using h3.entry-title a is usually safer for text
                links = [a['href'] for a in soup.select('h3.entry-title a')]
                
                # Filter useful links (ensure they look like posts, not ads)
                clean_links = []
                for link in links:
                    if link.startswith(self.base_url) and '/category/' not in link and '/page/' not in link:
                         clean_links.append(link)
                    elif link.startswith('/') and '/category/' not in link:
                         clean_links.append(f"{self.base_url}{link}")

                clean_links = list(set(clean_links))
                
                new_on_page = 0
                new_items_batch = []
                for link in clean_links:
                    if link not in self.processed_urls:
                        if self.d1.enabled:
                            # Add to batch list instead of individual calls
                            new_items_batch.append((link, category, page))
                        new_on_page += 1
                        total_new += 1
                
                # Batch Insert
                if self.d1.enabled and new_items_batch:
                    self.d1.add_discovered_urls_batch(new_items_batch, source=self.source)

                logger.info(f"Category {category} Page {page}: Found {len(clean_links)} links ({new_on_page} NEW)")
                
                self.tracker.total_found = self.d1.get_pending_count(source=self.source)
                
                if self.d1.enabled:
                    self.d1.save_state(category, page, source=self.source)
                
                if not clean_links:
                    logger.info(f"Category {category}: Page {page} returned no links. End of category.")
                    break
                
                if limit_pages and new_on_page == 0:
                    logger.info("Monitoring mode: No new items on this page.")
                    break
                    
                page += 1
                time.sleep(random.uniform(0.1, 0.3)) # Reduced sleep for speed

        logger.info(f"Discovery complete. Total new URLs found: {total_new}")
        self.tracker.stop()
        return total_new

    def _process_one(self, url):
        """Download and upload a single subtitle"""
        try:
            # 1. Fetch detail page
            res = self.get_page(url)
            if not res:
                self.d1.add_processed_url(url, False, "404/Fail", source=self.source)
                return False
            
            soup = BeautifulSoup(res.text, 'html.parser')
            title_node = soup.select_one('h1.entry-title')
            title = title_node.get_text(strip=True) if title_node else "Unknown"
            
            # 2. Find Download Button
            # Zoom.lk typically has a button with class 'download-button'
            # Or inspect link with 'sub-download' in href
            dl_btn = soup.select_one('a.download-button')
            
            # Fallback search if class not found
            if not dl_btn:
                for a in soup.find_all('a', href=True):
                    if 'sub-download' in a['href']:
                        dl_btn = a
                        break
            
            if not dl_btn:
                logger.warning(f"No Download Button: {url} (Title: {title})")
                self.d1.add_processed_url(url, False, "No DL Button", source=self.source)
                return False
                
            dl_page_url = dl_btn['href']
            
            # 3. Visit Download Page (if it's a redirect/intermediate page)
            # Zoom.lk often has an intermediate page like /sub-download/12345/
            logger.info(f"Visiting Download Page: {dl_page_url}")
            dl_res = self.get_page(dl_page_url)
            if not dl_res:
                return False
                
            dl_soup = BeautifulSoup(dl_res.content, 'html.parser')
            
            # Find the FINAL download link on this page
            # Usually a button that says "Download" or similar, or maybe it's a direct file trigger
            # Let's look for a link that ends in .zip, .rar, .srt or has 'download' in text
            final_dl_link = None
            
            # Method A: Look for explicit file extensions
            for a in dl_soup.find_all('a', href=True):
                h = a['href'].lower()
                if h.endswith('.zip') or h.endswith('.rar') or h.endswith('.srt'):
                    final_dl_link = a['href']
                    break
            
            # Method B: Look for 'Download' button if A failed (specific to Zoom templates)
            if not final_dl_link:
                 # Sometimes the intermediate page just redirects or has a button
                 # Let's look for a button with 'download' text
                 for a in dl_soup.find_all('a', href=True):
                     if 'download' in a.get_text(strip=True).lower():
                         final_dl_link = a['href']
                         break
            
            if not final_dl_link:
                # Fallback: Maybe the dl_page_url WAS the file (if it was a redirect)? 
                # But headers would show content-type. 
                # Let's assume text/html means we missed the link.
                if 'text/html' not in dl_res.headers.get('Content-Type', ''):
                    # It was the file!
                    file_content = dl_res.content
                    final_dl_link = dl_page_url # for logging
                else:
                    logger.warning(f"Could not find final link on: {dl_page_url}")
                    return False
            else:
                # 4. Download File
                if not final_dl_link.startswith('http'):
                    final_dl_link = urljoin(self.base_url, final_dl_link)
                
                logger.info(f"Downloading File: {final_dl_link}")
                file_res = self.get_page(final_dl_link)
                if not file_res:
                    return False
                file_content = file_res.content

            # 5. Metadata & Naming
            if file_content[:4] == b'PK\x03\x04': ext = ".zip"
            elif file_content[:4] == b'Rar!': ext = ".rar"
            else: ext = ".srt" # Default/Fallback
            
            clean_title = re.sub(r'[^\w\s-]', '', title).strip()[:100]
            filename = f"{clean_title}{ext}"
            norm_name = normalize_filename(filename)
            
            # 6. Duplicate Check
            with self.lock:
                if norm_name in self.existing_filenames:
                    logger.info(f"Skipping Duplicate: {filename}")
                    self.d1.add_processed_url(url, True, title, source=self.source)
                    self.processed_urls.add(url)
                    return True
            
            # 7. Upload
            caption = f"<b>{title}</b>\n\nSource: Zoom.lk\nLink: {url}"
            file_info = self.telegram.send_document(file_content, filename, caption)
            
            if file_info:
                if self.d1.enabled:
                    self.d1.save_telegram_file_with_normalized(
                        file_id=file_info['file_id'],
                        file_unique_id=file_info.get('file_unique_id', ''),
                        filename=filename,
                        normalized_filename=norm_name,
                        file_size=len(file_content),
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
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            return False

    def process_queue_mode(self, limit=None):
        """Process pending URLs"""
        logger.info(">>> STARTING PROCESSING PHASE <<<")
        processed_count = 0
        
        while True:
            if limit and processed_count >= limit: break
            
            batch = self.d1.get_pending_urls(limit=self.batch_size, source=self.source)
            if not batch: break
            
            urls = [r['url'] for r in batch if r.get('url')]
            
            if not self.tracker.thread or not self.tracker.thread.is_alive():
                self.tracker.start(self.d1.get_pending_count(source=self.source))
                
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                futures = {executor.submit(self._process_one, u): u for u in urls}
                for future in as_completed(futures):
                    res = future.result()
                    self.tracker.update(success=res)
                    processed_count += 1
            
            sys.stdout.flush()
            time.sleep(2)
            
        self.tracker.stop()
        return processed_count

    def scrape_all_categories(self, limit=None):
        """Full Scrape"""
        self.crawl_only()
        return self.process_queue_mode(limit=limit)

if __name__ == "__main__":
    s = ZoomLkScraper(os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID'))
    s.initialize()
    s.scrape_all_categories(limit=10)
