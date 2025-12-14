from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup
import os
import time
import logging
import zipfile
import io
import json
import boto3
from urllib.parse import urljoin, urlparse
from botocore.exceptions import ClientError
import random
import requests
import threading
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed

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
                 telegram_token=None, telegram_chat_id=None, batch_size=100):
        self.base_url = 'https://www.baiscope.lk'
        self.batch_size = batch_size
        self.state_file = 'scraper_state/progress.json'
        self.urls_file = 'scraper_state/discovered_urls.json'
        
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
        
        self.processed_urls = self._load_state()
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, saving state before exit...")
            self._save_state()
            self.notifier.send_message(
                f"<b>Scraper Interrupted</b>\n"
                f"Saved progress: {len(self.processed_urls)} URLs processed\n"
                f"Will resume from here on next run"
            )
            logger.info("State saved, exiting gracefully")
        
        try:
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
            logger.info("Signal handlers registered for graceful shutdown")
        except Exception as e:
            logger.warning(f"Could not register signal handlers: {e}")
    
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
    
    def _load_state(self):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=self.state_file)
            state = json.loads(response['Body'].read().decode('utf-8'))
            processed = set(state.get('processed_urls', []))
            logger.info(f"Loaded state: {len(processed)} previously processed URLs")
            return processed
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info("No previous state found, starting fresh")
            else:
                logger.warning(f"Error loading state: {e}")
            return set()
        except Exception as e:
            logger.warning(f"Error loading state: {e}")
            return set()
    
    def _save_state(self):
        try:
            state = {
                'processed_urls': list(self.processed_urls),
                'last_updated': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=self.state_file,
                Body=json.dumps(state),
                ContentType='application/json'
            )
            logger.info(f"Saved state: {len(self.processed_urls)} processed URLs")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def _load_discovered_urls(self):
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=self.urls_file)
            data = json.loads(response['Body'].read().decode('utf-8'))
            urls = data.get('urls', [])
            discovered_at = data.get('discovered_at', 'unknown')
            logger.info(f"Loaded {len(urls)} discovered URLs from R2 (discovered: {discovered_at})")
            return urls
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                logger.info("No discovered URLs cache found")
            return None
        except Exception as e:
            logger.warning(f"Error loading discovered URLs: {e}")
            return None
    
    def _save_discovered_urls(self, urls):
        try:
            data = {
                'urls': urls,
                'count': len(urls),
                'discovered_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=self.urls_file,
                Body=json.dumps(data),
                ContentType='application/json'
            )
            logger.info(f"Saved {len(urls)} discovered URLs to R2")
        except Exception as e:
            logger.error(f"Error saving discovered URLs: {e}")
    
    def get_page(self, url, retries=4):
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
                        'Upgrade-Insecure-Requests': '1',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    }
                )
                response.raise_for_status()
                
                time.sleep(random.uniform(1.5, 3.0))
                return response
            except Exception as e:
                error_str = str(e)
                is_403 = '403' in error_str
                
                if is_403:
                    backoff_time = random.uniform(3, 6) * (attempt + 1)
                    logger.warning(f"403 Blocked! Attempt {attempt + 1} - backing off for {backoff_time:.1f}s")
                    time.sleep(backoff_time)
                else:
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
                    if attempt < retries - 1:
                        time.sleep(random.uniform(5, 10))
                
                if attempt == retries - 1:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
    
    def get_all_subtitle_pages(self):
        subtitle_urls = set()
        
        categories = [
            "/category/sinhala-subtitles/movies/",
            "/category/sinhala-subtitles/",
            "/category/anime/",
            "/category/war/",
            "/category/crime/",
            "/category/action/",
            "/category/adventure/",
            "/category/comedy/",
            "/category/drama/",
            "/category/fantasy/",
            "/category/horror/",
            "/category/mystery/",
            "/category/romance/",
            "/category/sci-fi/",
            "/category/thriller/",
            "/category/animation/",
            "/category/biography/",
            "/category/family/",
            "/category/history/",
            "/category/music/",
            "/category/sport/",
            "/category/western/",
            "/category/documentary/",
            "/category/tv-series/",
            "/category/hindi-subtitles/",
            "/category/korean-subtitles/",
            "/category/tamil-subtitles/",
        ]
        
        for category in categories:
            page = 1
            max_pages = 500
            consecutive_empty = 0
            
            while page <= max_pages:
                if page == 1:
                    url = f"{self.base_url}{category}"
                else:
                    url = f"{self.base_url}{category}page/{page}/"
                
                logger.info(f"Fetching {category} page {page}")
                response = self.get_page(url)
                
                if not response:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        break
                    page += 1
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                all_links = soup.find_all('a', href=True)
                found_on_page = 0
                
                for link in all_links:
                    href = link.get('href', '')
                    if ('sinhala-subtitle' in href.lower() or 'subtitles' in href.lower()) and '/category/' not in href and '/tag/' not in href:
                        full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                        if full_url not in subtitle_urls and 'baiscope.lk' in full_url and full_url != self.base_url + '/':
                            subtitle_urls.add(full_url)
                            found_on_page += 1
                
                logger.info(f"Found {found_on_page} new links on {category} page {page} (Total: {len(subtitle_urls)})")
                
                if found_on_page == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        logger.info(f"No more content in {category}")
                        break
                else:
                    consecutive_empty = 0
                
                page += 1
                time.sleep(random.uniform(0.5, 1))
        
        logger.info(f"Total subtitle pages found: {len(subtitle_urls)}")
        return list(subtitle_urls)
    
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
    
    def scrape_all(self, limit=None, workers=3, force_recrawl=False):
        logger.info("Starting Baiscope.lk subtitle scraper with curl_cffi browser impersonation...")
        logger.info(f"Using {workers} parallel workers, batch size: {self.batch_size}")
        logger.info(f"Previously processed URLs: {len(self.processed_urls)}")
        
        cached_urls = None if force_recrawl else self._load_discovered_urls()
        
        if cached_urls and len(cached_urls) > 0:
            subtitle_urls = cached_urls
            logger.info(f"Using {len(subtitle_urls)} cached URLs (skipping crawl)")
            self.notifier.send_message(
                f"<b>Scraper Resumed</b>\n"
                f"Using cached URLs: {len(subtitle_urls)}\n"
                f"Already processed: {len(self.processed_urls)}"
            )
        else:
            logger.info("No cached URLs found, crawling all categories...")
            self.notifier.send_message("<b>Scraper Starting</b>\nCrawling all categories to find subtitles...")
            subtitle_urls = self.get_all_subtitle_pages()
            self._save_discovered_urls(subtitle_urls)
            self.notifier.send_message(f"<b>Crawl Complete</b>\nDiscovered {len(subtitle_urls)} subtitle URLs")
        
        new_urls = [url for url in subtitle_urls if url not in self.processed_urls]
        skipped_count = len(subtitle_urls) - len(new_urls)
        logger.info(f"Skipping {skipped_count} already processed URLs")
        logger.info(f"New URLs to process: {len(new_urls)}")
        
        if self.batch_size and len(new_urls) > self.batch_size:
            new_urls = new_urls[:self.batch_size]
            logger.info(f"Processing batch of {self.batch_size} URLs (remaining: {len(subtitle_urls) - skipped_count - self.batch_size})")
        
        if limit and len(new_urls) > limit:
            new_urls = new_urls[:limit]
            logger.info(f"Limited to first {limit} subtitles")
        
        if len(new_urls) == 0:
            logger.info("No new URLs to process!")
            self.notifier.send_message("<b>Scraper Status</b>\nNo new subtitles to process. All caught up!")
            return 0
        
        self.tracker.start(len(new_urls))
        
        success_count = 0
        batch_processed = 0
        
        def process_url(url):
            try:
                result = self.download_and_process_subtitle(url)
                time.sleep(random.uniform(0.5, 1))
                return url, result
            except Exception as e:
                logger.error(f"Error processing {url}: {e}")
                return url, False
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_url, url): url for url in new_urls}
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    processed_url, success = future.result()
                    self.processed_urls.add(processed_url)
                    batch_processed += 1
                    
                    if success:
                        success_count += 1
                    self.tracker.update(success=success)
                    
                    if batch_processed % 10 == 0:
                        self._save_state()
                        
                except Exception as e:
                    logger.error(f"Future error for {url}: {e}")
                    self.processed_urls.add(url)
                    self.tracker.update(success=False)
        
        self._save_state()
        self.tracker.stop()
        
        logger.info(f"Batch complete! Successfully processed {success_count}/{len(new_urls)} subtitles")
        logger.info(f"Total processed so far: {len(self.processed_urls)}")
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
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 100))
    
    scraper = BaiscopeScraperAdvanced(
        r2_account_id=R2_ACCOUNT_ID,
        r2_access_key=R2_ACCESS_KEY,
        r2_secret_key=R2_SECRET_KEY,
        r2_bucket_name=R2_BUCKET_NAME,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        batch_size=BATCH_SIZE
    )
    
    scraper.scrape_all()
