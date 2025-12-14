import os
import threading
import time
from flask import Flask, jsonify
from main import BaiscopeScraperAdvanced
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

scraper_status = {
    'status': 'initializing',
    'start_time': None,
    'processed_urls': 0,
    'current_batch': 0,
    'success': 0,
    'failed': 0
}

current_scraper = None

def run_scraper():
    global current_scraper, scraper_status
    
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'baiscope-subtitles')
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY]):
        logger.error("Missing R2 credentials!")
        scraper_status['status'] = 'error: missing credentials'
        return
    
    BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 100))
    
    scraper_status['status'] = 'starting'
    scraper_status['start_time'] = time.strftime('%Y-%m-%d %H:%M:%S')
    
    current_scraper = BaiscopeScraperAdvanced(
        r2_account_id=R2_ACCOUNT_ID,
        r2_access_key=R2_ACCESS_KEY,
        r2_secret_key=R2_SECRET_KEY,
        r2_bucket_name=R2_BUCKET_NAME,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
        batch_size=BATCH_SIZE
    )
    
    scraper_status['status'] = 'running'
    scraper_status['processed_urls'] = len(current_scraper.processed_urls)
    
    result = current_scraper.scrape_all()
    
    scraper_status['status'] = 'completed'
    scraper_status['processed_urls'] = len(current_scraper.processed_urls)

scraper_thread = threading.Thread(target=run_scraper, daemon=True)
scraper_thread.start()

@app.route('/')
def health():
    return 'Scraper running', 200

@app.route('/status')
def status():
    global current_scraper, scraper_status
    
    response = {
        'status': scraper_status['status'],
        'start_time': scraper_status['start_time'],
        'total_processed': scraper_status['processed_urls']
    }
    
    if current_scraper:
        response['total_processed'] = len(current_scraper.processed_urls)
        if hasattr(current_scraper, 'tracker'):
            tracker = current_scraper.tracker
            response['current_batch'] = {
                'processed': tracker.processed,
                'total': tracker.total_found,
                'success': tracker.success,
                'failed': tracker.failed
            }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
