"""
Subz.lk Dedicated Web Controller
Manages background scraping and provide status updates.
"""
import os
import threading
import time
import logging
import sys
from flask import Flask, jsonify, request
from subz_scraper import SubzLkScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global Scraper Instance and Thread
current_scraper = None
worker_thread = None
job_type = "idle" # idle, full_scrape, monitoring

def get_scraper():
    """Lazily create the scraper instance with fresh credentials"""
    global current_scraper
    if not current_scraper:
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not token:
            logger.error("Missing TELEGRAM_BOT_TOKEN")
            return None
        current_scraper = SubzLkScraper(token, chat_id)
    return current_scraper

def run_job(target_type):
    """Generic wrapper to run background jobs with initialization"""
    global job_type, current_scraper
    job_type = target_type
    
    try:
        scraper = get_scraper()
        if not scraper: return
        
        # Non-blocking registration for status page
        scraper.initialize()
        
        if target_type == "full_scrape":
            scraper.scrape_all_categories()
        elif target_type == "monitoring":
            scraper.monitor_new_subtitles()
            
    except Exception as e:
        logger.error(f"Background Job Error ({target_type}): {e}", exc_info=True)
    finally:
        job_type = "idle"

@app.route('/')
def health():
    return jsonify({
        'service': 'Subz.lk Dedicated Scraper (v2)',
        'status': 'online',
        'current_job': job_type,
        'endpoints': ['/status', '/scrape/subz', '/trigger']
    }), 200

@app.route('/status')
def status():
    """Live status of the scraper and database counts"""
    scraper = get_scraper()
    res = {
        'job_info': {
            'type': job_type,
            'is_running': worker_thread.is_alive() if worker_thread else False
        },
        'database': {
            'discovered': scraper.stats['discovered'] if scraper else 0,
            'processed': scraper.stats['processed'] if scraper else 0,
            'init_status': scraper.initialization_status if scraper else "not_created"
        }
    }
    return jsonify(res)

@app.route('/trigger')
def trigger():
    """Quick check for new subtitles"""
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        return jsonify({'error': f'Job already running: {job_type}'}), 400
    
    worker_thread = threading.Thread(target=run_job, args=("monitoring",), daemon=True)
    worker_thread.start()
    return jsonify({'message': 'Monitoring cycle started in background'})

@app.route('/scrape/subz')
def full_scrape():
    """Exhaustive crawl of site history (Resume-supported)"""
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        return jsonify({'error': f'Job already running: {job_type}'}), 400
    
    worker_thread = threading.Thread(target=run_job, args=("full_scrape",), daemon=True)
    worker_thread.start()
    return jsonify({'message': 'Full historical scrape started/resumed'})

def background_maintenance():
    """15-minute loop to keep service alive and auto-resume if needed"""
    global worker_thread
    while True:
        time.sleep(15 * 60) # 15 minutes
        logger.info("Maintenance Check: Heartbeat...")
        
        # If no job is running, we can check if we should auto-resume a full scrape
        # but for now, we'll just log a heartbeat to keep Render logs flowing.

if __name__ == '__main__':
    # Start maintenance heartbeat
    threading.Thread(target=background_maintenance, daemon=True).start()
    
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
