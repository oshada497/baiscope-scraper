"""
Script to run the processor logic for subz.lk
Picks up pending URLs from the queue and processes them (download, upload to Telegram, store metadata).
"""
import os
import logging
import sys
import argparse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subz_scraper import SubzLkScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='Process pending subtitles for subz.lk')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of subtitles to process')
    args = parser.parse_args()

    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        return 1
        
    scraper = SubzLkScraper(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        cf_account_id=CF_ACCOUNT_ID,
        cf_api_token=CF_API_TOKEN,
        d1_database_id=D1_DATABASE_ID
    )
    
    # Run process mode
    scraper.process_queue_mode(limit=args.limit)
    return 0

if __name__ == '__main__':
    exit(main())
