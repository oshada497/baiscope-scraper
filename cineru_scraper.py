"""
Cineru.lk Subtitle Scraper with Cloudflare Bypass
Uses cloudscraper to bypass Cloudflare protection
"""
import cloudscraper
from bs4 import BeautifulSoup
import os
import time
import logging
import random
import re
import threading
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from d1_database import D1Database
from telegram_bot import TelegramBot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class CineruScraper:
    def __init__(self):
        self.base_url = 'https://cineru.lk'
        
        # Create cloudscraper session (bypasses Cloudflare)
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        # Initialize components
        self.db = D1Database(
            os.getenv('CF_ACCOUNT_ID'),
            os.getenv('CF_API_TOKEN'),
            os.getenv('D1_DATABASE_ID'),
            table_prefix='cineru_'  # Separate table from subz.lk
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
        logger.info(f"Cineru.lk Initialized: {len(self.processed_urls)} URLs, {len(self.processed_filenames)} files tracked")
        
    def fetch_page(self, url, retries=5):
        """Fetch a page with Cloudflare bypass"""
        for attempt in range(retries):
            try:
                response = self.scraper.get(url, timeout=30)
                if response.status_code == 200:
                    return response
                if response.status_code == 404:
                    return None
                logger.warning(f"Status {response.status_code} for {url}")
            except Exception as e:
                logger.warning(f"Fetch error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        return None
        
    def find_categories(self):
        """Discover category pages on cineru.lk"""
        logger.info("Discovering categories...")
        response = self.fetch_page(self.base_url)
        
        if not response:
            logger.error("Failed to load homepage")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for category links in navigation
        categories = []
        nav_links = soup.find_all('a', href=True)
        
        for link in nav_links:
            href = link['href']
            text = link.get_text(strip=True).lower()
            
            # Common category patterns
            if any(keyword in text for keyword in ['movie', 'tv', 'series', 'show', 'subtitle']):
                if href.startswith('http'):
                    categories.append(href)
                else:
                    categories.append(f"{self.base_url}{href}")
                    
        # Remove duplicates
        categories = list(set(categories))
        logger.info(f"Found {len(categories)} category pages: {categories}")
        return categories
        
    def crawl_category(self, category_url):
        """Crawl all pages in a category and return subtitle URLs"""
        found_urls = []
        page = 1
        
        while True:
            # Build page URL (adjust based on actual site structure)
            if page == 1:
                url = category_url
            else:
                # Common pagination patterns
                if '?' in category_url:
                    url = f"{category_url}&page={page}"
                else:
                    url = f"{category_url}/page/{page}"
                    
            logger.info(f"Crawling {url}...")
            response = self.fetch_page(url)
            
            if not response:
                logger.info(f"Category ended at page {page}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find subtitle links (adjust selector based on actual HTML)
            subtitle_links = []
            
            # Try common patterns
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Adjust this pattern based on actual cineru.lk URL structure
                if 'subtitle' in href.lower() or 'sinhala' in href.lower():
                    if href.startswith('http'):
                        subtitle_links.append(href)
                    else:
                        subtitle_links.append(f"{self.base_url}{href}")
                        
            if not subtitle_links:
                logger.info(f"No links found on page {page}")
                break
                
            # Add new URLs
            new_count = 0
            for link in set(subtitle_links):
                if link not in self.processed_urls and link not in found_urls:
                    found_urls.append(link)
                    new_count += 1
                    
            logger.info(f"Page {page}: Found {len(subtitle_links)} links ({new_count} new)")
            page += 1
            time.sleep(random.uniform(1, 3))  # Slower to avoid triggering Cloudflare
            
        return found_urls
        
    def normalize_filename(self, filename):
        """Normalize filename for duplicate detection"""
        name = re.sub(r'\.[^.]+$', '', filename.lower())
        name = re.sub(r'[^a-z0-9]', '', name)
        return name
        
    def process_subtitle(self, url):
        """Download and upload a single subtitle from cineru.lk"""
        try:
            logger.info(f"Processing: {url}")
            
            # Fetch detail page
            response = self.fetch_page(url)
            if not response:
                logger.warning(f"Failed to fetch: {url}")
                return False
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title (adjust selector based on actual HTML)
            title_elem = soup.find('h1') or soup.find('h2')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title = title.replace('Sinhala Subtitle', '').replace('Sinhala Sub', '').strip()
            
            # Find download link (adjust based on actual HTML structure)
            download_link = None
            
            # Try common patterns
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True).lower()
                if 'download' in text or 'get subtitle' in text:
                    download_link = link['href']
                    if not download_link.startswith('http'):
                        download_link = f"{self.base_url}{download_link}"
                    break
                    
            if not download_link:
                logger.warning(f"No download link found: {url}")
                return False
                
            # Download file
            logger.info(f"Downloading from: {download_link}")
            file_response = self.fetch_page(download_link)
            
            if not file_response:
                logger.warning(f"Download failed: {url}")
                return False
                
            # Determine file type
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
            caption = f"<b>{title}</b>\n\nSource: Cineru.lk\nLink: {url}"
            file_info = self.telegram.upload_file(content, filename, caption)
            
            if file_info:
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
            
    def scrape_all(self, worker_threads=2):
        """Main scraping function"""
        logger.info("=== STARTING CINERU.LK SCRAPE ===")
        self.telegram.send_message("<b>Cineru.lk Scraper Started</b>\nDiscovering categories...")
        
        # Discover categories
        categories = self.find_categories()
        
        if not categories:
            logger.warning("No categories found, trying default paths...")
            categories = [
                f"{self.base_url}/category/movies",
                f"{self.base_url}/category/tv-series",
                f"{self.base_url}/subtitles"
            ]
        
        # Crawl all categories
        all_urls = []
        for category in categories:
            urls = self.crawl_category(category)
            all_urls.extend(urls)
            logger.info(f"Category {category}: {len(urls)} new subtitles")
            
        logger.info(f"=== DISCOVERY COMPLETE ===")
        logger.info(f"Total new URLs: {len(all_urls)}")
        
        if not all_urls:
            logger.info("No new subtitles found")
            self.telegram.send_message("No new subtitles to process")
            return
            
        self.telegram.send_message(f"<b>Processing {len(all_urls)} cineru.lk subtitles...</b>")
        
        # Process all URLs (slower to avoid Cloudflare issues)
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
                    
                if i % 25 == 0:
                    logger.info(f"Progress: {i}/{len(all_urls)} ({success_count} success)")
                    
                time.sleep(random.uniform(2, 4))  # Slower rate
                
        # Final report
        self.telegram.send_message(
            f"<b>Cineru.lk Scraping Complete!</b>\n"
            f"Processed: {len(all_urls)}\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}"
        )
        logger.info("=== SCRAPING COMPLETE ===")

if __name__ == "__main__":
    scraper = CineruScraper()
    scraper.initialize()
    scraper.scrape_all()
