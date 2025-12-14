from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import zipfile
import io
import boto3
from urllib.parse import urljoin, urlparse
from botocore.exceptions import ClientError
import random
import requests
import threading

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.enabled = bool(bot_token and chat_id)
        
    def send_message(self, message):
        if not self.enabled:
            return False
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, data=data, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Failed to send Telegram message: {e}")
            return False


class ProgressTracker:
    def __init__(self, telegram_notifier, interval=60):
        self.notifier = telegram_notifier
        self.interval = interval
        self.total_found = 0
        self.processed = 0
        self.success = 0
        self.failed = 0
        self.start_time = None
        self.running = False
        self.thread = None
        
    def start(self, total_found):
        self.total_found = total_found
        self.start_time = time.time()
        self.running = True
        self.thread = threading.Thread(target=self._notification_loop, daemon=True)
        self.thread.start()
        self.notifier.send_message(
            f"<b>Baiscope Scraper Started</b>\n"
            f"Total subtitles found: {total_found}"
        )
        
    def update(self, success=True):
        self.processed += 1
        if success:
            self.success += 1
        else:
            self.failed += 1
            
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
                    f"<b>Scraper Progress Update</b>\n"
                    f"Processed: {self.processed}/{self.total_found} ({(self.processed/self.total_found*100):.1f}%)\n"
                    f"Success: {self.success} | Failed: {self.failed}\n"
                    f"Rate: {rate:.1f}/min\n"
                    f"Elapsed: {hours}h {minutes}m\n"
                    f"ETA: ~{eta_hours}h {eta_mins}m"
                )


class BaiscopeScraperAdvanced:
    def __init__(self, r2_account_id, r2_access_key, r2_secret_key, r2_bucket_name, 
                 telegram_token=None, telegram_chat_id=None):
        self.base_url = 'https://www.baiscope.lk'
        
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{r2_account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            region_name='auto'
        )
        self.bucket_name = r2_bucket_name
        
        self._ensure_bucket_exists()
        
        self.notifier = TelegramNotifier(telegram_token, telegram_chat_id)
        self.tracker = ProgressTracker(self.notifier, interval=60)
        
        self.browser_versions = ["chrome110", "chrome116", "chrome120", "chrome124"]
    
    def _ensure_bucket_exists(self):
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' exists")
        except ClientError:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Created bucket '{self.bucket_name}'")
            except Exception as e:
                logger.error(f"Error creating bucket: {e}")
    
    def get_page(self, url, retries=3):
        for attempt in range(retries):
            try:
                browser = random.choice(self.browser_versions)
                logger.info(f"Fetching {url} (attempt {attempt + 1}, browser: {browser})")
                
                response = curl_requests.get(
                    url,
                    impersonate=browser,
                    timeout=30,
                    headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1'
                    }
                )
                response.raise_for_status()
                
                time.sleep(random.uniform(0.5, 1.5))
                return response
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(5, 10))
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
    
    def get_all_subtitle_pages(self):
        subtitle_urls = []
        page = 1
        max_pages = 2000
        consecutive_empty = 0
        
        while page <= max_pages:
            if page == 1:
                url = f"{self.base_url}/subtitles/"
            else:
                url = f"{self.base_url}/subtitles/page/{page}/"
            
            logger.info(f"Fetching subtitle list page {page}")
            response = self.get_page(url)
            
            if not response:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                page += 1
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            all_links = soup.find_all('a', href=True)
            found_on_page = 0
            
            for link in all_links:
                href = link.get('href', '')
                if ('-sinhala-subtitles' in href or '-sinhala-subtitle' in href) and '/category/' not in href and '/tag/' not in href:
                    full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                    if full_url not in subtitle_urls and 'baiscope.lk' in full_url:
                        subtitle_urls.append(full_url)
                        found_on_page += 1
            
            logger.info(f"Found {found_on_page} unique subtitle links on page {page} (Total: {len(subtitle_urls)})")
            
            if found_on_page == 0:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    logger.info(f"3 consecutive empty pages, stopping at page {page}")
                    break
            else:
                consecutive_empty = 0
            
            page += 1
            
            time.sleep(random.uniform(1, 2))
        
        logger.info(f"Total subtitle pages found: {len(subtitle_urls)}")
        return subtitle_urls
    
    def extract_srt_from_zip(self, zip_content):
        srt_files = {}
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
                for file_info in zip_file.filelist:
                    if file_info.filename.lower().endswith('.srt'):
                        logger.info(f"Extracting: {file_info.filename}")
                        srt_content = zip_file.read(file_info.filename)
                        srt_files[file_info.filename] = srt_content
        except zipfile.BadZipFile:
            logger.warning("Not a valid ZIP file, might be direct SRT")
            if zip_content[:3] == b'\xef\xbb\xbf' or b'-->' in zip_content[:200]:
                srt_files['subtitle.srt'] = zip_content
        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}")
        
        return srt_files
    
    def upload_to_r2(self, file_content, file_name, metadata=None):
        try:
            extra_args = {}
            if metadata:
                extra_args['Metadata'] = metadata
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=file_name,
                Body=file_content,
                **extra_args
            )
            
            logger.info(f"Uploaded to R2: {file_name}")
            return True
        except Exception as e:
            logger.error(f"Error uploading to R2: {e}")
            return False
    
    def download_and_process_subtitle(self, subtitle_url):
        logger.info(f"Processing: {subtitle_url}")
        
        response = self.get_page(subtitle_url)
        if not response:
            return False
        
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
            return False
        
        download_url = urljoin(self.base_url, download_link)
        logger.info(f"Downloading from: {download_url}")
        
        try:
            file_response = self.get_page(download_url)
            if not file_response:
                return False
            
            file_content = file_response.content
            
            srt_files = self.extract_srt_from_zip(file_content)
            
            if not srt_files:
                logger.warning("No SRT files found")
                return False
            
            success_count = 0
            for srt_filename, srt_content in srt_files.items():
                clean_title = ''.join(c for c in title_text if c.isalnum() or c in (' ', '-', '_'))
                clean_title = clean_title.strip().replace(' ', '_')[:100]
                
                r2_filename = f"subtitles/{clean_title}/{srt_filename}"
                
                metadata = {
                    'source_url': subtitle_url,
                    'movie_title': title_text.encode('ascii', 'ignore').decode('ascii'),
                    'download_date': time.strftime('%Y-%m-%d')
                }
                
                if self.upload_to_r2(srt_content, r2_filename, metadata):
                    success_count += 1
            
            logger.info(f"Uploaded {success_count}/{len(srt_files)} SRT files to R2")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error processing subtitle: {e}")
            return False
    
    def scrape_all(self, limit=None):
        logger.info("Starting Baiscope.lk subtitle scraper with curl_cffi browser impersonation...")
        
        subtitle_urls = self.get_all_subtitle_pages()
        
        if limit:
            subtitle_urls = subtitle_urls[:limit]
            logger.info(f"Limited to first {limit} subtitles")
        
        if len(subtitle_urls) > 0:
            self.tracker.start(len(subtitle_urls))
        
        success_count = 0
        for i, url in enumerate(subtitle_urls, 1):
            logger.info(f"Processing {i}/{len(subtitle_urls)}: {url}")
            success = self.download_and_process_subtitle(url)
            if success:
                success_count += 1
            self.tracker.update(success=success)
            
            time.sleep(random.uniform(1, 2))
        
        if len(subtitle_urls) > 0:
            self.tracker.stop()
        
        logger.info(f"Scraping complete! Successfully processed {success_count}/{len(subtitle_urls)} subtitles")
        return success_count


if __name__ == '__main__':
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'baiscope-subtitles')
    
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY]):
        logger.error("Missing R2 credentials! Please set the following environment variables:")
        logger.error("  - R2_ACCOUNT_ID: Your Cloudflare account ID")
        logger.error("  - R2_ACCESS_KEY: Your R2 access key")
        logger.error("  - R2_SECRET_KEY: Your R2 secret key")
        logger.error("  - R2_BUCKET_NAME (optional): Bucket name (default: baiscope-subtitles)")
        exit(1)
    
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram notifications disabled. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable.")
    
    scraper = BaiscopeScraperAdvanced(
        r2_account_id=R2_ACCOUNT_ID,
        r2_access_key=R2_ACCESS_KEY,
        r2_secret_key=R2_SECRET_KEY,
        r2_bucket_name=R2_BUCKET_NAME,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    
    scraper.scrape_all()
