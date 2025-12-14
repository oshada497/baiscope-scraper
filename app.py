import os
import threading
from flask import Flask
from main import BaiscopeScraperAdvanced
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

def run_scraper():
    R2_ACCOUNT_ID = os.environ.get('R2_ACCOUNT_ID')
    R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY')
    R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY')
    R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME', 'baiscope-subtitles')
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not all([R2_ACCOUNT_ID, R2_ACCESS_KEY, R2_SECRET_KEY]):
        logger.error("Missing R2 credentials!")
        return
    
    scraper = BaiscopeScraperAdvanced(
        r2_account_id=R2_ACCOUNT_ID,
        r2_access_key=R2_ACCESS_KEY,
        r2_secret_key=R2_SECRET_KEY,
        r2_bucket_name=R2_BUCKET_NAME,
        telegram_token=TELEGRAM_BOT_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID
    )
    scraper.scrape_all()

scraper_thread = threading.Thread(target=run_scraper, daemon=True)
scraper_thread.start()

@app.route('/')
def health():
    return 'Scraper running', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
