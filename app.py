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
    'status': 'idle',
    'last_run': None,
    'processed': 0,
    'success': 0
}

current_scraper = None
scraper_thread = None


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
    """Run monitoring for Subz.lk (called periodically)"""
    global current_scraper, scraper_status, scraper_thread
    
    # Check if a full scrape is already running
    if scraper_thread and scraper_thread.is_alive():
        logger.info("Skip monitoring: Full scrape is currently active.")
        return
        
    creds = get_credentials()
    
    if not creds['telegram_token']:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        return
    
    logger.info("="*60)
    logger.info("STARTING SUBZ.LK MONITORING CYCLE")
    logger.info("="*60)
    
    try:
        scraper_status['status'] = 'monitoring'
        scraper_status['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
        
        scraper = SubzLkScraper(
            telegram_token=creds['telegram_token'],
            telegram_chat_id=creds['telegram_chat_id'],
            cf_account_id=creds['cf_account_id'],
            cf_api_token=creds['cf_api_token'],
            d1_database_id=creds['d1_database_id']
        )
        
        current_scraper = scraper
        scraper.initialize()
        
        result = scraper.monitor_new_subtitles()
        
        scraper_status['status'] = 'idle'
        scraper_status['success'] = result
        scraper_status['processed'] = len(scraper.processed_urls)
        
        logger.info(f"Subz.lk monitoring complete: {result} new subtitles")
        
    except Exception as e:
        logger.error(f"Error monitoring subz.lk: {e}", exc_info=True)
        scraper_status['status'] = f'error: {str(e)[:100]}'
    
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
        'service': 'Subz.lk Dedicated Scraper',
        'mode': 'Monitoring (15 min intervals)',
        'status': 'running',
        'endpoints': [
            '/status - View scraper status',
            '/trigger - Manually trigger monitoring',
            '/scrape/subz - Full history scrape',
            '/debug - Internal diagnostics'
        ]
    }), 200


@app.route('/status')
def status():
    """Get current status of Subz.lk scraper"""
    response = {
        'service_info': {
            'name': 'Subz.lk Dedicated Scraper',
            'auto_monitor_interval': '15 minutes',
            'render_note': 'Service sleeps after 15m inactivity on Free Tier'
        },
        'scraper': scraper_status,
        'diagnostics': {
            'thread_active': scraper_thread.is_alive() if scraper_thread else False,
            'pid': os.getpid()
        }
    }
    
    if current_scraper:
        response['scraper']['d1_stats'] = current_scraper.stats
        if hasattr(current_scraper, 'initialization_status'):
            response['scraper']['init_status'] = current_scraper.initialization_status
            
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
    global scraper_thread
    
    if scraper_thread and scraper_thread.is_alive():
        return jsonify({'error': 'Subz scraper is already running'}), 400
    
    def run_full_scrape():
        global current_scraper, scraper_status
        
        creds = get_credentials()
        
        try:
            scraper_status['status'] = 'initializing'
            scraper_status['last_run'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            scraper = SubzLkScraper(
                telegram_token=creds['telegram_token'],
                telegram_chat_id=creds['telegram_chat_id'],
                cf_account_id=creds['cf_account_id'],
                cf_api_token=creds['cf_api_token'],
                d1_database_id=creds['d1_database_id']
            )
            
            # Expose scraper immediately so /status sees it
            current_scraper = scraper
            scraper_status['status'] = 'initializing_db'
            
            # Load data (this takes time)
            scraper.initialize()
            
            scraper_status['status'] = 'full_scrape_running'
            
            result = scraper.scrape_all_categories()
            
            scraper_status['status'] = 'idle'
            scraper_status['success'] = result
            scraper_status['processed'] = len(scraper.processed_urls)
            
        except Exception as e:
            logger.error(f"Error in full scrape: {e}", exc_info=True)
            scraper_status['status'] = f'error: {str(e)[:100]}'
    
    scraper_thread = threading.Thread(target=run_full_scrape, daemon=True)
    scraper_thread.start()
    
    return jsonify({
        'message': 'Full scrape of subz.lk started',
        'note': 'This will take several hours. Check /status for progress'
    })


@app.route('/debug')
def debug_state():
    """Dump internal state for debugging"""
    response = {
        'pid': os.getpid(),
        'scraper_status': scraper_status,
        'scraper_is_none': current_scraper is None,
        'thread_active': scraper_thread.is_alive() if scraper_thread else False
    }
    
    if current_scraper:
        s = current_scraper
        response['details'] = {
            'type': str(type(s)),
            'has_stats': hasattr(s, 'stats'),
            'd1_enabled': s.d1.enabled if hasattr(s, 'd1') else 'no_d1',
            'stats': s.stats if hasattr(s, 'stats') else 'missing',
            'init_status': s.initialization_status if hasattr(s, 'initialization_status') else 'unknown'
        }
        
    return jsonify(response)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)
