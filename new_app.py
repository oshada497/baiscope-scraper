"""
Flask Web Server for Multi-Site Subtitle Scraper
Supports: Subz.lk and Cineru.lk
"""
import os
import threading
import logging
import sys
from flask import Flask, jsonify
from new_scraper import SubzScraper
from cineru_scraper import CineruScraper

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
current_site = None

def run_scraper(site='subz'):
    """Background scraper job"""
    global is_running, scraper, current_site
    try:
        is_running = True
        current_site = site
        
        if site == 'subz':
            scraper = SubzScraper()
            scraper.initialize()
            scraper.scrape_all()
        elif site == 'cineru':
            scraper = CineruScraper()
            scraper.initialize()
            scraper.scrape_all()
    except Exception as e:
        logger.error(f"{site} scraper error: {e}", exc_info=True)
    finally:
        is_running = False
        current_site = None

@app.route('/')
def health():
    return jsonify({
        'service': 'Multi-Site Subtitle Scraper',
        'sites': ['subz.lk', 'cineru.lk'],
        'status': 'online',
        'scraping': is_running,
        'current_site': current_site,
        'endpoints': ['/scrape', '/scrape/cineru', '/status']
    })

@app.route('/scrape')
def start_scrape_subz():
    """Start subz.lk scrape"""
    global worker_thread, is_running
    
    if is_running:
        return jsonify({'error': f'Scraper already running for {current_site}'}), 400
        
    worker_thread = threading.Thread(target=run_scraper, args=('subz',), daemon=True)
    worker_thread.start()
    
    return jsonify({'message': 'Subz.lk scraper started'})

@app.route('/scrape/cineru')
def start_scrape_cineru():
    """Start cineru.lk scrape"""
    global worker_thread, is_running
    
    if is_running:
        return jsonify({'error': f'Scraper already running for {current_site}'}), 400
        
    worker_thread = threading.Thread(target=run_scraper, args=('cineru',), daemon=True)
    worker_thread.start()
    
    return jsonify({'message': 'Cineru.lk scraper started'})

@app.route('/status')
def status():
    """Get scraper status"""
    return jsonify({
        'running': is_running,
        'current_site': current_site,
        'thread_alive': worker_thread.is_alive() if worker_thread else False,
        'processed_urls': len(scraper.processed_urls) if scraper else 0,
        'processed_files': len(scraper.processed_filenames) if scraper else 0
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

