"""
Cineru.lk Scraper using Manual Cookies for Cloudflare Bypass
Simple and effective - no external services needed
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
        
        # Create session with realistic browser headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
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
        """Fetch page using cookies"""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    # Check if we got Cloudflare challenge page
                    if 'Checking your browser' in response.text or 'Just a moment' in response.text:
                        logger.error("Cookies expired or invalid - got Cloudflare challenge")
                        return None
                    return response
                elif response.status_code == 403:
                    logger.warning(f"403 Forbidden - cookies may be expired")
                    return None
                elif response.status_code == 404:
                    return None
                    
            except Exception as e:
                logger.warning(f"Fetch error (attempt {attempt + 1}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    
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
                    url = f"{category_url}/page/{page}/"
                    
            logger.info(f"Crawling {url}...")
            response = self.fetch_page(url)
            
            if not response:
                logger.info(f"Category ended at page {page}")
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            subtitle_links = []
            
            # Look for subtitle links
            for link in soup.find_all('a', href=True):
                href = link['href']
                # Common patterns for subtitle detail pages
                if any(pattern in href.lower() for pattern in ['subtitle', 'sinhala', '/sub/', '/movie/', '/tv/']):
                    if href.startswith('http') and 'cineru.lk' in href:
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
            
            if new_count == 0 and page > 1:
                # All duplicates, likely end of new content
                break
                
            page += 1
            time.sleep(random.uniform(1, 3))
            
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
            title_elem = soup.find('h1') or soup.find('h2', class_='entry-title')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title = title.replace('Sinhala Subtitle', '').replace('Sinhala Sub', '').strip()
            
            # Find download link
            download_link = None
            for link in soup.find_all('a', href=True):
                text = link.get_text(strip=True).lower()
                href = link['href']
                if 'download' in text or 'download' in href.lower():
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
            if len(content) < 100:
                logger.warning(f"File too small (likely error page): {url}")
                return False
                
            # Determine file type
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
        logger.info("=== STARTING CINERU.LK SCRAPE (Header-Based) ===")
        self.telegram.send_message("<b>Cineru.lk Scraper Started</b>\nUsing browser headers...")
        
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
                    
                time.sleep(random.uniform(2, 4))
                
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

