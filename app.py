import os
import threading
import time
from flask import Flask, jsonify
from main import BaiscopeScraperTelegram
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

def run_scraper():
    global current_scraper, scraper_status
    
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '-1003442794989')
    
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN!")
        scraper_status['status'] = 'error: missing telegram token'
        return
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 50))
    
    scraper_status['status'] = 'starting'
    scraper_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    current_scraper = BaiscopeScraperTelegram(
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
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
    return 'Baiscope Subtitle Scraper - Telegram Storage Mode', 200

@app.route('/status')
def status():
    global current_scraper, scraper_status
    
    response = {
        'status': scraper_status['status'],
        'start_time': scraper_status['start_time'],
        'total_processed': scraper_status['processed_urls'],
        'storage': 'telegram'
    }
    
    if current_scraper:
        response['total_processed'] = len(current_scraper.processed_urls)
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
