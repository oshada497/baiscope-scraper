"""
Cineru.lk Scraper using FlareSolverr for Cloudflare bypass
FlareSolverr must be running as a separate service
"""
import requests
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

class CineruScraperV2:
    def __init__(self):
        self.base_url = 'https://cineru.lk'
        
        # FlareSolverr endpoint (set as environment variable)
        self.flaresolverr_url = os.getenv('FLARESOLVERR_URL', 'http://localhost:8191/v1')
        
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
        self.session_id = None
        
    def initialize(self):
        """Load existing data and create FlareSolverr session"""
        if self.db.enabled:
            self.db.create_tables()
            self.processed_urls = self.db.get_processed_urls()
            self.processed_filenames = self.db.get_processed_filenames()
        
        # Create FlareSolverr session
        try:
            response = requests.post(self.flaresolverr_url, json={
                'cmd': 'sessions.create'
            }, timeout=30)
            data = response.json()
            if data.get('status') == 'ok':
                self.session_id = data['session']
                logger.info(f"FlareSolverr session created: {self.session_id}")
        except Exception as e:
            logger.warning(f"FlareSolverr not available: {e}")
            self.session_id = None
            
        logger.info(f"Cineru.lk Initialized: {len(self.processed_urls)} URLs, {len(self.processed_filenames)} files tracked")
        
    def fetch_page(self, url, retries=3):
        """Fetch page using FlareSolverr"""
        if not self.session_id:
            logger.error("No FlareSolverr session - cannot bypass Cloudflare")
            return None
            
        for attempt in range(retries):
            try:
                payload = {
                    'cmd': 'request.get',
                    'url': url,
                    'session': self.session_id,
                    'maxTimeout': 60000
                }
                
                response = requests.post(self.flaresolverr_url, json=payload, timeout=70)
                data = response.json()
                
                if data.get('status') == 'ok':
                    solution = data.get('solution', {})
                    html = solution.get('response')
                    status = solution.get('status')
                    
                    if status == 200 and html:
                        # Create mock response object
                        class MockResponse:
                            def __init__(self, text, status_code):
                                self.text = text
                                self.status_code = status_code
                                self.content = text.encode('utf-8')
                        return MockResponse(html, status)
                    elif status == 404:
                        return None
                        
                logger.warning(f"FlareSolverr attempt {attempt + 1} failed for {url}")
                time.sleep(3 * (attempt + 1))
                
            except Exception as e:
                logger.error(f"FlareSolverr error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(5)
                    
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
                if href.startswith('http'):
                    categories.append(href)
                else:
                    categories.append(f"{self.base_url}{href}")
                    
        categories = list(set(categories))
        logger.info(f"Found {len(categories)} categories")
        return categories if categories else [
            f"{self.base_url}/category/movies",
            f"{self.base_url}/category/tv-series"
        ]
        
    def crawl_category(self, category_url):
        """Crawl all pages in a category"""
        found_urls = []
        page = 1
        
        while True:
            if page == 1:
                url = category_url
            else:
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
            subtitle_links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'subtitle' in href.lower() or 'sinhala' in href.lower():
                    if href.startswith('http'):
                        subtitle_links.append(href)
                    else:
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
            
            title_elem = soup.find('h1') or soup.find('h2')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title = title.replace('Sinhala Subtitle', '').replace('Sinhala Sub', '').strip()
            
            download_link = None
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True).lower()
                if 'download' in text or 'get' in text:
                    download_link = link['href']
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
            if content[:4] == b'PK\x03\x04':
                ext = '.zip'
            elif content[:4] == b'Rar!':
                ext = '.rar'
            else:
                ext = '.srt'
                
            clean_title = re.sub(r'[^\w\s-]', '', title)[:100]
            filename = f"{clean_title}{ext}"
            normalized = self.normalize_filename(filename)
            
            with self.lock:
                if normalized in self.processed_filenames:
                    logger.info(f"Duplicate: {filename}")
                    self.db.mark_processed(url, title)
                    self.processed_urls.add(url)
                    return True
                    
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
        logger.info("=== STARTING CINERU.LK SCRAPE (FlareSolverr) ===")
        self.telegram.send_message("<b>Cineru.lk Scraper Started</b>\nUsing FlareSolver...")
        
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
            self.telegram.send_message("No new subtitles found")
            return
            
        self.telegram.send_message(f"<b>Processing {len(all_urls)} cineru.lk subtitles...</b>")
        
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
                    logger.info(f"Progress: {i}/{len(all_urls)}")
                    
                time.sleep(random.uniform(3, 5))
                
        self.telegram.send_message(
            f"<b>Cineru.lk Complete!</b>\n"
            f"Processed: {len(all_urls)}\n"
            f"Success: {success_count}\n"
            f"Failed: {failed_count}"
        )
        logger.info("=== SCRAPING COMPLETE ===")
        
        # Cleanup FlareSolverr session
        if self.session_id:
            try:
                requests.post(self.flaresolverr_url, json={
                    'cmd': 'sessions.destroy',
                    'session': self.session_id
                })
            except:
                pass

if __name__ == "__main__":
    scraper = CineruScraperV2()
    scraper.initialize()
    scraper.scrape_all()
