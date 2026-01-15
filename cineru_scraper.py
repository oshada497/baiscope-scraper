"""
Cineru.lk Scraper - Robust Version
Uses curl_cffi for real browser impersonation + Cookies support
"""
from curl_cffi import requests
from bs4 import BeautifulSoup
import os
import time
import logging
import random
import re
import threading
import sys
import json
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
        
        # Initialize session with chrome impersonation and SOCKS5 proxy
        self.session = requests.Session(
            impersonate="chrome120",
            proxies={"http": "socks5://127.0.0.1:10808", "https": "socks5://127.0.0.1:10808"}
        )
        
        # Load cookies if available
        cookies_json = os.getenv('CINERU_COOKIES', '{}')
        try:
            self.cookies = json.loads(cookies_json)
            if self.cookies:
                self.session.cookies.update(self.cookies)
                logger.info(f"Loaded {len(self.cookies)} cookies from environment")
        except Exception as e:
            logger.warning(f"Could not load cookies: {e}")
            self.cookies = {}

        # Standard headers
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Initialize components
        self.db = D1Database(
            os.getenv('CF_ACCOUNT_ID'),
            os.getenv('CF_API_TOKEN'),
            os.getenv('D1_DATABASE_ID'),
            table_prefix='cineru_'
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
        
    def fetch_page(self, url, retries=3):
        """Fetch page using curl_cffi with impersonation"""
        for attempt in range(retries):
            try:
                # curl_cffi requests
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    # Check for Cloudflare challenge in content
                    if 'Checking your browser' in response.text or 'Just a moment' in response.text:
                        logger.error("Got Cloudflare challenge page - Cookies needed or expired!")
                        return None
                    return response
                elif response.status_code == 403:
                    logger.warning(f"403 Forbidden - Cloudflare blocked request (Attempt {attempt+1})")
                elif response.status_code == 404:
                    return None
                    
            except Exception as e:
                logger.warning(f"Fetch error (attempt {attempt + 1}): {e}")
                
            if attempt < retries - 1:
                time.sleep(random.uniform(2, 5))
                    
        return None
        
    def find_categories(self):
        """Discover category pages"""
        logger.info("Discovering categories...")
        response = self.fetch_page(self.base_url)
        
        if not response:
            logger.warning("Failed to load homepage, using default categories")
            return [
                f"{self.base_url}/category/movies",
                f"{self.base_url}/category/tv-series"
            ]
            
        soup = BeautifulSoup(response.text, 'html.parser')
        categories = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            text = link.get_text(strip=True).lower()
            
            if any(keyword in text for keyword in ['movie', 'tv', 'series', 'show']):
                if href.startswith('http') and 'cineru.lk' in href:
                    categories.append(href)
                elif href.startswith('/'):
                    categories.append(f"{self.base_url}{href}")
                    
        # Filter and unique
        categories = list(set([c for c in categories if 'cineru.lk' in c]))
        logger.info(f"Found {len(categories)} categories")
        
        # Fallback if discovery fails but page loaded
        if not categories:
             categories = [f"{self.base_url}/category/movies", f"{self.base_url}/category/tv-series"]
             
        return categories
        
    def crawl_category(self, category_url):
        """Crawl all pages in a category"""
        found_urls = []
        page = 1
        
        while True:
            # Construct URL
            if page == 1:
                url = category_url
            else:
                if '?' in category_url:
                    url = f"{category_url}&page={page}"
                else:
                    url = f"{category_url}/page/{page}/"
                    
            logger.info(f"Crawling {url}...")
            response = self.fetch_page(url)
            
            if not response:
                logger.info(f"Category ended or blocked at page {page}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            subtitle_links = []
            
            # Look for subtitle links - finding a tags
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Check for subtitle listing patterns
                if '/subtitle/' in href or ('/sinhala-' in href and 'subtitle' in href):
                    if href.startswith('http'):
                        if 'cineru.lk' in href:
                            subtitle_links.append(href)
                    elif href.startswith('/'):
                        subtitle_links.append(f"{self.base_url}{href}")
            
            if not subtitle_links:
                logger.info(f"No links found on page {page}")
                break
                
            new_count = 0
            for link in set(subtitle_links):
                if link not in self.processed_urls and link not in found_urls:
                    found_urls.append(link)
                    new_count += 1
                    
            logger.info(f"Page {page}: Found {len(subtitle_links)} links ({new_count} new)")
            
            # Stop if we see a page of all duplicates (optimization)
            # But during first run or deep scraping, we might want to continue.
            # Allowing continue for now, but break if 0 links found total
            if new_count == 0 and page > 5: # Arbitrary depth check to stop deep crawls of old content
                 logger.info("No new items for 5+ pages, stopping category")
                 break

            page += 1
            time.sleep(random.uniform(2, 4))
            
        return found_urls
        
    def normalize_filename(self, filename):
        """Normalize filename for duplicate detection"""
        name = re.sub(r'\.[^.]+$', '', filename.lower())
        name = re.sub(r'[^a-z0-9]', '', name)
        return name
        
    def process_subtitle(self, url):
        """Download and upload a single subtitle"""
        try:
            logger.info(f"Processing: {url}")
            
            response = self.fetch_page(url)
            if not response:
                logger.warning(f"Failed to fetch: {url}")
                return False
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_elem = soup.find('h1', class_='entry-title') or soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title = title.replace('Sinhala Subtitle', '').replace('Sinhala Sub', '').strip()
            
            # Find download link
            download_link = None
            # Need strict extraction logic here
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'download' in href.lower() or 'download' in link.get_text(strip=True).lower():
                    # Helper link check
                    if 'cineru.lk' in href or href.startswith('/'):
                        download_link = href
                        if not download_link.startswith('http'):
                            download_link = f"{self.base_url}{download_link}"
                        break
            
            if not download_link:
                logger.warning(f"No download link: {url}")
                return False
                
            logger.info(f"Downloading from: {download_link}")
            file_response = self.fetch_page(download_link)
            
            if not file_response:
                logger.warning(f"Download failed: {url}")
                return False
                
            content = file_response.content
            # Check if it's an HTML error page usually small
            if len(content) < 500 and b'html' in content.lower():
                 logger.warning(f"Download returned HTML (likely error/block): {url}")
                 return False

            # Determine file type
            if content.startswith(b'PK'):
                ext = '.zip'
            elif content.startswith(b'Rar!'):
                ext = '.rar'
            else:
                ext = '.zip' # Default fallback
                
            clean_title = re.sub(r'[^\w\s-]', '', title)[:100]
            filename = f"{clean_title}{ext}"
            normalized = self.normalize_filename(filename)
            
            # Check for duplicates
            with self.lock:
                if normalized in self.processed_filenames:
                    logger.info(f"Duplicate: {filename}")
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
                return False
                
        except Exception as e:
            logger.error(f"Error processing {url}: {e}", exc_info=True)
            return False
            
    def scrape_all(self, worker_threads=2):
        """Main scraping function"""
        logger.info("=== STARTING CINERU.LK SCRAPE (curl_cffi + Cookies) ===")
        
        if not self.cookies:
            logger.warning("No cookies loaded. Relying on browser impersonation only.")
            self.telegram.send_message("<b>Cineru.lk Scraper Started</b>\nUsing browser impersonation (No cookies)...")
        else:
            self.telegram.send_message("<b>Cineru.lk Scraper Started</b>\nUsing Cookies + Browser Impersonation...")
        
        categories = self.find_categories()
        
        all_urls = []
        for category in categories:
            urls = self.crawl_category(category)
            all_urls.extend(urls)
            logger.info(f"Category {category}: {len(urls)} new subtitles")
            
        logger.info(f"=== DISCOVERY COMPLETE ===")
        logger.info(f"Total new URLs: {len(all_urls)}")
        
        if not all_urls:
            logger.info("No new subtitles found")
            self.telegram.send_message("No new cineru.lk subtitles found")
            return
            
        self.telegram.send_message(f"<b>Processing {len(all_urls)} cineru.lk subtitles...</b>")
        
        success_count = 0
        failed_count = 0
        
        # Use ThreadPool
        with ThreadPoolExecutor(max_workers=worker_threads) as executor:
            futures = {executor.submit(self.process_subtitle, url): url for url in all_urls}
            
            for i, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                    if result:
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                     logger.error(f"Worker failed: {e}")
                     failed_count += 1
                    
                if i % 25 == 0:
                    logger.info(f"Progress: {i}/{len(all_urls)}")
                    
                time.sleep(random.uniform(2, 5))
                
        self.telegram.send_message(
            f"<b>Cineru.lk Complete!</b>\n"
            f"Processed: {len(all_urls)}\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}"
        )
        logger.info("=== SCRAPING COMPLETE ===")

if __name__ == "__main__":
    scraper = CineruScraper()
    scraper.initialize()
    scraper.scrape_all()
