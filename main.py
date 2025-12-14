import cloudscraper
from bs4 import BeautifulSoup
import os
import time
import logging
import zipfile
import io
import boto3
from urllib.parse import urljoin, urlparse
from botocore.exceptions import ClientError
import tempfile
import random

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaiscopeScraperAdvanced:
    def __init__(self, r2_account_id, r2_access_key, r2_secret_key, r2_bucket_name):
        """
        Initialize scraper with R2 credentials
        
        Args:
            r2_account_id: Your Cloudflare account ID
            r2_access_key: R2 access key
            r2_secret_key: R2 secret key
            r2_bucket_name: R2 bucket name
        """
        self.base_url = 'https://www.baiscope.lk'
        
        # Setup R2 client FIRST
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{r2_account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            region_name='auto'
        )
        self.bucket_name = r2_bucket_name
        
        # Ensure bucket exists
        self._ensure_bucket_exists()
        
        # Create cloudscraper session AFTER R2 setup (bypasses Cloudflare)
        self.scraper = None  # Will be initialized on first use
        
        # User agents for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Bucket '{self.bucket_name}' exists")
        except ClientError:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Created bucket '{self.bucket_name}'")
            except Exception as e:
                logger.error(f"Error creating bucket: {e}")
    
    def _rotate_user_agent(self):
        """Rotate user agent to appear more human-like"""
        scraper = self._get_scraper()
        scraper.headers.update({
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def _get_scraper(self):
        """Lazy initialization of cloudscraper to avoid conflicts with boto3"""
        if self.scraper is None:
            logger.info("Initializing cloudscraper...")
            self.scraper = cloudscraper.create_scraper()
        return self.scraper
    
    def get_page(self, url, retries=3):
        """Fetch a page with Cloudflare bypass and retry logic"""
        scraper = self._get_scraper()
        for attempt in range(retries):
            try:
                # Don't rotate user agent - it breaks cloudscraper's Cloudflare bypass
                logger.info(f"Fetching {url} (attempt {attempt + 1})")
                response = scraper.get(url, timeout=30)
                response.raise_for_status()
                
                # Random delay between requests (2-5 seconds)
                time.sleep(random.uniform(2, 5))
                return response
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(5, 10))
                else:
                    logger.error(f"Failed to fetch {url} after {retries} attempts")
                    return None
    
    def get_all_subtitle_pages(self):
        """Get all subtitle listing pages"""
        subtitle_urls = []
        page = 1
        max_pages = 2000  # Increased to handle 20,000+ subtitles (roughly 10-15 per page)
        
        while page <= max_pages:
            # The site uses /subtitles/ as main listing page
            if page == 1:
                url = f"{self.base_url}/subtitles/"
            else:
                url = f"{self.base_url}/subtitles/page/{page}/"
            
            logger.info(f"Fetching subtitle list page {page}")
            response = self.get_page(url)
            
            if not response:
                break
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all links - the site uses Elementor and posts end with -sinhala-subtitles/
            all_links = soup.find_all('a', href=True)
            found_on_page = 0
            
            for link in all_links:
                href = link.get('href', '')
                # Look for actual subtitle post URLs (not categories)
                if '-sinhala-subtitles' in href and '/category/' not in href:
                    full_url = href if href.startswith('http') else urljoin(self.base_url, href)
                    if full_url not in subtitle_urls:
                        subtitle_urls.append(full_url)
                        found_on_page += 1
            
            logger.info(f"Found {found_on_page} unique subtitle links on page {page}")
            
            if found_on_page == 0:
                logger.warning(f"No subtitle links found on page {page}")
                break
            
            # Check for next page - look for pagination links
            next_page_url = f"{self.base_url}/subtitles/page/{page + 1}/"
            next_btn = soup.find('a', href=next_page_url)
            if not next_btn:
                # Also check for 'next' class
                next_btn = soup.find('a', class_='next')
            
            if not next_btn:
                logger.info("No more pages found")
                break
            
            page += 1
            
            # Be respectful - don't scrape too fast
            time.sleep(random.uniform(3, 6))
        
        logger.info(f"Total subtitle pages found: {len(subtitle_urls)}")
        return subtitle_urls
    
    def extract_srt_from_zip(self, zip_content):
        """Extract .srt files from ZIP content"""
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
            # If it's not a ZIP, assume it's a direct SRT file
            if zip_content[:3] == b'\xef\xbb\xbf' or b'-->' in zip_content[:200]:
                srt_files['subtitle.srt'] = zip_content
        except Exception as e:
            logger.error(f"Error extracting ZIP: {e}")
        
        return srt_files
    
    def upload_to_r2(self, file_content, file_name, metadata=None):
        """Upload file to Cloudflare R2"""
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
        """Download subtitle, extract SRT files, and upload to R2"""
        logger.info(f"Processing: {subtitle_url}")
        
        response = self.get_page(subtitle_url)
        if not response:
            return False
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract movie title for metadata
        movie_title = soup.find('h1')
        title_text = movie_title.get_text(strip=True) if movie_title else 'Unknown'
        
        # Find download link - look for actual file URLs first
        download_link = None
        
        # Pattern 1: Look for direct file links (.zip, .srt, .rar)
        for link in soup.find_all('a', href=True):
            href = link['href']
            if any(ext in href.lower() for ext in ['.zip', '.srt', '.rar']):
                download_link = href
                logger.info(f"Found direct file link: {href[:80]}")
                break
        
        # Pattern 2: Look for download manager links (download.php, ?download=)
        if not download_link:
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'download' in href.lower() and ('?' in href or '.php' in href):
                    download_link = href
                    logger.info(f"Found download manager link: {href[:80]}")
                    break
        
        # Pattern 3: Look for buttons with download text that contain file URLs
        if not download_link:
            for link in soup.find_all('a', href=True):
                href = link['href']
                text = link.get_text(strip=True).lower()
                # Skip generic redirect domains
                if 'baiscopedownloads.link' in href:
                    continue
                if any(keyword in text for keyword in ['download subtitle', 'get subtitle', '.srt', '.zip']):
                    download_link = href
                    logger.info(f"Found download button: {href[:80]}")
                    break
        
        if not download_link:
            logger.warning(f"No valid download link found on {subtitle_url}")
            return False
        
        # Download the file
        download_url = urljoin(self.base_url, download_link)
        logger.info(f"Downloading from: {download_url}")
        
        try:
            file_response = self.get_page(download_url)
            if not file_response:
                return False
            
            file_content = file_response.content
            
            # Extract SRT files
            srt_files = self.extract_srt_from_zip(file_content)
            
            if not srt_files:
                logger.warning("No SRT files found")
                return False
            
            # Upload each SRT file to R2
            success_count = 0
            for srt_filename, srt_content in srt_files.items():
                # Generate clean filename
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
        """Main scraping method"""
        logger.info("Starting Baiscope.lk subtitle scraper with Cloudflare bypass...")
        
        # Get all subtitle pages
        subtitle_urls = self.get_all_subtitle_pages()
        
        if limit:
            subtitle_urls = subtitle_urls[:limit]
            logger.info(f"Limited to first {limit} subtitles")
        
        # Process each subtitle
        success_count = 0
        for i, url in enumerate(subtitle_urls, 1):
            logger.info(f"Processing {i}/{len(subtitle_urls)}: {url}")
            if self.download_and_process_subtitle(url):
                success_count += 1
            
            # Random delay between subtitle pages
            time.sleep(random.uniform(4, 8))
        
        logger.info(f"Scraping complete! Successfully processed {success_count}/{len(subtitle_urls)} subtitles")
        return success_count

if __name__ == '__main__':
    # Get credentials from environment variables
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'baiscope-subtitles')
    
    # Check if credentials are set
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY]):
        logger.error("Missing R2 credentials! Please set the following environment variables:")
        logger.error("  - R2_ACCOUNT_ID: Your Cloudflare account ID")
        logger.error("  - R2_ACCESS_KEY: Your R2 access key")
        logger.error("  - R2_SECRET_KEY: Your R2 secret key")
        logger.error("  - R2_BUCKET_NAME (optional): Bucket name (default: baiscope-subtitles)")
        exit(1)
    
    scraper = BaiscopeScraperAdvanced(
        r2_account_id=R2_ACCOUNT_ID,
        r2_access_key=R2_ACCESS_KEY,
        r2_secret_key=R2_SECRET_KEY,
        r2_bucket_name=R2_BUCKET_NAME
    )
    
    # Full scrape - no limit for production
    scraper.scrape_all()
