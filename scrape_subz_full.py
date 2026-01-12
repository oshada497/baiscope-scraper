"""
Full scraper for subz.lk - processes all categories and pages
Run once to populate the database with all existing subtitles
"""
import os
import logging
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subz_scraper import SubzLkScraper

# Configure logging to force output to stdout for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """
    Unified Scraper Entry Point
    Executes the full pipeline:
    1. Crawls all categories to discover new subtitles (stored in DB with status='pending')
    2. Processes the queue to download and upload text/zip files (updates DB status)
    """
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN! Please set the environment variable.")
        return 1
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Full scrape of subz.lk')
    parser.add_argument('--limit', type=int, help='Limit number of subtitles to process (for testing)')
    args = parser.parse_args()
    
    logger.info("\n" + "="*60)
    logger.info("STARTING FULL SUBZ.LK SCRAPE")
    logger.info("="*60 + "\n")
    
    try:
        scraper = SubzLkScraper(
            telegram_token=TELEGRAM_BOT_TOKEN,
            telegram_chat_id=TELEGRAM_CHAT_ID,
            cf_account_id=CF_ACCOUNT_ID,
            cf_api_token=CF_API_TOKEN,
            d1_database_id=D1_DATABASE_ID
        )
        
        result = scraper.scrape_all_categories(limit=args.limit)
        
        logger.info("\n" + "="*60)
        logger.info(f"SCRAPING COMPLETE - {result} subtitles processed")
        logger.info("="*60 + "\n")
        
        return 0
        
    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
