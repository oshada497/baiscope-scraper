"""
Flask web app for running scrapers on Render.com
Supports both baiscope.lk and subz.lk with monitoring mode
"""
import os
import threading
import time
from flask import Flask, jsonify, request
import logging
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from subz_scraper import SubzLkScraper

# Configure logging to force output to stdout for Render (Unbuffered)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global status tracking
scraper_status = {
    'baiscope': {
        'status': 'idle',
        'last_run': None,
        'processed': 0,
        'success': 0
    },
    'subz': {
        'status': 'idle',
        'last_run': None,
        'processed': 0,
        'success': 0
    }
}

current_scrapers = {
    'baiscope': None,
    'subz': None
}

scraper_threads = {
    'baiscope': None,
    'subz': None
}


def get_credentials():
    """Get credentials from environment variables"""
    creds = {
        'telegram_token': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989'),
        'cf_account_id': os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID'),
        'cf_api_token': os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN'),
        'd1_database_id': os.environ.get('D1_DATABASE_ID')
    }
    
    # Debug logging to find missing creds
    missing = [k for k, v in creds.items() if not v]
    if missing:
        logger.error(f"Missing credentials: {', '.join(missing)}")
    else:
        logger.info(f"Credentials loaded: Account={creds['cf_account_id'][:4]}..., DB={creds['d1_database_id']}")
        
    return creds


def run_monitoring_job():
    """Run monitoring for both sites (called periodically)"""
    global current_scrapers, scraper_status
    
    creds = get_credentials()
    
    if not creds['telegram_token']:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        return
    
    logger.info("="*60)
    logger.info("STARTING PERIODIC MONITORING")
    logger.info("="*60)
    
    # Monitor Subz.lk
    try:
        scraper_status['subz']['status'] = 'running'
        scraper_status['subz']['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
        subz_scraper = SubzLkScraper(
            telegram_token=creds['telegram_token'],
            telegram_chat_id=creds['telegram_chat_id'],
            cf_account_id=creds['cf_account_id'],
            cf_api_token=creds['cf_api_token'],
            d1_database_id=creds['d1_database_id']
        )
        
        current_scrapers['subz'] = subz_scraper
        result = subz_scraper.monitor_new_subtitles()
        
        scraper_status['subz']['status'] = 'idle'
        scraper_status['subz']['success'] = result
        scraper_status['subz']['processed'] = len(subz_scraper.processed_urls)
        
        logger.info(f"Subz.lk monitoring complete: {result} new subtitles")
        
    except Exception as e:
        logger.error(f"Error monitoring subz.lk: {e}", exc_info=True)
        scraper_status['subz']['status'] = f'error: {str(e)[:100]}'
    
    # Monitor Baiscope.lk (check recent pages only)
    try:
        from main import BaiscopeScraperTelegram
        
        scraper_status['baiscope']['status'] = 'running'
        scraper_status['baiscope']['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
        baiscope_scraper = BaiscopeScraperTelegram(
            telegram_token=creds['telegram_token'],
            telegram_chat_id=creds['telegram_chat_id'],
            cf_account_id=creds['cf_account_id'],
            cf_api_token=creds['cf_api_token'],
            d1_database_id=creds['d1_database_id']
        )
        
        current_scrapers['baiscope'] = baiscope_scraper
        
        # Check first 3 pages of main category for new content
        category = "/category/sinhala-subtitles/"
        new_count = 0
        
        for page in range(1, 4):
            subtitle_urls = baiscope_scraper.get_subtitle_urls_from_page(category, page)
            if subtitle_urls:
                new_urls = [url for url in subtitle_urls if url not in baiscope_scraper.processed_urls]
                if new_urls:
                    logger.info(f"Baiscope page {page}: {len(new_urls)} new URLs")
                    success = baiscope_scraper.process_page_subtitles(new_urls)
                    new_count += success
        
        scraper_status['baiscope']['status'] = 'idle'
        scraper_status['baiscope']['success'] = new_count
        scraper_status['baiscope']['processed'] = len(baiscope_scraper.processed_urls)
        
        logger.info(f"Baiscope.lk monitoring complete: {new_count} new subtitles")
        
    except Exception as e:
        logger.error(f"Error monitoring baiscope.lk: {e}", exc_info=True)
        scraper_status['baiscope']['status'] = f'error: {str(e)[:100]}'
    
    logger.info("="*60)
    logger.info("MONITORING CYCLE COMPLETE")
    logger.info("="*60)


def start_monitoring_loop():
    """Background thread that runs monitoring periodically"""
    logger.info("Starting monitoring loop (runs every 15 minutes)")
    
    while True:
        try:
            run_monitoring_job()
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}", exc_info=True)
        
        # Wait 15 minutes before next run
        logger.info("Waiting 15 minutes until next monitoring cycle...")
        time.sleep(15 * 60)


# Start monitoring loop in background
monitoring_thread = threading.Thread(target=start_monitoring_loop, daemon=True)
monitoring_thread.start()


@app.route('/')
def health():
    """Health check endpoint"""
    return jsonify({
        'service': 'BiScope & Subz.lk Subtitle Scraper',
        'mode': 'Monitoring (15 min intervals)',
        'status': 'running',
        'endpoints': [
            '/status - View scraper status',
            '/trigger - Manually trigger monitoring',
            '/scrape/subz - Full scrape of subz.lk',
        ]
    }), 200


@app.route('/status')
def status():
    """Get current status of both scrapers"""
    response = {
        'monitoring_interval': '15 minutes',
        'scrapers': scraper_status
    }
    
    # Add D1 stats if available
    # Add D1 stats if available (use cached stats to avoid timeout)
    for site, scraper in current_scrapers.items():
        if scraper and hasattr(scraper, 'stats'):
             response['scrapers'][site]['d1_stats'] = scraper.stats
        elif scraper and hasattr(scraper, 'd1') and scraper.d1.enabled:
             # Fallback (careful with timeouts)
             try:
                response['scrapers'][site]['d1_stats'] = {
                    'discovered': scraper.d1.get_discovered_urls_count(source=scraper.source if hasattr(scraper, 'source') else site),
                    'processed': scraper.d1.get_processed_urls_count(source=scraper.source if hasattr(scraper, 'source') else site)
                }
             except Exception:
                response['scrapers'][site]['d1_stats'] = {'error': 'timeout'}
    
    return jsonify(response)


@app.route('/trigger')
def trigger_monitoring():
    """Manually trigger a monitoring cycle"""
    thread = threading.Thread(target=run_monitoring_job, daemon=True)
    thread.start()
    
    return jsonify({
        'message': 'Monitoring cycle triggered',
        'note': 'Check /status for progress'
    })


@app.route('/scrape/subz')
def scrape_subz_full():
    """Trigger full scrape of subz.lk (run once for initial setup)"""
    global scraper_threads
    
    if scraper_threads['subz'] and scraper_threads['subz'].is_alive():
        return jsonify({'error': 'Subz scraper is already running'}), 400
    
    def run_full_scrape():
        global current_scrapers, scraper_status
        
        creds = get_credentials()
        
        try:
            scraper_status['subz']['status'] = 'full_scrape_running'
            scraper_status['subz']['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            scraper = SubzLkScraper(
                telegram_token=creds['telegram_token'],
                telegram_chat_id=creds['telegram_chat_id'],
                cf_account_id=creds['cf_account_id'],
                cf_api_token=creds['cf_api_token'],
                d1_database_id=creds['d1_database_id']
            )
            
            current_scrapers['subz'] = scraper
            result = scraper.scrape_all_categories()
            
            scraper_status['subz']['status'] = 'idle'
            scraper_status['subz']['success'] = result
            scraper_status['subz']['processed'] = len(scraper.processed_urls)
            
        except Exception as e:
            logger.error(f"Error in full scrape: {e}", exc_info=True)
            scraper_status['subz']['status'] = f'error: {str(e)[:100]}'
    
    scraper_threads['subz'] = threading.Thread(target=run_full_scrape, daemon=True)
    scraper_threads['subz'].start()
    
    return jsonify({
        'message': 'Full scrape of subz.lk started',
        'note': 'This will take several hours. Check /status for progress'
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)
