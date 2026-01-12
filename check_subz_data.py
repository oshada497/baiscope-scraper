import os
import sys
import logging
from scraper_utils import CloudflareD1

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_d1():
    creds = {
        'cf_account_id': os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID'),
        'cf_api_token': os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN'),
        'd1_database_id': os.environ.get('D1_DATABASE_ID')
    }
    
    if not all(creds.values()):
        logger.error("Missing credentials in environment variables.")
        return

    d1 = CloudflareD1(creds['cf_account_id'], creds['cf_api_token'], creds['d1_database_id'])
    
    logger.info("Checking D1 database for 'subz' source...")
    
    # Check discovered_urls
    discovered = d1.get_discovered_urls_count(source='subz')
    logger.info(f"Discovered URLs (subz): {discovered}")
    
    # Check processed_urls
    processed = d1.get_processed_urls_count(source='subz')
    logger.info(f"Processed URLs (subz): {processed}")
    
    # Check sample discovered
    logger.info("Fetching sample discovered URLs...")
    full_res = d1.execute("SELECT url, status, discovered_at FROM discovered_urls WHERE source='subz' LIMIT 5")
    if full_res and len(full_res) > 0:
        results = full_res[0].get("results", [])
        if results:
            for row in results:
                logger.info(f" - {row}")
        else:
            logger.info("No discovered URLs found.")
    else:
        logger.error("Failed to query discovered_urls.")

if __name__ == "__main__":
    check_d1()
