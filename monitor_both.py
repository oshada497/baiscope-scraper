"""
Unified monitoring script for both baiscope.lk and subz.lk
Checks for new subtitles on both sites and processes them
"""
import os
import logging
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subz_scraper import SubzLkScraper

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def main():
    """Monitor both sites for new subtitles"""
    # Get credentials from environment
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN! Please set the environment variable.")
        return 1
    
    if not D1_DATABASE_ID:
        logger.warning("D1 database not configured - duplicate detection will be limited")
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Monitor subtitle sites for new content')
    parser.add_argument('--limit', type=int, help='Limit number of subtitles to process (for testing)')
    parser.add_argument('--site', choices=['all', 'baiscope', 'subz'], default='all',
                       help='Which site to monitor (default: all)')
    args = parser.parse_args()
    
    results = {}
    
    # Monitor subz.lk
    if args.site in ['all', 'subz']:
        logger.info("\n" + "="*60)
        logger.info("MONITORING SUBZ.LK FOR NEW SUBTITLES")
        logger.info("="*60 + "\n")
        
        try:
            subz_scraper = SubzLkScraper(
                telegram_token=TELEGRAM_BOT_TOKEN,
                telegram_chat_id=TELEGRAM_CHAT_ID,
                cf_account_id=CF_ACCOUNT_ID,
                cf_api_token=CF_API_TOKEN,
                d1_database_id=D1_DATABASE_ID
            )
            
            results['subz'] = subz_scraper.monitor_new_subtitles(limit=args.limit)
            logger.info(f"Subz.lk monitoring complete: {results['subz']} new subtitles processed")
            
        except Exception as e:
            logger.error(f"Error monitoring subz.lk: {e}", exc_info=True)
            results['subz'] = 0
    
    # Monitor baiscope.lk
    if args.site in ['all', 'baiscope']:
        logger.info("\n" + "="*60)
        logger.info("MONITORING BAISCOPE.LK FOR NEW SUBTITLES")
        logger.info("="*60 + "\n")
        
        try:
            # Import here to avoid circular dependency
            from main import BaiscopeScraperTelegram
            
            baiscope_scraper = BaiscopeScraperTelegram(
                telegram_token=TELEGRAM_BOT_TOKEN,
                telegram_chat_id=TELEGRAM_CHAT_ID,
                cf_account_id=CF_ACCOUNT_ID,
                cf_api_token=CF_API_TOKEN,
                d1_database_id=D1_DATABASE_ID
            )
            
            # For baiscope, just check recent pages of main category
            # Since most content is already scraped
            logger.info("Checking baiscope.lk recent pages for new content...")
            
            # Check first 3 pages of main Sinhala subtitles category
            category = "/category/sinhala-subtitles/"
            new_count = 0
            
            for page in range(1, 4):  # Check pages 1-3
                subtitle_urls = baiscope_scraper.get_subtitle_urls_from_page(category, page)
                if subtitle_urls:
                    new_urls = [url for url in subtitle_urls if url not in baiscope_scraper.processed_urls]
                    if new_urls:
                        logger.info(f"Found {len(new_urls)} new URLs on page {page}")
                        success = baiscope_scraper.process_page_subtitles(new_urls[:args.limit if args.limit else len(new_urls)])
                        new_count += success
                        
                        if args.limit and new_count >= args.limit:
                            break
            
            results['baiscope'] = new_count
            logger.info(f"Baiscope.lk monitoring complete: {new_count} new subtitles processed")
            
        except Exception as e:
            logger.error(f"Error monitoring baiscope.lk: {e}", exc_info=True)
            results['baiscope'] = 0
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("MONITORING SUMMARY")
    logger.info("="*60)
    for site, count in results.items():
        logger.info(f"{site.upper()}: {count} new subtitles processed")
    logger.info("="*60 + "\n")
    
    return 0


if __name__ == '__main__':
    exit(main())
