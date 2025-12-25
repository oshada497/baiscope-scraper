import os
import requests
import zipfile
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from telebot import TeleBot
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
bot = TeleBot(TELEGRAM_TOKEN)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

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
                process_download(link, "biscope.lk", title)
                
    except Exception as e:
        logger.error(f"Biscope scrape error: {e}")

def scrape_subz():
    """Scrape subz.lk for subtitle files"""
    logger.info("Starting subz.lk scrape...")
    try:
        url = "https://subz.lk/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('a', class_='entry-title-link')
        
        for item in items[:5]:
            title = item.text.strip()
            link = item.get('href')
            if link:
                process_download(link, "subz.lk", title)
                
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
        items = soup.find_all('a', class_='post-link')
        
        for item in items[:5]:
            title = item.text.strip()
            link = item.get('href')
            if link:
                process_download(link, "zoom.lk", title)
                
    except Exception as e:
        logger.error(f"Zoom scrape error: {e}")

def process_download(url, source, title):
    """Download files from subtitle page and upload to Telegram"""
    try:
        logger.info(f"Processing: {title} from {source}")
        response = requests.get(url, timeout=15, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        zip_file = None
        srt_file = None
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href:
                if href.endswith('.zip'):
                    zip_file = href
                elif href.endswith('.srt'):
                    srt_file = href
        
        if zip_file:
            upload_file_to_telegram(zip_file, source, title, "zip")
        elif srt_file:
            upload_file_to_telegram(srt_file, source, title, "srt")
        else:
            logger.warning(f"No ZIP or SRT file found for {title}")
            
    except Exception as e:
        logger.error(f"Error processing {title}: {e}")

def upload_file_to_telegram(file_url, source, title, file_type):
    """Download and upload file to Telegram"""
    try:
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
                bot.send_document(TELEGRAM_CHAT_ID, f, caption=caption)
            
            logger.info(f"Uploaded {filename} to Telegram")
            filepath.unlink()
        else:
            logger.error(f"Downloaded file is empty: {filename}")
            filepath.unlink()
            
    except Exception as e:
        logger.error(f"Upload error for {file_url}: {e}")

def main():
    """Run all scrapers"""
    logger.info("Starting subtitle scraper...")
    
    try:
        scrape_biscope()
        time.sleep(2)
        
        scrape_subz()
        time.sleep(2)
        
        scrape_zoom()
        
        logger.info("Scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Main error: {e}")

if __name__ == "__main__":
    main()
