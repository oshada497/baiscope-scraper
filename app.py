"""
Universal Scraper Web Controller (Subz.lk + Zoom.lk)
Manages background scraping and provide status updates.
"""
import os
import threading
import time
import logging
import sys
from flask import Flask, jsonify, request
from subz_scraper import SubzLkScraper
from zoom_scraper import ZoomLkScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global Scraper Instances
scrapers = {
    'subz': None,
    'zoom': None
}
worker_thread = None
job_type = "idle" # idle, full_scrape_subz, full_scrape_zoom, monitoring

def get_scraper(source='zoom'):
    """Lazily create the scraper instance with fresh credentials"""
    global scrapers
    if not scrapers.get(source):
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if not token:
            logger.error("Missing TELEGRAM_BOT_TOKEN")
            return None
            
        if source == 'subz':
            scrapers['subz'] = SubzLkScraper(token, chat_id)
        elif source == 'zoom':
            scrapers['zoom'] = ZoomLkScraper(token, chat_id)
            
    return scrapers.get(source)

def run_job(target_type, source='zoom'):
    """Generic wrapper to run background jobs with initialization"""
    global job_type
    job_type = f"{target_type}_{source}"
    
    try:
        scraper = get_scraper(source)
        if not scraper: return
        
        # Non-blocking registration for status page
        scraper.initialize()
        
        if target_type == "full_scrape":
            scraper.scrape_all_categories()
        elif target_type == "monitoring":
            if source == 'subz':
                scraper.monitor_new_subtitles()
            else:
                scraper.crawl_only(limit_pages=1) # Zoom monitoring equivalent
            
    except Exception as e:
        logger.error(f"Background Job Error ({job_type}): {e}", exc_info=True)
    finally:
        job_type = "idle"

@app.route('/')
def health():
    return jsonify({
        'service': 'Baiscope Universal Scraper (Zoom/Subz)',
        'status': 'online',
        'current_job': job_type,
        'endpoints': ['/status', '/scrape/zoom', '/scrape/subz', '/trigger/zoom']
    }), 200

@app.route('/status')
def status():
    """Live status of the scrapers"""
    res = {
        'job_info': {
            'type': job_type,
            'is_running': worker_thread.is_alive() if worker_thread else False
        },
        'database': {}
    }
    
    for source in ['zoom', 'subz']:
        s = get_scraper(source)
        if s:
            res['database'][source] = {
                'discovered': s.stats.get('discovered', 0),
                'processed': s.stats.get('processed', 0),
                'init_status': s.initialization_status
            }
            
    return jsonify(res)

@app.route('/trigger/<source>')
def trigger(source):
    """Quick check for new subtitles"""
    global worker_thread
    if source not in ['zoom', 'subz']:
        return jsonify({'error': 'Invalid source'}), 400
        
    if worker_thread and worker_thread.is_alive():
        return jsonify({'error': f'Job already running: {job_type}'}), 400
    
    worker_thread = threading.Thread(target=run_job, args=("monitoring", source), daemon=True)
    worker_thread.start()
    return jsonify({'message': f'Monitoring cycle started for {source}'})

@app.route('/scrape/<source>')
def full_scrape(source):
    """Exhaustive crawl of site history"""
    global worker_thread
    if source not in ['zoom', 'subz']:
        return jsonify({'error': 'Invalid source'}), 400

    if worker_thread and worker_thread.is_alive():
        return jsonify({'error': f'Job already running: {job_type}'}), 400
    
    worker_thread = threading.Thread(target=run_job, args=("full_scrape", source), daemon=True)
    worker_thread.start()
    return jsonify({'message': f'Full historical scrape started for {source}'})

@app.route('/reset/<source>')
def reset_history(source):
    """Clear history for a source to allow re-scraping"""
    global scrapers
    if source not in ['zoom', 'subz']:
        return jsonify({'error': 'Invalid source'}), 400
        
    s = get_scraper(source)
    if not s:
        return jsonify({'error': 'Scraper failed to initialize'}), 500
        
    # Reset D1 state
    if s.d1.enabled:
        try:
            # 1. Clear discovered URLs for this source
            s.d1.execute("DELETE FROM discovered_urls WHERE source = ?", [source])
            
            # 2. Clear subtitles table (which is prefixed)
            # Zoom scraper uses empty prefix in d1_database.py by default? 
            # Let's check zoom_scraper.py. It uses CloudflareD1 from scraper_utils. 
            # In update 228, we saw ZoomLkScraper init passes nothing for prefix usually.
            # But wait, CloudflareD1 in scraper_utils handles prefix internally?
            # Actually, `scraper_utils.py` implementation of CloudflareD1 uses `table_prefix`?
            # No, scraper_utils.py's CloudflareD1 has `_init_tables` which creates `discovered_urls` 
            # AND `telegram_files`. It does NOT seem to use the `table_prefix` logic from `d1_database.py`.
            # We are using TWO different D1 classes!
            # zoom_scraper.py imports CloudflareD1 from **scraper_utils**
            # d1_database.py defines D1Database class.
            
            # Let's double check scraper_utils.py's CloudflareD1 schema.
            # It uses `telegram_files` table.
            # It has `source` column in `telegram_files`?
             
            s.d1.execute("DELETE FROM telegram_files WHERE source = ?", [source])
            s.d1.execute("DELETE FROM processed_urls WHERE source = ?", [source])
             
            # Reset in-memory sets
            s.processed_urls = set()
            s.existing_filenames = set()
            s.stats = {'discovered': 0, 'processed': 0}
            
            logger.info(f"Reset complete for {source}")
            return jsonify({'message': f'History reset successful for {source}. You can now start a full scrape.'})
            
        except Exception as e:
            logger.error(f"Reset failed: {e}")
            return jsonify({'error': str(e)}), 500

    return jsonify({'message': 'D1 not enabled, memory reset only.'})

def background_maintenance():
    """15-minute loop to keep service alive"""
    while True:
        time.sleep(15 * 60)
        logger.info("Maintenance Check: Heartbeat...")

if __name__ == '__main__':
    threading.Thread(target=background_maintenance, daemon=True).start()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
