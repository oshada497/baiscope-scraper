"""
Flask Web Server for Subz.lk Scraper
"""
import os
import threading
import logging
import sys
from flask import Flask, jsonify
from new_scraper import SubzScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
scraper = None
worker_thread = None
is_running = False

def run_scraper():
    """Background scraper job"""
    global is_running, scraper
    try:
        is_running = True
        scraper = SubzScraper()
        scraper.initialize()
        scraper.scrape_all()
    except Exception as e:
        logger.error(f"Scraper error: {e}", exc_info=True)
    finally:
        is_running = False

@app.route('/')
def health():
    return jsonify({
        'service': 'Subz.lk Scraper (Clean)',
        'status': 'online',
        'scraping': is_running
    })

@app.route('/scrape')
def start_scrape():
    """Start a full scrape"""
    global worker_thread, is_running
    
    if is_running:
        return jsonify({'error': 'Scraper already running'}), 400
        
    worker_thread = threading.Thread(target=run_scraper, daemon=True)
    worker_thread.start()
    
    return jsonify({'message': 'Scraper started'})

@app.route('/status')
def status():
    """Get scraper status"""
    return jsonify({
        'running': is_running,
        'thread_alive': worker_thread.is_alive() if worker_thread else False,
        'processed_urls': len(scraper.processed_urls) if scraper else 0,
        'processed_files': len(scraper.processed_filenames) if scraper else 0
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
