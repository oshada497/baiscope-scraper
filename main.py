import os
import requests
import zipfile
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from telebot import TeleBot
import time
import logging
from database import init_database, is_already_processed, add_processed_subtitle, get_processed_count

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_database()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

bot = None
if TELEGRAM_TOKEN:
    bot = TeleBot(TELEGRAM_TOKEN)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

SUBTITLE_EXTENSIONS = {'.zip', '.srt', '.rar', '.7z'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.m3u8', '.ts', '.m2ts', '.mts'}

def is_subtitle_file(url):
    """Check if URL is a subtitle file"""
    if not isinstance(url, str):
        return False
    url_lower = url.lower()
    return any(url_lower.endswith(ext) for ext in SUBTITLE_EXTENSIONS)

def is_video_file(url):
    """Check if URL is a video file"""
    if not isinstance(url, str):
        return False
    url_lower = url.lower()
    return any(url_lower.endswith(ext) for ext in VIDEO_EXTENSIONS)

def scrape_biscope():
    """Scrape biscope.lk for subtitle files"""
    logger.info("Starting biscope.lk scrape...")
    try:
        url = "https://www.biscope.lk/sinhala-subtitles/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('a', class_='post-title-link')
        
        for item in items[:5]:
            title = item.text.strip()
            link = item.get('href')
            if link:
                process_biscope_download(link, title)
                
    except Exception as e:
        logger.error(f"Biscope scrape error: {e}")

def scrape_subz():
    """Scrape subz.lk for subtitle files using card-link class"""
    logger.info("Starting subz.lk scrape...")
    try:
        url = "https://subz.lk/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('a', class_='card-link')
        
        for item in items[:5]:
            title_attr = item.get('title')
            title = (title_attr.strip() if isinstance(title_attr, str) else '') or (item.text.strip() if isinstance(item.text, str) else '')
            link = item.get('href')
            if link and title and isinstance(link, str):
                process_subz_download(link, title)
                
    except Exception as e:
        logger.error(f"Subz scrape error: {e}")

def scrape_zoom():
    """Scrape zoom.lk for subtitle files"""
    logger.info("Starting zoom.lk scrape...")
    try:
        url = "http://zoom.lk/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('a', href=True)
        
        links_found = []
        for item in items:
            href = item.get('href')
            if href and 'zoom.lk' in href and ('/20' in href or '/subtitle' in href):
                title = item.text.strip()
                if title and title not in [l[1] for l in links_found]:
                    links_found.append((href, title))
        
        for link, title in links_found[:5]:
            process_zoom_download(link, title)
                
    except Exception as e:
        logger.error(f"Zoom scrape error: {e}")

def process_biscope_download(url, title):
    """Process biscope.lk download page - only subtitle files"""
    try:
        logger.info(f"Processing biscope: {title}")
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        subtitle_file = None
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if isinstance(href, str) and is_subtitle_file(href) and not is_video_file(href):
                subtitle_file = href
                break
        
        if subtitle_file:
            file_ext = subtitle_file.lower().split('.')[-1]
            upload_file_to_telegram(subtitle_file, "biscope.lk", title, file_ext)
        else:
            logger.warning(f"No subtitle file found for biscope: {title}")
            
    except Exception as e:
        logger.error(f"Error processing biscope {title}: {e}")

def process_subz_download(url, title):
    """Process subz.lk download page - only subtitle files, skip videos"""
    try:
        logger.info(f"Processing subz: {title}")
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try to find download button with sub_id and nonce
        download_link = soup.find('a', class_='sub-download')
        if download_link:
            href = download_link.get('href')
            if href and is_subtitle_file(href) and not is_video_file(href):
                upload_file_to_telegram(href, "subz.lk", title, "zip")
                return
        
        # Fallback: look for direct subtitle file links only
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if isinstance(href, str) and is_subtitle_file(href) and not is_video_file(href):
                file_ext = href.lower().split('.')[-1]
                upload_file_to_telegram(href, "subz.lk", title, file_ext)
                return
        
        logger.warning(f"No subtitle file found for subz: {title}")
            
    except Exception as e:
        logger.error(f"Error processing subz {title}: {e}")

def process_zoom_download(url, title):
    """Process zoom.lk download page - only subtitle files, skip videos"""
    try:
        logger.info(f"Processing zoom: {title}")
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for download monitor links (dlm plugin) - only subtitles
        download_links = soup.find_all('a', class_='dlm-link')
        if download_links:
            for link in download_links:
                href = link.get('href')
                if isinstance(href, str) and is_subtitle_file(href) and not is_video_file(href):
                    file_ext = href.lower().split('.')[-1]
                    upload_file_to_telegram(href, "zoom.lk", title, file_ext)
                    return
        
        # Fallback: look for direct subtitle file links only
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if isinstance(href, str) and is_subtitle_file(href) and not is_video_file(href):
                file_ext = href.lower().split('.')[-1]
                upload_file_to_telegram(href, "zoom.lk", title, file_ext)
                return
        
        logger.warning(f"No subtitle file found for zoom: {title}")
            
    except Exception as e:
        logger.error(f"Error processing zoom {title}: {e}")

def upload_file_to_telegram(file_url, source, title, file_type):
    """Download and upload file to Telegram"""
    try:
        if is_already_processed(file_url):
            logger.info(f"Skipping already processed: {title}")
            return
        
        if not bot or not TELEGRAM_CHAT_ID:
            logger.warning(f"Telegram not configured, saving {file_url} locally")
            add_processed_subtitle(file_url, title, source, file_type)
            return
            
        logger.info(f"Downloading {file_type} file: {file_url}")
        
        file_response = requests.get(file_url, timeout=30, stream=True)
        file_response.raise_for_status()
        
        filename = file_url.split('/')[-1]
        if not filename:
            filename = f"{title.replace(' ', '_')}.{file_type}"
        
        filepath = DOWNLOAD_DIR / filename
        
        with open(filepath, 'wb') as f:
            for chunk in file_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        if filepath.stat().st_size > 0:
            caption = f"📺 {title}\n🔗 Source: {source}\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            with open(filepath, 'rb') as f:
                bot.send_document(int(TELEGRAM_CHAT_ID), f, caption=caption)
            
            logger.info(f"Uploaded {filename} to Telegram")
            add_processed_subtitle(file_url, title, source, file_type)
            filepath.unlink()
        else:
            logger.error(f"Downloaded file is empty: {filename}")
            filepath.unlink()
            
    except Exception as e:
        logger.error(f"Upload error for {file_url}: {e}")

def main():
    """Run all scrapers"""
    logger.info("Starting subtitle scraper...")
    logger.info(f"Total processed so far: {get_processed_count()}")
    
    try:
        scrape_biscope()
        time.sleep(2)
        
        scrape_subz()
        time.sleep(2)
        
        scrape_zoom()
        
        logger.info(f"Scraping completed successfully. Total processed: {get_processed_count()}")
        
    except Exception as e:
        logger.error(f"Main error: {e}")

if __name__ == "__main__":
    main()
