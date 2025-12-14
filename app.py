import os
import threading
import time
from flask import Flask, jsonify
from main import BaiscopeScraperTelegram
from sync_telegram import sync_existing_files
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

scraper_status = {
    'status': 'initializing',
    'start_time': None,
    'processed_urls': 0,
    'success': 0,
    'failed': 0
}

current_scraper = None
scraper_thread = None
sync_thread = None
sync_status = {'status': 'idle', 'synced': 0}

def run_scraper():
    global current_scraper, scraper_status
    
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989')
    
    CF_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID') or os.environ.get('CLOUDFLARE_ACCOUNT_ID')
    CF_API_TOKEN = os.environ.get('CF_API_TOKEN') or os.environ.get('CLOUDFLARE_API_TOKEN')
    D1_DATABASE_ID = os.environ.get('D1_DATABASE_ID')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        scraper_status['status'] = 'error: missing telegram token'
        return
    
    if not all([CF_ACCOUNT_ID, CF_API_TOKEN, D1_DATABASE_ID]):
        logger.warning("D1 database credentials not set - using local file storage")
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 50))
    
    scraper_status['status'] = 'starting'
    scraper_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    current_scraper = BaiscopeScraperTelegram(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        cf_account_id=CF_ACCOUNT_ID,
        cf_api_token=CF_API_TOKEN,
        d1_database_id=D1_DATABASE_ID,
        batch_size=BATCH_SIZE
    )
    
    scraper_status['status'] = 'running'
    scraper_status['processed_urls'] = len(current_scraper.processed_urls)
    
    try:
        result = current_scraper.scrape_all()
        scraper_status['status'] = 'completed'
        scraper_status['success'] = result
    except Exception as e:
        logger.error(f"Scraper error: {e}")
        scraper_status['status'] = f'error: {str(e)[:100]}'
    finally:
        if current_scraper:
            scraper_status['processed_urls'] = len(current_scraper.processed_urls)

def start_scraper_if_needed():
    global scraper_thread
    
    if scraper_thread is None or not scraper_thread.is_alive():
        scraper_thread = threading.Thread(target=run_scraper, daemon=True)
        scraper_thread.start()
        logger.info("Scraper thread started")

start_scraper_if_needed()

@app.route('/')
def health():
    return 'Baiscope Subtitle Scraper - Telegram + D1 Storage Mode', 200

@app.route('/status')
def status():
    global current_scraper, scraper_status
    
    response = {
        'status': scraper_status['status'],
        'start_time': scraper_status['start_time'],
        'total_processed': scraper_status['processed_urls'],
        'storage': 'telegram + d1'
    }
    
    if current_scraper:
        response['total_processed'] = len(current_scraper.processed_urls)
        
        if current_scraper.d1.enabled:
            response['d1_discovered'] = current_scraper.d1.get_discovered_urls_count()
            response['d1_processed'] = current_scraper.d1.get_processed_urls_count()
        
        if hasattr(current_scraper, 'tracker'):
            tracker = current_scraper.tracker
            response['current_progress'] = {
                'processed': tracker.processed,
                'success': tracker.success,
                'failed': tracker.failed,
                'current_category': tracker.current_category,
                'current_page': tracker.current_page
            }
    
    return jsonify(response)

@app.route('/restart')
def restart():
    global scraper_thread, current_scraper, scraper_status
    
    if scraper_thread and scraper_thread.is_alive():
        return jsonify({'error': 'Scraper is still running'}), 400
    
    scraper_status = {
        'status': 'restarting',
        'start_time': None,
        'processed_urls': 0,
        'success': 0,
        'failed': 0
    }
    
    start_scraper_if_needed()
    return jsonify({'message': 'Scraper restarted'})

def run_sync():
    global sync_status
    try:
        sync_status['status'] = 'running'
        count = sync_existing_files()
        sync_status['synced'] = count
        sync_status['status'] = 'completed'
    except Exception as e:
        logger.error(f"Sync error: {e}")
        sync_status['status'] = f'error: {str(e)[:100]}'

@app.route('/sync')
def sync():
    global sync_thread, sync_status
    
    if sync_thread and sync_thread.is_alive():
        return jsonify({'status': 'already running', 'synced': sync_status.get('synced', 0)})
    
    sync_status = {'status': 'starting', 'synced': 0}
    sync_thread = threading.Thread(target=run_sync, daemon=True)
    sync_thread.start()
    
    return jsonify({'message': 'Sync started - fetching existing files from Telegram channel'})

@app.route('/sync/status')
def sync_status_endpoint():
    global sync_thread, sync_status
    
    response = {
        'status': sync_status.get('status', 'idle'),
        'synced': sync_status.get('synced', 0),
        'running': sync_thread.is_alive() if sync_thread else False
    }
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
