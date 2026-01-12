"""
Subz.lk subtitle scraper with Telegram upload and D1 database tracking
"""
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import random
import re
import threading
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from scraper_utils import CloudflareD1, TelegramUploader, ProgressTracker, normalize_filename

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class SubzLkScraper:
    def __init__(self, telegram_token, telegram_chat_id, 
                 cf_account_id=None, cf_api_token=None, d1_database_id=None,
                 batch_size=50):
        self.base_url = 'https://subz.lk'
        self.batch_size = batch_size
        self.source = "subz"
        
        self.d1 = CloudflareD1(cf_account_id, cf_api_token, d1_database_id)
        self.telegram = TelegramUploader(telegram_token, telegram_chat_id)
        self.tracker = ProgressTracker(self.telegram, interval=120)
        
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
        
        self.processed_urls = self._load_processed_urls()
        self.existing_filenames = self._load_existing_filenames()
        
        self.lock = threading.Lock()
        self.num_workers = 3
        
    def _load_processed_urls(self):
        if self.d1.enabled:
            urls = self.d1.get_all_processed_urls(source=self.source)
            if urls:
                logger.info(f"Loaded {len(urls)} processed URLs from D1 for subz.lk")
                return urls
        logger.info("No previous state found for subz.lk, starting fresh")
        return set()
    
    def _load_existing_filenames(self):
        if self.d1.enabled:
            filenames = self.d1.get_all_normalized_filenames(source=self.source)
            if filenames:
                logger.info(f"Loaded {len(filenames)} existing filenames from D1 for subz.lk")
                return filenames
        return set()
    
    def _mark_url_processed(self, url, success=False, title=""):
        self.processed_urls.add(url)
        if self.d1.enabled:
            self.d1.add_processed_url(url, success, title, source=self.source)
    
    def _save_discovered_url(self, url, category="", page=0):
        if self.d1.enabled:
            self.d1.add_discovered_url(url, category, page, source=self.source)
    
    def get_page(self, url, retries=6):
        """Fetch a page with retries and anti-blocking measures"""
        for attempt in range(retries):
            try:
                browser = random.choice(self.browser_versions)
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                response = curl_requests.get(
                    url,
                    impersonate=browser,
                    timeout=45,
                    headers=headers
                )
                response.raise_for_status()
                
                time.sleep(random.uniform(0.5, 1.5))
                return response
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(3, 8))
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
        return None
    
    def _extract_download_params(self, detail_page_html):
        """Extract sub_id and nonce from the download button on detail page"""
        soup = BeautifulSoup(detail_page_html, 'html.parser')
        
        # Find the download button - it has class 'sub-download'
        download_btn = soup.find('a', class_='sub-download')
        if not download_btn:
            logger.warning("No download button found with class 'sub-download'")
            return None, None
        
        # Extract data attributes or href parameters
        href = download_btn.get('href', '')
        
        # Parse sub_id and nonce from URL parameters
        # Example: wp-admin/admin-ajax.php?action=sub_download&sub_id=12345&nonce=abc123
        sub_id_match = re.search(r'sub_id=(\d+)', href)
        nonce_match = re.search(r'nonce=([^&]+)', href)
        
        if not sub_id_match or not nonce_match:
            # Try data attributes
            sub_id = download_btn.get('data-sub-id')
            nonce = download_btn.get('data-nonce')
        else:
            sub_id = sub_id_match.group(1)
            nonce = nonce_match.group(1)
        
        if sub_id and nonce:
            logger.info(f"Extracted download params: sub_id={sub_id}, nonce={nonce[:10]}...")
            return sub_id, nonce
        
        logger.warning("Could not extract sub_id or nonce from download button")
        return None, None
    
    def download_and_process_subtitle(self, subtitle_url):
        """Download subtitle from detail page and upload to Telegram"""
        logger.info(f"Processing: {subtitle_url}")
        
        # Fetch the detail page
        response = self.get_page(subtitle_url)
        if not response:
            return False, ""
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title_elem = soup.find('h1', class_='entry-title') or soup.find('h1')
        title_text = title_elem.get_text(strip=True) if title_elem else 'Unknown'
        
        # Extract download parameters
        sub_id, nonce = self._extract_download_params(response.text)
        if not sub_id or not nonce:
            logger.warning(f"Cannot download from {subtitle_url} - missing download params")
            return False, title_text
        
        # Construct download URL
        download_url = f"{self.base_url}/wp-admin/admin-ajax.php?action=sub_download&sub_id={sub_id}&nonce={nonce}"
        logger.info(f"Downloading from: {download_url}")
        
        try:
            # Download the file
            file_response = self.get_page(download_url)
            if not file_response:
                return False, title_text
            
            file_content = file_response.content
            
            # Determine file type
            is_zip = file_content[:4] == b'PK\x03\x04'
            is_rar = file_content[:4] == b'Rar!'
            
            # Clean title for filename
            clean_title = ''.join(c for c in title_text if c.isalnum() or c in (' ', '-', '_', '.'))
            clean_title = clean_title.strip()[:80]
            
            # Set extension based on file type
            if is_zip:
                ext = '.zip'
            elif is_rar:
                ext = '.rar'
            else:
                ext = '.srt'
            
            final_filename = f"{clean_title}{ext}"
            final_filename = final_filename.replace('/', '_').replace('\\', '_')
            
            # Check for duplicates
            normalized = normalize_filename(final_filename)
            
            with self.lock:
                if self.d1.enabled and normalized in self.existing_filenames:
                    logger.info(f"SKIPPING (already exists in Telegram): {final_filename}")
                    return True, title_text
            
            # Upload to Telegram
            caption = f"<b>{title_text[:200]}</b>\n\nSource: subz.lk\nURL: {subtitle_url[:100]}"
            
            file_info = self.telegram.send_document(file_content, final_filename, caption)
            
            if file_info:
                # Save to D1 database
                if self.d1.enabled and file_info.get('file_id'):
                    self.d1.save_telegram_file_with_normalized(
                        file_id=file_info['file_id'],
                        file_unique_id=file_info.get('file_unique_id', ''),
                        filename=final_filename,
                        normalized_filename=normalized,
                        file_size=file_info.get('file_size', 0),
                        title=title_text,
                        source_url=subtitle_url,
                        category="",
                        message_id=file_info.get('message_id', 0),
                        source=self.source
                    )
                    with self.lock:
                        self.existing_filenames.add(normalized)
                
                logger.info(f"Uploaded to Telegram: {final_filename}")
                return True, title_text
            
            return False, title_text
            
        except Exception as e:
            logger.error(f"Error processing subtitle: {e}")
            return False, title_text
    
    def get_subtitle_urls_from_page(self, category_url, page=1):
        """Get subtitle URLs from a category page"""
        if page == 1:
            url = category_url
        else:
            # WordPress pagination: /category/movies/page/2/
            url = f"{category_url.rstrip('/')}/page/{page}/"
        
        logger.info(f"Fetching category page: {url}")
        response = self.get_page(url)
        
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find subtitle links - they typically have class 'card-link' or are within article cards
        subtitle_urls = []
        
        # Look for links with specific patterns
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            # Subz.lk subtitle pages typically have '-sinhala-subtitle/' in the URL
            if 'sinhala-subtitle' in href.lower() and href.startswith('http'):
                if href not in subtitle_urls:
                    subtitle_urls.append(href)
                    self._save_discovered_url(href, category_url, page)
        
        logger.info(f"Found {len(subtitle_urls)} subtitle links on page {page}")
        return subtitle_urls
    
    def get_homepage_updates(self):
        """Get recently updated subtitles from homepage"""
        logger.info("Checking homepage for new subtitles...")
        response = self.get_page(self.base_url)
        
        if not response:
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find recent updates - check sidebar or main content area
        subtitle_urls = []
        
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if 'sinhala-subtitle' in href.lower() and href.startswith('http'):
                if href not in subtitle_urls:
                    subtitle_urls.append(href)
        
        logger.info(f"Found {len(subtitle_urls)} subtitle links on homepage")
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
        """Process all subtitles from a page using parallel workers"""
        urls_to_process = [url for url in subtitle_urls if url not in self.processed_urls]
        
        if not urls_to_process:
            logger.info("No new URLs to process on this page")
            return 0
        
        logger.info(f"Processing {len(urls_to_process)} URLs with {self.num_workers} parallel workers")
        
        success_count = 0
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
        
        return success_count
    
    def monitor_new_subtitles(self, limit=None):
        """Monitor homepage for new subtitles and process them"""
        logger.info("Starting subz.lk monitoring mode...")
        
        self.telegram.send_message(
            f"<b>Subz.lk Monitor Starting</b>\n"
            f"Mode: Monitor for new subtitles\n"
            f"Previously processed: {len(self.processed_urls)}"
        )
        
        # Get homepage updates
        all_urls = self.get_homepage_updates()
        new_urls = [url for url in all_urls if url not in self.processed_urls]
        
        if not new_urls:
            logger.info("No new subtitles found")
            self.telegram.send_message("<b>No new subtitles found on subz.lk</b>")
            return 0
        
        logger.info(f"Found {len(new_urls)} new subtitles to process")
        
        if limit:
            new_urls = new_urls[:limit]
        
        self.tracker.start(len(new_urls))
        success = self.process_page_subtitles(new_urls)
        self.tracker.stop()
        
        logger.info(f"Monitoring complete: {success}/{len(new_urls)} successful")
        return success
    
    def scrape_all_categories(self, limit=None):
        """Full scrape of all categories on subz.lk"""
        logger.info("Starting full subz.lk scrape...")
        
        categories = [
            "/category/movies/",
            "/category/tv-shows/",
        ]
        
        self.telegram.send_message(
            f"<b>Subz.lk Full Scraper Starting</b>\n"
            f"Mode: Full scrape\n"
            f"Categories: {len(categories)}\n"
            f"Previously processed: {len(self.processed_urls)}"
        )
        
        total_success = 0
        total_processed = 0
        
        for category in categories:
            page = 1
            max_pages = 500
            consecutive_empty = 0
            
            logger.info(f"\n=== Processing category: {category} ===")
            
            while page <= max_pages:
                category_url = f"{self.base_url}{category}"
                subtitle_urls = self.get_subtitle_urls_from_page(category_url, page)
                
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
        
        self.telegram.send_message(
            f"<b>Subz.lk Scraping Complete!</b>\n"
            f"Total processed: {total_processed}\n"
            f"Successfully uploaded: {total_success}\n"
            f"Total in database: {len(self.processed_urls)}"
        )
        
        logger.info(f"Scraping complete! Processed {total_processed}, success: {total_success}")
        return total_success


if __name__ == '__main__':
    # For testing purposes
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN! Please set the environment variable.")
        exit(1)
    
    scraper = SubzLkScraper(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        cf_account_id=CF_ACCOUNT_ID,
        cf_api_token=CF_API_TOKEN,
        d1_database_id=D1_DATABASE_ID
    )
    
    # Run monitoring mode by default
    scraper.monitor_new_subtitles(limit=5)
