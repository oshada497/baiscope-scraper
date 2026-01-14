"""
Clean Subz.lk Subtitle Scraper
No legacy code, no migrations - just pure subz.lk scraping
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
from d1_database import D1Database
from telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class SubzScraper:
    def __init__(self):
        self.base_url = 'https://subz.lk'
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
        
        # Initialize components
        self.db = D1Database(
            os.getenv('CF_ACCOUNT_ID'),
            os.getenv('CF_API_TOKEN'),
            os.getenv('D1_DATABASE_ID')
        )
        self.telegram = TelegramBot(
            os.getenv('TELEGRAM_BOT_TOKEN'),
            os.getenv('TELEGRAM_CHAT_ID')
        )
        
        # State
        self.processed_urls = set()
        self.processed_filenames = set()
        self.lock = threading.Lock()
        
    def initialize(self):
        """Load existing data from database"""
        if self.db.enabled:
            self.db.create_tables()
            self.processed_urls = self.db.get_processed_urls()
            self.processed_filenames = self.db.get_processed_filenames()
        logger.info(f"Initialized: {len(self.processed_urls)} URLs, {len(self.processed_filenames)} files tracked")
        
    def fetch_page(self, url, retries=5):
        """Fetch a page with retries"""
        for attempt in range(retries):
            try:
                response = curl_requests.get(
                    url,
                    impersonate=random.choice(self.browser_versions),
                    timeout=30
                )
                if response.status_code == 200:
                    return response
                if response.status_code == 404:
                    return None
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None
        
    def crawl_category(self, category_path):
        """Crawl all pages in a category and return list of subtitle URLs"""
        found_urls = []
        page = 1
        
        while True:
            # Build page URL
            if page == 1:
                url = f"{self.base_url}{category_path}"
            else:
                url = f"{self.base_url}{category_path}page/{page}/"
                
            logger.info(f"Crawling {category_path} page {page}...")
            response = self.fetch_page(url)
            
            if not response:
                logger.info(f"Category {category_path} ended at page {page}")
                break
                
            # Parse and extract subtitle links
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=True)
            subtitle_links = [
                a['href'] for a in links 
                if 'sinhala-subtitle' in a['href'].lower()
            ]
            
            if not subtitle_links:
                logger.info(f"No links found on page {page}, ending category")
                break
                
            # Add new URLs
            new_count = 0
            for link in set(subtitle_links):
                if link not in self.processed_urls and link not in found_urls:
                    found_urls.append(link)
                    new_count += 1
                    
            logger.info(f"Page {page}: Found {len(subtitle_links)} links ({new_count} new)")
            page += 1
            time.sleep(random.uniform(0.5, 1.5))
            
        return found_urls
        
    def normalize_filename(self, filename):
        """Normalize filename for duplicate detection"""
        # Remove extension
        name = re.sub(r'\.[^.]+$', '', filename.lower())
        # Remove special chars
        name = re.sub(r'[^a-z0-9]', '', name)
        return name
        
    def process_subtitle(self, url):
        """Download and upload a single subtitle"""
        try:
            logger.info(f"Processing: {url}")
            
            # Fetch detail page
            response = self.fetch_page(url)
            if not response:
                logger.warning(f"Failed to fetch: {url}")
                return False
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_elem = soup.find('h2', class_='subz_title') or soup.find('h1')
            title = title_elem.get_text(strip=True).replace(' Sinhala Subtitle', '') if title_elem else "Unknown"
            
            # Find download button
            dl_button = soup.find('a', class_='sub-download')
            if not dl_button:
                logger.warning(f"No download button: {url}")
                return False
                
            href = dl_button.get('href', '')
            sub_id = re.search(r'sub_id=(\d+)', href)
            nonce = re.search(r'nonce=([^&]+)', href)
            
            if not sub_id or not nonce:
                logger.warning(f"Invalid download params: {url}")
                return False
                
            # Download file
            dl_url = f"{self.base_url}/wp-admin/admin-ajax.php?action=sub_download&sub_id={sub_id.group(1)}&nonce={nonce.group(1)}"
            file_response = self.fetch_page(dl_url)
            if not file_response:
                logger.warning(f"Download failed: {url}")
                return False
                
            # Determine file type and name
            content = file_response.content
            if content[:4] == b'PK\x03\x04':
                ext = '.zip'
            elif content[:4] == b'Rar!':
                ext = '.rar'
            else:
                ext = '.srt'
                
            clean_title = re.sub(r'[^\w\s-]', '', title)[:100]
            filename = f"{clean_title}{ext}"
            normalized = self.normalize_filename(filename)
            
            # Check for duplicates
            with self.lock:
                if normalized in self.processed_filenames:
                    logger.info(f"Duplicate file skipped: {filename}")
                    self.db.mark_processed(url, title)
                    self.processed_urls.add(url)
                    return True
                    
            # Upload to Telegram
            caption = f"<b>{title}</b>\n\nSource: Subz.lk\nLink: {url}"
            file_info = self.telegram.upload_file(content, filename, caption)
            
            if file_info:
                # Save to database
                with self.lock:
                    self.db.save_file(
                        url=url,
                        title=title,
                        filename=filename,
                        normalized_filename=normalized,
                        file_id=file_info['file_id'],
                        file_size=len(content)
                    )
                    self.processed_urls.add(url)
                    self.processed_filenames.add(normalized)
                    
                logger.info(f"✓ Uploaded: {filename}")
                return True
            else:
                logger.warning(f"Upload failed: {filename}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing {url}: {e}", exc_info=True)
            return False
            
    def scrape_all(self, worker_threads=3):
        """Main scraping function"""
        categories = ['/category/movies/', '/category/tv-shows/']
        
        logger.info("=== STARTING FULL SCRAPE ===")
        self.telegram.send_message("<b>Scraper Started</b>\nDiscovering all subtitles...")
        
        # Phase 1: Discover all URLs
        all_urls = []
        for category in categories:
            urls = self.crawl_category(category)
            all_urls.extend(urls)
            logger.info(f"Category {category}: {len(urls)} new subtitles found")
            
        logger.info(f"\n=== DISCOVERY COMPLETE ===")
        logger.info(f"Total new URLs to process: {len(all_urls)}")
        
        if not all_urls:
            logger.info("No new subtitles found")
            self.telegram.send_message("No new subtitles to process")
            return
            
        self.telegram.send_message(f"<b>Processing {len(all_urls)} subtitles...</b>")
        
        # Phase 2: Process all URLs
        success_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=worker_threads) as executor:
            futures = {executor.submit(self.process_subtitle, url): url for url in all_urls}
            
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    success_count += 1
                else:
                    failed_count += 1
                    
                # Progress update every 50 items
                if i % 50 == 0:
                    logger.info(f"Progress: {i}/{len(all_urls)} ({success_count} success, {failed_count} failed)")
                    
                time.sleep(1)  # Rate limiting
                
        # Final report
        self.telegram.send_message(
            f"<b>Scraping Complete!</b>\n"
            f"Processed: {len(all_urls)}\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}"
        )
        logger.info(f"=== SCRAPING COMPLETE ===")

if __name__ == "__main__":
    scraper = SubzScraper()
    scraper.initialize()
    scraper.scrape_all()
